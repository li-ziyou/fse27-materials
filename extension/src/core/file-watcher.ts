import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import { Workspace } from './workspace';
import { isProtectedPath } from './file-policy';
const IGNORED_DIR_SEGMENTS = new Set([
    '.contextbranch',
    '.study',
    '.git',
    'node_modules',
    'dist',
    'out',
    'build',
    '.venv',
    'venv',
    '__pycache__',
    '.next',
    '.cache',
    '.idea',
    '.vscode',
]);
const IGNORED_EXTENSIONS = new Set([
    '.lock', '.log', '.pid', '.swp', '.tmp',
    '.png', '.jpg', '.jpeg', '.gif', '.ico', '.pdf', '.zip', '.tar', '.gz',
]);
const MAX_CAPTURE_BYTES = 1000000;
export class WorkspaceCapture implements vscode.Disposable {
    private watcher?: vscode.FileSystemWatcher;
    private suppressed = new Map<string, number>();
    private disposables: vscode.Disposable[] = [];
    constructor(private workspaceRoot: string, private getWorkspace: () => Workspace | null, private onCaptured: () => void) { }
    start(): void {
        if (this.watcher)
            return;
        this.watcher = vscode.workspace.createFileSystemWatcher('**/*');
        this.disposables.push(this.watcher, this.watcher.onDidChange(uri => this.handleChange(uri)), this.watcher.onDidCreate(uri => this.handleCreate(uri)), this.watcher.onDidDelete(uri => this.handleDelete(uri)));
    }
    dispose(): void {
        for (const d of this.disposables)
            d.dispose();
        this.disposables = [];
        this.watcher = undefined;
    }
    suppress(absPath: string, ttlMs = 2000): void {
        this.suppressed.set(absPath, Date.now() + ttlMs);
    }
    suppressMany(absPaths: string[], ttlMs = 2000): void {
        for (const p of absPaths)
            this.suppress(p, ttlMs);
    }
    private async handleChange(uri: vscode.Uri): Promise<void> {
        if (!this.shouldCapture(uri))
            return;
        const config = vscode.workspace.getConfiguration('contextbranch');
        if (!(config.get<boolean>('captureUserEdits') ?? true))
            return;
        const ws = this.getWorkspace();
        if (!ws)
            return;
        const relPath = this.relativize(uri.fsPath);
        if (!relPath)
            return;
        const artifacts = ws.getArtifacts(ws.activeBranchId);
        const existing = artifacts.find(a => a.path === relPath);
        const newContent = this.readSafe(uri.fsPath);
        if (newContent === null)
            return;
        if (!existing) {
            const captureNew = config.get<boolean>('captureNewFiles') ?? true;
            if (!captureNew)
                return;
            ws.upsertArtifact(ws.activeBranchId, relPath, newContent, null, 'merge');
            ws.storage.appendTelemetry({
                type: 'user_create_captured',
                branchId: ws.activeBranchId,
                path: relPath,
                bytes: newContent.length,
            });
            this.onCaptured();
            return;
        }
        if (newContent === existing.content)
            return;
        ws.upsertArtifact(ws.activeBranchId, relPath, newContent, existing.content, 'merge');
        ws.storage.appendTelemetry({
            type: 'user_edit_captured',
            branchId: ws.activeBranchId,
            path: relPath,
            bytes: newContent.length,
        });
        this.onCaptured();
    }
    private async handleCreate(uri: vscode.Uri): Promise<void> {
        if (!this.shouldCapture(uri))
            return;
        const config = vscode.workspace.getConfiguration('contextbranch');
        if (!(config.get<boolean>('captureNewFiles') ?? true))
            return;
        const ws = this.getWorkspace();
        if (!ws)
            return;
        const relPath = this.relativize(uri.fsPath);
        if (!relPath)
            return;
        const artifacts = ws.getArtifacts(ws.activeBranchId);
        if (artifacts.some(a => a.path === relPath))
            return;
        const content = this.readSafe(uri.fsPath);
        if (content === null)
            return;
        ws.upsertArtifact(ws.activeBranchId, relPath, content, null, 'merge');
        ws.storage.appendTelemetry({
            type: 'user_create_captured',
            branchId: ws.activeBranchId, path: relPath, bytes: content.length,
        });
        this.onCaptured();
    }
    private handleDelete(uri: vscode.Uri): void {
        if (!this.shouldCapture(uri))
            return;
        const ws = this.getWorkspace();
        if (!ws)
            return;
        const relPath = this.relativize(uri.fsPath);
        if (!relPath)
            return;
        ws.storage.appendTelemetry({
            type: 'workspace_delete_observed',
            branchId: ws.activeBranchId, path: relPath,
        });
        const config = vscode.workspace.getConfiguration('contextbranch');
        if (!(config.get<boolean>('captureUserEdits') ?? true))
            return;
        const prefix = relPath + '/';
        const arts = ws.getArtifacts(ws.activeBranchId);
        const affected = arts.some(a => a.path === relPath || a.path.startsWith(prefix));
        if (!affected)
            return;
        const removed = ws.removeArtifactsByPath(ws.activeBranchId, relPath);
        if (removed.length) {
            ws.storage.appendTelemetry({
                type: 'workspace_delete_applied',
                branchId: ws.activeBranchId, path: relPath,
            });
            this.onCaptured();
        }
    }
    ingestExisting(): number {
        const ws = this.getWorkspace();
        if (!ws)
            return 0;
        let count = 0;
        const existingPaths = new Set(ws.getArtifacts(ws.activeBranchId).map(a => a.path));
        const walk = (dir: string): void => {
            let entries: fs.Dirent[];
            try {
                entries = fs.readdirSync(dir, { withFileTypes: true });
            }
            catch {
                return;
            }
            for (const ent of entries) {
                const abs = path.join(dir, ent.name);
                if (ent.isDirectory()) {
                    if (IGNORED_DIR_SEGMENTS.has(ent.name))
                        continue;
                    walk(abs);
                }
                else if (ent.isFile()) {
                    const uri = vscode.Uri.file(abs);
                    if (!this.shouldCapture(uri))
                        continue;
                    const rel = this.relativize(abs);
                    if (!rel || existingPaths.has(rel))
                        continue;
                    const content = this.readSafe(abs);
                    if (content === null)
                        continue;
                    ws.upsertArtifact(ws.activeBranchId, rel, content, null, 'merge');
                    ws.storage.appendTelemetry({
                        type: 'project_ingested',
                        branchId: ws.activeBranchId, path: rel, bytes: content.length,
                    });
                    existingPaths.add(rel);
                    count++;
                }
            }
        };
        walk(this.workspaceRoot);
        if (count)
            this.onCaptured();
        return count;
    }
    private shouldCapture(uri: vscode.Uri): boolean {
        if (uri.scheme !== 'file')
            return false;
        const abs = uri.fsPath;
        if (this.isSuppressed(abs))
            return false;
        const rel = path.relative(this.workspaceRoot, abs);
        if (rel.startsWith('..') || path.isAbsolute(rel))
            return false;
        const segments = rel.split(path.sep);
        for (const seg of segments) {
            if (IGNORED_DIR_SEGMENTS.has(seg))
                return false;
            if (seg.startsWith('.') && IGNORED_DIR_SEGMENTS.has(seg))
                return false;
        }
        if (isProtectedPath(rel))
            return false;
        const ext = path.extname(rel).toLowerCase();
        if (IGNORED_EXTENSIONS.has(ext))
            return false;
        return true;
    }
    private isSuppressed(absPath: string): boolean {
        const expiry = this.suppressed.get(absPath);
        if (expiry === undefined)
            return false;
        if (Date.now() > expiry) {
            this.suppressed.delete(absPath);
            return false;
        }
        return true;
    }
    private relativize(absPath: string): string | null {
        const rel = path.relative(this.workspaceRoot, absPath);
        if (rel.startsWith('..') || path.isAbsolute(rel))
            return null;
        return rel.split(path.sep).join('/');
    }
    private readSafe(absPath: string): string | null {
        try {
            const stat = fs.statSync(absPath);
            if (!stat.isFile())
                return null;
            if (stat.size > MAX_CAPTURE_BYTES)
                return null;
            const buf = fs.readFileSync(absPath);
            const str = buf.toString('utf-8');
            const nonPrintable = (str.match(/[\x00-\x08\x0E-\x1F]/g) || []).length;
            if (nonPrintable > str.length * 0.05)
                return null;
            return str;
        }
        catch {
            return null;
        }
    }
}
