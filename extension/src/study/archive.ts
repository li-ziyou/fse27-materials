import * as fs from 'fs';
import * as path from 'path';
import * as crypto from 'crypto';
import archiver from 'archiver';
import { StudyArchive, StudyFinishedRecord, StudyRunFile } from './types';
interface ArchiveSessionMetadata {
    schemaVersion: 1;
    archiveKind: 'contextbranch-study2';
    run: {
        runId: string;
        participantId: string;
        sequenceId: string;
        period: 1 | 2;
        taskId: string;
        formId: string;
        condition: StudyRunFile['condition'];
        createdAt: string;
        startedAt: string | null;
        timeLimitSeconds: number;
        model: StudyRunFile['model'];
        manifest: StudyRunFile['manifest'];
    };
    finished: StudyFinishedRecord;
}
function safeFileSegment(value: string): string {
    const normalized = value.replace(/[^A-Za-z0-9._-]+/g, '-').replace(/-+/g, '-');
    return normalized.replace(/^-|-$/g, '') || 'unknown';
}
export function studyArchiveFileName(run: StudyRunFile): string {
    return [
        safeFileSegment(run.participantId),
        safeFileSegment(run.taskId),
        safeFileSegment(run.condition),
        String(run.period),
    ].join('_') + '.zip';
}
export function defaultStudyExportDirectory(workspaceRoot: string): string {
    return path.join(path.dirname(path.dirname(workspaceRoot)), 'participant-exports');
}
export async function createStudyArchive(workspaceRoot: string, run: StudyRunFile, finished: StudyFinishedRecord): Promise<StudyArchive> {
    const exportDirectory = run.exportDirectory || defaultStudyExportDirectory(workspaceRoot);
    const fileName = studyArchiveFileName(run);
    const filePath = path.join(exportDirectory, fileName);
    if (fs.existsSync(filePath))
        return { filePath, fileName, created: false };
    fs.mkdirSync(exportDirectory, { recursive: true });
    const temporaryPath = path.join(exportDirectory, `.${fileName}.${crypto.randomBytes(8).toString('hex')}.tmp`);
    const metadata: ArchiveSessionMetadata = {
        schemaVersion: 1,
        archiveKind: 'contextbranch-study2',
        run: {
            runId: run.runId,
            participantId: run.participantId,
            sequenceId: run.sequenceId,
            period: run.period,
            taskId: run.taskId,
            formId: run.formId ?? 'F1',
            condition: run.condition,
            createdAt: run.createdAt,
            startedAt: run.startedAt,
            timeLimitSeconds: run.timeLimitSeconds,
            model: run.model,
            manifest: run.manifest,
        },
        finished,
    };
    try {
        await new Promise<void>((resolve, reject) => {
            const output = fs.createWriteStream(temporaryPath);
            const zip = archiver('zip', { zlib: { level: 9 } });
            let settled = false;
            const fail = (error: Error) => {
                if (settled)
                    return;
                settled = true;
                reject(error);
            };
            output.on('close', () => {
                if (!settled) {
                    settled = true;
                    resolve();
                }
            });
            output.on('error', fail);
            zip.on('warning', (error) => {
                if ((error as NodeJS.ErrnoException).code !== 'ENOENT')
                    fail(error);
            });
            zip.on('error', fail);
            zip.pipe(output);
            zip.append(JSON.stringify(metadata, null, 2) + '\n', { name: 'metadata/session.json' });
            zip.append(JSON.stringify(finished, null, 2) + '\n', { name: 'metadata/finished.json' });
            const ticketPath = path.join(workspaceRoot, '.study', 'TASK.md');
            if (fs.existsSync(ticketPath))
                zip.file(ticketPath, { name: 'task/TASK.md' });
            const contextBranchDirectory = path.join(workspaceRoot, '.contextbranch');
            if (fs.existsSync(contextBranchDirectory))
                zip.directory(contextBranchDirectory, 'contextbranch');
            for (const relativePath of run.manifest.submission.allowedProductionPaths) {
                const sourcePath = path.join(workspaceRoot, relativePath);
                if (!fs.existsSync(sourcePath)) {
                    fail(new Error(`Cannot archive missing production file: ${relativePath}`));
                    return;
                }
                zip.file(sourcePath, { name: path.posix.join('submission', 'main', relativePath) });
            }
            void zip.finalize();
        });
        fs.renameSync(temporaryPath, filePath);
        return { filePath, fileName, created: true };
    }
    catch (error) {
        fs.rmSync(temporaryPath, { force: true });
        throw error;
    }
}
