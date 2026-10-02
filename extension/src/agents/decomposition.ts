import { LLMProvider } from '../llm/provider';
import { DECOMPOSITION_AGENT_SYSTEM } from '../llm/prompts';
export interface DecompositionResult {
    branches: {
        name: string;
        scope: string;
    }[];
    mergeOrder: {
        branch: string;
        after: string[];
        reason: string;
    }[];
    overlapWarnings: {
        branches: string[];
        files: string[];
        note: string;
    }[];
}
export class DecompositionAgent {
    constructor(private provider: LLMProvider) { }
    async decompose(taskDescription: string, signal?: AbortSignal): Promise<DecompositionResult> {
        let raw = '';
        for await (const ev of this.provider.stream({
            system: DECOMPOSITION_AGENT_SYSTEM,
            messages: [{ role: 'user', content: taskDescription }],
            maxTokens: 2000,
            temperature: 0.3,
            signal,
        })) {
            if (ev.type === 'delta')
                raw += ev.text;
            if (ev.type === 'error')
                throw new Error(`Decomposition failed: ${ev.error}`);
        }
        const jsonMatch = raw.match(/\{[\s\S]*\}/);
        if (!jsonMatch) {
            throw new Error('Decomposition agent did not return JSON');
        }
        try {
            return JSON.parse(jsonMatch[0]) as DecompositionResult;
        }
        catch (err: any) {
            throw new Error(`Decomposition JSON parse failed: ${err.message}`);
        }
    }
}
