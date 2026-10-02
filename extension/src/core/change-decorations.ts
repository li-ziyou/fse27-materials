import * as vscode from 'vscode';
import { diffLines, DiffHunk } from './edits';
function addedLineNumbers(hunks: DiffHunk[]): number[] {
    const added: number[] = [];
    for (const h of hunks) {
        let afterLine = h.afterStart;
        for (const ln of h.lines) {
            if (ln.type === 'add') {
                added.push(afterLine);
                afterLine++;
            }
            else if (ln.type === 'ctx') {
                afterLine++;
            }
        }
    }
    return added;
}
interface PreviewSession {
    savedText: string;
    lines: number[];
}
export class ChangeDecorations {
    private readonly addedDecoration: vscode.TextEditorDecorationType;
    private readonly pending = new Map<string, number[]>();
    private readonly previews = new Map<string, PreviewSession>();
    private readonly beforeSnapshots = new Map<string, string>();
    private readonly selfWrite = new Map<string, number>();
    private applyingPreviewEdit = false;
    private readonly disposables: vscode.Disposable[] = [];
    constructor() {
        this.addedDecoration = vscode.window.createTextEditorDecorationType({
            isWholeLine: true,
            backgroundColor: new vscode.ThemeColor('diffEditor.insertedLineBackground'),
            overviewRulerColor: new vscode.ThemeColor('minimapGutter.addedBackground'),
            overviewRulerLane: vscode.OverviewRulerLane.Left,
            borderWidth: '0 0 0 3px',
            borderStyle: 'solid',
            borderColor: new vscode.ThemeColor('editorGutter.addedBackground'),
        });
        this.disposables.push(vscode.window.onDidChangeVisibleTextEditors(editors => {
            for (const e of editors)
                this.refresh(e);
        }));
        this.disposables.push(vscode.window.onDidChangeTextEditorSelection(e => {
            const key = e.textEditor.document.uri.fsPath;
            const session = this.previews.get(key);
            if (!session)
                return;
            if (e.kind === undefined)
                return;
            const line = e.selections[0]?.active.line;
            if (line === undefined)
                return;
            if (session.lines.includes(line)) {
                void this.dismissLine(key, line);
            }
        }));
        this.disposables.push(vscode.workspace.onDidChangeTextDocument(e => {
            const key = e.document.uri.fsPath;
            if (this.applyingPreviewEdit)
                return;
            if (this.previews.has(key))
                return;
            if (!this.pending.has(key) || e.contentChanges.length === 0)
                return;
            if (this.isSelfWrite(key))
                return;
            this.clearFile(key);
        }));
    }
    async previewChanges(absPath: string, afterContent: string, opts: {
        reveal?: boolean;
    } = {}): Promise<boolean> {
        const uri = vscode.Uri.file(absPath);
        let doc: vscode.TextDocument;
        try {
            doc = await vscode.workspace.openTextDocument(uri);
        }
        catch {
            return false;
        }
        const before = doc.getText();
        if (before === afterContent) {
            this.clearFile(absPath);
            return false;
        }
        const lines = addedLineNumbers(diffLines(before, afterContent));
        if (lines.length === 0) {
            this.clearFile(absPath);
            return false;
        }
        const fullRange = new vscode.Range(doc.positionAt(0), doc.positionAt(before.length));
        const edit = new vscode.WorkspaceEdit();
        edit.replace(uri, fullRange, afterContent);
        this.applyingPreviewEdit = true;
        let ok = false;
        try {
            ok = await vscode.workspace.applyEdit(edit);
        }
        finally {
            this.applyingPreviewEdit = false;
        }
        if (!ok)
            return false;
        this.previews.set(absPath, { savedText: before, lines: [...lines].sort((a, b) => a - b) });
        this.pending.delete(absPath);
        await this.paint(absPath, { open: true, reveal: opts.reveal });
        return true;
    }
    async commitPreview(absPath: string): Promise<boolean> {
        const session = this.previews.get(absPath);
        if (!session)
            return false;
        const doc = vscode.workspace.textDocuments.find(d => d.uri.fsPath === absPath);
        if (!doc) {
            this.previews.delete(absPath);
            return false;
        }
        this.noteSelfWrite(absPath, 4000);
        const saved = await doc.save();
        const keptLines = session.lines.slice();
        this.previews.delete(absPath);
        if (keptLines.length) {
            this.pending.set(absPath, keptLines);
            await this.paint(absPath, { open: true });
        }
        else {
            this.clearFile(absPath);
        }
        return saved;
    }
    async dismissPreview(absPath: string): Promise<void> {
        const session = this.previews.get(absPath);
        if (!session)
            return;
        const uri = vscode.Uri.file(absPath);
        const doc = vscode.workspace.textDocuments.find(d => d.uri.fsPath === absPath);
        this.previews.delete(absPath);
        if (!doc)
            return;
        const fullRange = new vscode.Range(doc.positionAt(0), doc.positionAt(doc.getText().length));
        const edit = new vscode.WorkspaceEdit();
        edit.replace(uri, fullRange, session.savedText);
        this.applyingPreviewEdit = true;
        try {
            await vscode.workspace.applyEdit(edit);
        }
        finally {
            this.applyingPreviewEdit = false;
        }
        this.clearFile(absPath);
    }
    private async dismissLine(absPath: string, line: number): Promise<void> {
        const session = this.previews.get(absPath);
        if (!session)
            return;
        const uri = vscode.Uri.file(absPath);
        const doc = vscode.workspace.textDocuments.find(d => d.uri.fsPath === absPath);
        if (!doc || line < 0 || line >= doc.lineCount)
            return;
        const start = new vscode.Position(line, 0);
        const end = line + 1 < doc.lineCount
            ? new vscode.Position(line + 1, 0)
            : doc.lineAt(line).range.end;
        const edit = new vscode.WorkspaceEdit();
        edit.delete(uri, new vscode.Range(start, end));
        this.applyingPreviewEdit = true;
        try {
            await vscode.workspace.applyEdit(edit);
        }
        finally {
            this.applyingPreviewEdit = false;
        }
        session.lines = session.lines
            .filter(n => n !== line)
            .map(n => (n > line ? n - 1 : n));
        if (session.lines.length === 0) {
            this.previews.delete(absPath);
            this.clearFile(absPath);
            return;
        }
        await this.paint(absPath);
    }
    hasPreview(absPath: string): boolean {
        return this.previews.has(absPath);
    }
    async dismissAllPreviews(): Promise<void> {
        for (const absPath of Array.from(this.previews.keys())) {
            await this.dismissPreview(absPath);
        }
    }
    snapshotBefore(absPath: string): void {
        const doc = vscode.workspace.textDocuments.find(d => d.uri.fsPath === absPath);
        if (doc) {
            this.beforeSnapshots.set(absPath, doc.getText());
            return;
        }
        try {
            const fs = require('fs') as typeof import('fs');
            this.beforeSnapshots.set(absPath, fs.readFileSync(absPath, 'utf-8'));
        }
        catch {
            this.beforeSnapshots.set(absPath, '');
        }
    }
    async markChanges(absPath: string, afterContent: string, opts: {
        reveal?: boolean;
    } = {}): Promise<void> {
        this.noteSelfWrite(absPath);
        this.previews.delete(absPath);
        const before = this.beforeSnapshots.get(absPath) ?? '';
        this.beforeSnapshots.delete(absPath);
        if (before === afterContent) {
            this.clearFile(absPath);
            return;
        }
        const lines = addedLineNumbers(diffLines(before, afterContent));
        if (lines.length === 0) {
            this.clearFile(absPath);
            return;
        }
        this.pending.set(absPath, lines);
        await this.paint(absPath, { open: true, reveal: opts.reveal });
    }
    private async paint(absPath: string, opts: {
        open?: boolean;
        reveal?: boolean;
    } = {}): Promise<void> {
        let editor = vscode.window.visibleTextEditors.find(ed => ed.document.uri.fsPath === absPath);
        if (!editor && opts.open) {
            try {
                const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(absPath));
                editor = await vscode.window.showTextDocument(doc, {
                    preview: false,
                    preserveFocus: !opts.reveal,
                });
            }
            catch { }
        }
        if (!editor)
            return;
        this.refresh(editor);
        if (opts.reveal) {
            const lines = this.linesFor(absPath);
            if (lines.length) {
                editor.revealRange(new vscode.Range(lines[0], 0, lines[0], 0), vscode.TextEditorRevealType.InCenterIfOutsideViewport);
            }
        }
        const reapply = () => {
            const ed = vscode.window.visibleTextEditors.find(e => e.document.uri.fsPath === absPath);
            if (ed)
                this.refresh(ed);
        };
        setTimeout(reapply, 0);
        setTimeout(reapply, 60);
        setTimeout(reapply, 200);
    }
    private linesFor(absPath: string): number[] {
        const session = this.previews.get(absPath);
        return session ? session.lines : (this.pending.get(absPath) ?? []);
    }
    private refresh(editor: vscode.TextEditor): void {
        const key = editor.document.uri.fsPath;
        const max = editor.document.lineCount - 1;
        const session = this.previews.get(key);
        const lines = session ? session.lines : (this.pending.get(key) ?? []);
        const ranges = lines
            .filter(n => n >= 0 && n <= max)
            .map(n => new vscode.Range(n, 0, n, 0));
        editor.setDecorations(this.addedDecoration, ranges);
    }
    noteSelfWrite(absPath: string, ttlMs = 1500): void {
        this.selfWrite.set(absPath, Date.now() + ttlMs);
    }
    private isSelfWrite(absPath: string): boolean {
        const expiry = this.selfWrite.get(absPath);
        if (expiry === undefined)
            return false;
        if (Date.now() > expiry) {
            this.selfWrite.delete(absPath);
            return false;
        }
        return true;
    }
    clearFile(absPath: string): void {
        this.pending.delete(absPath);
        const open = vscode.window.visibleTextEditors.find(ed => ed.document.uri.fsPath === absPath);
        if (open)
            open.setDecorations(this.addedDecoration, []);
    }
    clearAll(): void {
        const paths = new Set<string>([...this.pending.keys(), ...this.previews.keys()]);
        this.pending.clear();
        this.previews.clear();
        for (const p of paths) {
            const open = vscode.window.visibleTextEditors.find(ed => ed.document.uri.fsPath === p);
            if (open)
                open.setDecorations(this.addedDecoration, []);
        }
    }
    dispose(): void {
        this.addedDecoration.dispose();
        for (const d of this.disposables)
            d.dispose();
        this.disposables.length = 0;
        this.pending.clear();
        this.previews.clear();
        this.beforeSnapshots.clear();
    }
}
