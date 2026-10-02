import * as fs from 'fs';
import * as path from 'path';
import * as crypto from 'crypto';
import { Workspace } from '../core/workspace';
import { InterruptionReason } from '../core/types';
import { createStudyArchive, defaultStudyExportDirectory, studyArchiveFileName } from './archive';
import { StudyArchive, StudyFinishedRecord, StudyPublicTestTarget, StudyRunFile, StudyUiState } from './types';
export class StudyController {
    private readonly runPath: string;
    private constructor(private readonly workspaceRoot: string, private run: StudyRunFile) {
        this.runPath = path.join(workspaceRoot, '.study', 'run.json');
    }
    static load(workspaceRoot: string | undefined): StudyController | null {
        if (!workspaceRoot)
            return null;
        const runPath = path.join(workspaceRoot, '.study', 'run.json');
        try {
            const run = JSON.parse(fs.readFileSync(runPath, 'utf-8')) as StudyRunFile;
            if (run.schemaVersion !== 1 || !run.runId || !run.taskId || !run.condition)
                return null;
            return new StudyController(workspaceRoot, run);
        }
        catch {
            return null;
        }
    }
    get condition(): StudyRunFile['condition'] { return this.run.condition; }
    get isContextBranch(): boolean { return this.run.condition === 'contextbranch'; }
    get taskId(): string { return this.run.taskId; }
    get formId(): string { return this.run.formId ?? 'F1'; }
    get participantId(): string { return this.run.participantId; }
    get providerName(): StudyRunFile['model']['provider'] { return this.run.model.provider; }
    get modelId(): string { return this.run.model.id; }
    get publicTestCommand(): string { return this.run.manifest.runner.publicTestCommand; }
    get finalState(): string { return this.run.manifest.submission.finalState; }
    publicTestSelection(ws: Workspace): {
        target: StudyPublicTestTarget;
        label: string;
        command: string;
    } {
        const commands = this.run.manifest.runner.publicTestCommands;
        if (!commands) {
            return { target: 'main', label: 'Run public tests', command: this.publicTestCommand };
        }
        let target: StudyPublicTestTarget = 'main';
        if (this.isContextBranch && ws.activeBranchId !== ws.mainBranchId) {
            const active = ws.getBranch(ws.activeBranchId);
            const siblingIndex = this.run.manifest.contextBranch.siblingStates.findIndex(sibling => active?.tags?.includes(sibling.id));
            if (siblingIndex === 0)
                target = 'responsibilityA';
            if (siblingIndex === 1)
                target = 'responsibilityB';
        }
        const label = target === 'responsibilityA'
            ? 'Test A'
            : target === 'responsibilityB'
                ? 'Test B'
                : 'Test Main';
        return { target, label, command: commands[target] };
    }
    initialize(ws: Workspace): void {
        const initialized = ws.storage.loadTelemetry().some(event => event.type === 'study_initialized' && event.runId === this.run.runId);
        if (initialized)
            return;
        const root = ws.getBranch(ws.mainBranchId);
        if (!root)
            throw new Error('Study workspace has no main state.');
        ws.appendMessage(root.id, 'system', this.rootTaskMessage());
        const siblingIds: string[] = [];
        if (this.isContextBranch) {
            const siblings = this.run.manifest.contextBranch.siblingStates;
            const sharedCheckpoint = ws.createCheckpoint(ws.mainBranchId, 'Study sibling shared fork point');
            for (const [index, sibling] of siblings.entries()) {
                const other = siblings[(index + 1) % siblings.length];
                const branch = ws.createBranch({
                    name: sibling.label,
                    description: `Study branch ticket: ${sibling.label}`,
                    parentBranchId: ws.mainBranchId,
                    inheritMessages: false,
                    checkpointId: sharedCheckpoint.id,
                    tags: ['study-sibling', sibling.id],
                });
                ws.appendMessage(branch.id, 'system', `[study][branch-context] ContextBranch created this isolated state for “${sibling.label}”. ` +
                    `It and “${other.label}” start from the same checkpoint because the feature has two ` +
                    'cooperating implementation responsibilities. This state keeps its own conversation, code candidate, and test evidence while you work.');
                ws.appendMessage(branch.id, 'system', this.branchTicketMessage(sibling));
                ws.storage.appendTelemetry({
                    type: 'study_state_created',
                    actor: 'system',
                    runId: this.run.runId,
                    stateId: branch.id,
                    parentStateId: ws.mainBranchId,
                    stateLabel: sibling.label,
                });
                siblingIds.push(branch.id);
            }
            ws.appendMessage(root.id, 'system', this.mainContextBranchPlanMessage());
        }
        ws.storage.appendTelemetry({
            type: 'study_initialized',
            runId: this.run.runId,
            taskId: this.run.taskId,
            formId: this.formId,
            condition: this.run.condition,
            siblingStateIds: siblingIds,
            taskManifestHash: this.run.manifest.sha256,
        });
    }
    start(ws: Workspace): void {
        if (this.isFinished())
            throw new Error('This task has already been finished.');
        if (this.run.startedAt)
            return;
        this.run.startedAt = new Date().toISOString();
        this.persist();
        ws.storage.appendTelemetry({ type: 'study_started', runId: this.run.runId, taskId: this.run.taskId });
    }
    finish(ws: Workspace, stateBeforeFinalization: string = ws.activeBranchId): StudyFinishedRecord {
        const finishedPath = path.join(this.workspaceRoot, '.study', 'finished.json');
        if (fs.existsSync(finishedPath))
            return this.readFinishedRecord(finishedPath);
        const finishedAt = new Date().toISOString();
        const event: StudyFinishedRecord = {
            schemaVersion: 1,
            runId: this.run.runId,
            taskId: this.run.taskId,
            condition: this.run.condition,
            startedAt: this.run.startedAt,
            finishedAt,
            durationMs: this.run.startedAt ? Math.max(0, Date.parse(finishedAt) - Date.parse(this.run.startedAt)) : 0,
            timedOut: this.isTimedOut(),
            finalState: this.run.manifest.submission.finalState,
            activeStateAtFinish: stateBeforeFinalization,
            modelCallsUsed: this.modelCallsUsed(ws),
            modelTokensUsed: this.modelTokensUsed(ws),
            productionFileHashes: this.productionFileHashes(),
        };
        fs.writeFileSync(finishedPath, JSON.stringify(event, null, 2) + '\n', 'utf-8');
        ws.storage.appendTelemetry({ type: 'study_finished', ...event });
        return event;
    }
    async exportFinishedArchive(ws: Workspace): Promise<StudyArchive> {
        const finished = this.readFinishedRecord(path.join(this.workspaceRoot, '.study', 'finished.json'));
        this.verifyFinalProductionFiles(finished);
        const exportDirectory = this.run.exportDirectory || defaultStudyExportDirectory(this.workspaceRoot);
        const fileName = studyArchiveFileName(this.run);
        const archivePath = path.join(exportDirectory, fileName);
        if (!fs.existsSync(archivePath)) {
            ws.storage.appendTelemetry({
                type: 'study_archive_prepared',
                actor: 'system',
                runId: this.run.runId,
                fileName,
            });
        }
        const archive = await createStudyArchive(this.workspaceRoot, this.run, finished);
        if (archive.created) {
            ws.storage.appendTelemetry({
                type: 'study_archive_created',
                actor: 'system',
                runId: this.run.runId,
                fileName: archive.fileName,
            });
        }
        return archive;
    }
    actionError(): string | null {
        if (this.isFinished())
            return 'This task has already been finished.';
        if (!this.run.startedAt)
            return 'Click Start task before using the assistant or test runner.';
        if (this.isTimedOut())
            return 'The task time limit has ended. Finish task to submit the main state.';
        return null;
    }
    beginModelCall(ws: Workspace, stateId: string = ws.activeBranchId): string | null {
        const actionError = this.actionError();
        if (actionError)
            return actionError;
        ws.storage.appendTelemetry({ type: 'study_model_call_started', runId: this.run.runId, stateId });
        return null;
    }
    recordModelUsage(ws: Workspace, inputTokens: number, outputTokens: number, model: string, stateId: string = ws.activeBranchId, details?: {
        interruptionReason?: InterruptionReason;
        observedOutputChars?: number;
    }): void {
        ws.storage.appendTelemetry({
            type: 'study_model_call_completed',
            runId: this.run.runId,
            stateId,
            provider: this.providerName,
            model,
            inputTokens,
            outputTokens,
            interruptionReason: details?.interruptionReason,
            observedOutputChars: details?.observedOutputChars,
        });
    }
    recordEditRetry(ws: Workspace, stateId: string, failureCount: number): void {
        ws.storage.appendTelemetry({
            type: 'study_edit_retry_started',
            actor: 'participant',
            runId: this.run.runId,
            stateId,
            retryCount: 1,
            failureCount,
        });
    }
    recordMergeModelCallStarted(ws: Workspace, sourceStateId: string, targetStateId: string, path: string, purpose: 'conflict_resolution' | 'conflict_revision'): void {
        ws.storage.appendTelemetry({
            type: 'study_merge_model_call_started',
            actor: 'participant',
            runId: this.run.runId,
            sourceStateId,
            targetStateId,
            path,
            purpose,
            provider: this.providerName,
            model: this.modelId,
        });
    }
    recordMergeModelUsage(ws: Workspace, sourceStateId: string, targetStateId: string, path: string, purpose: 'conflict_resolution' | 'conflict_revision', inputTokens: number, outputTokens: number): void {
        ws.storage.appendTelemetry({
            type: 'study_merge_model_call_completed',
            actor: 'system',
            runId: this.run.runId,
            sourceStateId,
            targetStateId,
            path,
            purpose,
            provider: this.providerName,
            model: this.modelId,
            inputTokens,
            outputTokens,
        });
    }
    recordPublicTest(ws: Workspace, target: StudyPublicTestTarget, exitCode: number | null, output: string, durationMs: number): void {
        ws.storage.appendTelemetry({
            type: 'study_public_test_run',
            actor: 'participant',
            runId: this.run.runId,
            stateId: ws.activeBranchId,
            target,
            exitCode,
            durationMs,
            output,
        });
    }
    recordStateMapOpened(ws: Workspace): void {
        ws.storage.appendTelemetry({ type: 'study_state_map_opened', actor: 'participant', runId: this.run.runId });
    }
    recordStateMapClosed(ws: Workspace, durationMs: number, actor: 'participant' | 'system' = 'participant', reason: string = 'participant_closed'): void {
        ws.storage.appendTelemetry({
            type: 'study_state_map_closed', actor, reason, runId: this.run.runId,
            durationMs: Math.max(0, durationMs),
        });
    }
    recordStateMapNodeInspected(ws: Workspace, node: {
        nodeId: string;
        nodeKind: string;
        stateId?: string;
    }): void {
        ws.storage.appendTelemetry({
            type: 'study_state_map_node_inspected', actor: 'participant', runId: this.run.runId,
            ...node,
        });
    }
    recordStateSwitch(ws: Workspace, fromStateId: string, toStateId: string, actor: 'participant' | 'system', reason: string): void {
        ws.storage.appendTelemetry({
            type: 'study_state_switched', actor, runId: this.run.runId,
            fromStateId, toStateId, reason,
        });
    }
    recordIntegrationOpened(ws: Workspace, sourceStateId: string): void {
        ws.storage.appendTelemetry({
            type: 'study_integration_opened', actor: 'participant', runId: this.run.runId,
            sourceStateId, targetStateId: ws.mainBranchId,
        });
    }
    recordIntegrationCompleted(ws: Workspace, sourceStateId: string, eventId: string): void {
        ws.storage.appendTelemetry({
            type: 'study_integration_completed', actor: 'participant', runId: this.run.runId,
            sourceStateId, targetStateId: ws.mainBranchId, eventId,
        });
    }
    allowsMerge(sourceBranchId: string, targetBranchId: string, ws: Workspace): boolean {
        if (!this.isContextBranch || targetBranchId !== ws.mainBranchId)
            return false;
        const source = ws.getBranch(sourceBranchId);
        return source?.status === 'active' && source.tags?.includes('study-sibling') === true;
    }
    uiState(ws: Workspace): StudyUiState {
        const elapsed = this.elapsedSeconds();
        const remaining = this.run.startedAt
            ? Math.max(0, this.run.timeLimitSeconds - elapsed)
            : this.run.timeLimitSeconds;
        const siblings = ws.getAllBranches()
            .filter(branch => branch.tags?.includes('study-sibling'))
            .map(branch => branch.id);
        return {
            active: true,
            runId: this.run.runId,
            taskTitle: this.run.manifest.ticket.summary,
            condition: this.run.condition,
            started: Boolean(this.run.startedAt),
            finished: this.isFinished(),
            timeLimitSeconds: this.run.timeLimitSeconds,
            remainingSeconds: remaining,
            modelCallsUsed: this.modelCallsUsed(ws),
            modelTokensUsed: this.modelTokensUsed(ws),
            publicTestLabel: this.publicTestSelection(ws).label,
            siblingStateIds: siblings,
        };
    }
    private rootTaskMessage(): string {
        const ticket = this.run.manifest.ticket;
        if (ticket.mainMarkdown)
            return `[study][main-ticket]\n\n${ticket.mainMarkdown}`;
        const requirements = ticket.requirements.map(item => `- ${item}`).join('\n');
        return `[study][main-ticket] ${ticket.summary}\n\nRequirements:\n${requirements}\n\nUse this total feature ticket and the public tests as the working specification. Submit the final feature from main.`;
    }
    private mainContextBranchPlanMessage(): string {
        const labels = this.run.manifest.contextBranch.siblingStates.map(state => `“${state.label}”`).join(' and ');
        return `[study][main-plan] ContextBranch created two optional sibling states: ${labels}. Each starts from the same checkpoint and keeps its own focused conversation, code candidate, and test evidence.\n\nYou may use either state, both states, neither state, or work directly in main. There is no required order. Integrate a state into main only when it is useful, after reviewing the merge preview.\n\nFinal check: ${this.run.manifest.contextBranch.finalVerification}`;
    }
    private branchTicketMessage(sibling: StudyRunFile['manifest']['contextBranch']['siblingStates'][number]): string {
        const requirements = sibling.ticket.requirements.map(item => `- ${item}`).join('\n');
        return `[study][branch-ticket] ${sibling.label}\n\nFocus in this state:\n${requirements}\n\nThis state is optional. You may switch states, continue in main, or integrate this state into main after reviewing the merge preview. The final submission is always main.`;
    }
    private elapsedSeconds(): number {
        if (!this.run.startedAt)
            return 0;
        return Math.floor((Date.now() - Date.parse(this.run.startedAt)) / 1000);
    }
    private isTimedOut(): boolean {
        return Boolean(this.run.startedAt) && this.elapsedSeconds() >= this.run.timeLimitSeconds;
    }
    isFinished(): boolean {
        return fs.existsSync(path.join(this.workspaceRoot, '.study', 'finished.json'));
    }
    private readFinishedRecord(finishedPath: string): StudyFinishedRecord {
        const parsed = JSON.parse(fs.readFileSync(finishedPath, 'utf-8')) as Partial<StudyFinishedRecord>;
        const startedAt = parsed.startedAt ?? this.run.startedAt;
        const durationMs = typeof parsed.durationMs === 'number'
            ? parsed.durationMs
            : (startedAt && parsed.finishedAt ? Math.max(0, Date.parse(parsed.finishedAt) - Date.parse(startedAt)) : 0);
        const record: StudyFinishedRecord = {
            ...(parsed as StudyFinishedRecord),
            startedAt,
            durationMs,
        };
        if (parsed.startedAt !== startedAt || parsed.durationMs !== durationMs) {
            fs.writeFileSync(finishedPath, JSON.stringify(record, null, 2) + '\n', 'utf-8');
        }
        return record;
    }
    private verifyFinalProductionFiles(finished: StudyFinishedRecord): void {
        for (const relativePath of this.run.manifest.submission.allowedProductionPaths) {
            const file = path.join(this.workspaceRoot, relativePath);
            const expectedHash = finished.productionFileHashes[relativePath];
            const stat = fs.existsSync(file) ? fs.lstatSync(file) : null;
            if (!stat?.isFile() || stat.isSymbolicLink()) {
                throw new Error(`Final main state is not a regular file: ${relativePath}`);
            }
            const actualHash = crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
            if (!expectedHash || actualHash !== expectedHash) {
                throw new Error(`Final main state changed after Finish task: ${relativePath}`);
            }
        }
    }
    private modelCallsUsed(ws: Workspace): number {
        return ws.storage.loadTelemetry().filter(event => event.type === 'study_model_call_started' && event.runId === this.run.runId).length;
    }
    private modelTokensUsed(ws: Workspace): number {
        return ws.storage.loadTelemetry()
            .filter(event => event.type === 'study_model_call_completed' && event.runId === this.run.runId)
            .reduce((total, event) => total + Number(event.inputTokens ?? 0) + Number(event.outputTokens ?? 0), 0);
    }
    private productionFileHashes(): Record<string, string> {
        const hashes: Record<string, string> = {};
        for (const relativePath of this.run.manifest.submission.allowedProductionPaths) {
            const file = path.join(this.workspaceRoot, relativePath);
            const stat = fs.existsSync(file) ? fs.lstatSync(file) : null;
            if (!stat?.isFile() || stat.isSymbolicLink()) {
                throw new Error(`Required production file is missing or unsafe at finish: ${relativePath}`);
            }
            hashes[relativePath] = crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
        }
        return hashes;
    }
    private persist(): void {
        fs.writeFileSync(this.runPath, JSON.stringify(this.run, null, 2) + '\n', 'utf-8');
    }
}
