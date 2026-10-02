import { LLMProvider } from '../llm/provider';
import { MERGE_ANALYST_SYSTEM } from '../llm/prompts';
import { parseEdits, looksElided } from '../core/edits';
export interface CascadingEditProposal {
    path: string;
    rationale: string;
    proposedContent: string;
    currentContent: string;
}
export interface AnalystResult {
    summary: string;
    proposals: CascadingEditProposal[];
    error?: string;
}
interface ArtifactView {
    path: string;
    content: string;
}
interface ChangedFileView {
    path: string;
    before: string;
    after: string;
    status: 'add' | 'modify' | 'conflict';
}
export class MergeAnalystAgent {
    constructor(private provider: LLMProvider, private onUsage?: (inputTokens: number, outputTokens: number) => void) { }
    async analyze(opts: {
        sourceArtifacts: ArtifactView[];
        targetArtifacts: ArtifactView[];
        changedFiles: ChangedFileView[];
        recentMessages?: {
            role: string;
            content: string;
        }[];
        signal?: AbortSignal;
        maxProposals?: number;
    }): Promise<AnalystResult> {
        const max = opts.maxProposals ?? 4;
        if (opts.changedFiles.length === 0) {
            return { summary: 'No changes in source — nothing to cascade.', proposals: [] };
        }
        const changedPaths = new Set(opts.changedFiles.map(f => f.path));
        const unchangedTarget = opts.targetArtifacts.filter(a => !changedPaths.has(a.path));
        if (unchangedTarget.length === 0) {
            return { summary: 'No unchanged target files to consider.', proposals: [] };
        }
        const userContent = this.buildUserMessage(opts.sourceArtifacts, unchangedTarget, opts.changedFiles, opts.recentMessages, max);
        let raw = '';
        try {
            for await (const ev of this.provider.stream({
                system: MERGE_ANALYST_SYSTEM,
                messages: [{ role: 'user', content: userContent }],
                maxTokens: 4096,
                temperature: 0.2,
                signal: opts.signal,
            })) {
                if (ev.type === 'delta')
                    raw += ev.text;
                if (ev.type === 'usage')
                    this.onUsage?.(ev.inputTokens ?? 0, ev.outputTokens ?? 0);
                if (ev.type === 'error') {
                    return { summary: '', proposals: [], error: ev.error };
                }
                if (ev.type === 'done' && ev.truncated) {
                    return { summary: '', proposals: [], error: 'model output was truncated at the provider limit; no merge proposals were accepted' };
                }
            }
        }
        catch (err: any) {
            return { summary: '', proposals: [], error: err.message ?? String(err) };
        }
        return this.parse(raw, opts.targetArtifacts);
    }
    private buildUserMessage(source: ArtifactView[], unchangedTarget: ArtifactView[], changed: ChangedFileView[], recentMessages: {
        role: string;
        content: string;
    }[] | undefined, maxProposals: number): string {
        const parts: string[] = [];
        parts.push(`MAX PROPOSALS: ${maxProposals}\n`);
        parts.push('=== CHANGED FILES (these are the trigger; do not propose edits to these) ===');
        for (const f of changed) {
            parts.push(`\n--- ${f.path} (status: ${f.status}) ---`);
            parts.push('TARGET (before):');
            parts.push(f.before || '<file does not exist in target>');
            parts.push('\nSOURCE (after):');
            parts.push(f.after);
        }
        parts.push('\n=== UNCHANGED TARGET FILES (you may propose edits to these) ===');
        if (unchangedTarget.length === 0) {
            parts.push('(none)');
        }
        else {
            for (const a of unchangedTarget) {
                parts.push(`\n--- ${a.path} ---`);
                parts.push(a.content);
            }
        }
        if (recentMessages && recentMessages.length > 0) {
            parts.push('\n=== RECENT CONVERSATION (most recent last; for context only) ===');
            for (const m of recentMessages.slice(-6)) {
                const snippet = m.content.length > 800 ? m.content.slice(0, 800) + '…' : m.content;
                parts.push(`[${m.role}] ${snippet}`);
            }
        }
        parts.push('\n=== TASK ===', 'Identify which UNCHANGED TARGET FILES need updates to remain consistent with the CHANGED FILES.', 'For each, output a fenced block with its complete new content, in the SUMMARY + fenced-block format from your instructions. Be concrete — no placeholders, no ellipses. No JSON.');
        return parts.join('\n');
    }
    private parse(raw: string, targetArtifacts: ArtifactView[]): AnalystResult {
        const summary = raw.match(/SUMMARY:\s*(.+)/i)?.[1]?.trim() ?? '';
        const ops = parseEdits(raw);
        const targetByPath = new Map<string, string>();
        for (const a of targetArtifacts)
            targetByPath.set(a.path, a.content);
        const proposals: CascadingEditProposal[] = [];
        for (const op of ops) {
            if (op.kind !== 'create' || typeof op.content !== 'string')
                continue;
            const currentContent = targetByPath.get(op.path) ?? '';
            if (op.content.trim() === currentContent.trim())
                continue;
            if (currentContent && looksElided(op.content, currentContent))
                continue;
            proposals.push({
                path: op.path,
                rationale: '',
                proposedContent: op.content,
                currentContent,
            });
        }
        return { summary, proposals };
    }
}
