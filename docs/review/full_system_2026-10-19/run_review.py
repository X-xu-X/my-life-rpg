"""Independent review run: synthetic DB only, preserve Writer evidence."""
import os
import sys
import json
import contextlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.environ['DB_URL'] = 'sqlite://'
os.environ['DEEPSEEK_API_KEY'] = ''
os.environ.pop('TEST_PG_URL', None)
HERE = Path(__file__).resolve().parent
names = ['tests.test_full_system', 'tests.test_continuation', 'tests.test_trial_p1',
         'tests.test_next_iteration', 'tests.test_v1_11_safety', 'tests.test_ops_next']
with (HERE/'backend-tests.log').open('w', encoding='utf-8') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names))
report = {'status': 'PASS' if result.wasSuccessful() else 'FAIL', 'run': result.testsRun,
          'passed': result.testsRun-len(result.skipped)-len(result.failures)-len(result.errors),
          'skipped': [str(t)+': '+why for t, why in result.skipped],
          'failures': [str(t) for t, _ in result.failures], 'errors': [str(t) for t, _ in result.errors],
          'scope': 'Independent synthetic SQLite run; no real DB, supplier, SMTP or lifespan'}
(HERE/'backend-results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=True))
raise SystemExit(0 if result.wasSuccessful() else 1)
