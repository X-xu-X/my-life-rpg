import os
os.environ.pop('TEST_PG_URL',None)
os.environ['DB_URL']='sqlite://'
os.environ['DEEPSEEK_API_KEY']=''
import contextlib,json,unittest
from pathlib import Path
root=Path('docs/review/continuation_2026-10-16')
root.mkdir(parents=True,exist_ok=True)
names=['tests.test_continuation','tests.test_trial_p1','tests.test_next_iteration','tests.test_v1_11_safety','tests.test_ops_next']
with (root/'test-log.txt').open('w',encoding='utf-8') as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names))
report={'status':'PASS' if result.wasSuccessful() else 'FAIL','run':result.testsRun,
        'passed':result.testsRun-len(result.skipped)-len(result.failures)-len(result.errors),
        'skipped':[reason for test,reason in result.skipped],'failures':len(result.failures),'errors':len(result.errors),
        'modules':names,'database':'isolated synthetic SQLite; TEST_PG_URL disabled','supplier':'doubles only','independent_postgres':'NOT_RUN'}
(root/'test-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=True));raise SystemExit(0 if result.wasSuccessful() else 1)
