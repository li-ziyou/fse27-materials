import { LLMProvider } from '../llm/provider';
import { META_AGENT_SYSTEM, CONSOLIDATION_SYSTEM, REBASE_CHECK_SYSTEM, CONSISTENCY_CHECK_SYSTEM } from '../llm/prompts';
import { Branch, Message } from '../core/types';
import { diffLines } from '../core/edits';
export interface ConsistencyEvidence {
    path: string;
    status: 'add' | 'modify' | 'conflict';
    before: string;
    after: string;
}
export type MetaTrigger = 'branch_created' | 'merge_attempted' | 'merge_completed' | 'user_request';
export interface MetaSuggestion {
    shouldSpeak: boolean;
    tone?: 'brief' | 'warning' | 'suggestion';
    message?: string;
    suggestedActions?: {
        label: string;
        kind: string;
        branch?: string;
    }[];
}
export class MetaAgent {
    constructor(private provider: LLMProvider) { }
    async observe(opts: {
        trigger: MetaTrigger;
        branches: Branch[];
        activeBranch: Branch;
        recentMessages?: Message[];
        userQuery?: string;
        signal?: AbortSignal;
    }): Promise<MetaSuggestion> {
        const context = this.buildGraphContext(opts.branches, opts.activeBranch);
        const userContent = [
            `Trigger: ${opts.trigger}`,
            `Active branch: ${opts.activeBranch.name}`,
            '',
            'Branch graph:',
            context,
            opts.userQuery ? `\nUser query: ${opts.userQuery}` : '',
        ].join('\n');
        let raw = '';
        for await (const ev of this.provider.stream({
            system: META_AGENT_SYSTEM,
            messages: [{ role: 'user', content: userContent }],
            maxTokens: 800,
            temperature: 0.4,
            signal: opts.signal,
        })) {
            if (ev.type === 'delta')
                raw += ev.text;
            if (ev.type === 'error')
                return { shouldSpeak: false };
        }
        const jsonMatch = raw.match(/\{[\s\S]*\}/);
        if (!jsonMatch)
            return { shouldSpeak: false };
        try {
            return JSON.parse(jsonMatch[0]) as MetaSuggestion;
        }
        catch {
            return { shouldSpeak: false };
        }
    }
    async consolidate(branch: Branch, messages: Message[], changedFiles?: {
        path: string;
        status: string;
        before: string;
        after: string;
    }[], signal?: AbortSignal): Promise<string> {
        let diffSection: string;
        if (changedFiles && changedFiles.length) {
            const blocks: string[] = [];
            for (const f of changedFiles) {
                const lines: string[] = [];
                for (const h of diffLines(f.before, f.after, 2)) {
                    for (const ln of h.lines) {
                        lines.push((ln.type === 'add' ? '+ ' : ln.type === 'del' ? '- ' : '  ') + ln.text);
                    }
                    lines.push('  …');
                }
                let body = lines.join('\n');
                if (body.length > 2500)
                    body = body.slice(0, 2500) + '\n  …(diff truncated)';
                blocks.push(`--- ${f.path} (${f.status}) ---\n${body || '(no textual diff)'}`);
            }
            diffSection = `FILE CHANGES THIS BRANCH INTRODUCES (authoritative — summarize THESE):\n${blocks.join('\n\n')}\n\n`;
        }
        else {
            diffSection = 'FILE CHANGES: (none detected)\n\n';
        }
        const transcript = messages
            .filter(m => m.role !== 'system')
            .map(m => {
            const c = m.content.length > 500 ? m.content.slice(0, 500) + '…' : m.content;
            return `${m.role.toUpperCase()}: ${c}`;
        })
            .join('\n\n');
        const userContent = `Branch: ${branch.name}\n` +
            `Description: ${branch.description ?? '(none)'}\n\n` +
            diffSection +
            `Conversation (intent only — do NOT assume anything here was applied unless it appears in the diffs above):\n${transcript}`;
        let raw = '';
        for await (const ev of this.provider.stream({
            system: CONSOLIDATION_SYSTEM,
            messages: [{ role: 'user', content: userContent }],
            maxTokens: 1500,
            temperature: 0.3,
            signal,
        })) {
            if (ev.type === 'delta')
                raw += ev.text;
            if (ev.type === 'error')
                throw new Error(`Consolidation failed: ${ev.error}`);
        }
        return raw.trim();
    }
    async rebaseCheck(source: Branch, target: Branch, sourceMessages: Message[], targetMessages: Message[], signal?: AbortSignal): Promise<string[]> {
        const userContent = `SOURCE branch: ${source.name}\n` +
            `Source conversation:\n` +
            sourceMessages.slice(-20).map(m => `${m.role}: ${m.content}`).join('\n') +
            `\n\nTARGET branch: ${target.name}\n` +
            `Target recent additions:\n` +
            targetMessages.slice(-15).map(m => `${m.role}: ${m.content}`).join('\n');
        let raw = '';
        for await (const ev of this.provider.stream({
            system: REBASE_CHECK_SYSTEM,
            messages: [{ role: 'user', content: userContent }],
            maxTokens: 800,
            temperature: 0.2,
            signal,
        })) {
            if (ev.type === 'delta')
                raw += ev.text;
            if (ev.type === 'error')
                return [];
        }
        const jsonMatch = raw.match(/\{[\s\S]*\}/);
        if (!jsonMatch)
            return [];
        try {
            const parsed = JSON.parse(jsonMatch[0]);
            return Array.isArray(parsed.warnings) ? parsed.warnings : [];
        }
        catch {
            return [];
        }
    }
    async consistencyCheck(target: Branch, mergedMessages: Message[], evidence: ConsistencyEvidence[], signal?: AbortSignal): Promise<string[]> {
        const fileBlocks = evidence.map(f => {
            const before = f.before.length > 12000 ? f.before.slice(0, 12000) + '\n…(before truncated)' : f.before;
            const after = f.after.length > 12000 ? f.after.slice(0, 12000) + '\n…(after truncated)' : f.after;
            return `--- ${f.path} (${f.status}) ---\nBEFORE (target):\n${before || '(file absent)'}\n\nAFTER (merge candidate):\n${after || '(empty file)'}`;
        }).join('\n\n');
        const transcript = mergedMessages.slice(-12)
            .map(m => `${m.role}: ${m.content.slice(0, 500)}${m.content.length > 500 ? '…' : ''}`)
            .join('\n');
        const userContent = `Target branch after merge: ${target.name}\n\n` +
            `AUTHORITATIVE FILE EVIDENCE (use this as the source of truth):\n${fileBlocks || '(no changed-file evidence supplied)'}\n\n` +
            `Conversation is context only; do NOT infer that a file was changed, duplicated, or merged unless the file evidence above supports that claim.\n` +
            `Conversation:\n${transcript}`;
        let raw = '';
        for await (const ev of this.provider.stream({
            system: CONSISTENCY_CHECK_SYSTEM,
            messages: [{ role: 'user', content: userContent }],
            maxTokens: 600,
            temperature: 0.2,
            signal,
        })) {
            if (ev.type === 'delta')
                raw += ev.text;
            if (ev.type === 'error')
                return [];
        }
        const jsonMatch = raw.match(/\{[\s\S]*\}/);
        if (!jsonMatch)
            return [];
        try {
            const parsed = JSON.parse(jsonMatch[0]);
            return Array.isArray(parsed.warnings) ? parsed.warnings : [];
        }
        catch {
            return [];
        }
    }
    private buildGraphContext(branches: Branch[], active: Branch): string {
        return branches.map(b => {
            const tag = b.id === active.id ? ' (ACTIVE)' : '';
            const parent = b.parentBranchId ? ` ← ${b.parentBranchId}` : '';
            return `  - ${b.name} [${b.status}]${tag}${parent} (${b.messageIds.length} msgs)`;
        }).join('\n');
    }
}
