"""Mechanism test on an isolated restored database; no real model requests."""
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run():
    if os.environ.get('LIFEXP_ISOLATED_REHEARSAL') != 'reward-repair-copy-only':
        raise ValueError('ISOLATED_REHEARSAL_REQUIRED')
    from app.database import SessionLocal
    from app.services.llm_service import llm_service
    from app.models import AttributeHistory, CoinLedger
    from app.models.workflow import FactSettlement
    from ops.cloud_update_snapshot import capture
    from ops import repair_confirmed_rewards as repair
    def blocked(*args, **kwargs):
        raise ValueError('REAL_MODEL_FORBIDDEN_IN_REHEARSAL')
    llm_service.chat = llm_service.chat_json = blocked
    before = capture()
    with SessionLocal() as db:
        user, snapshot, targets = repair.inspect_source(db, '旭旭仔', 3, 35, 24)
        uid = user.id
        original_settlements = [(r.id, r.fact_id, r.judgment_id) for r in db.query(FactSettlement).filter_by(user_id=uid).order_by(FactSettlement.id)]
        old_history = db.query(AttributeHistory).filter_by(user_id=uid).count()
        old_balance = snapshot['balance']
        def synthetic_model(messages, **kwargs):
            # Exercise bookkeeping only. Real compensation uses the person's model.
            data = json.loads(messages[-1]['content'])
            name = next(a['name'] for a in data['allowed_attributes'] if a['name'] == '智力')
            return {'facts': [{'fact_id': f['fact_id'], 'changes': [
                {'name': name, 'delta': .1, 'reason': '隔离副本账务机制测试', 'evidence': f['excerpt']}]} for f in data['facts']]}
        plan = repair.assess(db, '旭旭仔', 3, 35, 24, call=synthetic_model)
        result = repair.apply(db, plan, repair.digest(plan))
        assert result['coins_added'] == 24 and result['balance'] == old_balance + 24
        assert db.query(AttributeHistory).filter_by(user_id=uid).count() == old_history + 4
        assert db.query(CoinLedger).filter_by(user_id=uid, ref_type='reward_repair').count() == 4
        assert [(r.id, r.fact_id, r.judgment_id) for r in db.query(FactSettlement).filter_by(user_id=uid).order_by(FactSettlement.id)] == original_settlements
        again = repair.apply(db, plan, repair.digest(plan))
        assert again['replayed'] and db.query(CoinLedger).filter_by(user_id=uid, ref_type='reward_repair').count() == 4
    return {'status': 'ISOLATED_PG_REHEARSAL_PASS', 'head': before['head'],
            'restored_tables': len(before['tables']), 'credential_rows_checked': before['credential_rows_checked'],
            'application_role': 'gol_app', 'repair_coins_on_copy': 24,
            'repair_attribute_rows_on_copy': 4, 'same_plan_replay': 'PASS',
            'fact_settlement_ids_preserved': True, 'real_supplier': 'NOT_CALLED',
            'production_database_connection': 'NONE'}


if __name__ == '__main__':
    try:
        print(json.dumps(run(), ensure_ascii=False))
    except Exception as exc:
        code = str(exc) if type(exc) is ValueError and str(exc).replace('_', '').isupper() else type(exc).__name__
        print(json.dumps({'status': 'REHEARSAL_STOPPED', 'code': code}))
        raise SystemExit(2)
