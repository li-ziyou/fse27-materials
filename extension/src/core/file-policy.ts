const PROTECTED_TEST_DIRECTORIES = new Set(['test', 'tests', '__tests__']);
export function isProtectedPath(relativePath: string): boolean {
    return relativePath.replace(/\\/g, '/').split('/')
        .some(segment => PROTECTED_TEST_DIRECTORIES.has(segment.toLowerCase()));
}
export function protectedPathReason(relativePath: string): string {
    return `${relativePath} is inside a protected test directory; tests are not available to the coding agent.`;
}
