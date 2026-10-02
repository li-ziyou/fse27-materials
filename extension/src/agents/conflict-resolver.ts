import { LLMProvider } from '../llm/provider';
import { CONFLICT_RESOLVER_SYSTEM } from '../llm/prompts';
import { parseEdits, looksElided, merge3 } from '../core/edits';
export interface ConflictResolution {
    path: string;
    resolvedContent: string;
    rationale: string;
    confidence: 'high' | 'medium' | 'low';
    originalContent: string;
    error?: string;
}
export function extractSingleCompleteFileBlock(raw: string): string | undefined {
    const blocks = [...raw.matchAll(/```[^\r\n`]*\r?\n([\s\S]*?)```/g)];
    if (blocks.length !== 1)
        return undefined;
    const content = blocks[0][1];
    return content.trim() ? content : undefined;
}
export class ConflictResolverAgent {
    constructor(private provider: LLMProvider, private onUsage?: (inputTokens: number, outputTokens: number) => void) { }
    async resolve(opts: {
        path: string;
        base: string;
        theirs: string;
        ours: string;
        theirContext: {
            role: string;
            content: string;
        }[];
        ourContext: {
            role: string;
            content: string;
        }[];
        revisionInstruction?: string;
        currentResolution?: string;
        signal?: AbortSignal;
        model?: string;
    }): Promise<ConflictResolution> {
        const userContent = this.buildUserMessage(opts);
        let raw = '';
        try {
            for await (const ev of this.provider.stream({
                system: CONFLICT_RESOLVER_SYSTEM,
                messages: [{ role: 'user', content: userContent }],
                maxTokens: 8192,
                temperature: 0.1,
                signal: opts.signal,
                model: opts.model,
            })) {
                if (ev.type === 'delta')
                    raw += ev.text;
                if (ev.type === 'usage')
                    this.onUsage?.(ev.inputTokens ?? 0, ev.outputTokens ?? 0);
                if (ev.type === 'error') {
                    return this.fallback(opts, ev.error ?? 'unknown error');
                }
                if (ev.type === 'done' && ev.truncated) {
                    return this.fallback(opts, 'resolver output was truncated at the provider limit');
                }
            }
        }
        catch (err: any) {
            return this.fallback(opts, err.message ?? String(err));
        }
        return this.parse(raw, opts);
    }
    private buildUserMessage(opts: {
        path: string;
        base: string;
        theirs: string;
        ours: string;
        theirContext: {
            role: string;
            content: string;
        }[];
        ourContext: {
            role: string;
            content: string;
        }[];
        revisionInstruction?: string;
        currentResolution?: string;
    }): string {
        const parts: string[] = [];
        parts.push(`path: ${opts.path}\n`);
        parts.push('=== BASE (common ancestor) ===');
        parts.push(opts.base || '<file did not exist at fork point>');
        parts.push('\n=== THEIRS (target branch current) ===');
        parts.push(opts.theirs || '<file does not exist in target>');
        parts.push('\n=== OURS (source branch current) ===');
        parts.push(opts.ours);
        if (opts.theirContext.length > 0) {
            parts.push('\n=== TARGET BRANCH INTENT (recent messages) ===');
            for (const m of opts.theirContext.slice(-4)) {
                const snippet = m.content.length > 600 ? m.content.slice(0, 600) + '…' : m.content;
                parts.push(`[${m.role}] ${snippet}`);
            }
        }
        if (opts.ourContext.length > 0) {
            parts.push('\n=== SOURCE BRANCH INTENT (recent messages) ===');
            for (const m of opts.ourContext.slice(-4)) {
                const snippet = m.content.length > 600 ? m.content.slice(0, 600) + '…' : m.content;
                parts.push(`[${m.role}] ${snippet}`);
            }
        }
        if (opts.revisionInstruction?.trim()) {
            parts.push('\n=== CURRENT AI PROPOSED RESOLUTION ===', opts.currentResolution || '<no previous proposal>', '\n=== USER REVISION REQUEST ===', opts.revisionInstruction.trim(), 'Revise the current proposed resolution according to the request while preserving compatible work from BOTH branches. Return the complete revised file.');
        }
        parts.push('\n=== TASK ===', 'Resolve the conflict and output the result in the CONFIDENCE/RATIONALE + fenced-block format from your instructions. No JSON.');
        return parts.join('\n');
    }
    private parse(raw: string, opts: {
        path: string;
        base: string;
        theirs: string;
        ours: string;
    }): ConflictResolution {
        const ops = parseEdits(raw);
        const match = ops.find(o => o.kind === 'create' && o.path === opts.path && typeof o.content === 'string');
        const anyCreate = ops.find(o => o.kind === 'create' && typeof o.content === 'string');
        const content = (match ?? anyCreate)?.content ?? extractSingleCompleteFileBlock(raw);
        const confRaw = (raw.match(/CONFIDENCE:\s*(high|medium|low)/i)?.[1] ?? 'medium').toLowerCase();
        const confidence = (confRaw === 'high' || confRaw === 'low') ? confRaw as 'high' | 'low' : 'medium';
        const rationale = raw.match(/RATIONALE:\s*(.+)/i)?.[1]?.trim() ?? '';
        if (typeof content !== 'string' || content.trim() === '') {
            return this.fallback(opts, 'Resolver did not return a usable file block. Raw start: ' + raw.slice(0, 160));
        }
        if (/<{5,}|>{5,}/.test(content) || looksElided(content, opts.theirs)) {
            return this.fallback(opts, 'Resolved content looked incomplete; keeping conflict markers for manual review.');
        }
        return {
            path: opts.path,
            resolvedContent: content,
            rationale,
            confidence,
            originalContent: opts.theirs,
        };
    }
    private fallback(opts: {
        path: string;
        base: string;
        theirs: string;
        ours: string;
    }, error: string): ConflictResolution {
        const merged = merge3(opts.base, opts.theirs, opts.ours, { ours: 'target', theirs: 'source' });
        return {
            path: opts.path,
            resolvedContent: merged.text,
            rationale: '',
            confidence: 'low',
            originalContent: opts.theirs,
            error,
        };
    }
}
