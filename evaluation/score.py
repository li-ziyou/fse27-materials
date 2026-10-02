from pathlib import Path
import concurrent.futures
import csv
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent

def score(row):
    bundle = ROOT / 'evaluation/tasks' / row['task']
    result = {key: row[key] for key in ['participant', 'period', 'condition', 'task', 'form']}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        code = tmp / 'code'
        shutil.copytree(bundle / 'baseline', code)
        shutil.copytree(ROOT / row['snapshot'], code, dirs_exist_ok=True)
        env = dict(os.environ, PYTHONPATH=str(code), CONTEXTBRANCH_STUDY_FORM_ID=row['form'], PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONDONTWRITEBYTECODE='1')
        for suite in ['private', 'public']:
            tests = bundle / (suite + '_tests')
            report = tmp / 'results.xml'
            command = [sys.executable, '-m', 'pytest', str(tests), '-q', '-p', 'no:cacheprovider', '--junitxml=' + str(report)]
            try:
                run = subprocess.run(command, cwd=code, env=env, capture_output=True, timeout=20)
                cases = list(ET.parse(report).iter('testcase')) if report.exists() else []
                passed = sum(not any(c.find(tag) is not None for tag in ['failure', 'error', 'skipped']) for c in cases) if run.returncode in [0, 1] else 0
            except subprocess.TimeoutExpired:
                collect = subprocess.run([sys.executable, '-m', 'pytest', str(tests), '--collect-only', '-q', '-p', 'no:cacheprovider'], cwd=code, env=env, capture_output=True, text=True, timeout=20)
                targets = [line.strip() for line in collect.stdout.splitlines() if '::test_' in line and not line.startswith(' ')]
                passed = 0
                for target in targets:
                    relative = target.split('::')[0]
                    file = next(tests.rglob(Path(relative).name))
                    node = str(file) + '::' + target.split('::', 1)[1]
                    try:
                        run = subprocess.run([sys.executable, '-m', 'pytest', node, '-q', '-p', 'no:cacheprovider'], cwd=code, env=env, capture_output=True, timeout=5)
                        passed += run.returncode == 0
                    except subprocess.TimeoutExpired:
                        pass
            result[suite + '_passed'] = passed
            result[suite + '_total'] = int(row[suite + '_total'])
            result[suite + '_rate'] = passed / result[suite + '_total']
    return result

if __name__ == '__main__':
    with (ROOT / 'snapshots/index.csv').open() as f:
        rows = list(csv.DictReader(f))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        scores = list(pool.map(score, rows))
    with (ROOT / 'evaluation/scores.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(scores[0]))
        writer.writeheader()
        writer.writerows(scores)
    print('Scored', len(scores), 'sessions; output: evaluation/scores.csv')
