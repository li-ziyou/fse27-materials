const esbuild = require('esbuild');
const production = process.argv.includes('--production');
const watch = process.argv.includes('--watch');
const config = {
    entryPoints: ['src/extension.ts'],
    bundle: true,
    format: 'cjs',
    minify: production,
    sourcemap: !production,
    sourcesContent: false,
    platform: 'node',
    outfile: 'dist/extension.js',
    external: ['vscode'],
    logLevel: 'info'
};
async function main() {
    if (watch) {
        const ctx = await esbuild.context(config);
        await ctx.watch();
        console.log('Watching for changes...');
    }
    else {
        await esbuild.build(config);
        console.log('Build complete.');
    }
}
main().catch(err => {
    console.error(err);
    process.exit(1);
});
