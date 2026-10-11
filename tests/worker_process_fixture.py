"""Test-only adapter around the real worker entrypoint. No production test switches."""
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    config=json.load(sys.stdin)
    from app import worker
    from app.services import judge_service
    from app.services.llm_service import llm_service
    root=Path(config['root'])
    def barrier(stage):
        if config['stage']!=stage:return
        (root/'phase').write_text(stage)
        while not (root/'continue').exists():time.sleep(.02)
    # Only redirect the heartbeat location; init_db, claim, process, reservations and DB locks are real.
    worker.Path=lambda _:root/'heartbeat'
    original_claim=worker.claim
    def claim(factory):
        result=original_claim(factory)
        if result:barrier('claimed')
        return result
    worker.claim=claim
    original_process=worker.process
    def process(factory,claimed):
        original_process(factory,claimed)
        worker.stopping=True
    worker.process=process
    def create(**kwargs):
        barrier('request')
        payload={'event_type':'positive','category':'运动','confidence':1,'summary':'synthetic worker',
            'suggested_changes':[{'name':'健康','delta':1,'reason':'synthetic','evidence':'synthetic'}], 'analysis':[]}
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])
    llm_service._get_client=lambda config=None:SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)),close=lambda:None)
    original_judge=judge_service.judge_event
    def judge(*args,**kwargs):
        validate=kwargs['before_write']
        def before_write(db):validate(db);barrier('before_write')
        kwargs['before_write']=before_write
        return original_judge(*args,**kwargs)
    judge_service.judge_event=judge
    worker.main()


if __name__=='__main__':main()
