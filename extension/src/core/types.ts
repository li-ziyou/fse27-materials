export type Role = 'system' | 'user' | 'assistant';
export type InterruptionReason = 'user_abort' | 'output_limit' | 'repetition' | 'provider_error';
export interface Message {
    id: string;
    role: Role;
    content: string;
    timestamp: number;
    meta?: {
        inputTokens?: number;
        outputTokens?: number;
        model?: string;
        interrupted?: boolean;
        interruptionReason?: InterruptionReason;
        artifactIds?: string[];
    };
}
export interface Artifact {
    id: string;
    path: string;
    content: string;
    baseContent: string | null;
    mergeIntent: 'merge' | 'discard' | 'ask';
    createdAt: number;
    updatedAt: number;
}
export interface Checkpoint {
    id: string;
    branchId: string;
    parentCheckpointId: string | null;
    messageIds: string[];
    artifactIds: string[];
    createdAt: number;
    label?: string;
}
export type BranchStatus = 'draft' | 'active' | 'ready' | 'merging' | 'merged' | 'abandoned';
export interface Branch {
    id: string;
    name: string;
    description?: string;
    parentBranchId: string | null;
    parentCheckpointId: string | null;
    activeCheckpointId: string | null;
    forkedAtMessageCount: number;
    messageIds: string[];
    artifactIds: string[];
    status: BranchStatus;
    createdAt: number;
    updatedAt: number;
    mergedIntoBranchId?: string;
    mergedAt?: number;
    mergedAsCheckpointId?: string;
    tags?: string[];
}
export interface MergePlanEntry {
    branchId: string;
    predecessors: string[];
    priority: number;
    merged: boolean;
}
export interface Task {
    id: string;
    name: string;
    description: string;
    rootBranchId: string;
    branchIds: string[];
    mergePlan: MergePlanEntry[];
    createdAt: number;
    status: 'planning' | 'executing' | 'completed';
}
export type VerificationStatus = 'pass' | 'fail' | 'skipped' | 'pending';
export interface VerificationResult {
    status: VerificationStatus;
    ranAt: number;
    testOutput?: string;
    lintOutput?: string;
    consistencyWarnings?: string[];
    artifactConflicts?: ArtifactConflict[];
    forced: boolean;
}
export interface ArtifactConflict {
    path: string;
    conflictRegion: string;
    baseContent: string;
    branchAContent: string;
    branchBContent: string;
}
export interface MergeEvent {
    id: string;
    sourceBranchId: string;
    targetBranchId: string;
    taskId?: string;
    startedAt: number;
    completedAt?: number;
    verification: VerificationResult;
    targetSnapshotCheckpointId: string;
    postMergeCheckpointId: string;
    sourcePreviousStatus?: BranchStatus;
    undoneAt?: number;
    undoTargetCheckpointId?: string;
    undoSourceBranchStatus?: BranchStatus;
    synthesisMessageId?: string;
    rebaseNotes?: string[];
}
export interface WorkspaceState {
    version: 1;
    createdAt: number;
    activeBranchId: string;
    mainBranchId: string;
    branchIds: string[];
    taskIds: string[];
    mergeEventIds: string[];
    telemetry: {
        sessionStartedAt: number;
        totalApiCalls: number;
        totalInputTokens: number;
        totalOutputTokens: number;
        totalMergeApiCalls: number;
        totalMergeInputTokens: number;
        totalMergeOutputTokens: number;
    };
}
export interface StudyExport {
    participantId: string;
    condition: 'linear' | 'branched' | 'contextbranch';
    exportedAt: number;
    sessionDurationMs: number;
    branches: Branch[];
    mergeEvents: MergeEvent[];
    branchCount: number;
    mergeCount: number;
    forcedMergeCount: number;
    abandonedBranchCount: number;
}
