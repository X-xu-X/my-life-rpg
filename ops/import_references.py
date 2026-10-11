"""Legacy semantic references: explicit JSON columns and fields, never arbitrary integers.

Producers: challenge_service Event.params._challenge_id; judge_service JudgmentLog
payload (delete source_history_ids/reversed_changes, reject event_id, exemption.id);
audit extensions use explicit *_id / *_ids in judgment_logs.payload and goals.audit.
merged_with.ref is historical display text, not an executable object identity.
"""
SCALAR = {'event_id':'events', 'judgment_id':'ai_judgments', 'attribute_id':'attributes',
    'goal_id':'goals', 'item_id':'checkin_items', 'challenge_id':'challenges',
    'shop_item_id':'shop_items', 'redemption_id':'redemptions', 'exemption_id':'exemptions',
    'achievement_id':'achievements'}
ARRAY = {key[:-3]+'_ids':table for key, table in SCALAR.items()}
ARRAY['source_history_ids'] = 'attribute_history'
LEDGER = {'event':'events', 'challenge':'challenges', 'shop_item':'shop_items',
    'achievement':'achievements', 'exemption':'exemptions'}
AUDIT_COLUMNS = {('judgment_logs','payload'), ('goals','audit')}


def transform(table, column, value, resolve):
    def visit(item, path, context=''):
        if isinstance(item, dict):
            result = {}
            for key, child in item.items():
                child_path = f'{path}.{key}'
                target = SCALAR.get(key)
                if key == 'id' and context == 'exemption': target = 'exemptions'
                if target and child is not None:
                    result[key] = resolve(target, child, child_path)
                elif key in ARRAY and isinstance(child, list):
                    result[key] = [resolve(ARRAY[key], ident, f'{child_path}[{i}]') for i,ident in enumerate(child)]
                else:
                    result[key] = visit(child, child_path, key)
            return result
        if isinstance(item, list): return [visit(child, f'{path}[{i}]', context) for i,child in enumerate(item)]
        return item
    if (table, column) in AUDIT_COLUMNS: return visit(value, column)
    if (table, column) == ('events', 'params') and isinstance(value, dict) and '_challenge_id' in value:
        return {**value, '_challenge_id':resolve('challenges', value['_challenge_id'], 'params._challenge_id')}
    return value


def audit(data, mappers):
    from sqlalchemy import JSON
    import json
    indexed = {name:{row['id']:row for row in rows} for name,rows in data.items()}
    issues, count = [], 0
    for name, rows in data.items():
        for row in rows:
            def check(target, old, path):
                nonlocal count
                count += 1
                found = indexed.get(target, {}).get(old) if type(old) is int else None
                reason = 'NON_FK_MISSING_REFERENCE' if found is None else (
                    'NON_FK_CROSS_USER_REFERENCE' if row.get('user_id') != found.get('user_id') else None)
                if reason: issues.append({'table':name,'id':row['id'],'path':path,
                    'target_table':target,'referenced_id':old if type(old) is int else None,
                    'value_type':type(old).__name__,'reason':reason})
                return old
            for column in mappers[name].__table__.columns:
                if isinstance(column.type, JSON) and row.get(column.name) is not None:
                    value = row[column.name]
                    try: value = json.loads(value) if isinstance(value,str) else value
                    except (ValueError, TypeError): continue  # Type validation reports this separately.
                    transform(name, column.name, value, check)
            if name == 'coin_ledger' and row.get('ref_id') is not None:
                target = LEDGER.get(row.get('ref_type'))
                if target: check(target, row['ref_id'], 'ref_id')
                else: issues.append({'table':name,'id':row['id'],'path':'ref_type', 'reason':'UNKNOWN_LEDGER_REFERENCE_TYPE'})
    return issues, count
