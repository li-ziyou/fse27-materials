export type EditKind = 'create' | 'replace';
export interface EditOp {
    path: string;
    kind: EditKind;
    search?: string;
    replace?: string;
    content?: string;
    malformed?: boolean;
}
export interface AppliedOp {
    index: number;
    kind: EditKind;
    ok: boolean;
    reason?: string;
    search?: string;
    replace?: string;
    matched?: 'exact' | 'whitespace' | 'symbol' | 'whole-file';
}
export interface ApplyEditOptions {
    allowUniquePythonSymbolRebase?: boolean;
}
export interface AppliedFile {
    path: string;
    before: string;
    after: string;
    isNew: boolean;
    ops: AppliedOp[];
    failedCount: number;
    hunks: DiffHunk[];
}
export function buildEditRetryInstruction(files: AppliedFile[], previousDraft: string, currentByPath?: ReadonlyMap<string, string>): string {
    const failures = files.flatMap(file => file.ops
        .filter(op => !op.ok)
        .map(op => {
        const search = (op.search ?? '').slice(0, 4000);
        const replace = (op.replace ?? '').slice(0, 4000);
        return [
            `File: ${file.path}`,
            `Failure: ${op.reason ?? 'the edit could not be applied safely'}`,
            search
                ? `Rejected SEARCH omitted (${search.length} characters). Do not reconstruct or reuse it; copy a new SEARCH block only from the authoritative current file below.`
                : '',
            replace ? `Intended REPLACE:\n${replace}` : '',
        ].filter(Boolean).join('\n');
    }));
    const currentFiles = [...new Set(files.map(file => file.path))]
        .map(filePath => {
        const content = currentByPath?.get(filePath);
        if (content == null)
            return '';
        const bounded = content.length > 100000
            ? content.slice(0, 100000) + '\n[current file truncated]'
            : content;
        return `CURRENT FILE: ${filePath}\n<<<CURRENT_FILE\n${bounded}\nCURRENT_FILE`;
    })
        .filter(Boolean);
    return [
        'TOOL EDIT RECOVERY. The previous proposed edits were not applied because one or more SEARCH anchors did not match the authoritative current file.',
        'Re-read the authoritative current file contents supplied by the system for the paths below.',
        'Return a corrected complete edit proposal for the same intended changes. Copy every SEARCH block verbatim from the current file and keep each block small and unique.',
        'Do not assume that code from the previous proposal exists. Do not use fuzzy anchors, do not replace an existing file in full, and do not add unrelated changes.',
        'Ignore all earlier assistant code drafts. They describe obsolete file versions.',
        'The CURRENT FILE blocks below were read immediately before this retry. Copy SEARCH text only from these blocks.',
        'This is the only automatic retry, so verify every anchor before responding.',
        '',
        failures.join('\n\n'),
        currentFiles.length ? `\nAUTHORITATIVE CURRENT FILE CONTENTS:\n\n${currentFiles.join('\n\n')}` : '',
        previousDraft ? '\nThe previous proposal is intentionally omitted because its anchors are stale. Preserve only the intended changes described above.' : '',
    ].filter(Boolean).join('\n');
}
export interface DiffLine {
    type: 'ctx' | 'add' | 'del';
    text: string;
}
export interface DiffHunk {
    beforeStart: number;
    afterStart: number;
    lines: DiffLine[];
}
const FENCE_BLOCK_RE = /```[^\n]*\n([\s\S]*?)```/g;
const ANY_FENCE_RE = /```[\s\S]*?```/g;
const PATH_RE = /^(?:#|\/\/)\s*path:\s*(.+)$/;
const SR_BLOCK_RE = /<{5,}\s*SEARCH\s*\n([\s\S]*?)\n={5,}\s*\n([\s\S]*?)\n>{5,}\s*REPLACE/g;
function stripTrailingNewline(s: string): string {
    return s.endsWith('\n') ? s.slice(0, -1) : s;
}
function parseFileBody(path: string, body: string): EditOp[] {
    const ops: EditOp[] = [];
    let m: RegExpExecArray | null;
    SR_BLOCK_RE.lastIndex = 0;
    while ((m = SR_BLOCK_RE.exec(body)) !== null) {
        ops.push({ path, kind: 'replace', search: m[1], replace: m[2] });
    }
    if (ops.length > 0)
        return ops;
    const hasSearchMarker = /[<>=]{3,}\s*SEARCH\b/.test(body);
    const hasReplaceMarker = /[<>=]{3,}\s*REPLACE\b/.test(body);
    if (hasSearchMarker || hasReplaceMarker) {
        return [{ path, kind: 'create', content: stripTrailingNewline(body), malformed: true }];
    }
    return [{ path, kind: 'create', content: stripTrailingNewline(body) }];
}
function parseBareBlocks(text: string): EditOp[] {
    const ops: EditOp[] = [];
    const lines = text.split('\n');
    let currentPath: string | null = null;
    let body: string[] = [];
    const flush = () => {
        if (currentPath !== null) {
            ops.push(...parseFileBody(currentPath, body.join('\n')));
        }
        currentPath = null;
        body = [];
    };
    for (const line of lines) {
        const pathMatch = line.trim().match(PATH_RE);
        if (pathMatch) {
            flush();
            currentPath = pathMatch[1].trim();
            continue;
        }
        if (currentPath !== null) {
            body.push(line);
        }
    }
    flush();
    return ops;
}
export function parseEdits(text: string): EditOp[] {
    text = text.replace(/^[ \t]*((?:#|\/\/)\s*path:\s*.+?)(?:\r?\n)+[ \t]*(```[^\n]*\r?\n)/gm, (_m, pathLine, fenceOpen) => `${fenceOpen}${pathLine}\n`);
    const ops: EditOp[] = [];
    let m: RegExpExecArray | null;
    FENCE_BLOCK_RE.lastIndex = 0;
    while ((m = FENCE_BLOCK_RE.exec(text)) !== null) {
        const body = m[1];
        const lines = body.split('\n');
        const pathMatch = lines[0]?.trim().match(PATH_RE);
        if (!pathMatch)
            continue;
        const path = pathMatch[1].trim();
        const rest = lines.slice(1).join('\n');
        ops.push(...parseFileBody(path, rest));
    }
    const bareText = text.replace(ANY_FENCE_RE, fence => '\n'.repeat(fence.split('\n').length));
    ops.push(...parseBareBlocks(bareText));
    return ops;
}
function normalize(s: string): string {
    return s.split('\n').map(l => l.replace(/\s+/g, ' ').trim()).join('\n').trim();
}
type LocateResult = {
    status: 'found';
    start: number;
    end: number;
    how: 'exact' | 'whitespace' | 'symbol';
} | {
    status: 'missing';
} | {
    status: 'ambiguous';
    count: number;
};
function locate(content: string, search: string): LocateResult {
    if (search.length === 0)
        return { status: 'missing' };
    const exactStarts: number[] = [];
    for (let from = 0;;) {
        const i = content.indexOf(search, from);
        if (i === -1)
            break;
        exactStarts.push(i);
        from = i + Math.max(1, search.length);
    }
    if (exactStarts.length === 1) {
        return { status: 'found', start: exactStarts[0], end: exactStarts[0] + search.length, how: 'exact' };
    }
    if (exactStarts.length > 1)
        return { status: 'ambiguous', count: exactStarts.length };
    const cLines = content.split('\n');
    const sLines = search.split('\n').filter((_, i, a) => !(i === a.length - 1 && a[i] === ''));
    const sNorm = sLines.map(l => l.replace(/\s+/g, ' ').trim());
    if (sNorm.length === 0)
        return { status: 'missing' };
    const wsMatches: {
        start: number;
        end: number;
    }[] = [];
    for (let i = 0; i + sNorm.length <= cLines.length; i++) {
        let ok = true;
        for (let j = 0; j < sNorm.length; j++) {
            if (cLines[i + j].replace(/\s+/g, ' ').trim() !== sNorm[j]) {
                ok = false;
                break;
            }
        }
        if (ok) {
            const start = cLines.slice(0, i).join('\n').length + (i > 0 ? 1 : 0);
            const matchedText = cLines.slice(i, i + sNorm.length).join('\n');
            wsMatches.push({ start, end: start + matchedText.length });
        }
    }
    if (wsMatches.length === 1)
        return { status: 'found', ...wsMatches[0], how: 'whitespace' };
    if (wsMatches.length > 1)
        return { status: 'ambiguous', count: wsMatches.length };
    return { status: 'missing' };
}
function locateUniquePythonSymbol(path: string, content: string, search: string, replace: string): LocateResult {
    if (!path.endsWith('.py'))
        return { status: 'missing' };
    const definition = /^(\s*)(?:(async)\s+)?(def|class)\s+([A-Za-z_]\w*)\b.*:\s*$/;
    const searchDeclaration = search.split('\n').find(line => definition.test(line));
    const replaceDeclaration = replace.split('\n').find(line => definition.test(line));
    if (!searchDeclaration || !replaceDeclaration)
        return { status: 'missing' };
    const searchMatch = searchDeclaration.match(definition);
    const replaceMatch = replaceDeclaration.match(definition);
    if (!searchMatch || !replaceMatch)
        return { status: 'missing' };
    if (searchMatch[2] !== replaceMatch[2] || searchMatch[3] !== replaceMatch[3] || searchMatch[4] !== replaceMatch[4]) {
        return { status: 'missing' };
    }
    const declarationKey = normalize(searchDeclaration);
    const lines = content.split('\n');
    const candidates = lines
        .map((line, index) => ({ line, index }))
        .filter(candidate => normalize(candidate.line) === declarationKey && definition.test(candidate.line));
    if (candidates.length === 0)
        return { status: 'missing' };
    if (candidates.length > 1)
        return { status: 'ambiguous', count: candidates.length };
    const startLine = candidates[0].index;
    const indent = candidates[0].line.match(/^\s*/)?.[0].length ?? 0;
    let boundaryLine = lines.length;
    for (let i = startLine + 1; i < lines.length; i++) {
        if (!lines[i].trim())
            continue;
        const candidateIndent = lines[i].match(/^\s*/)?.[0].length ?? 0;
        const isDefinition = definition.test(lines[i]);
        const isDecorator = lines[i].trimStart().startsWith('@');
        if (candidateIndent <= indent && (isDefinition || isDecorator)) {
            boundaryLine = i;
            break;
        }
    }
    let endLine = boundaryLine;
    while (endLine > startLine + 1 && lines[endLine - 1].trim() === '')
        endLine--;
    const offsets: number[] = [0];
    for (let i = 0; i < lines.length; i++) {
        offsets.push(offsets[i] + lines[i].length + (i < lines.length - 1 ? 1 : 0));
    }
    return { status: 'found', start: offsets[startLine], end: offsets[endLine], how: 'symbol' };
}
export function applyEdits(ops: EditOp[], currentByPath: Map<string, string>, options: ApplyEditOptions = {}): AppliedFile[] {
    const byPath = new Map<string, EditOp[]>();
    for (const op of ops) {
        if (!byPath.has(op.path))
            byPath.set(op.path, []);
        byPath.get(op.path)!.push(op);
    }
    const results: AppliedFile[] = [];
    for (const [path, fileOps] of byPath) {
        const isNew = !currentByPath.has(path);
        const before = currentByPath.get(path) ?? '';
        let working = before;
        const applied: AppliedOp[] = [];
        let idx = 0;
        let failed = 0;
        for (const op of fileOps) {
            if (op.kind === 'create') {
                const content = op.content ?? '';
                if (!isNew) {
                    const reason = op.malformed
                        ? 'edit was malformed or truncated. Existing files must use `<<<<<<< SEARCH` / `=======` / `>>>>>>> REPLACE` blocks; the partial block was not applied.'
                        : 'whole-file replacement of an existing file was refused. Existing files must use SEARCH/REPLACE blocks so unchanged content cannot be lost. Resend the change as an anchored edit.';
                    applied.push({ index: idx, kind: 'replace', ok: false, reason });
                    failed++;
                }
                else {
                    working = content;
                    applied.push({ index: idx, kind: 'create', ok: true, matched: 'whole-file' });
                }
            }
            else {
                const search = op.search ?? '';
                const replace = op.replace ?? '';
                let loc = locate(working, search);
                if (loc.status === 'missing' && options.allowUniquePythonSymbolRebase) {
                    loc = locateUniquePythonSymbol(path, working, search, replace);
                }
                if (loc.status !== 'found') {
                    const reason = loc.status === 'ambiguous'
                        ? `SEARCH anchor matches ${loc.count} places — too ambiguous to place safely; include more surrounding context so it identifies exactly one location`
                        : 'could not locate the SEARCH anchor in the current file';
                    applied.push({ index: idx, kind: 'replace', ok: false, reason, search, replace });
                    failed++;
                }
                else {
                    working = working.slice(0, loc.start) + replace + working.slice(loc.end);
                    applied.push({ index: idx, kind: 'replace', ok: true, matched: loc.how, search, replace });
                }
            }
            idx++;
        }
        results.push({
            path, before, after: working, isNew, ops: applied, failedCount: failed,
            hunks: diffLines(before, working),
        });
    }
    return results;
}
export function applySelected(ops: EditOp[], currentByPath: Map<string, string>, acceptedIndexByPath: Map<string, Set<number>>): AppliedFile[] {
    const byPath = new Map<string, EditOp[]>();
    for (const op of ops) {
        if (!byPath.has(op.path))
            byPath.set(op.path, []);
        byPath.get(op.path)!.push(op);
    }
    const chosen: EditOp[] = [];
    for (const [path, fileOps] of byPath) {
        const accepted = acceptedIndexByPath.get(path);
        fileOps.forEach((op, i) => {
            if (!accepted || accepted.has(i))
                chosen.push(op);
        });
    }
    return applyEdits(chosen, currentByPath);
}
export function looksElided(proposed: string, current: string): boolean {
    return elisionReason(proposed, current) !== null;
}
export function elisionReason(proposed: string, current: string): string | null {
    const placeholderRe = /(\/\*|#|\/\/|<!--)\s*\.{2,}\s*(existing|rest|unchanged|previous|original|same as before|your)|\bexisting (code|styles|content)\b|\brest of (the )?(file|code)\b|(\.\.\.\s*(rest|existing|unchanged))/i;
    if (placeholderRe.test(proposed)) {
        return 'whole-file content has a placeholder like "...existing..." — provide the COMPLETE file, or use precise search/replace edits';
    }
    if (!current || proposed.length >= current.length * 0.30)
        return null;
    const balance = structuralBalance(proposed);
    if (balance.unclosed > 0 || balance.unclosedStrings || /```$/.test(proposed.trim())) {
        return 'the proposed whole-file content is extremely smaller than the current file and appears structurally incomplete; it may have been truncated';
    }
    const oldLines = current.split('\n').map(x => x.trim()).filter(Boolean);
    const newLines = new Set(proposed.split('\n').map(x => x.trim()).filter(Boolean));
    if (oldLines.length >= 12) {
        let overlap = 0;
        for (const line of oldLines)
            if (newLines.has(line))
                overlap++;
        const ratio = overlap / oldLines.length;
        if (ratio < 0.05) {
            return 'the proposed whole-file content is extremely smaller than the current file and shares almost none of its existing structure; it may be an incomplete reconstruction';
        }
    }
    return null;
}
function structuralBalance(text: string): {
    unclosed: number;
    unclosedStrings: boolean;
} {
    const stack: string[] = [];
    let quote: string | null = null;
    let escaped = false;
    let lineComment = false;
    let blockComment = false;
    for (let i = 0; i < text.length; i++) {
        const c = text[i], n = text[i + 1];
        if (lineComment) {
            if (c === '\n')
                lineComment = false;
            continue;
        }
        if (blockComment) {
            if (c === '*' && n === '/') {
                blockComment = false;
                i++;
            }
            continue;
        }
        if (quote) {
            if (escaped) {
                escaped = false;
                continue;
            }
            if (c === '\\') {
                escaped = true;
                continue;
            }
            if (c === quote)
                quote = null;
            continue;
        }
        if (c === '/' && n === '/') {
            lineComment = true;
            i++;
            continue;
        }
        if (c === '/' && n === '*') {
            blockComment = true;
            i++;
            continue;
        }
        if (c === '"' || c === "'" || c === '`') {
            quote = c;
            continue;
        }
        if (c === '{' || c === '(' || c === '[')
            stack.push(c);
        else if (c === '}' || c === ')' || c === ']') {
            const expected = c === '}' ? '{' : c === ')' ? '(' : '[';
            if (stack[stack.length - 1] === expected)
                stack.pop();
            else if (stack.length)
                stack.pop();
        }
    }
    return { unclosed: stack.length, unclosedStrings: quote !== null || blockComment };
}
export function diffLines(before: string, after: string, ctx = 2): DiffHunk[] {
    const a = before.length ? before.split('\n') : [];
    const b = after.length ? after.split('\n') : [];
    const ops = lcsDiff(a, b);
    const hunks: DiffHunk[] = [];
    let cur: DiffLine[] = [];
    let pendingCtx: DiffLine[] = [];
    let beforeStart = 0, afterStart = 0, started = false;
    let ai = 0, bi = 0, curBeforeStart = 0, curAfterStart = 0;
    const flush = () => {
        if (cur.length) {
            hunks.push({ beforeStart: curBeforeStart, afterStart: curAfterStart, lines: cur });
        }
        cur = [];
        started = false;
    };
    for (let k = 0; k < ops.length; k++) {
        const op = ops[k];
        if (op.type === 'ctx') {
            if (started) {
                pendingCtx.push(op);
                if (pendingCtx.length > ctx * 2) {
                    cur.push(...pendingCtx.slice(0, ctx));
                    pendingCtx = [];
                    flush();
                }
            }
            else {
                pendingCtx.push(op);
                if (pendingCtx.length > ctx)
                    pendingCtx.shift();
            }
            ai++;
            bi++;
        }
        else {
            if (!started) {
                const lead = pendingCtx.slice(-ctx);
                curBeforeStart = ai - lead.length;
                curAfterStart = bi - lead.length;
                cur.push(...lead);
                pendingCtx = [];
                started = true;
            }
            else if (pendingCtx.length) {
                cur.push(...pendingCtx);
                pendingCtx = [];
            }
            cur.push({ type: op.type, text: op.text });
            if (op.type === 'del')
                ai++;
            else
                bi++;
        }
    }
    if (started) {
        cur.push(...pendingCtx.slice(0, ctx));
        flush();
    }
    return hunks;
}
interface LcsOp {
    type: 'ctx' | 'add' | 'del';
    text: string;
}
function lcsDiff(a: string[], b: string[]): LcsOp[] {
    const n = a.length, m = b.length;
    const dp: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
    for (let i = n - 1; i >= 0; i--) {
        for (let j = m - 1; j >= 0; j--) {
            dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
        }
    }
    const out: LcsOp[] = [];
    let i = 0, j = 0;
    while (i < n && j < m) {
        if (a[i] === b[j]) {
            out.push({ type: 'ctx', text: a[i] });
            i++;
            j++;
        }
        else if (dp[i + 1][j] >= dp[i][j + 1]) {
            out.push({ type: 'del', text: a[i] });
            i++;
        }
        else {
            out.push({ type: 'add', text: b[j] });
            j++;
        }
    }
    while (i < n) {
        out.push({ type: 'del', text: a[i] });
        i++;
    }
    while (j < m) {
        out.push({ type: 'add', text: b[j] });
        j++;
    }
    return out;
}
export interface Merge3Result {
    ok: boolean;
    text: string;
    conflicts: number;
}
interface Hunk {
    start: number;
    end: number;
    lines: string[];
}
function hunksFromDiff(baseLines: string[], sideLines: string[]): Hunk[] {
    const ops = lcsDiff(baseLines, sideLines);
    const hunks: Hunk[] = [];
    let bi = 0;
    let cur: Hunk | null = null;
    for (const op of ops) {
        if (op.type === 'ctx') {
            if (cur) {
                hunks.push(cur);
                cur = null;
            }
            bi++;
        }
        else if (op.type === 'del') {
            if (!cur)
                cur = { start: bi, end: bi, lines: [] };
            cur.end = bi + 1;
            bi++;
        }
        else {
            if (!cur)
                cur = { start: bi, end: bi, lines: [] };
            cur.lines.push(op.text);
        }
    }
    if (cur)
        hunks.push(cur);
    return hunks;
}
function hunkOverlap(a: Hunk, b: Hunk): boolean {
    if (a.start < b.end && b.start < a.end)
        return true;
    if (a.start === a.end && b.start === b.end && a.start === b.start)
        return true;
    if (a.start === a.end && a.start >= b.start && a.start < b.end)
        return true;
    if (b.start === b.end && b.start >= a.start && b.start < a.end)
        return true;
    return false;
}
function reconstruct(base: string[], hunks: Hunk[], s: number, e: number): string[] {
    const res: string[] = [];
    let p = s;
    for (const h of hunks) {
        res.push(...base.slice(p, h.start));
        res.push(...h.lines);
        p = h.end;
    }
    res.push(...base.slice(p, e));
    return res;
}
function sameLines(a: string[], b: string[]): boolean {
    return a.length === b.length && a.every((x, i) => x === b[i]);
}
export function merge3(base: string, ours: string, theirs: string, labels = { ours: 'target', theirs: 'source' }): Merge3Result {
    if (ours === theirs)
        return { ok: true, text: ours, conflicts: 0 };
    if (ours === base)
        return { ok: true, text: theirs, conflicts: 0 };
    if (theirs === base)
        return { ok: true, text: ours, conflicts: 0 };
    const B = base.length ? base.split('\n') : [];
    const ourH = hunksFromDiff(B, ours.length ? ours.split('\n') : []);
    const theirH = hunksFromDiff(B, theirs.length ? theirs.split('\n') : []);
    const out: string[] = [];
    let i = 0, oi = 0, ti = 0, conflicts = 0;
    while (i < B.length || oi < ourH.length || ti < theirH.length) {
        const oStart = oi < ourH.length ? ourH[oi].start : Infinity;
        const tStart = ti < theirH.length ? theirH[ti].start : Infinity;
        const next = Math.min(oStart, tStart);
        if (i < next && i < B.length) {
            out.push(B[i]);
            i++;
            continue;
        }
        const oh = oi < ourH.length ? ourH[oi] : null;
        const th = ti < theirH.length ? theirH[ti] : null;
        if (oh && th && hunkOverlap(oh, th)) {
            const oTaken: Hunk[] = [oh], tTaken: Hunk[] = [th];
            let s = Math.min(oh.start, th.start);
            let e = Math.max(oh.end, th.end);
            oi++;
            ti++;
            const inRegion = (h: Hunk) => (h.start < e && h.end > s) || (h.start === h.end && h.start >= s && h.start <= e);
            let grew = true;
            while (grew) {
                grew = false;
                while (oi < ourH.length && inRegion(ourH[oi])) {
                    s = Math.min(s, ourH[oi].start);
                    e = Math.max(e, ourH[oi].end);
                    oTaken.push(ourH[oi]);
                    oi++;
                    grew = true;
                }
                while (ti < theirH.length && inRegion(theirH[ti])) {
                    s = Math.min(s, theirH[ti].start);
                    e = Math.max(e, theirH[ti].end);
                    tTaken.push(theirH[ti]);
                    ti++;
                    grew = true;
                }
            }
            if (s === e) {
                const ol = oTaken.flatMap(h => h.lines);
                const tl = tTaken.flatMap(h => h.lines);
                if (sameLines(ol, tl))
                    out.push(...ol);
                else
                    out.push(...ol, ...tl);
            }
            else {
                const ourLines = reconstruct(B, oTaken, s, e);
                const theirLines = reconstruct(B, tTaken, s, e);
                if (sameLines(ourLines, theirLines)) {
                    out.push(...ourLines);
                }
                else {
                    conflicts++;
                    out.push(`<<<<<<< ${labels.ours}`, ...ourLines, '=======', ...theirLines, `>>>>>>> ${labels.theirs}`);
                }
            }
            i = e;
        }
        else if (oStart <= tStart && oh) {
            out.push(...oh.lines);
            i = oh.end;
            oi++;
        }
        else if (th) {
            out.push(...th.lines);
            i = th.end;
            ti++;
        }
        else if (i < B.length) {
            out.push(B[i]);
            i++;
        }
        else
            break;
    }
    return { ok: conflicts === 0, text: out.join('\n'), conflicts };
}
