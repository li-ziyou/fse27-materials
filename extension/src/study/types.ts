export type StudyCondition = 'linear' | 'contextbranch';
export type StudyProvider = 'anthropic' | 'openai' | 'openrouter' | 'gemini';
export type StudyPublicTestTarget = 'responsibilityA' | 'responsibilityB' | 'main';
export interface StudyPublicTestCommands {
    responsibilityA: string;
    responsibilityB: string;
    main: string;
}
export interface StudySiblingState {
    id: string;
    label: string;
    ticket: {
        requirements: string[];
    };
}
export interface StudyTaskManifest {
    schemaVersion: 1;
    taskId: string;
    participantTitle: string;
    contextBranch: {
        siblingStates: [
            StudySiblingState,
            StudySiblingState
        ];
        finalVerification: string;
    };
    runner: {
        publicTestCommand: string;
        publicTestCommands?: StudyPublicTestCommands;
        runtime: 'contextbranch-study-python';
        network: 'not-required';
    };
    submission: {
        allowedProductionPaths: string[];
        finalState: 'main';
    };
}
export interface StudyRunConfig {
    runId: string;
    participantId: string;
    taskSetId?: string;
    period: 1 | 2;
    condition: StudyCondition;
    manifestPath: string;
    timeLimitSeconds: number;
    provider: StudyProvider;
    modelId: string;
    modelCallBudget?: number;
    modelTokenBudget?: number;
}
export interface StudyRunFile {
    schemaVersion: 1;
    runId: string;
    participantId: string;
    taskSetId?: string;
    sequenceId: string;
    period: 1 | 2;
    taskId: string;
    formId?: string;
    condition: StudyCondition;
    createdAt: string;
    startedAt: string | null;
    exportDirectory?: string;
    timeLimitSeconds: number;
    model: {
        provider: StudyProvider;
        id: string;
        modelCallBudget?: number;
        modelTokenBudget?: number;
    };
    runtimePython: string;
    manifest: {
        taskId: string;
        sha256: string;
        ticket: {
            summary: string;
            requirements: string[];
            mainMarkdown?: string;
        };
        contextBranch: StudyTaskManifest['contextBranch'];
        runner: StudyTaskManifest['runner'];
        submission: StudyTaskManifest['submission'];
    };
}
export interface StudyFinishedRecord {
    schemaVersion: 1;
    runId: string;
    taskId: string;
    condition: StudyCondition;
    startedAt: string | null;
    finishedAt: string;
    durationMs: number;
    timedOut: boolean;
    finalState: 'main';
    activeStateAtFinish: string;
    modelCallsUsed: number;
    modelTokensUsed: number;
    productionFileHashes: Record<string, string>;
}
export interface StudyArchive {
    filePath: string;
    fileName: string;
    created: boolean;
}
export interface StudyUiState {
    active: boolean;
    runId: string;
    taskTitle: string;
    condition: StudyCondition;
    started: boolean;
    finished: boolean;
    timeLimitSeconds: number;
    remainingSeconds: number;
    modelCallsUsed: number;
    modelTokensUsed: number;
    publicTestLabel: string;
    siblingStateIds: string[];
}
