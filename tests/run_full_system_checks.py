"""Repeatable synthetic acceptance; never reads DB_URL/keys from the real deployment."""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['DB_URL']='sqlite://'
os.environ['DEEPSEEK_API_KEY']=''
os.environ.pop('TEST_PG_URL',None)
import contextlib,json,unittest,argparse
parser=argparse.ArgumentParser()
parser.add_argument('--repairs',action='store_true')
parser.add_argument('--daily-use',action='store_true')
parser.add_argument('--output',default='docs/review/full_system_2026-10-18')
args=parser.parse_args()
root=Path(args.output);root.mkdir(parents=True,exist_ok=True)
os.environ['FULL_SYSTEM_EVIDENCE_DIR']=str(root)
names=['tests.test_full_system','tests.test_continuation','tests.test_trial_p1','tests.test_next_iteration','tests.test_v1_11_safety','tests.test_ops_next','tests.test_account_identity']
if args.repairs:names.append('tests.test_review_repairs')
if args.daily_use:names.append('tests.test_daily_use_redesign')
with (root/'backend-tests.log').open('w',encoding='utf-8') as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names))
report={'status':'PASS' if result.wasSuccessful() else 'FAIL','run':result.testsRun,
    'passed':result.testsRun-len(result.skipped)-len(result.failures)-len(result.errors),'skipped':[str(t)+': '+why for t,why in result.skipped],
    'failures':[str(t) for t,why in result.failures],'errors':[str(t) for t,why in result.errors],
    'database':'synthetic SQLite; no application lifespan or real data','real_postgres':'NOT_RUN','real_supplier':'NOT_RUN','real_mail':'NOT_RUN'}
(root/'backend-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=True));raise SystemExit(0 if result.wasSuccessful() else 1)
