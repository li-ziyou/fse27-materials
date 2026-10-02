import * as fs from 'fs';
import * as path from 'path';
import { LLMProvider } from '../llm/provider';
import { isProtectedPath } from '../core/file-policy';
export interface WorkspaceFileCandidate {
    path: string;
    size: number;
    symbols: string[];
}
export interface ContextSelection {
    paths: string[];
    rationale?: string;
    summary?: string;
    error?: string;
}
const IGNORED_DIRS = new Set([
    '.contextbranch', '.git', 'node_modules', 'dist', 'out', 'build',
    '.venv', 'venv', '__pycache__', '.next', '.cache', '.idea',
]);
const IGNORED_EXTENSIONS = new Set([
    '.lock', '.log', '.pid', '.swp', '.tmp', '.png', '.jpg', '.jpeg', '.gif',
    '.ico', '.pdf', '.zip', '.tar', '.gz', '.exe', '.dll', '.so', '.dylib',
    '.pem', '.key', '.p12', '.pfx', '.crt', '.cer',
]);
const IGNORED_RELATIVE_PREFIXES = new Set(['.study/bin/']);
const IGNORED_RELATIVE_FILES = new Set([
    '.study/run.json', '.study/finished.json', '.study/telemetry.jsonl',
]);
const IGNORED_FILENAMES = new Set([
    '.env', '.env.local', '.env.development', '.env.production',
    '.npmrc', '.pypirc', '.netrc', 'credentials.json',
    'service-account.json', 'id_rsa', 'id_ed25519',
]);
const MAX_FILE_BYTES = 2000000;
const MAX_FILES = 5000;
const MAX_SYMBOLS_PER_FILE = 24;
export function scanWorkspaceFiles(root: string): WorkspaceFileCandidate[] {
    const out: WorkspaceFileCandidate[] = [];
    const walk = (dir: string): void => {
        if (out.length >= MAX_FILES)
            return;
        let entries: fs.Dirent[];
        try {
            entries = fs.readdirSync(dir, { withFileTypes: true });
        }
        catch {
            return;
        }
        for (const ent of entries) {
            if (out.length >= MAX_FILES)
                return;
            const abs = path.join(dir, ent.name);
            if (ent.isDirectory()) {
                if (!IGNORED_DIRS.has(ent.name))
                    walk(abs);
                continue;
            }
            if (!ent.isFile())
                continue;
            const rel = path.relative(root, abs).split(path.sep).join('/');
            if (!rel || rel.startsWith('../') || path.isAbsolute(rel))
                continue;
            if (isProtectedPath(rel))
                continue;
            if (rel.split('/').some(s => IGNORED_DIRS.has(s)))
                continue;
            if ([...IGNORED_RELATIVE_PREFIXES].some(prefix => rel.startsWith(prefix)) ||
                IGNORED_RELATIVE_FILES.has(rel))
                continue;
            const basename = path.basename(rel).toLowerCase();
            if (IGNORED_FILENAMES.has(basename) ||
                basename.startsWith('.env.') ||
                basename.startsWith('credentials.') ||
                basename.startsWith('service-account.'))
                continue;
            if (IGNORED_EXTENSIONS.has(path.extname(rel).toLowerCase()))
                continue;
            let stat: fs.Stats;
            try {
                stat = fs.statSync(abs);
            }
            catch {
                continue;
            }
            if (stat.size > MAX_FILE_BYTES)
                continue;
            let content: string;
            try {
                content = fs.readFileSync(abs, 'utf8');
            }
            catch {
                continue;
            }
            if (content.includes('\u0000'))
                continue;
            out.push({ path: rel, size: Buffer.byteLength(content, 'utf8'), symbols: extractSymbols(content) });
        }
    };
    walk(root);
    return out.sort((a, b) => a.path.localeCompare(b.path));
}
function extractSymbols(content: string): string[] {
    const found = new Set<string>();
    const add = (s: string | undefined) => {
        if (s && s.length >= 3 && s.length <= 80)
            found.add(s);
    };
    const patterns = [
        /\b(?:function|class|interface|type|enum)\s+([A-Za-z_$][\w$-]*)/g,
        /\b(?:const|let|var)\s+([A-Za-z_$][\w$-]*)/g,
        /\bexport\s+(?:default\s+)?(?:function|class|const|let|var)?\s*([A-Za-z_$][\w$-]*)?/g,
        /\bid=["']([A-Za-z][\w:-]{2,})["']/g,
        /\bclass=["']([^"']+)["']/g,
        /^\s*([.#][A-Za-z][\w-]{2,})\s*[{,]/gm,
    ];
    for (const re of patterns) {
        for (const m of content.matchAll(re)) {
            const raw = m[1];
            if (!raw)
                continue;
            for (const token of raw.split(/\s+/))
                add(token.replace(/[{},]/g, ''));
            if (found.size >= MAX_SYMBOLS_PER_FILE)
                return [...found].slice(0, MAX_SYMBOLS_PER_FILE);
        }
    }
    return [...found].slice(0, MAX_SYMBOLS_PER_FILE);
}
export class ContextAgent {
    constructor(private provider: LLMProvider, private onUsage?: (i: number, o: number) => void) { }
    async select(opts: {
        conversation: {
            role: string;
            content: string;
        }[];
        files: WorkspaceFileCandidate[];
        branchArtifacts: {
            path: string;
            size: number;
        }[];
        model?: string;
        signal?: AbortSignal;
        maxFiles?: number;
    }): Promise<ContextSelection> {
        if (opts.files.length === 0)
            return { paths: [] };
        const maxFiles = Math.max(1, Math.min(opts.maxFiles ?? 12, 24));
        const inventory = opts.files.map(f => `${f.path}\t${f.size} bytes${f.symbols.length ? `\t[${f.symbols.join(', ')}]` : ''}`).join('\n');
        const conversation = buildConversationContext(opts.conversation);
        const branchPaths = new Set(opts.branchArtifacts.map(a => a.path));
        const system = [
            'You are ContextBranch Context Agent. Your ONLY job is to select workspace files that the coding agent should read for the user request.',
            'You are given the full recent conversation and a workspace inventory. The workspace inventory is authoritative: you may only return paths that appear in it.',
            'Infer references from the entire conversation, including follow-ups such as "fix it then", pronouns, previously discussed filenames, functions, selectors, errors, and code snippets.',
            'Select ALL files needed to understand and safely implement the request, including closely coupled files when the change crosses boundaries. Prefer a small complete set over one guessed file.',
            'If the request is ambiguous, select the most plausible relevant files rather than asking the user for paths. Never ask the user to provide contents of a file that exists in the inventory.',
            `Return at most ${maxFiles} paths.`,
            'Output FILE lines first, then one SUMMARY: line describing the current requested change in 1-2 sentences using the conversation, then one RATIONALE: line. No markdown fences and no invented paths.',
        ].join('\n');
        const user = [
            '=== CONVERSATION ===', conversation,
            '\n=== WORKSPACE INVENTORY ===', inventory,
            '\n=== BRANCH-OWNED PATHS (these have authoritative branch versions) ===',
            [...branchPaths].join('\n') || '(none)',
            '\n=== TASK ===', 'Choose the files the coding agent must read now.',
        ].join('\n');
        let raw = '';
        try {
            for await (const ev of this.provider.stream({
                system,
                messages: [{ role: 'user', content: user }],
                model: opts.model,
                maxTokens: 1200,
                temperature: 0,
                signal: opts.signal,
            })) {
                if (ev.type === 'delta')
                    raw += ev.text ?? '';
                if (ev.type === 'usage')
                    this.onUsage?.(ev.inputTokens ?? 0, ev.outputTokens ?? 0);
                if (ev.type === 'error')
                    return { paths: [], error: ev.error ?? 'context selection failed' };
                if (ev.type === 'done' && ev.truncated)
                    return { paths: [], error: 'context selector was truncated' };
            }
        }
        catch (err: any) {
            return { paths: [], error: err.message ?? String(err) };
        }
        const valid = new Set(opts.files.map(f => f.path));
        const paths: string[] = [];
        for (const m of raw.matchAll(/^\s*FILE:\s*(.+?)\s*$/gmi)) {
            const p = m[1].trim().replace(/^['"]|['"]$/g, '');
            if (valid.has(p) && !paths.includes(p))
                paths.push(p);
            if (paths.length >= maxFiles)
                break;
        }
        const summary = raw.match(/^\s*SUMMARY:\s*(.+)$/mi)?.[1]?.trim();
        const rationale = raw.match(/^\s*RATIONALE:\s*(.+)$/mi)?.[1]?.trim();
        return { paths, summary, rationale };
    }
}
function buildConversationContext(messages: {
    role: string;
    content: string;
}[]): string {
    const parts: string[] = [];
    let budget = 70000;
    for (let i = messages.length - 1; i >= 0 && budget > 0; i--) {
        const m = messages[i];
        const cap = m.role === 'assistant' ? 3500 : 5000;
        const text = m.content.length > cap ? m.content.slice(-cap) + '\n[…truncated for context selection…]' : m.content;
        const piece = `[${m.role}] ${text}`;
        if (piece.length <= budget) {
            parts.unshift(piece);
            budget -= piece.length;
        }
    }
    return parts.join('\n\n');
}
