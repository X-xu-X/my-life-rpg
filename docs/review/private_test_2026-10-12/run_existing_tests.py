"""Run existing suites with disposable DBs; never enable optional external integrations."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
OUT = Path(__file__).resolve().parent
for name in ('TEST_PG_URL', 'TEST_CADDY_BIN', 'TEST_RESTIC_BIN'):
    os.environ.pop(name, None)
with tempfile.TemporaryDirectory(dir=OUT, prefix='isolated_') as tmp:
    assert Path(tmp).resolve().is_relative_to(OUT.resolve())
    os.environ.update(DB_URL='sqlite:///' + str(Path(tmp) / 'unused-default.sqlite3'),
        RUN_MODE='local', DEEPSEEK_API_KEY='', PUBLIC_ORIGIN='https://rpg.test')
    started = time.monotonic()
    suite = unittest.defaultTestLoader.discover('tests', pattern='test_*.py')
    with (OUT / 'unittest.log').open('w', encoding='utf-8') as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    summary = dict(tests_run=result.testsRun,
        passed=result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
        failures=len(result.failures), errors=len(result.errors),
        skipped=[dict(test=str(test), reason=reason) for test,reason in result.skipped],
        elapsed_seconds=round(time.monotonic()-started, 2), successful=result.wasSuccessful(),
        scope='Disposable SQLite fixtures, synthetic model responses; optional PostgreSQL/Caddy/restic integrations disabled',
        failing_tests=[str(test) for test,_ in result.failures+result.errors])
    (OUT / 'unittest-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    sys.exit(0 if result.wasSuccessful() else 1)
