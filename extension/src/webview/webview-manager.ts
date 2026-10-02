import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { Workspace } from '../core/workspace';
import { WorkspaceCapture } from '../core/file-watcher';
import { CodingAgent, hasRepeatedSearchReplaceBlock } from '../agents/coding';
import { ContextAgent, scanWorkspaceFiles, WorkspaceFileCandidate } from '../agents/context';
import { parseEdits, applyEdits, applySelected, buildEditRetryInstruction, EditOp, AppliedFile, } from '../core/edits';
import { DecompositionAgent } from '../agents/decomposition';
import { MetaAgent } from '../agents/meta';
import { MergeAnalystAgent } from '../agents/merge-analyst';
import { ConflictResolverAgent } from '../agents/conflict-resolver';
import { LLMProvider } from '../llm/provider';
import { previewMerge, finalizeMerge, undoMerge, detectTestCommand, detectLintCommand } from '../core/merge';
import { Branch, Artifact, Message, InterruptionReason } from '../core/types';
import { Storage } from '../core/storage';
import { ChangeDecorations } from '../core/change-decorations';
import { isProtectedPath, protectedPathReason } from '../core/file-policy';
import { StudyController } from '../study/controller';
import { exec } from 'child_process';
import { promisify } from 'util';
const execAsync = promisify(exec);
interface PendingEditProposal {
    ops: EditOp[];
    files: ReturnType<typeof serializeProposal>[];
    draft: string;
    retryCount: number;
}
interface EditRecoveryRequest {
    instruction: string;
    retryCount: 1;
    failureCount: number;
}
export class ContextBranchView implements vscode.WebviewViewProvider {
    public static readonly viewType = 'contextbranch.sidebar';
    private view?: vscode.WebviewView;
    private currentAbort?: AbortController;
    private codingRuns = new Map<string, {
        controller: AbortController;
        partialText: string;
        done: Promise<void>;
        finish: () => void;
    }>();
    private finishingTimedOutStudy = false;
    private readonly studyTestController: vscode.TestController;
    private studyTestRunningStateId?: string;
    private pendingEditsByBranch = new Map<string, PendingEditProposal>();
    private mergeInProgress?: boolean;
    private pendingMergePreview?: {
        sourceBranchId: string;
        targetBranchId: string;
        fingerprint: string;
        preview: any;
    };
    private pendingMergeContextAbort?: AbortController;
    private pendingManualMerge?: {
        sourceBranchId: string;
        targetBranchId: string;
        paths: string[];
        acceptedCascadePaths: string[];
    };
    private studyStateMapOpenedAt?: number;
    private decorations?: ChangeDecorations;
    private getDecorations(): ChangeDecorations {
        if (!this.decorations) {
            this.decorations = new ChangeDecorations();
            this.context.subscriptions.push(this.decorations);
        }
        return this.decorations;
    }
    constructor(private context: vscode.ExtensionContext, private getWorkspace: () => Workspace | null, private getProvider: () => LLMProvider | null, private getCondition: () => 'linear' | 'branched' | 'contextbranch', private getStudyMode: () => boolean, private getCapture: () => WorkspaceCapture | null = () => null, private getStudyController: () => StudyController | null = () => null) {
        this.studyTestController = vscode.tests.createTestController('contextbranch-study-tests', 'ContextBranch Study');
        this.studyTestController.createRunProfile('Run current study tests', vscode.TestRunProfileKind.Run, async () => this.handleRunStudyTests(), true);
        this.context.subscriptions.push(this.studyTestController);
    }
    resolveWebviewView(view: vscode.WebviewView): void {
        this.view = view;
        view.webview.options = {
            enableScripts: true,
            localResourceRoots: [
                vscode.Uri.file(path.join(this.context.extensionPath, 'webview')),
            ],
        };
        view.webview.html = this.renderHtml(view.webview);
        view.webview.onDidReceiveMessage(async (msg) => {
            try {
                await this.handleMessage(msg);
            }
            catch (err: any) {
                view.webview.postMessage({ type: 'error', message: err.message ?? String(err) });
            }
        });
        this.pushState();
    }
    private postMessage(msg: any): void {
        this.view?.webview.postMessage(msg);
    }
    pushState(): void {
        const ws = this.getWorkspace();
        if (!ws) {
            this.postMessage({
                type: 'state',
                condition: this.getCondition(),
                providerReady: !!this.getProvider(),
                activeBranchId: null,
                mainBranchId: null,
                branches: [],
                messages: [],
                activeBranchName: '',
                activeBranchStatus: '',
                isMain: true,
                telemetry: null,
                historyGraph: null,
                branchRuns: {},
                pendingEdits: null,
                pendingEditRetryAvailable: false,
                noWorkspace: true,
            });
            return;
        }
        const branches = ws.getAllBranches();
        const activeId = ws.activeBranchId;
        const active = ws.getBranch(activeId)!;
        const messages = ws.getMessages(activeId);
        const checkpoints = ws.getCheckpoints(activeId);
        const condition = this.getCondition();
        const provider = this.getProvider();
        const study = this.getStudyController();
        const activePendingEdits = this.pendingEditsByBranch.get(activeId);
        this.postMessage({
            type: 'state',
            condition,
            providerReady: !!provider,
            activeBranchId: activeId,
            mainBranchId: ws.mainBranchId,
            activeCheckpointId: active.activeCheckpointId ?? null,
            checkpoints: checkpoints.map(cp => ({
                id: cp.id,
                branchId: cp.branchId,
                parentCheckpointId: cp.parentCheckpointId,
                messageCount: cp.messageIds.length,
                artifactCount: cp.artifactIds.length,
                createdAt: cp.createdAt,
                label: cp.label,
            })),
            branches: branches.map(b => ({
                id: b.id, name: b.name, description: b.description,
                status: b.status, parentBranchId: b.parentBranchId,
                activeCheckpointId: b.activeCheckpointId ?? null,
                messageCount: b.messageIds.length, tags: b.tags,
            })),
            messages: messages.map(m => ({
                id: m.id, role: m.role, content: m.content, timestamp: m.timestamp,
            })),
            activeBranchName: active.name,
            activeBranchStatus: active.status,
            isMain: activeId === ws.mainBranchId,
            telemetry: ws.workspaceState.telemetry,
            study: study?.uiState(ws) ?? null,
            branchRuns: Object.fromEntries([...this.codingRuns.entries()].map(([branchId, run]) => [
                branchId,
                { partialText: run.partialText },
            ])),
            pendingEdits: activePendingEdits?.files ?? null,
            pendingEditRetryAvailable: Boolean(activePendingEdits &&
                activePendingEdits.retryCount === 0 &&
                activePendingEdits.files.some(file => file.failedCount > 0)),
            noWorkspace: false,
            historyGraph: ws.getHistoryGraph(),
        });
    }
    private requireWorkspace(): Workspace | null {
        const ws = this.getWorkspace();
        if (!ws) {
            this.postMessage({
                type: 'error',
                message: 'Open a folder first (File → Open Folder) and reload the window.',
            });
            return null;
        }
        return ws;
    }
    private async handleMessage(msg: any): Promise<void> {
        switch (msg.type) {
            case 'send': return this.handleSend(msg.content, msg.branchId);
            case 'startStudyTask': return this.handleStartStudyTask();
            case 'runStudyTests': return this.handleRunStudyTests();
            case 'openStudyIntegration': return this.handleOpenStudyIntegration();
            case 'finishStudyTask': return this.handleFinishStudyTask();
            case 'studyStateMapOpened': return this.handleStudyStateMapOpened();
            case 'studyStateMapClosed': return this.handleStudyStateMapClosed(msg.durationMs);
            case 'studyStateMapNodeInspected': return this.handleStudyStateMapNodeInspected(msg.nodeId, msg.nodeKind, msg.stateId);
            case 'createBranch': return this.handleCreateBranch(msg.name, msg.description, msg.fromMessageId, msg.parentBranchId, msg.select);
            case 'switchBranch': return this.handleSwitchBranch(msg.branchId);
            case 'abandonBranch': return this.handleAbandonBranch(msg.branchId);
            case 'mergeBranch': return this.handleMergeBranch(msg.sourceBranchId, msg.targetBranchId, msg.force, msg.acceptedCascadePaths, msg.acceptedConflictPaths);
            case 'beginManualMergeResolution': return this.handleBeginManualMergeResolution(msg.acceptedCascadePaths ?? []);
            case 'finalizeManualMergeResolution': return this.handleFinalizeManualMergeResolution();
            case 'cancelManualMergeResolution': return this.handleCancelManualMergeResolution();
            case 'reviseConflictResolution': return this.handleReviseConflictResolution(msg.path, msg.instruction);
            case 'undoMerge': return this.handleUndoMerge(msg.mergeEventId);
            case 'previewMerge': return this.handlePreviewMerge(msg.sourceBranchId, msg.targetBranchId, Boolean(msg.allowCascade));
            case 'createCheckpoint': return this.handleCreateCheckpoint(msg.branchId, msg.label);
            case 'restoreCheckpoint': return this.handleRestoreCheckpoint(msg.branchId, msg.checkpointId);
            case 'abortStream': return this.handleAbort(msg.branchId);
            case 'decompose': return this.handleDecompose(msg.taskDescription);
            case 'requestState': return this.pushState();
            case 'applyArtifactsToWorkspace': return this.handleApplyArtifacts(msg.branchId);
            case 'previewArtifactsInWorkspace': return this.handlePreviewArtifacts(msg.branchId);
            case 'dismissArtifactsPreview': return this.handleDismissPreview(msg.branchId);
            case 'applyProposedEdits': return this.handleApplyProposedEdits(msg.branchId, msg.accepted);
            case 'discardProposedEdits': return this.handleDiscardProposedEdits(msg.branchId);
            case 'retryProposedEdits': return this.handleRetryProposedEdits(msg.branchId);
        }
    }
    private authoritativeContents(ws: Workspace, branchId: string, workspaceRoot: string | undefined, paths: Iterable<string>): Map<string, string> {
        const current = new Map<string, string>();
        const active = ws.activeBranchId === branchId;
        const artifacts = new Map(ws.getArtifacts(branchId).map(artifact => [artifact.path, artifact.content]));
        for (const filePath of paths) {
            const onDisk = active ? readWorkspaceFile(workspaceRoot, filePath) : null;
            if (onDisk != null)
                current.set(filePath, onDisk);
            else {
                const artifact = artifacts.get(filePath);
                if (artifact != null)
                    current.set(filePath, artifact);
            }
        }
        return current;
    }
    private resolveCodingContextWithoutAgent(ws: Workspace, branchId: string, history: Message[]): {
        workspaceFiles: WorkspaceFileCandidate[];
        selectedFiles: {
            path: string;
            content: string;
        }[];
    } {
        const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        if (!root)
            return { workspaceFiles: [], selectedFiles: [] };
        const scanned = ws.activeBranchId === branchId ? scanWorkspaceFiles(root) : [];
        const branchArtifacts = ws.getArtifacts(branchId);
        const known = new Set(scanned.map(f => f.path));
        const inventory = [...scanned];
        for (const a of branchArtifacts)
            if (!known.has(a.path))
                inventory.push({ path: a.path, size: a.content.length, symbols: [] });
        inventory.sort((a, b) => a.path.localeCompare(b.path));
        const totalBytes = inventory.reduce((n, f) => n + f.size, 0);
        const conversationText = history.map(m => m.content).join('\n').toLowerCase();
        const explicit = inventory
            .filter(f => conversationText.includes(f.path.toLowerCase()) ||
            conversationText.includes('/' + f.path.toLowerCase()) ||
            conversationText.includes(path.posix.basename(f.path).toLowerCase()))
            .map(f => f.path);
        let selectedPaths: string[];
        if (totalBytes <= 80000) {
            selectedPaths = inventory.map(f => f.path);
        }
        else if (explicit.length) {
            selectedPaths = explicit;
        }
        else {
            const tokens = conversationText.match(/[a-z][a-z0-9_-]{3,}/g) ?? [];
            const scored = inventory.map(f => {
                const hay = `${f.path} ${f.symbols.join(' ')}`.toLowerCase();
                let score = 0;
                for (const t of tokens)
                    if (hay.includes(t))
                        score++;
                return { path: f.path, score };
            }).sort((a, b) => b.score - a.score || a.path.localeCompare(b.path));
            selectedPaths = scored.slice(0, 16).map(x => x.path);
            if (!selectedPaths.length)
                selectedPaths = inventory.slice(0, 8).map(f => f.path);
        }
        const branchByPath = new Map(branchArtifacts.map(a => [a.path, a]));
        const selectedFiles: {
            path: string;
            content: string;
        }[] = [];
        const active = ws.activeBranchId === branchId;
        for (const filePath of selectedPaths) {
            const branch = branchByPath.get(filePath);
            if (branch && !active) {
                selectedFiles.push({ path: filePath, content: branch.content });
                continue;
            }
            const abs = path.join(root, filePath);
            const relative = path.relative(root, abs);
            if (relative.startsWith('..') || path.isAbsolute(relative))
                continue;
            try {
                const content = fs.readFileSync(abs, 'utf8');
                if (!content.includes('\u0000'))
                    selectedFiles.push({ path: filePath, content });
            }
            catch {
                if (branch)
                    selectedFiles.push({ path: filePath, content: branch.content });
            }
        }
        return { workspaceFiles: inventory, selectedFiles };
    }
    private async resolveCodingContext(ws: Workspace, branchId: string, history: Message[], model: string, signal: AbortSignal): Promise<{
        workspaceFiles: WorkspaceFileCandidate[];
        selectedFiles: {
            path: string;
            content: string;
        }[];
        summary?: string;
        rationale?: string;
        inputTokens: number;
        outputTokens: number;
        usedAgent: boolean;
    }> {
        const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        if (!root)
            return { workspaceFiles: [], selectedFiles: [], inputTokens: 0, outputTokens: 0, usedAgent: false };
        const scanned = ws.activeBranchId === branchId ? scanWorkspaceFiles(root) : [];
        const branchArtifacts = ws.getArtifacts(branchId);
        const known = new Set(scanned.map(f => f.path));
        const inventory = [...scanned];
        for (const a of branchArtifacts) {
            if (!known.has(a.path)) {
                inventory.push({ path: a.path, size: a.content.length, symbols: [] });
            }
        }
        inventory.sort((a, b) => a.path.localeCompare(b.path));
        const totalBytes = inventory.reduce((n, f) => n + f.size, 0);
        let selectedPaths: string[];
        let summary: string | undefined;
        let rationale: string | undefined;
        let inputTokens = 0;
        let outputTokens = 0;
        if (totalBytes <= 80000) {
            selectedPaths = inventory.map(f => f.path);
        }
        else {
            const contextAgent = new ContextAgent(this.getProvider()!, (i, o) => {
                inputTokens += i;
                outputTokens += o;
            });
            const result = await contextAgent.select({
                conversation: history.map(m => ({ role: m.role, content: m.content })),
                files: inventory,
                branchArtifacts: branchArtifacts.map(a => ({ path: a.path, size: a.content.length })),
                model,
                signal,
                maxFiles: 16,
            });
            selectedPaths = result.paths;
            summary = result.summary;
            rationale = result.rationale;
            const conversationText = history.map(m => m.content).join('\n').toLowerCase();
            const exact = inventory
                .filter(f => conversationText.includes(f.path.toLowerCase()) ||
                conversationText.includes('/' + f.path.toLowerCase()) ||
                conversationText.includes(path.posix.basename(f.path).toLowerCase()))
                .map(f => f.path);
            for (const p of exact)
                if (!selectedPaths.includes(p))
                    selectedPaths.push(p);
            if (selectedPaths.length === 0) {
                const tokens = conversationText.match(/[a-z][a-z0-9_-]{3,}/g) ?? [];
                const scored = inventory.map(f => {
                    const hay = `${f.path} ${f.symbols.join(' ')}`.toLowerCase();
                    let score = 0;
                    for (const t of tokens)
                        if (hay.includes(t))
                            score++;
                    return { path: f.path, score };
                }).sort((a, b) => b.score - a.score || a.path.localeCompare(b.path));
                selectedPaths = scored.slice(0, 12).map(x => x.path);
            }
        }
        const branchByPath = new Map(branchArtifacts.map(a => [a.path, a]));
        const selectedFiles: {
            path: string;
            content: string;
        }[] = [];
        const active = ws.activeBranchId === branchId;
        for (const filePath of selectedPaths) {
            const branch = branchByPath.get(filePath);
            if (branch && !active) {
                selectedFiles.push({ path: filePath, content: branch.content });
                continue;
            }
            const abs = path.join(root, filePath);
            const relative = path.relative(root, abs);
            if (relative.startsWith('..') || path.isAbsolute(relative))
                continue;
            try {
                const content = fs.readFileSync(abs, 'utf8');
                if (!content.includes('\u0000'))
                    selectedFiles.push({ path: filePath, content });
            }
            catch {
                if (branch)
                    selectedFiles.push({ path: filePath, content: branch.content });
            }
        }
        return { workspaceFiles: inventory, selectedFiles, summary, rationale, inputTokens, outputTokens, usedAgent: totalBytes > 80000 };
    }
    private async handleSend(content: string, requestedBranchId?: string, editRecovery?: EditRecoveryRequest): Promise<void> {
        const ws = this.requireWorkspace();
        if (!ws)
            return;
        const provider = this.getProvider();
        if (!provider) {
            this.postMessage({ type: 'error', message: 'No API key configured. Run "ContextBranch: Set API Key".' });
            return;
        }
        const branchId = typeof requestedBranchId === 'string' ? requestedBranchId : ws.activeBranchId;
        const branch = ws.getBranch(branchId);
        if (!branch) {
            this.postMessage({ type: 'error', branchId, message: 'The selected state no longer exists.' });
            return;
        }
        if (this.codingRuns.has(branch.id)) {
            this.postMessage({ type: 'error', branchId: branch.id, message: 'This state is already generating a response.' });
            return;
        }
        if (this.pendingEditsByBranch.has(branch.id)) {
            this.postMessage({ type: 'error', branchId: branch.id, message: 'Review or discard this state\'s proposed edits before sending another prompt.' });
            return;
        }
        const study = this.getStudyController();
        if (study) {
            const denial = study.beginModelCall(ws, branch.id);
            if (denial) {
                this.postMessage({ type: 'error', branchId: branch.id, message: denial });
                return;
            }
        }
        const controller = new AbortController();
        let finishRun!: () => void;
        const done = new Promise<void>(resolve => { finishRun = resolve; });
        this.codingRuns.set(branch.id, { controller, partialText: '', done, finish: finishRun });
        if (editRecovery) {
            ws.appendMessage(branch.id, 'system', `[edit-retry] Retrying ${editRecovery.failureCount} failed change(s) against the authoritative current file (attempt 1/1).`);
            if (study) {
                study.recordEditRetry(ws, branch.id, editRecovery.failureCount);
            }
            else {
                ws.storage.appendTelemetry({
                    type: 'edit_retry_started',
                    actor: 'participant',
                    branchId: branch.id,
                    retryCount: editRecovery.retryCount,
                    failureCount: editRecovery.failureCount,
                });
            }
        }
        else {
            ws.appendMessage(branch.id, 'user', content);
        }
        this.pushState();
        try {
            const agent = new CodingAgent(provider);
            const parent = branch.parentBranchId ? ws.getBranch(branch.parentBranchId) : null;
            const history = ws.getMessages(branch.id);
            const isMain = branch.id === ws.mainBranchId;
            const cfg = vscode.workspace.getConfiguration('contextbranch');
            const model = study?.modelId || cfg.get<string>('model') || provider.defaultModel;
            const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
            let contextInputTokens = 0, contextOutputTokens = 0;
            let contextCallStarted = false;
            let codingContext: {
                workspaceFiles: WorkspaceFileCandidate[];
                selectedFiles: {
                    path: string;
                    content: string;
                }[];
                summary?: string;
                rationale?: string;
            } = { workspaceFiles: [], selectedFiles: [] };
            try {
                const contextEnabled = cfg.get<boolean>('contextAgentEnabled') ?? true;
                if (contextEnabled && workspaceRoot) {
                    const scanned = ws.activeBranchId === branch.id ? scanWorkspaceFiles(workspaceRoot) : [];
                    const branchArtifacts = ws.getArtifacts(branch.id);
                    const inventoryBytes = scanned.reduce((n, f) => n + f.size, 0) +
                        branchArtifacts.filter(a => !scanned.some(f => f.path === a.path))
                            .reduce((n, a) => n + a.content.length, 0);
                    if (inventoryBytes > 80000) {
                        if (study) {
                            const denial = study.beginModelCall(ws, branch.id);
                            if (!denial) {
                                contextCallStarted = true;
                                const context = await this.resolveCodingContext(ws, branch.id, history, model, controller.signal);
                                contextInputTokens = context.inputTokens;
                                contextOutputTokens = context.outputTokens;
                                codingContext = {
                                    workspaceFiles: context.workspaceFiles,
                                    selectedFiles: context.selectedFiles,
                                    summary: context.summary,
                                    rationale: context.rationale,
                                };
                                study.recordModelUsage(ws, contextInputTokens, contextOutputTokens, model, branch.id);
                                contextCallStarted = false;
                            }
                            else {
                                codingContext = this.resolveCodingContextWithoutAgent(ws, branch.id, history);
                            }
                        }
                        else {
                            const context = await this.resolveCodingContext(ws, branch.id, history, model, controller.signal);
                            contextInputTokens = context.inputTokens;
                            contextOutputTokens = context.outputTokens;
                            codingContext = {
                                workspaceFiles: context.workspaceFiles,
                                selectedFiles: context.selectedFiles,
                                summary: context.summary,
                                rationale: context.rationale,
                            };
                        }
                    }
                    else {
                        codingContext = this.resolveCodingContextWithoutAgent(ws, branch.id, history);
                    }
                }
                else if (workspaceRoot) {
                    codingContext = this.resolveCodingContextWithoutAgent(ws, branch.id, history);
                }
            }
            catch (err: any) {
                if (contextCallStarted && study) {
                    study.recordModelUsage(ws, contextInputTokens, contextOutputTokens, model, branch.id);
                    contextCallStarted = false;
                }
                if (workspaceRoot)
                    codingContext = this.resolveCodingContextWithoutAgent(ws, branch.id, history);
                this.postMessage({
                    type: 'contextWarning',
                    branchId: branch.id,
                    message: `Context selection fallback: ${err.message ?? String(err)}`,
                });
            }
            const runCoding = async (repairInstruction?: string): Promise<{
                text: string;
                inputTokens: number;
                outputTokens: number;
                truncated: boolean;
                aborted: boolean;
                interruptionReason?: InterruptionReason;
            }> => {
                let assistantText = '';
                let inputTokens = 0, outputTokens = 0;
                let truncated = false;
                let aborted = false;
                let interruptionReason: InterruptionReason | undefined;
                let repetitionDetected = false;
                let nextRepetitionCheckAt = 2048;
                const run = this.codingRuns.get(branch.id);
                if (run)
                    run.partialText = '';
                this.postMessage({ type: 'streamStart', branchId: branch.id });
                try {
                    for await (const ev of agent.streamReply({
                        branch,
                        parentBranchName: parent?.name ?? 'main',
                        isMain,
                        history,
                        workspaceRoot,
                        signal: controller.signal,
                        artifacts: ws.getArtifacts(branch.id),
                        workspaceFiles: codingContext.workspaceFiles,
                        selectedFiles: codingContext.selectedFiles,
                        contextRationale: codingContext.rationale,
                        contextSummary: codingContext.summary,
                        model,
                        repairInstruction,
                    })) {
                        if (ev.type === 'delta' && ev.text) {
                            assistantText += ev.text;
                            const activeRun = this.codingRuns.get(branch.id);
                            if (activeRun)
                                activeRun.partialText += ev.text;
                            this.postMessage({ type: 'streamDelta', branchId: branch.id, text: ev.text });
                            if (!repetitionDetected && assistantText.length >= nextRepetitionCheckAt) {
                                nextRepetitionCheckAt = assistantText.length + 512;
                                if (hasRepeatedSearchReplaceBlock(assistantText)) {
                                    repetitionDetected = true;
                                    aborted = true;
                                    interruptionReason = 'repetition';
                                    controller.abort();
                                    this.postMessage({
                                        type: 'error',
                                        branchId: branch.id,
                                        message: 'The model repeated the same edit block, so generation was stopped. No edits were applied. Please send a narrower follow-up.',
                                    });
                                }
                            }
                        }
                        else if (ev.type === 'usage') {
                            inputTokens = ev.inputTokens ?? 0;
                            outputTokens = ev.outputTokens ?? 0;
                        }
                        else if (ev.type === 'error') {
                            if (ev.error === 'aborted') {
                                aborted = true;
                                interruptionReason ??= repetitionDetected ? 'repetition' : 'user_abort';
                                this.postMessage({ type: 'streamAborted', branchId: branch.id });
                            }
                            else {
                                aborted = true;
                                interruptionReason = 'provider_error';
                                this.postMessage({ type: 'error', branchId: branch.id, message: ev.error ?? 'Unknown LLM error' });
                            }
                            break;
                        }
                        else if (ev.type === 'done') {
                            truncated = Boolean(ev.truncated);
                            if (truncated) {
                                aborted = true;
                                interruptionReason = 'output_limit';
                                this.postMessage({
                                    type: 'error',
                                    branchId: branch.id,
                                    message: 'The model hit its output limit before finishing. The partial response was not applied as code edits; please resend the request or make the change smaller.',
                                });
                            }
                            break;
                        }
                    }
                }
                catch (err: any) {
                    aborted = true;
                    interruptionReason ??= repetitionDetected ? 'repetition' : 'provider_error';
                    this.postMessage({
                        type: 'error',
                        branchId: branch.id,
                        message: err.message ?? String(err),
                    });
                }
                if (repetitionDetected) {
                    aborted = true;
                    interruptionReason = 'repetition';
                }
                return { text: assistantText, inputTokens, outputTokens, truncated, aborted, interruptionReason };
            };
            const refreshCodingContext = (requiredPaths: Iterable<string>): void => {
                const refreshed = this.resolveCodingContextWithoutAgent(ws, branch.id, ws.getMessages(branch.id));
                const byPath = new Map(refreshed.selectedFiles.map(file => [file.path, file.content]));
                for (const [filePath, content] of this.authoritativeContents(ws, branch.id, workspaceRoot, requiredPaths)) {
                    byPath.set(filePath, content);
                }
                codingContext = {
                    workspaceFiles: refreshed.workspaceFiles,
                    selectedFiles: [...byPath].map(([path, content]) => ({ path, content })),
                };
            };
            let result = await runCoding(editRecovery?.instruction);
            if (study) {
                study.recordModelUsage(ws, result.inputTokens, result.outputTokens, model, branch.id, {
                    interruptionReason: result.interruptionReason,
                    observedOutputChars: result.text.length,
                });
            }
            let retried = false;
            let repairCount = editRecovery?.retryCount ?? 0;
            let ops = result.aborted ? [] : parseEdits(result.text);
            let proposed = !result.aborted && ops.length
                ? applyEdits(ops, this.authoritativeContents(ws, branch.id, workspaceRoot, new Set(ops.map(op => op.path))), { allowUniquePythonSymbolRebase: repairCount > 0 })
                : [];
            const failedChanges = proposed.reduce((sum, file) => sum + file.failedCount, 0);
            if (!result.aborted && repairCount === 0 && failedChanges > 0) {
                const denial = study?.beginModelCall(ws, branch.id);
                if (denial) {
                    this.postMessage({ type: 'error', branchId: branch.id, message: denial });
                }
                else {
                    const retryContents = this.authoritativeContents(ws, branch.id, workspaceRoot, new Set(ops.map(op => op.path)));
                    const instruction = buildEditRetryInstruction(proposed, result.text, retryContents);
                    ws.appendMessage(branch.id, 'system', `[edit-retry] Retrying ${failedChanges} failed change(s) against freshly read current file contents (attempt 1/1).`);
                    if (study)
                        study.recordEditRetry(ws, branch.id, failedChanges);
                    else
                        ws.storage.appendTelemetry({
                            type: 'edit_retry_started', actor: 'system', branchId: branch.id,
                            retryCount: 1, failureCount: failedChanges,
                        });
                    this.postMessage({ type: 'editRetryStarted', branchId: branch.id, failureCount: failedChanges });
                    refreshCodingContext(new Set(ops.map(op => op.path)));
                    retried = true;
                    repairCount = 1;
                    result = await runCoding(instruction);
                    ops = result.aborted ? [] : parseEdits(result.text);
                    proposed = !result.aborted && ops.length
                        ? applyEdits(ops, this.authoritativeContents(ws, branch.id, workspaceRoot, new Set(ops.map(op => op.path))), { allowUniquePythonSymbolRebase: true })
                        : [];
                }
            }
            if (result.text) {
                const totalInput = result.inputTokens;
                const totalOutput = result.outputTokens;
                ws.appendMessage(branch.id, 'assistant', result.text, {
                    inputTokens: totalInput,
                    outputTokens: totalOutput,
                    model,
                    interrupted: result.aborted ? true : undefined,
                    interruptionReason: result.interruptionReason,
                    artifactIds: ops.length ? [...new Set(ops.map(o => o.path))] : undefined,
                });
                if (!result.aborted && ops.length) {
                    const review = cfg.get<boolean>('reviewEdits') ?? true;
                    if (review) {
                        const files = proposed.map(serializeProposal);
                        const canRetry = repairCount === 0 && proposed.some(file => file.failedCount > 0);
                        this.pendingEditsByBranch.set(branch.id, {
                            ops,
                            files,
                            draft: result.text,
                            retryCount: repairCount,
                        });
                        this.postMessage({ type: 'proposedEdits', branchId: branch.id, files, canRetry });
                    }
                    else {
                        this.commitProposedFiles(branch.id, proposed);
                    }
                }
            }
            if (retried && study) {
                study.recordModelUsage(ws, result.inputTokens, result.outputTokens, model, branch.id, {
                    interruptionReason: result.interruptionReason,
                    observedOutputChars: result.text.length,
                });
            }
        }
        finally {
            const run = this.codingRuns.get(branch.id);
            this.codingRuns.delete(branch.id);
            run?.finish();
            this.postMessage({ type: 'streamEnd', branchId: branch.id });
            this.pushState();
        }
    }
    private handleAbort(branchId?: string): void {
        const ws = this.getWorkspace();
        const target = typeof branchId === 'string' ? branchId : ws?.activeBranchId;
        if (target)
            this.codingRuns.get(target)?.controller.abort();
    }
    private async abortAllCodingRuns(): Promise<void> {
        const runs = [...this.codingRuns.values()];
        for (const run of runs)
            run.controller.abort();
        await Promise.all(runs.map(run => run.done));
    }
    private commitProposedFiles(branchId: string, files: AppliedFile[]): void {
        const ws = this.requireWorkspace();
        if (!ws)
            return;
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        let applied = 0;
        const failures: string[] = [];
        const notes: string[] = [];
        for (const f of files) {
            if (isProtectedPath(f.path)) {
                failures.push(protectedPathReason(f.path));
                continue;
            }
            const total = f.ops.length;
            const okOps = f.ops.filter(o => o.ok).length;
            const skipped = total - okOps;
            if (okOps === 0) {
                for (const o of f.ops.filter(x => !x.ok))
                    failures.push(`${f.path}: ${o.reason}`);
                if (total)
                    notes.push(`${f.path} — 0/${total} applied (all skipped)`);
                continue;
            }
            ws.upsertArtifact(branchId, f.path, f.after, f.before === '' ? null : f.before);
            applied++;
            notes.push(f.isNew
                ? `${f.path} — created`
                : `${f.path} — ${okOps}/${total} change(s) applied${skipped ? ` (${skipped} skipped)` : ''}`);
            for (const o of f.ops.filter(x => !x.ok))
                failures.push(`${f.path}: ${o.reason}`);
            if (workspaceRoot && branchId === ws.activeBranchId) {
                const art = ws.getArtifacts(branchId).find(a => a.path === f.path);
                if (art)
                    this.syncArtifactsToWorkspace(workspaceRoot, new Set(), [art], 3000);
            }
        }
        if (notes.length) {
            ws.appendMessage(branchId, 'system', `[edit-log] ${notes.join('; ')}`);
        }
        this.postMessage({
            type: 'editsApplied', applied,
            branchId,
            failures: failures.length ? failures : undefined,
        });
        this.pushState();
    }
    private handleApplyProposedEdits(branchId?: string, accepted?: Record<string, number[]>): void {
        const ws = this.requireWorkspace();
        if (!ws)
            return;
        const targetBranchId = typeof branchId === 'string' ? branchId : ws.activeBranchId;
        const pending = this.pendingEditsByBranch.get(targetBranchId);
        if (!pending)
            return;
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        const currentByPath = this.authoritativeContents(ws, targetBranchId, workspaceRoot, new Set(pending.ops.map(op => op.path)));
        const acceptedMap = new Map<string, Set<number>>();
        if (accepted)
            for (const [p, idxs] of Object.entries(accepted))
                acceptedMap.set(p, new Set(idxs));
        const resolved = applySelected(pending.ops, currentByPath, acceptedMap);
        this.pendingEditsByBranch.delete(targetBranchId);
        this.commitProposedFiles(targetBranchId, resolved);
    }
    private async handleRetryProposedEdits(branchId?: string): Promise<void> {
        const ws = this.requireWorkspace();
        if (!ws)
            return;
        const targetBranchId = typeof branchId === 'string' ? branchId : ws.activeBranchId;
        const pending = this.pendingEditsByBranch.get(targetBranchId);
        if (!pending)
            return;
        if (pending.retryCount >= 1) {
            this.postMessage({
                type: 'error',
                branchId: targetBranchId,
                message: 'This proposal already used its one safe retry. Discard it or edit the file manually.',
            });
            return;
        }
        if (this.codingRuns.has(targetBranchId)) {
            this.postMessage({ type: 'error', branchId: targetBranchId, message: 'This state is already generating a response.' });
            return;
        }
        if (!this.getProvider()) {
            this.postMessage({ type: 'error', branchId: targetBranchId, message: 'No API key configured.' });
            return;
        }
        const study = this.getStudyController();
        const actionError = study?.actionError();
        if (actionError) {
            this.postMessage({ type: 'error', branchId: targetBranchId, message: actionError });
            return;
        }
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        const currentByPath = this.authoritativeContents(ws, targetBranchId, workspaceRoot, new Set(pending.ops.map(op => op.path)));
        const resolved = applyEdits(pending.ops, currentByPath);
        const failureCount = resolved.reduce((sum, file) => sum + file.failedCount, 0);
        if (failureCount === 0) {
            const files = resolved.map(serializeProposal);
            pending.files = files;
            this.postMessage({
                type: 'proposedEdits',
                branchId: targetBranchId,
                files,
                canRetry: false,
            });
            this.pushState();
            return;
        }
        const instruction = buildEditRetryInstruction(resolved, pending.draft, currentByPath);
        this.pendingEditsByBranch.delete(targetBranchId);
        this.postMessage({
            type: 'editRetryStarted',
            branchId: targetBranchId,
            failureCount,
        });
        this.pushState();
        await this.handleSend('', targetBranchId, { instruction, retryCount: 1, failureCount });
    }
    private handleDiscardProposedEdits(branchId?: string): void {
        const ws = this.getWorkspace();
        const targetBranchId = typeof branchId === 'string' ? branchId : ws?.activeBranchId;
        if (!targetBranchId)
            return;
        this.pendingEditsByBranch.delete(targetBranchId);
        this.postMessage({ type: 'editsDiscarded', branchId: targetBranchId });
        this.pushState();
    }
    private handleCreateBranch(name: string, description?: string, fromMessageId?: string, parentBranchId?: string, select: boolean = true): void {
        if (this.getStudyController()) {
            this.postMessage({ type: 'error', message: 'Study states are created automatically for this task.' });
            return;
        }
        if (this.getCondition() === 'linear') {
            this.postMessage({ type: 'error', message: 'Branching disabled in linear condition.' });
            return;
        }
        const ws = this.requireWorkspace();
        if (!ws)
            return;
        const branch = ws.createBranch({ name, description, fromMessageId, parentBranchId });
        if (select)
            ws.switchBranch(branch.id);
        this.pushState();
    }
    private async handleSwitchBranch(branchId: string, actor: 'participant' | 'system' = 'participant', reason: string = 'state_selector'): Promise<void> {
        const ws = this.requireWorkspace();
        if (!ws)
            return;
        if (this.studyTestRunningStateId && branchId !== ws.activeBranchId) {
            this.postMessage({ type: 'error', message: 'Wait for the current state test to finish before switching states.' });
            return;
        }
        this.pendingMergePreview = undefined;
        this.pendingManualMerge = undefined;
        await this.getDecorations().dismissAllPreviews();
        const config = vscode.workspace.getConfiguration('contextbranch');
        const autoApply = config.get<boolean>('autoApplyOnSwitch') ?? true;
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        const oldBranchId = ws.activeBranchId;
        const oldPaths: Set<string> = new Set<string>(ws.getArtifacts(oldBranchId).map(a => a.path));
        ws.switchBranch(branchId, { actor, reason });
        const study = this.getStudyController();
        if (study && oldBranchId !== branchId) {
            study.recordStateSwitch(ws, oldBranchId, branchId, actor, reason);
        }
        if (autoApply && workspaceRoot && oldBranchId !== branchId) {
            const newArtifacts = ws.getArtifacts(branchId);
            const sync = this.syncArtifactsToWorkspace(workspaceRoot, oldPaths, newArtifacts, 3000);
            if (sync.wrote > 0 || sync.removed > 0) {
                this.postMessage({
                    type: 'switchApplied',
                    wrote: sync.wrote,
                    removed: sync.removed,
                    branchName: ws.getBranch(branchId)?.name ?? branchId,
                });
            }
        }
        this.pushState();
    }
    private handleAbandonBranch(branchId: string): void {
        if (this.getStudyController()) {
            this.postMessage({ type: 'error', message: 'Study states cannot be abandoned during a task.' });
            return;
        }
        const ws = this.requireWorkspace();
        if (!ws)
            return;
        if (this.codingRuns.has(branchId)) {
            this.postMessage({ type: 'error', branchId, message: 'Stop this state\'s generation before abandoning it.' });
            return;
        }
        ws.abandonBranch(branchId);
        if (ws.activeBranchId === branchId)
            ws.switchBranch(ws.mainBranchId);
        this.pushState();
    }
    private syncArtifactsToWorkspace(workspaceRoot: string, oldPaths: Set<string>, newArtifacts: Artifact[], suppressMs = 3000): {
        wrote: number;
        removed: number;
    } {
        const newPaths: Set<string> = new Set<string>(newArtifacts.map(a => a.path));
        const allTouchedAbs: string[] = [];
        for (const a of newArtifacts)
            allTouchedAbs.push(path.join(workspaceRoot, a.path));
        for (const op of oldPaths)
            allTouchedAbs.push(path.join(workspaceRoot, op));
        this.getCapture()?.suppressMany(allTouchedAbs, suppressMs);
        let wrote = 0, removed = 0;
        const deco = this.getDecorations();
        const marked: {
            full: string;
            content: string;
        }[] = [];
        for (const art of newArtifacts) {
            if (isProtectedPath(art.path))
                continue;
            try {
                const full = path.join(workspaceRoot, art.path);
                deco.snapshotBefore(full);
                deco.noteSelfWrite(full, 4000);
                fs.mkdirSync(path.dirname(full), { recursive: true });
                fs.writeFileSync(full, art.content, 'utf-8');
                marked.push({ full, content: art.content });
                wrote++;
            }
            catch { }
        }
        for (const orphanPath of oldPaths) {
            if (isProtectedPath(orphanPath))
                continue;
            if (newPaths.has(orphanPath))
                continue;
            try {
                const full = path.join(workspaceRoot, orphanPath);
                deco.clearFile(full);
                if (fs.existsSync(full)) {
                    fs.unlinkSync(full);
                    removed++;
                }
            }
            catch { }
        }
        for (const m of marked) {
            void deco.markChanges(m.full, m.content);
        }
        return { wrote, removed };
    }
    private handleCreateCheckpoint(branchId: string, label?: string): void {
        if (this.getStudyController()) {
            this.postMessage({ type: 'error', message: 'Manual checkpoints are disabled during a study task.' });
            return;
        }
        const ws = this.requireWorkspace();
        if (!ws)
            return;
        const cp = ws.createCheckpoint(branchId, label);
        this.pushState();
        this.postMessage({
            type: 'checkpointCreated',
            checkpointId: cp.id,
            branchId,
            message: `Checkpoint created${cp.label ? `: ${cp.label}` : ''}.`,
        });
    }
    private handleRestoreCheckpoint(branchId: string, checkpointId: string): void {
        if (this.getStudyController()) {
            this.postMessage({ type: 'error', message: 'Manual checkpoint restore is disabled during a study task.' });
            return;
        }
        const ws = this.requireWorkspace();
        if (!ws)
            return;
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        const beforePaths: Set<string> = new Set<string>(ws.getArtifacts(branchId).map(a => a.path));
        const cp = ws.restoreCheckpoint(branchId, checkpointId);
        let wrote = 0;
        let removed = 0;
        if (workspaceRoot && ws.activeBranchId === branchId) {
            const afterArtifacts = ws.getArtifacts(branchId);
            const sync = this.syncArtifactsToWorkspace(workspaceRoot, beforePaths, afterArtifacts, 3000);
            wrote = sync.wrote;
            removed = sync.removed;
        }
        this.pushState();
        this.postMessage({
            type: 'checkpointRestored',
            branchId,
            checkpointId: cp.id,
            wrote,
            removed,
            message: `Restored checkpoint${cp.label ? `: ${cp.label}` : ''}.`,
        });
    }
    private buildAnalyzeCascadeHook(): NonNullable<Parameters<typeof previewMerge>[1]['analyzeCascade']> | null {
        const provider = this.getProvider();
        if (!provider)
            return null;
        const analyst = new MergeAnalystAgent(provider, (i, o) => this.getWorkspace()?.recordMergeApiUsage(i, o));
        return async (_source: Branch, _target: Branch, sourceArtifacts: Artifact[], targetArtifacts: Artifact[], changedFiles: {
            path: string;
            before: string;
            after: string;
            status: 'add' | 'modify' | 'conflict';
        }[], recentMessages: Message[]) => {
            return await analyst.analyze({
                sourceArtifacts: sourceArtifacts.map(a => ({ path: a.path, content: a.content })),
                targetArtifacts: targetArtifacts.map(a => ({ path: a.path, content: a.content })),
                changedFiles,
                recentMessages: recentMessages.map(m => ({ role: m.role, content: m.content })),
                signal: this.currentAbort?.signal,
            });
        };
    }
    private buildResolveConflictHook(opts?: {
        study?: StudyController | null;
        sourceBranchId?: string;
        targetBranchId?: string;
    }): NonNullable<Parameters<typeof previewMerge>[1]['resolveConflict']> | null {
        const provider = this.getProvider();
        if (!provider)
            return null;
        return async (conflict) => {
            const ws = this.getWorkspace();
            let inputTokens = 0;
            let outputTokens = 0;
            if (ws && opts?.study && opts.sourceBranchId && opts.targetBranchId) {
                opts.study.recordMergeModelCallStarted(ws, opts.sourceBranchId, opts.targetBranchId, conflict.path, 'conflict_resolution');
            }
            const resolver = new ConflictResolverAgent(provider, (i, o) => {
                inputTokens += i;
                outputTokens += o;
                ws?.recordMergeApiUsage(i, o);
            });
            const resolution = await resolver.resolve({
                path: conflict.path,
                base: conflict.base,
                theirs: conflict.theirs,
                ours: conflict.ours,
                theirContext: conflict.theirContext.map(m => ({ role: m.role, content: m.content })),
                ourContext: conflict.ourContext.map(m => ({ role: m.role, content: m.content })),
                signal: this.currentAbort?.signal,
                model: opts?.study?.modelId,
            });
            if (ws && opts?.study && opts.sourceBranchId && opts.targetBranchId) {
                opts.study.recordMergeModelUsage(ws, opts.sourceBranchId, opts.targetBranchId, conflict.path, 'conflict_resolution', inputTokens, outputTokens);
            }
            return resolution;
        };
    }
    private async handlePreviewMerge(sourceBranchId: string, targetBranchId: string, allowCascade = false): Promise<void> {
        const ws = this.requireWorkspace();
        if (!ws)
            return;
        if (this.codingRuns.has(sourceBranchId) || this.codingRuns.has(targetBranchId)) {
            this.postMessage({ type: 'error', message: 'Wait for the source and target generations to finish before previewing a merge.' });
            return;
        }
        if (this.pendingEditsByBranch.has(sourceBranchId) || this.pendingEditsByBranch.has(targetBranchId)) {
            this.postMessage({ type: 'error', message: 'Review or discard proposed edits in the source and target before previewing a merge.' });
            return;
        }
        const study = this.getStudyController();
        if (study) {
            const actionError = study.actionError();
            if (actionError) {
                this.postMessage({ type: 'error', message: actionError });
                return;
            }
            if (!study.allowsMerge(sourceBranchId, targetBranchId, ws)) {
                this.postMessage({ type: 'error', message: 'During this study task, only an active automatic sibling state may be integrated into main.' });
                return;
            }
        }
        const provider = this.getProvider();
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        const config = vscode.workspace.getConfiguration('contextbranch');
        const testCmd = config.get<string>('testCommand') || (workspaceRoot ? detectTestCommand(workspaceRoot) : null);
        const lintCmd = config.get<string>('lintCommand') || (workspaceRoot ? detectLintCommand(workspaceRoot) : null);
        const semanticMerge = config.get<boolean>('semanticMerge') ?? true;
        const meta = provider && !study ? new MetaAgent(provider) : null;
        const analyzeCascade = !study && semanticMerge && allowCascade ? this.buildAnalyzeCascadeHook() : null;
        const resolveConflict = provider && (Boolean(study) || semanticMerge)
            ? this.buildResolveConflictHook({ study, sourceBranchId, targetBranchId })
            : null;
        try {
            const preview = await previewMerge(ws, {
                sourceBranchId, targetBranchId,
                generateSynthesis: !study,
                workspaceRoot,
                testCommand: testCmd ?? undefined,
                lintCommand: lintCmd ?? undefined,
                skipVerification: Boolean(study),
                consolidate: meta ? (b: Branch, msgs: Message[], changed: any, _t: Branch) => meta.consolidate(b, msgs, changed) : undefined,
                rebaseCheck: meta ? (source: Branch, target: Branch, sm: Message[], tm: Message[]) => meta.rebaseCheck(source, target, sm, tm) : undefined,
                consistencyCheck: meta ? (target: Branch, mm: Message[], evidence: import('../core/merge').ConsistencyEvidence[]) => meta.consistencyCheck(target, mm, evidence, this.currentAbort?.signal) : undefined,
                analyzeCascade: analyzeCascade ?? undefined,
                resolveConflict: resolveConflict ?? undefined,
            });
            this.pendingMergePreview = {
                sourceBranchId,
                targetBranchId,
                fingerprint: preview.stateFingerprint,
                preview,
            };
            this.postMessage({ type: 'mergePreview', preview, sourceBranchId, targetBranchId });
        }
        catch (err: any) {
            this.pendingMergePreview = undefined;
            this.postMessage({ type: 'error', message: `Preview failed: ${err.message ?? err}` });
        }
    }
    private async handleBeginManualMergeResolution(acceptedCascadePaths: string[] = []): Promise<void> {
        const ws = this.requireWorkspace();
        const cached = this.pendingMergePreview;
        if (!ws || !cached) {
            this.postMessage({ type: 'error', message: 'Preview the merge before starting conflict resolution.' });
            return;
        }
        const study = this.getStudyController();
        if (study) {
            const actionError = study.actionError();
            if (actionError) {
                this.postMessage({ type: 'error', message: actionError });
                return;
            }
            if (!study.allowsMerge(cached.sourceBranchId, cached.targetBranchId, ws)) {
                this.postMessage({ type: 'error', message: 'During this study task, only an active automatic sibling state may be integrated into main.' });
                return;
            }
        }
        if (ws.activeBranchId !== cached.sourceBranchId) {
            this.postMessage({ type: 'error', message: 'Switch to the source branch before resolving merge conflicts in the editor.' });
            return;
        }
        const nowFingerprint = this.branchStateFingerprintPair(ws, cached.sourceBranchId, cached.targetBranchId);
        if (nowFingerprint !== cached.fingerprint) {
            this.postMessage({ type: 'error', message: 'The merge preview is stale. Preview the merge again before resolving conflicts.' });
            return;
        }
        const conflicts = cached.preview.verification?.artifactConflicts ?? [];
        if (!conflicts.length) {
            this.postMessage({ type: 'error', message: 'This merge has no textual conflicts to resolve in the editor.' });
            return;
        }
        const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        if (!root) {
            this.postMessage({ type: 'error', message: 'No workspace folder is open.' });
            return;
        }
        const deco = this.getDecorations();
        const started: string[] = [];
        try {
            for (let i = 0; i < conflicts.length; i++) {
                const conflict = conflicts[i];
                const full = path.join(root, conflict.path);
                const ok = await deco.previewChanges(full, conflict.conflictRegion, { reveal: i === 0 });
                if (!ok)
                    throw new Error(`Could not open ${conflict.path} for conflict resolution.`);
                started.push(conflict.path);
            }
            this.pendingManualMerge = {
                sourceBranchId: cached.sourceBranchId,
                targetBranchId: cached.targetBranchId,
                paths: conflicts.map((c: any) => c.path),
                acceptedCascadePaths: [...acceptedCascadePaths],
            };
            this.postMessage({ type: 'manualMergeResolutionStarted', paths: started });
        }
        catch (err: any) {
            await deco.dismissAllPreviews();
            this.pendingManualMerge = undefined;
            this.postMessage({ type: 'error', message: `Could not start IDE conflict resolution: ${err.message ?? err}` });
        }
    }
    private async handleFinalizeManualMergeResolution(): Promise<void> {
        const ws = this.requireWorkspace();
        const cached = this.pendingMergePreview;
        const manual = this.pendingManualMerge;
        if (!ws || !cached || !manual) {
            this.postMessage({ type: 'error', message: 'No active IDE conflict-resolution session.' });
            return;
        }
        const study = this.getStudyController();
        if (study) {
            const actionError = study.actionError();
            if (actionError) {
                this.postMessage({ type: 'error', message: actionError });
                return;
            }
            if (!study.allowsMerge(manual.sourceBranchId, manual.targetBranchId, ws)) {
                this.postMessage({ type: 'error', message: 'During this study task, only an active automatic sibling state may be integrated into main.' });
                return;
            }
        }
        if (ws.activeBranchId !== manual.sourceBranchId) {
            this.postMessage({ type: 'error', message: 'Return to the source branch before finalizing the resolved merge.' });
            return;
        }
        const nowFingerprint = this.branchStateFingerprintPair(ws, cached.sourceBranchId, cached.targetBranchId);
        if (nowFingerprint !== cached.fingerprint) {
            this.postMessage({ type: 'error', message: 'The merge preview became stale while you were resolving conflicts. The resolution was not finalized; preview the merge again.' });
            return;
        }
        const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        if (!root) {
            this.postMessage({ type: 'error', message: 'No workspace folder is open.' });
            return;
        }
        const manualResolved: Record<string, string> = {};
        const unresolved: string[] = [];
        for (const conflict of (cached.preview.verification?.artifactConflicts ?? [])) {
            const full = path.join(root, conflict.path);
            const doc = vscode.workspace.textDocuments.find(d => d.uri.fsPath === full);
            const content = doc?.getText() ?? readWorkspaceFile(root, conflict.path);
            if (content == null) {
                unresolved.push(`${conflict.path} (file is unavailable)`);
                continue;
            }
            if (/<{7}|>{7}|^={7}$/m.test(content)) {
                unresolved.push(conflict.path);
                continue;
            }
            manualResolved[conflict.path] = content;
        }
        if (unresolved.length) {
            this.postMessage({
                type: 'manualMergeResolutionBlocked',
                paths: unresolved,
                message: `Resolve the remaining conflict markers in: ${unresolved.join(', ')}`,
            });
            return;
        }
        this.mergeInProgress = true;
        try {
            const event = await finalizeMerge(ws, {
                sourceBranchId: cached.sourceBranchId,
                targetBranchId: cached.targetBranchId,
                force: false,
                workspaceRoot: root,
                testCommand: (() => {
                    const c = vscode.workspace.getConfiguration('contextbranch').get<string>('testCommand');
                    return c ?? (detectTestCommand(root) ?? undefined);
                })(),
                lintCommand: (() => {
                    const c = vscode.workspace.getConfiguration('contextbranch').get<string>('lintCommand');
                    return c ?? (detectLintCommand(root) ?? undefined);
                })(),
                skipVerification: Boolean(study),
                acceptedConflictPaths: manual.paths,
                manualResolvedContents: manualResolved,
                acceptedCascadePaths: manual.acceptedCascadePaths,
            }, cached.preview);
            await this.getDecorations().dismissAllPreviews();
            this.pendingManualMerge = undefined;
            this.pendingMergePreview = undefined;
            if (study)
                study.recordIntegrationCompleted(ws, cached.sourceBranchId, event.id);
            if (ws.activeBranchId === cached.sourceBranchId) {
                await this.handleSwitchBranch(cached.targetBranchId, 'system', 'merge_finalization');
            }
            this.pushState();
            this.postMessage({
                type: 'mergeCompleted',
                event,
                cascadingApplied: manual.acceptedCascadePaths.length,
                conflictsResolved: manual.paths.length,
                resolutionMode: 'manual',
            });
        }
        catch (err: any) {
            this.postMessage({ type: 'error', message: err.message ?? String(err) });
        }
        finally {
            this.mergeInProgress = false;
        }
    }
    private async handleReviseConflictResolution(pathToRevise: string, instruction: string): Promise<void> {
        const ws = this.requireWorkspace();
        const cached = this.pendingMergePreview;
        const provider = this.getProvider();
        if (!ws || !cached)
            return;
        if (!provider) {
            this.postMessage({ type: 'error', message: 'No LLM provider is configured for AI conflict resolution.' });
            return;
        }
        if (!pathToRevise || !instruction?.trim()) {
            this.postMessage({ type: 'error', message: 'Enter a revision request for the AI resolution.' });
            return;
        }
        const nowFingerprint = this.branchStateFingerprintPair(ws, cached.sourceBranchId, cached.targetBranchId);
        if (nowFingerprint !== cached.fingerprint) {
            this.postMessage({ type: 'error', message: 'The merge preview is stale. Preview the merge again before revising the AI resolution.' });
            return;
        }
        const conflict = (cached.preview.verification?.artifactConflicts ?? []).find((c: any) => c.path === pathToRevise);
        if (!conflict) {
            this.postMessage({ type: 'error', message: `No reviewed conflict exists for ${pathToRevise}.` });
            return;
        }
        const source = ws.getBranch(cached.sourceBranchId);
        const target = ws.getBranch(cached.targetBranchId);
        if (!source || !target)
            return;
        const sourceArtifact = ws.getArtifacts(source.id).find(a => a.path === pathToRevise);
        const targetArtifact = ws.getArtifacts(target.id).find(a => a.path === pathToRevise);
        if (!sourceArtifact || !targetArtifact) {
            this.postMessage({ type: 'error', message: `Could not load both branch versions of ${pathToRevise}.` });
            return;
        }
        const study = this.getStudyController();
        if (study) {
            const actionError = study.actionError();
            if (actionError) {
                this.postMessage({ type: 'error', message: actionError });
                return;
            }
            study.recordMergeModelCallStarted(ws, cached.sourceBranchId, cached.targetBranchId, pathToRevise, 'conflict_revision');
        }
        try {
            const previous = (cached.preview.conflictResolutions ?? []).find((r: any) => r.path === pathToRevise);
            let inputTokens = 0;
            let outputTokens = 0;
            const resolution = await new ConflictResolverAgent(provider, (i, o) => {
                inputTokens += i;
                outputTokens += o;
                ws.recordMergeApiUsage(i, o);
            }).resolve({
                path: pathToRevise,
                base: conflict.baseContent ?? sourceArtifact.baseContent ?? '',
                theirs: targetArtifact.content,
                ours: sourceArtifact.content,
                theirContext: ws.getMessages(target.id).slice(-4),
                ourContext: ws.getMessages(source.id).slice(-4),
                revisionInstruction: instruction,
                currentResolution: previous?.resolvedContent,
                model: study?.modelId,
            });
            if (study) {
                study.recordMergeModelUsage(ws, cached.sourceBranchId, cached.targetBranchId, pathToRevise, 'conflict_revision', inputTokens, outputTokens);
            }
            const resolutions = [...(cached.preview.conflictResolutions ?? [])];
            const index = resolutions.findIndex(r => r.path === pathToRevise);
            if (index >= 0)
                resolutions[index] = resolution;
            else
                resolutions.push(resolution);
            cached.preview.conflictResolutions = resolutions;
            cached.preview.synthesisDraft = undefined;
            this.postMessage({ type: 'mergePreview', preview: cached.preview, sourceBranchId: cached.sourceBranchId, targetBranchId: cached.targetBranchId });
        }
        catch (err: any) {
            this.postMessage({ type: 'error', message: `AI revision failed: ${err.message ?? String(err)}` });
        }
    }
    private async handleCancelManualMergeResolution(): Promise<void> {
        await this.getDecorations().dismissAllPreviews();
        this.pendingManualMerge = undefined;
        this.postMessage({ type: 'manualMergeResolutionCancelled' });
    }
    private branchStateFingerprintPair(ws: Workspace, sourceId: string, targetId: string): string {
        const fingerprint = (branchId: string): string => {
            const b = ws.getBranch(branchId);
            if (!b)
                throw new Error(`Branch ${branchId} not found`);
            return Storage.hash(JSON.stringify({
                branchId: b.id,
                status: b.status,
                parentCheckpointId: b.parentCheckpointId,
                activeCheckpointId: b.activeCheckpointId,
                messageIds: b.messageIds,
                artifactIds: b.artifactIds,
            }));
        };
        return Storage.hash(`${fingerprint(sourceId)}|${fingerprint(targetId)}`);
    }
    private async handleMergeBranch(sourceBranchId: string, targetBranchId: string, force: boolean, acceptedCascadePaths?: string[], acceptedConflictPaths?: string[]): Promise<void> {
        if (this.mergeInProgress) {
            this.postMessage({ type: 'error', message: 'A merge is already running.' });
            return;
        }
        const ws = this.requireWorkspace();
        if (!ws)
            return;
        if (this.codingRuns.has(sourceBranchId) || this.codingRuns.has(targetBranchId)) {
            this.postMessage({ type: 'error', message: 'Wait for the source and target generations to finish before merging.' });
            return;
        }
        if (this.pendingEditsByBranch.has(sourceBranchId) || this.pendingEditsByBranch.has(targetBranchId)) {
            this.postMessage({ type: 'error', message: 'Review or discard proposed edits in the source and target before merging.' });
            return;
        }
        const cached = this.pendingMergePreview;
        if (!cached || cached.sourceBranchId !== sourceBranchId || cached.targetBranchId !== targetBranchId) {
            this.postMessage({ type: 'error', message: 'Preview this exact merge before finalizing it.' });
            return;
        }
        const study = this.getStudyController();
        if (study) {
            const actionError = study.actionError();
            if (actionError) {
                this.postMessage({ type: 'error', message: actionError });
                return;
            }
            if (force || !study.allowsMerge(sourceBranchId, targetBranchId, ws)) {
                this.postMessage({ type: 'error', message: 'Study integrations are user-initiated sibling-to-main merges; force merge is disabled.' });
                return;
            }
        }
        this.mergeInProgress = true;
        try {
            const event = await finalizeMerge(ws, {
                sourceBranchId,
                targetBranchId,
                force,
                workspaceRoot: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath,
                testCommand: (() => {
                    const r = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
                    const c = vscode.workspace.getConfiguration('contextbranch').get<string>('testCommand');
                    return c ?? (r ? detectTestCommand(r) ?? undefined : undefined);
                })(),
                lintCommand: (() => {
                    const r = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
                    const c = vscode.workspace.getConfiguration('contextbranch').get<string>('lintCommand');
                    return c ?? (r ? detectLintCommand(r) ?? undefined : undefined);
                })(),
                skipVerification: Boolean(study),
                acceptedCascadePaths,
                acceptedConflictPaths,
            }, cached.preview);
            this.pendingMergePreview = undefined;
            if (study)
                study.recordIntegrationCompleted(ws, sourceBranchId, event.id);
            if (ws.activeBranchId === sourceBranchId) {
                await this.handleSwitchBranch(targetBranchId, 'system', 'merge_finalization');
            }
            this.pushState();
            this.postMessage({
                type: 'mergeCompleted',
                event,
                cascadingApplied: (acceptedCascadePaths ?? []).length,
                conflictsResolved: (acceptedConflictPaths ?? []).length,
            });
        }
        catch (err: any) {
            this.postMessage({ type: 'error', message: err.message ?? String(err) });
        }
        finally {
            this.mergeInProgress = false;
        }
    }
    private async handleUndoMerge(mergeEventId: string): Promise<void> {
        if (this.mergeInProgress) {
            this.postMessage({ type: 'error', message: 'A merge is already running.' });
            return;
        }
        const ws = this.requireWorkspace();
        if (!ws)
            return;
        if (this.getStudyController()) {
            this.postMessage({ type: 'error', message: 'Undoing merges is disabled during prepared study tasks.' });
            return;
        }
        this.mergeInProgress = true;
        try {
            const event = await undoMerge(ws, mergeEventId);
            this.pendingMergePreview = undefined;
            const target = ws.getBranch(event.targetBranchId);
            if (target && ws.activeBranchId !== target.id) {
                await this.handleSwitchBranch(target.id, 'system', 'merge_undo');
            }
            this.pushState();
            this.postMessage({ type: 'mergeUndone', event, message: 'Merge undone. The target was restored to its pre-merge checkpoint and the source branch is active again.' });
        }
        catch (err: any) {
            this.postMessage({ type: 'error', message: err.message ?? String(err) });
        }
        finally {
            this.mergeInProgress = false;
        }
    }
    private async handleDecompose(taskDescription: string): Promise<void> {
        if (this.getStudyController()) {
            this.postMessage({ type: 'error', message: 'Automatic study states are already available for this task.' });
            return;
        }
        const provider = this.getProvider();
        if (!provider) {
            this.postMessage({ type: 'error', message: 'No API key.' });
            return;
        }
        const agent = new DecompositionAgent(provider);
        try {
            const result = await agent.decompose(taskDescription);
            this.postMessage({ type: 'decompositionResult', result });
        }
        catch (err: any) {
            this.postMessage({ type: 'error', message: err.message });
        }
    }
    private async handlePreviewArtifacts(branchId: string): Promise<void> {
        if (this.getStudyController()) {
            this.postMessage({ type: 'error', message: 'Use state switching during a study task; artifact preview is disabled.' });
            return;
        }
        const ws = this.requireWorkspace();
        if (!ws)
            return;
        const branch = ws.getBranch(branchId);
        if (!branch) {
            this.postMessage({ type: 'error', message: 'Branch not found' });
            return;
        }
        const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        if (!root) {
            this.postMessage({ type: 'error', message: 'No workspace folder open' });
            return;
        }
        const artifacts = ws.getArtifacts(branchId);
        const deco = this.getDecorations();
        let changed = 0;
        for (let i = 0; i < artifacts.length; i++) {
            const full = path.join(root, artifacts[i].path);
            const had = await deco.previewChanges(full, artifacts[i].content, { reveal: changed === 0 });
            if (had)
                changed++;
        }
        this.postMessage({
            type: 'artifactsPreviewed',
            branchId,
            filesWithChanges: changed,
            branchName: branch.name,
        });
    }
    private async handleDismissPreview(branchId: string): Promise<void> {
        if (this.getStudyController())
            return;
        const ws = this.requireWorkspace();
        if (!ws)
            return;
        const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        if (!root)
            return;
        const deco = this.getDecorations();
        for (const art of ws.getArtifacts(branchId)) {
            const full = path.join(root, art.path);
            if (deco.hasPreview(full))
                await deco.dismissPreview(full);
        }
        this.postMessage({ type: 'artifactsPreviewDismissed', branchId });
    }
    private async handleApplyArtifacts(branchId: string): Promise<void> {
        if (this.getStudyController()) {
            this.postMessage({ type: 'error', message: 'Use state switching or integration during a study task; direct artifact apply is disabled.' });
            return;
        }
        const ws = this.requireWorkspace();
        if (!ws)
            return;
        const branch = ws.getBranch(branchId);
        if (!branch) {
            this.postMessage({ type: 'error', message: 'Branch not found' });
            return;
        }
        const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        if (!root) {
            this.postMessage({ type: 'error', message: 'No workspace folder open' });
            return;
        }
        const confirm = await vscode.window.showWarningMessage(`Apply artifacts from "${branch.name}" to your workspace? This will overwrite files.`, { modal: true }, 'Apply', 'Cancel');
        if (confirm !== 'Apply')
            return;
        const artifacts = ws.getArtifacts(branchId);
        const allAbs = artifacts.map(a => path.join(root, a.path));
        this.getCapture()?.suppressMany(allAbs, 3000);
        const deco = this.getDecorations();
        let count = 0;
        const written: {
            full: string;
            content: string;
        }[] = [];
        for (const art of artifacts) {
            if (isProtectedPath(art.path))
                continue;
            const full = path.join(root, art.path);
            if (deco.hasPreview(full)) {
                deco.noteSelfWrite(full, 4000);
                const ok = await deco.commitPreview(full);
                if (ok)
                    count++;
                continue;
            }
            deco.snapshotBefore(full);
            deco.noteSelfWrite(full, 4000);
            fs.mkdirSync(path.dirname(full), { recursive: true });
            fs.writeFileSync(full, art.content, 'utf-8');
            written.push({ full, content: art.content });
            count++;
        }
        for (let i = 0; i < written.length; i++) {
            await deco.markChanges(written[i].full, written[i].content, { reveal: i === 0 });
        }
        vscode.window.showInformationMessage(`Applied ${count} file(s) to workspace.`);
    }
    private handleStartStudyTask(): void {
        const ws = this.requireWorkspace();
        const study = this.getStudyController();
        if (!ws || !study)
            return;
        try {
            study.start(ws);
        }
        catch (error: any) {
            this.postMessage({ type: 'error', message: error.message ?? String(error) });
            return;
        }
        this.postMessage({ type: 'studyStarted' });
        this.pushState();
    }
    private async handleRunStudyTests(): Promise<void> {
        const ws = this.requireWorkspace();
        const study = this.getStudyController();
        if (!ws || !study)
            return;
        const denial = study.actionError();
        if (denial) {
            this.postMessage({ type: 'error', message: denial });
            return;
        }
        if (this.studyTestRunningStateId) {
            this.postMessage({ type: 'error', message: 'A study test is already running.' });
            return;
        }
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        if (!workspaceRoot)
            return;
        const selection = study.publicTestSelection(ws);
        const stateId = ws.activeBranchId;
        this.studyTestRunningStateId = stateId;
        this.postMessage({ type: 'studyTestStarted', label: selection.label });
        const item = this.studyTestController.createTestItem(`${study.taskId}:${selection.target}`, `${study.taskId}: ${selection.label}`, vscode.Uri.file(workspaceRoot));
        this.studyTestController.items.replace([item]);
        const request = new vscode.TestRunRequest([item], undefined, undefined, false, false);
        const testRun = this.studyTestController.createTestRun(request, selection.label, true);
        testRun.started(item);
        testRun.appendOutput(`$ ${selection.command}\r\n`, undefined, item);
        const startedAt = Date.now();
        let exitCode: number | null = 0;
        let output = '';
        try {
            const result = await execAsync(selection.command, {
                cwd: workspaceRoot,
                timeout: 90000,
                maxBuffer: 512000,
                env: { ...process.env, CONTEXTBRANCH_STUDY_FORM_ID: study.formId },
            });
            output = `${result.stdout}\n${result.stderr}`.trim();
        }
        catch (error: any) {
            exitCode = typeof error.code === 'number' ? error.code : 1;
            output = `${error.stdout ?? ''}\n${error.stderr ?? error.message ?? String(error)}`.trim();
        }
        const durationMs = Date.now() - startedAt;
        const testOutput = (output || '(No test output.)').replace(/\r?\n/g, '\r\n') + '\r\n';
        testRun.appendOutput(testOutput, undefined, item);
        if (exitCode === 0) {
            testRun.passed(item, durationMs);
        }
        else if (exitCode === 1) {
            testRun.failed(item, new vscode.TestMessage(output || 'Public tests did not pass.'), durationMs);
        }
        else {
            testRun.errored(item, new vscode.TestMessage(output || 'Public tests could not be completed.'), durationMs);
        }
        testRun.end();
        study.recordPublicTest(ws, selection.target, exitCode, output, durationMs);
        this.studyTestRunningStateId = undefined;
        this.postMessage({
            type: 'studyTestResult',
            exitCode,
            durationMs,
            label: selection.label,
        });
        this.pushState();
    }
    private handleOpenStudyIntegration(): void {
        const ws = this.requireWorkspace();
        const study = this.getStudyController();
        if (!ws || !study)
            return;
        const actionError = study.actionError();
        if (actionError) {
            this.postMessage({ type: 'error', message: actionError });
            return;
        }
        if (this.codingRuns.has(ws.activeBranchId)) {
            this.postMessage({ type: 'error', branchId: ws.activeBranchId, message: 'Wait for this state\'s generation to finish before integrating it.' });
            return;
        }
        if (this.pendingEditsByBranch.has(ws.activeBranchId)) {
            this.postMessage({ type: 'error', branchId: ws.activeBranchId, message: 'Review or discard this state\'s proposed edits before integrating it.' });
            return;
        }
        if (!study.allowsMerge(ws.activeBranchId, ws.mainBranchId, ws)) {
            this.postMessage({ type: 'error', message: 'Only the active automatic state can be integrated into main.' });
            return;
        }
        study.recordIntegrationOpened(ws, ws.activeBranchId);
        this.postMessage({
            type: 'openStudyIntegration',
            sourceBranchId: ws.activeBranchId,
            targetBranchId: ws.mainBranchId,
        });
    }
    private handleStudyStateMapOpened(): void {
        const ws = this.requireWorkspace();
        const study = this.getStudyController();
        if (!ws || !study || !study.isContextBranch)
            return;
        this.studyStateMapOpenedAt = Date.now();
        study.recordStateMapOpened(ws);
    }
    private handleStudyStateMapClosed(durationMs: unknown): void {
        const ws = this.requireWorkspace();
        const study = this.getStudyController();
        if (!ws || !study || !study.isContextBranch)
            return;
        const duration = typeof durationMs === 'number' && Number.isFinite(durationMs)
            ? durationMs
            : (this.studyStateMapOpenedAt ? Date.now() - this.studyStateMapOpenedAt : 0);
        study.recordStateMapClosed(ws, duration);
        this.studyStateMapOpenedAt = undefined;
    }
    private handleStudyStateMapNodeInspected(nodeId: unknown, nodeKind: unknown, stateId: unknown): void {
        const ws = this.requireWorkspace();
        const study = this.getStudyController();
        if (!ws || !study || !study.isContextBranch)
            return;
        if (typeof nodeId !== 'string' || typeof nodeKind !== 'string')
            return;
        study.recordStateMapNodeInspected(ws, {
            nodeId,
            nodeKind,
            stateId: typeof stateId === 'string' ? stateId : undefined,
        });
    }
    private async handleFinishStudyTask(): Promise<void> {
        const ws = this.requireWorkspace();
        const study = this.getStudyController();
        if (!ws || !study)
            return;
        if (this.studyTestRunningStateId) {
            this.postMessage({ type: 'error', message: 'Wait for the current state test to finish before finishing the task.' });
            return;
        }
        if (!study.uiState(ws).started) {
            this.postMessage({ type: 'error', message: 'Start the task before finishing it.' });
            return;
        }
        if (this.codingRuns.size > 0) {
            this.postMessage({ type: 'error', message: 'Wait for every running state to finish, or stop them, before finishing the task.' });
            return;
        }
        const activeStateAtFinish = ws.activeBranchId;
        if (ws.activeBranchId !== ws.mainBranchId) {
            const choice = await vscode.window.showWarningMessage('Only the final main state is submitted. Unintegrated work in the current state will not be included.', { modal: true }, 'Finish from main', 'Cancel');
            if (choice !== 'Finish from main')
                return;
            await this.handleSwitchBranch(ws.mainBranchId, 'system', 'finish_task');
        }
        study.finish(ws, activeStateAtFinish);
        this.closeStateMapForCompletion(study, ws, 'task_finished');
        await this.writeStudyArchive(study, ws);
        this.postMessage({ type: 'studyFinished' });
        this.pushState();
    }
    public async checkStudyTimeout(): Promise<void> {
        if (this.finishingTimedOutStudy)
            return;
        const ws = this.getWorkspace();
        const study = this.getStudyController();
        if (!ws || !study)
            return;
        const state = study.uiState(ws);
        if (!state.started || state.finished || state.remainingSeconds > 0)
            return;
        this.finishingTimedOutStudy = true;
        try {
            await this.abortAllCodingRuns();
            const activeStateAtFinish = ws.activeBranchId;
            if (activeStateAtFinish !== ws.mainBranchId) {
                await this.handleSwitchBranch(ws.mainBranchId, 'system', 'timeout_finalization');
            }
            study.finish(ws, activeStateAtFinish);
            this.closeStateMapForCompletion(study, ws, 'task_timeout');
            await this.writeStudyArchive(study, ws);
            this.postMessage({ type: 'studyTimedOut' });
            this.pushState();
        }
        catch (error: any) {
            this.postMessage({ type: 'error', message: `Could not finish the timed task: ${error.message ?? String(error)}` });
        }
        finally {
            this.finishingTimedOutStudy = false;
        }
    }
    private async writeStudyArchive(study: StudyController, ws: Workspace): Promise<void> {
        try {
            const archive = await study.exportFinishedArchive(ws);
            this.postMessage({ type: 'studyArchiveReady', fileName: archive.fileName, filePath: archive.filePath });
            if (archive.created) {
                vscode.window.showInformationMessage(`Study data ZIP saved: ${archive.fileName}`);
            }
        }
        catch (error: any) {
            const message = `Task finished, but the study data ZIP could not be created: ${error.message ?? String(error)}`;
            this.postMessage({ type: 'error', message });
            vscode.window.showErrorMessage(message);
        }
    }
    private closeStateMapForCompletion(study: StudyController, ws: Workspace, reason: string): void {
        if (this.studyStateMapOpenedAt === undefined)
            return;
        study.recordStateMapClosed(ws, Date.now() - this.studyStateMapOpenedAt, 'system', reason);
        this.studyStateMapOpenedAt = undefined;
    }
    private renderHtml(webview: vscode.Webview): string {
        const htmlPath = path.join(this.context.extensionPath, 'webview', 'index.html');
        const cssPath = vscode.Uri.file(path.join(this.context.extensionPath, 'webview', 'style.css'));
        const jsPath = vscode.Uri.file(path.join(this.context.extensionPath, 'webview', 'app.js'));
        const cssUri = webview.asWebviewUri(cssPath);
        const jsUri = webview.asWebviewUri(jsPath);
        const nonce = generateNonce();
        let html = fs.readFileSync(htmlPath, 'utf-8');
        html = html.replace(/\{\{cssUri\}\}/g, cssUri.toString());
        html = html.replace(/\{\{jsUri\}\}/g, jsUri.toString());
        html = html.replace(/\{\{nonce\}\}/g, nonce);
        html = html.replace(/\{\{cspSource\}\}/g, webview.cspSource);
        return html;
    }
}
function generateNonce(): string {
    let text = '';
    const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    for (let i = 0; i < 32; i++) {
        text += possible.charAt(Math.floor(Math.random() * possible.length));
    }
    return text;
}
function readWorkspaceFile(root: string | undefined, p: string): string | null {
    if (!root)
        return null;
    try {
        return fs.readFileSync(path.join(root, p), 'utf-8');
    }
    catch {
        return null;
    }
}
function serializeProposal(f: AppliedFile) {
    const cap = (s?: string) => {
        const arr = (s ?? '').length ? (s as string).split('\n') : [];
        return arr.length > 60 ? { lines: arr.slice(0, 60), more: arr.length - 60 } : { lines: arr, more: 0 };
    };
    return {
        path: f.path,
        isNew: f.isNew,
        failedCount: f.failedCount,
        ops: f.ops.map(o => o.kind === 'create'
            ? { index: o.index, kind: o.kind, ok: o.ok, reason: o.reason,
                del: { lines: [] as string[], more: 0 }, add: cap(o.ok ? f.after : '') }
            : { index: o.index, kind: o.kind, ok: o.ok, reason: o.reason,
                matched: o.matched, del: cap(o.search), add: cap(o.ok ? o.replace : '') }),
    };
}
