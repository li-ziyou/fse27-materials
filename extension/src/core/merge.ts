import { exec } from 'child_process';
import { promisify } from 'util';
import * as path from 'path';
import * as fs from 'fs';
import * as os from 'os';
import { Workspace } from './workspace';
import { Storage } from './storage';
import { Branch, Artifact, MergeEvent, VerificationResult, ArtifactConflict, Message } from './types';
import { CascadingEditProposal } from '../agents/merge-analyst';
import { ConflictResolution } from '../agents/conflict-resolver';
import { merge3, looksElided } from './edits';
const execAsync = promisify(exec);
export interface ConsistencyEvidence {
    path: string;
    status: 'add' | 'modify' | 'conflict';
    before: string;
    after: string;
}
export interface MergeOptions {
    sourceBranchId: string;
    targetBranchId: string;
    generateSynthesis?: boolean;
    force?: boolean;
    skipVerification?: boolean;
    taskId?: string;
    workspaceRoot?: string;
    testCommand?: string;
    lintCommand?: string;
    consolidate?: (branch: Branch, messages: Message[], changedFiles: {
        path: string;
        status: string;
        before: string;
        after: string;
    }[], targetBranch: Branch) => Promise<string>;
    rebaseCheck?: (source: Branch, target: Branch, sourceMessages: Message[], targetMessages: Message[]) => Promise<string[]>;
    consistencyCheck?: (target: Branch, mergedMessages: Message[], evidence: ConsistencyEvidence[]) => Promise<string[]>;
    analyzeCascade?: (source: Branch, target: Branch, sourceArtifacts: Artifact[], targetArtifacts: Artifact[], changedFiles: {
        path: string;
        before: string;
        after: string;
        status: 'add' | 'modify' | 'conflict';
    }[], recentMessages: Message[]) => Promise<{
        summary: string;
        proposals: CascadingEditProposal[];
        error?: string;
    }>;
    acceptedCascadePaths?: string[];
    resolveConflict?: (opts: {
        path: string;
        base: string;
        theirs: string;
        ours: string;
        theirContext: Message[];
        ourContext: Message[];
    }) => Promise<ConflictResolution>;
    acceptedConflictPaths?: string[];
    manualResolvedContents?: Record<string, string>;
}
export interface MergePreview {
    mergeEventId: string;
    verification: VerificationResult;
    artifactChanges: {
        path: string;
        status: 'add' | 'modify' | 'conflict';
    }[];
    rebaseNotes: string[];
    synthesisDraft?: string;
    cascadingProposals?: CascadingEditProposal[];
    cascadingSummary?: string;
    conflictResolutions?: ConflictResolution[];
    stateFingerprint: string;
    targetHeadFingerprint: string;
}
export function branchStateFingerprint(ws: Workspace, branchId: string): string {
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
}
function mergeStateFingerprint(ws: Workspace, sourceId: string, targetId: string): string {
    return Storage.hash(`${branchStateFingerprint(ws, sourceId)}|${branchStateFingerprint(ws, targetId)}`);
}
export async function previewMerge(ws: Workspace, opts: MergeOptions): Promise<MergePreview> {
    const source = ws.getBranch(opts.sourceBranchId);
    const target = ws.getBranch(opts.targetBranchId);
    if (!source)
        throw new Error(`Source branch ${opts.sourceBranchId} not found`);
    if (!target)
        throw new Error(`Target branch ${opts.targetBranchId} not found`);
    if (source.status === 'merged')
        throw new Error('Source already merged');
    const sourceMessages = ws.getMessages(source.id);
    const targetMessages = ws.getMessages(target.id);
    const rebaseNotes: string[] = [];
    if (source.parentCheckpointId) {
        const cp = ws.storage.loadCheckpoint(source.parentCheckpointId);
        if (cp) {
            const delta = target.messageIds.length - cp.messageIds.length;
            if (delta !== 0) {
                rebaseNotes.push(delta > 0
                    ? `Target branch has ${delta} additional messages since this branch's fork point.`
                    : `Target branch is ${Math.abs(delta)} messages behind this branch's fork point.`);
            }
            if (opts.rebaseCheck && delta !== 0) {
                try {
                    const aiNotes = await opts.rebaseCheck(source, target, sourceMessages, targetMessages);
                    rebaseNotes.push(...aiNotes);
                }
                catch (err: any) {
                    rebaseNotes.push(`Rebase check skipped (error): ${err.message}`);
                }
            }
        }
    }
    const { changes, conflicts } = computeArtifactDiff(ws, source, target);
    const consistencyEvidence: ConsistencyEvidence[] = changes.map(change => {
        const targetArtifact = ws.getArtifacts(target.id).find(a => a.path === change.path);
        return {
            path: change.path,
            status: change.status,
            before: targetArtifact?.content ?? '',
            after: mergedContentFor(ws, source, target, change),
        };
    });
    let verification: VerificationResult;
    if (opts.skipVerification) {
        verification = {
            status: 'skipped', ranAt: Date.now(), forced: false,
            artifactConflicts: conflicts,
        };
    }
    else {
        verification = await runVerification({
            ws, source, target, mergedMessages: [...targetMessages, ...sourceMessages],
            conflicts,
            workspaceRoot: opts.workspaceRoot,
            testCommand: opts.testCommand,
            lintCommand: opts.lintCommand,
            consistencyCheck: opts.consistencyCheck,
            consistencyEvidence,
        });
    }
    let cascadingProposals: CascadingEditProposal[] | undefined;
    let cascadingSummary: string | undefined;
    if (opts.analyzeCascade) {
        try {
            const sourceArtifacts = ws.getArtifacts(source.id);
            const targetArtifacts = ws.getArtifacts(target.id);
            const targetByPath = new Map(targetArtifacts.map(a => [a.path, a]));
            const changedFiles = changes.map(c => {
                const ta = targetByPath.get(c.path);
                const sa = sourceArtifacts.find(a => a.path === c.path);
                return {
                    path: c.path,
                    before: ta?.content ?? '',
                    after: sa?.content ?? '',
                    status: c.status,
                };
            });
            const recentMessages = sourceMessages.slice(-4);
            const analystResult = await opts.analyzeCascade(source, target, sourceArtifacts, targetArtifacts, changedFiles, recentMessages);
            cascadingProposals = analystResult.proposals;
            cascadingSummary = analystResult.error
                ? `Analyst error: ${analystResult.error}`
                : analystResult.summary;
        }
        catch (err: any) {
            cascadingSummary = `Cascade analysis failed: ${err.message ?? err}`;
        }
    }
    let conflictResolutions: ConflictResolution[] | undefined;
    if (opts.resolveConflict) {
        const conflictPaths = changes.filter(c => c.status === 'conflict').map(c => c.path);
        if (conflictPaths.length > 0) {
            conflictResolutions = [];
            const targetMessagesForCtx = ws.getMessages(target.id);
            const sourceArtifacts = ws.getArtifacts(source.id);
            const targetArtifacts = ws.getArtifacts(target.id);
            for (const cp of conflictPaths) {
                const sa = sourceArtifacts.find(a => a.path === cp);
                const ta = targetArtifacts.find(a => a.path === cp);
                if (!sa || !ta)
                    continue;
                try {
                    const resolution = await opts.resolveConflict({
                        path: cp,
                        base: forkBaseContent(ws, source, cp) ?? sa.baseContent ?? '',
                        theirs: ta.content,
                        ours: sa.content,
                        theirContext: targetMessagesForCtx.slice(-4),
                        ourContext: sourceMessages.slice(-4),
                    });
                    conflictResolutions.push(resolution);
                }
                catch (err: any) {
                    const base = forkBaseContent(ws, source, cp) ?? sa.baseContent ?? '';
                    const merged = merge3(base, ta.content, sa.content, { ours: 'target', theirs: 'source' });
                    conflictResolutions.push({
                        path: cp,
                        resolvedContent: merged.text,
                        rationale: '',
                        confidence: 'low',
                        originalContent: ta.content,
                        error: err.message ?? String(err),
                    });
                }
            }
        }
    }
    let synthesisDraft: string | undefined;
    if (opts.generateSynthesis && opts.consolidate) {
        try {
            const tgtArts = ws.getArtifacts(target.id);
            const tgtByPath = new Map(tgtArts.map(a => [a.path, a.content]));
            const resByPath = new Map((conflictResolutions ?? []).map(r => [r.path, r.resolvedContent]));
            const changedFiles = changes.map(c => ({
                path: c.path,
                status: c.status,
                before: tgtByPath.get(c.path) ?? '',
                after: (c.status === 'conflict' && resByPath.has(c.path))
                    ? resByPath.get(c.path)!
                    : mergedContentFor(ws, source, target, c),
            }));
            synthesisDraft = await opts.consolidate(source, sourceMessages, changedFiles, target);
        }
        catch (err: any) {
            synthesisDraft = `(Synthesis unavailable: ${err.message})`;
        }
    }
    const mergeEventId = `me_${Storage.hash(`${source.id}->${target.id}|${Date.now()}`)}`;
    return {
        mergeEventId,
        verification,
        artifactChanges: changes,
        rebaseNotes,
        synthesisDraft,
        cascadingProposals,
        cascadingSummary,
        conflictResolutions,
        stateFingerprint: mergeStateFingerprint(ws, source.id, target.id),
        targetHeadFingerprint: branchStateFingerprint(ws, target.id),
    };
}
export async function finalizeMerge(ws: Workspace, opts: MergeOptions, preview: MergePreview): Promise<MergeEvent> {
    const source = ws.getBranch(opts.sourceBranchId);
    const target = ws.getBranch(opts.targetBranchId);
    if (!source || !target)
        throw new Error('Merge branch no longer exists');
    if (source.status === 'merged')
        throw new Error('Source already merged');
    const nowFingerprint = mergeStateFingerprint(ws, source.id, target.id);
    if (nowFingerprint !== preview.stateFingerprint) {
        throw new Error('Merge preview is stale because the source or target branch changed after preview. Preview the merge again before finalizing.');
    }
    const acceptedConflicts = new Set(opts.acceptedConflictPaths ?? []);
    const manualResolved = opts.manualResolvedContents ?? {};
    const acceptedCascades = new Set(opts.acceptedCascadePaths ?? []);
    const conflicts = preview.verification.artifactConflicts ?? [];
    const unresolved = conflicts.filter(c => !acceptedConflicts.has(c.path));
    if (unresolved.length > 0) {
        throw new Error(`Merge blocked: ${unresolved.length} unresolved file conflict${unresolved.length === 1 ? '' : 's'} remain. Resolve or explicitly reject them before merging.`);
    }
    const resolutionByPath = new Map((preview.conflictResolutions ?? []).map(r => [r.path, r]));
    const conflictPaths = new Set(conflicts.map(c => c.path));
    for (const p of acceptedConflicts) {
        if (!conflictPaths.has(p)) {
            throw new Error(`Merge blocked: ${p} is not one of the conflicts in the reviewed preview.`);
        }
        if (Object.prototype.hasOwnProperty.call(manualResolved, p)) {
            const content = manualResolved[p];
            if (/<{7}|>{7}|^={7}$/m.test(content)) {
                throw new Error(`Merge blocked: ${p} still contains unresolved conflict markers. Resolve all incoming/current sections in the editor first.`);
            }
            continue;
        }
        const resolution = resolutionByPath.get(p);
        if (!resolution || resolution.path !== p || /<{5,}|>{5,}/.test(resolution.resolvedContent) || looksElided(resolution.resolvedContent, resolution.originalContent)) {
            throw new Error(`Merge blocked: accepted conflict resolution for ${p} is missing or unsafe.`);
        }
    }
    for (const p of Object.keys(manualResolved)) {
        if (!conflictPaths.has(p)) {
            throw new Error(`Merge blocked: manual resolution for ${p} is not part of the reviewed conflict set.`);
        }
        if (!acceptedConflicts.has(p)) {
            throw new Error(`Merge blocked: manual resolution for ${p} was supplied without accepting that conflict.`);
        }
    }
    const cascadeByPath = new Map((preview.cascadingProposals ?? []).map(p => [p.path, p]));
    for (const p of acceptedCascades) {
        const proposal = cascadeByPath.get(p);
        if (!proposal)
            throw new Error(`Merge blocked: cascade proposal for ${p} is not part of the reviewed preview.`);
        const currentTarget = ws.getArtifacts(target.id).find(a => a.path === p)?.content ?? '';
        if (currentTarget !== proposal.currentContent) {
            throw new Error(`Merge blocked: cascade proposal for ${p} is stale because that target file changed after preview.`);
        }
        if (/<{5,}|>{5,}/.test(proposal.proposedContent) || /\.\.\.\s*(rest|existing|unchanged)/i.test(proposal.proposedContent)) {
            throw new Error(`Merge blocked: cascade proposal for ${p} contains unsafe placeholder/conflict content.`);
        }
    }
    const candidate = buildCandidateFiles(ws, source, target, preview, acceptedConflicts, acceptedCascades, manualResolved);
    let candidateVerification: VerificationResult = {
        status: 'skipped', ranAt: Date.now(), forced: false,
        artifactConflicts: [],
    };
    if (!opts.skipVerification) {
        candidateVerification = await runCandidateVerification({
            workspaceRoot: opts.workspaceRoot,
            testCommand: opts.testCommand,
            lintCommand: opts.lintCommand,
            candidate,
        });
        if (candidateVerification.status === 'fail' && !opts.force) {
            throw new Error('Merge blocked: tests failed against the exact candidate merge. Fix the candidate or explicitly force a test failure (file conflicts can never be forced).');
        }
    }
    const targetSnapshot = ws.createCheckpoint(target.id, `Pre-merge of ${source.name}`);
    applyArtifactChanges(ws, source, target, preview, opts.acceptedConflictPaths, manualResolved);
    let cascadingAppliedCount = 0;
    for (const p of acceptedCascades) {
        const proposal = cascadeByPath.get(p)!;
        ws.upsertArtifact(target.id, proposal.path, proposal.proposedContent, proposal.currentContent, 'merge');
        cascadingAppliedCount++;
    }
    let synthesisMessageId: string | undefined;
    if (preview.synthesisDraft) {
        const synth = ws.appendMessage(target.id, 'system', `[merge] ${source.name} → ${target.name}\n\n${preview.synthesisDraft}`, { model: 'merge-synthesis' });
        synthesisMessageId = synth.id;
    }
    else {
        const sourceMessages = ws.getMessages(source.id);
        const baseSize = source.forkedAtMessageCount;
        const newMessages = sourceMessages.slice(baseSize);
        for (const m of newMessages)
            ws.appendMessage(target.id, m.role, m.content, m.meta);
    }
    const postMergeCheckpoint = ws.createCheckpoint(target.id, `Post-merge of ${source.name}`);
    const previousSourceStatus = source.status;
    source.status = 'merged';
    source.mergedIntoBranchId = target.id;
    source.mergedAt = Date.now();
    source.mergedAsCheckpointId = postMergeCheckpoint.id;
    ws.storage.saveBranch(source);
    const verification = {
        ...candidateVerification,
        artifactConflicts: preview.verification.artifactConflicts,
        forced: !!opts.force && candidateVerification.status === 'fail',
    };
    const event: MergeEvent = {
        id: preview.mergeEventId,
        sourceBranchId: source.id,
        targetBranchId: target.id,
        taskId: opts.taskId,
        startedAt: preview.verification.ranAt,
        completedAt: Date.now(),
        verification,
        targetSnapshotCheckpointId: targetSnapshot.id,
        postMergeCheckpointId: postMergeCheckpoint.id,
        sourcePreviousStatus: previousSourceStatus,
        synthesisMessageId,
        rebaseNotes: preview.rebaseNotes,
    };
    ws.storage.saveMergeEvent(event);
    ws.workspaceState.mergeEventIds.push(event.id);
    ws.storage.saveWorkspace(ws.workspaceState);
    ws.storage.appendTelemetry({
        type: 'merge_finalized',
        eventId: event.id,
        sourceBranchId: source.id, targetBranchId: target.id,
        verificationStatus: verification.status,
        forced: event.verification.forced,
        cascadingProposalsTotal: preview.cascadingProposals?.length ?? 0,
        cascadingProposalsAccepted: cascadingAppliedCount,
    });
    return event;
}
function buildCandidateFiles(ws: Workspace, source: Branch, target: Branch, preview: MergePreview, acceptedConflicts: Set<string>, acceptedCascades: Set<string>, manualResolved: Record<string, string> = {}): Map<string, string> {
    const out = new Map<string, string>();
    for (const a of ws.getArtifacts(target.id))
        out.set(a.path, a.content);
    const resolutionByPath = new Map((preview.conflictResolutions ?? []).map(r => [r.path, r]));
    for (const change of preview.artifactChanges) {
        const sa = ws.getArtifacts(source.id).find(a => a.path === change.path);
        if (!sa || sa.mergeIntent === 'discard')
            continue;
        const ta = ws.getArtifacts(target.id).find(a => a.path === change.path);
        if (change.status === 'add' || !ta)
            out.set(change.path, sa.content);
        else if (change.status === 'modify')
            out.set(change.path, mergedContentFor(ws, source, target, change));
        else if (acceptedConflicts.has(change.path)) {
            if (Object.prototype.hasOwnProperty.call(manualResolved, change.path)) {
                out.set(change.path, manualResolved[change.path]);
            }
            else {
                out.set(change.path, resolutionByPath.get(change.path)!.resolvedContent);
            }
        }
    }
    for (const p of acceptedCascades) {
        const proposal = (preview.cascadingProposals ?? []).find(x => x.path === p);
        if (proposal)
            out.set(p, proposal.proposedContent);
    }
    return out;
}
interface CandidateVerificationInput {
    workspaceRoot?: string;
    testCommand?: string;
    lintCommand?: string;
    candidate: Map<string, string>;
}
async function runCandidateVerification(input: CandidateVerificationInput): Promise<VerificationResult> {
    const result: VerificationResult = { status: 'skipped', ranAt: Date.now(), forced: false, artifactConflicts: [] };
    let ranVerification = false;
    if (!input.workspaceRoot) {
        result.status = 'skipped';
        return result;
    }
    const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'contextbranch-merge-'));
    try {
        fs.cpSync(input.workspaceRoot, temp, {
            recursive: true,
            force: true,
            filter: (src) => {
                const rel = path.relative(input.workspaceRoot!, src);
                if (!rel)
                    return true;
                const first = rel.split(path.sep)[0];
                return first !== '.git' && first !== '.contextbranch' && first !== '.study' && first !== 'node_modules';
            },
        });
        const nodeModules = path.join(input.workspaceRoot, 'node_modules');
        if (fs.existsSync(nodeModules)) {
            try {
                fs.symlinkSync(nodeModules, path.join(temp, 'node_modules'), 'junction');
            }
            catch { }
        }
        for (const [rel, content] of input.candidate) {
            const full = path.join(temp, rel);
            const safe = path.relative(temp, full);
            if (safe.startsWith('..') || path.isAbsolute(safe))
                throw new Error(`Unsafe candidate path: ${rel}`);
            fs.mkdirSync(path.dirname(full), { recursive: true });
            fs.writeFileSync(full, content, 'utf8');
        }
        const run = async (command: string, label: 'test' | 'lint') => {
            try {
                const { stdout, stderr } = await execAsync(command, { cwd: temp, timeout: 90000, maxBuffer: 1000000 });
                const text = `${stdout}\n${stderr}`.trim();
                if (label === 'test') {
                    result.testOutput = text;
                    ranVerification = true;
                }
                else {
                    result.lintOutput = text;
                    ranVerification = true;
                }
            }
            catch (err: any) {
                const detail = `${err.message ?? ''}\n${err.stderr ?? ''}`;
                const missing = err.code === 127 || err.code === 'ENOENT' || /command not found|ENOENT|no such file/i.test(detail);
                const text = missing
                    ? `SKIPPED: ${command} is not available in the candidate workspace.`
                    : `FAIL: ${err.message}\n${err.stdout ?? ''}\n${err.stderr ?? ''}`;
                if (label === 'test') {
                    result.testOutput = text;
                    if (!missing)
                        result.status = 'fail';
                }
                else {
                    result.lintOutput = text;
                }
            }
        };
        if (input.testCommand)
            await run(input.testCommand, 'test');
        if (input.lintCommand)
            await run(input.lintCommand, 'lint');
        if (ranVerification && result.status !== 'fail')
            result.status = 'pass';
        else if (!ranVerification && result.status !== 'fail')
            result.status = 'skipped';
    }
    catch (err: any) {
        result.status = 'fail';
        result.testOutput = `FAIL: candidate verification setup failed: ${err.message ?? String(err)}`;
    }
    finally {
        try {
            fs.rmSync(temp, { recursive: true, force: true });
        }
        catch { }
    }
    return result;
}
export async function undoMerge(ws: Workspace, mergeEventId: string): Promise<MergeEvent> {
    const event = ws.storage.loadMergeEvent(mergeEventId);
    if (!event)
        throw new Error(`Merge event ${mergeEventId} not found`);
    if (event.undoneAt)
        throw new Error('This merge has already been undone.');
    const target = ws.getBranch(event.targetBranchId);
    const source = ws.getBranch(event.sourceBranchId);
    if (!target || !source)
        throw new Error('Merge branches no longer exist.');
    if (!event.postMergeCheckpointId)
        throw new Error('This merge predates safe undo metadata and cannot be automatically undone.');
    const post = ws.storage.loadCheckpoint(event.postMergeCheckpointId);
    const pre = ws.storage.loadCheckpoint(event.targetSnapshotCheckpointId);
    if (!post || !pre)
        throw new Error('Merge checkpoints are missing; automatic undo is unsafe.');
    if (!branchMatchesCheckpoint(target, post)) {
        throw new Error('Cannot undo this merge safely: the target branch has changed since the merge. Create a checkpoint or revert those later changes first.');
    }
    ws.restoreCheckpoint(target.id, pre.id);
    const undoCheckpoint = ws.createCheckpoint(target.id, `Undo merge of ${source.name}`);
    source.status = event.sourcePreviousStatus ?? 'active';
    source.mergedIntoBranchId = undefined;
    source.mergedAt = undefined;
    source.mergedAsCheckpointId = undefined;
    ws.storage.saveBranch(source);
    event.undoneAt = Date.now();
    event.undoTargetCheckpointId = undoCheckpoint.id;
    event.undoSourceBranchStatus = source.status;
    ws.storage.saveMergeEvent(event);
    ws.storage.appendTelemetry({ type: 'merge_undone', eventId: event.id, sourceBranchId: source.id, targetBranchId: target.id });
    return event;
}
function branchMatchesCheckpoint(branch: Branch, cp: {
    messageIds: string[];
    artifactIds: string[];
}): boolean {
    return JSON.stringify(branch.messageIds) === JSON.stringify(cp.messageIds) &&
        JSON.stringify(branch.artifactIds) === JSON.stringify(cp.artifactIds);
}
function forkBaseContent(ws: Workspace, source: Branch, path: string): string | null {
    if (!source.parentCheckpointId)
        return null;
    const cp = ws.storage.loadCheckpoint(source.parentCheckpointId);
    if (!cp)
        return null;
    for (const aid of cp.artifactIds) {
        const a = ws.storage.loadArtifact(aid);
        if (a && a.path === path)
            return a.content;
    }
    return null;
}
function mergedContentFor(ws: Workspace, source: Branch, target: Branch, change: {
    path: string;
    status: 'add' | 'modify' | 'conflict';
}): string {
    const sa = ws.getArtifacts(source.id).find(a => a.path === change.path);
    const ta = ws.getArtifacts(target.id).find(a => a.path === change.path);
    if (!sa)
        return ta?.content ?? '';
    if (!ta || change.status === 'add')
        return sa.content;
    const base = forkBaseContent(ws, source, change.path) ?? sa.baseContent ?? '';
    if (base === ta.content)
        return sa.content;
    if (base === sa.content)
        return ta.content;
    return tryAutoMerge(base, ta.content, sa.content).text;
}
function computeArtifactDiff(ws: Workspace, source: Branch, target: Branch): {
    changes: {
        path: string;
        status: 'add' | 'modify' | 'conflict';
    }[];
    conflicts: ArtifactConflict[];
} {
    const sourceArtifacts = ws.getArtifacts(source.id);
    const targetArtifacts = ws.getArtifacts(target.id);
    const targetByPath = new Map<string, Artifact>();
    for (const a of targetArtifacts)
        targetByPath.set(a.path, a);
    const changes: {
        path: string;
        status: 'add' | 'modify' | 'conflict';
    }[] = [];
    const conflicts: ArtifactConflict[] = [];
    for (const sa of sourceArtifacts) {
        if (sa.mergeIntent === 'discard')
            continue;
        const ta = targetByPath.get(sa.path);
        if (!ta) {
            changes.push({ path: sa.path, status: 'add' });
            continue;
        }
        if (ta.content === sa.content)
            continue;
        const base = forkBaseContent(ws, source, sa.path) ?? sa.baseContent ?? '';
        if (base === ta.content) {
            changes.push({ path: sa.path, status: 'modify' });
        }
        else if (base === sa.content) {
            continue;
        }
        else {
            const merged = tryAutoMerge(base, ta.content, sa.content);
            if (merged.success) {
                changes.push({ path: sa.path, status: 'modify' });
            }
            else {
                changes.push({ path: sa.path, status: 'conflict' });
                conflicts.push({
                    path: sa.path,
                    conflictRegion: merged.text,
                    baseContent: base,
                    branchAContent: ta.content,
                    branchBContent: sa.content,
                });
            }
        }
    }
    return { changes, conflicts };
}
function applyArtifactChanges(ws: Workspace, source: Branch, target: Branch, preview: MergePreview, acceptedConflictPaths?: string[], manualResolved: Record<string, string> = {}): void {
    const sourceArtifacts = ws.getArtifacts(source.id);
    const targetArtifacts = ws.getArtifacts(target.id);
    const targetByPath = new Map<string, Artifact>();
    for (const a of targetArtifacts)
        targetByPath.set(a.path, a);
    const acceptedConflicts = new Set(acceptedConflictPaths ?? []);
    const resolutionByPath = new Map<string, ConflictResolution>();
    for (const r of preview.conflictResolutions ?? [])
        resolutionByPath.set(r.path, r);
    for (const change of preview.artifactChanges) {
        const sa = sourceArtifacts.find(a => a.path === change.path);
        if (!sa)
            continue;
        if (sa.mergeIntent === 'discard')
            continue;
        const ta = targetByPath.get(change.path);
        if (change.status === 'add' || !ta) {
            ws.upsertArtifact(target.id, sa.path, sa.content, sa.baseContent, 'merge');
        }
        else if (change.status === 'modify') {
            ws.upsertArtifact(target.id, sa.path, mergedContentFor(ws, source, target, change), ta.content, 'merge');
        }
        else {
            const resolution = resolutionByPath.get(sa.path);
            let finalContent: string;
            let mergeIntent: Artifact['mergeIntent'];
            if (acceptedConflicts.has(sa.path) && Object.prototype.hasOwnProperty.call(manualResolved, sa.path)) {
                finalContent = manualResolved[sa.path];
                mergeIntent = 'merge';
            }
            else if (resolution && acceptedConflicts.has(sa.path)) {
                finalContent = resolution.resolvedContent;
                mergeIntent = 'merge';
            }
            else {
                const merged = tryAutoMerge(sa.baseContent ?? '', ta.content, sa.content);
                finalContent = merged.text;
                mergeIntent = 'ask';
            }
            ws.upsertArtifact(target.id, sa.path, finalContent, ta.content, mergeIntent);
        }
    }
}
function tryAutoMerge(base: string, ours: string, theirs: string): {
    success: boolean;
    text: string;
} {
    const r = merge3(base, ours, theirs, { ours: 'target', theirs: 'source' });
    return { success: r.ok, text: r.text };
}
interface VerificationInput {
    ws: Workspace;
    source: Branch;
    target: Branch;
    mergedMessages: Message[];
    conflicts: ArtifactConflict[];
    workspaceRoot?: string;
    testCommand?: string;
    lintCommand?: string;
    consistencyCheck?: (target: Branch, mergedMessages: Message[], evidence: ConsistencyEvidence[]) => Promise<string[]>;
    consistencyEvidence: ConsistencyEvidence[];
}
async function runVerification(input: VerificationInput): Promise<VerificationResult> {
    const result: VerificationResult = {
        status: 'pending', ranAt: Date.now(), forced: false,
        artifactConflicts: input.conflicts,
    };
    if (input.conflicts.length > 0) {
        result.status = 'fail';
    }
    if (input.testCommand && input.workspaceRoot) {
        try {
            const { stdout, stderr } = await execAsync(input.testCommand, {
                cwd: input.workspaceRoot, timeout: 60000,
            });
            result.testOutput = (stdout + '\n' + stderr).trim();
        }
        catch (err: any) {
            const detail = `${err.message ?? ''}\n${err.stderr ?? ''}`;
            const runnerMissing = err.code === 127 ||
                err.code === 'ENOENT' ||
                /command not found|not found|ENOENT|no such file/i.test(detail);
            if (runnerMissing) {
                result.testOutput =
                    `SKIPPED: test command "${input.testCommand}" is not available on this machine; ` +
                        `verification did not run tests.`;
            }
            else {
                result.testOutput = `FAIL: ${err.message}\n${err.stdout ?? ''}\n${err.stderr ?? ''}`;
                result.status = 'fail';
            }
        }
    }
    if (input.lintCommand && input.workspaceRoot) {
        try {
            const { stdout, stderr } = await execAsync(input.lintCommand, {
                cwd: input.workspaceRoot, timeout: 60000,
            });
            result.lintOutput = (stdout + '\n' + stderr).trim();
        }
        catch (err: any) {
            result.lintOutput = `FAIL: ${err.message}\n${err.stdout ?? ''}\n${err.stderr ?? ''}`;
        }
    }
    if (input.consistencyCheck) {
        try {
            const warnings = await input.consistencyCheck(input.target, input.mergedMessages, input.consistencyEvidence);
            result.consistencyWarnings = warnings;
        }
        catch (err: any) {
            result.consistencyWarnings = [`Consistency check failed: ${err.message}`];
        }
    }
    if (result.status === 'pending')
        result.status = 'skipped';
    return result;
}
export function detectTestCommand(workspaceRoot: string): string | null {
    if (!workspaceRoot)
        return null;
    if (fs.existsSync(path.join(workspaceRoot, 'package.json'))) {
        try {
            const pkg = JSON.parse(fs.readFileSync(path.join(workspaceRoot, 'package.json'), 'utf-8'));
            if (pkg.scripts?.test)
                return 'npm test';
        }
        catch { }
    }
    if (fs.existsSync(path.join(workspaceRoot, 'pyproject.toml')) ||
        fs.existsSync(path.join(workspaceRoot, 'pytest.ini')) ||
        fs.existsSync(path.join(workspaceRoot, 'tests'))) {
        return 'pytest -q';
    }
    if (fs.existsSync(path.join(workspaceRoot, 'Cargo.toml')))
        return 'cargo test --quiet';
    return null;
}
export function detectLintCommand(workspaceRoot: string): string | null {
    if (!workspaceRoot)
        return null;
    if (fs.existsSync(path.join(workspaceRoot, 'package.json'))) {
        try {
            const pkg = JSON.parse(fs.readFileSync(path.join(workspaceRoot, 'package.json'), 'utf-8'));
            if (pkg.scripts?.lint)
                return 'npm run lint';
        }
        catch { }
    }
    if (fs.existsSync(path.join(workspaceRoot, '.eslintrc.json')) ||
        fs.existsSync(path.join(workspaceRoot, '.eslintrc.js'))) {
        return 'npx eslint .';
    }
    if (fs.existsSync(path.join(workspaceRoot, 'pyproject.toml'))) {
        return 'ruff check . || flake8 .';
    }
    return null;
}
