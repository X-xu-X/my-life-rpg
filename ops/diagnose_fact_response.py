"""One bounded replay of the installed fact prompt, stopped before all fact writes.

No original/model text is printed or retained. All business sessions are read-only.
The normal model usage counter may increment once; the provider may charge once.
This diagnoses a NEW response, not the lost response from the historical failure.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace

sys.path.insert(0, os.getcwd())

EXPECTED_SOURCE_SHA256 = 'bb8dc7125f4e7e768b251c0896d7a588d70ee3ab0066e68f21756582fe533a60'


def check(condition, code):
    if not condition:
        raise ValueError(code)


def kind(value):
    return type(value).__name__


def safe_path(location):
    known = {'facts', 'questions', 'excerpt', 'summary', 'grade', 'changes', 'confidence',
             'relation', 'related_event_id', 'related_fact_id', 'reason', 'goal_id', 'effort',
             'source_kind', 'source_id', 'name', 'delta', 'evidence', 'mainline'}
    return [v if type(v) is int or (isinstance(v, str) and v in known)
            else 'unknown_field' for v in location]


def validate_response(result, inputs, suggestion_model, *, event_valid, fact_valid):
    """Mirror the installed validators; metadata only, never include error inputs."""
    from pydantic import ValidationError
    report = {'response_type': kind(result), 'issues': []}
    issues = report['issues']
    if not isinstance(result, dict):
        issues.append({'stage': 'schema', 'code': 'ROOT_NOT_OBJECT'})
        return report
    report['recognized_keys'] = [key for key in ('facts', 'questions', 'affected_attributes', 'analysis', 'summary') if key in result]
    report['other_key_count'] = len(set(result) - set(report['recognized_keys']))
    raw = result.get('facts')
    report['facts_type'] = kind(raw)
    report['facts_count'] = len(raw) if isinstance(raw, list) else None
    if not isinstance(raw, list) or len(raw) > 20:
        issues.append({'stage': 'schema', 'code': 'FACTS_LIST_REQUIRED_MAX_20'})
        return report
    proposals = []
    for index, item in enumerate(raw):
        try:
            proposals.append((index, suggestion_model.model_validate(item)))
        except ValidationError as exc:
            issues.extend({'stage': 'schema', 'fact_index': index,
                           'field': safe_path(error['loc']), 'code': error['type']}
                          for error in exc.errors()[:20])
    questions = result.get('questions', [])
    if not isinstance(questions, list) or len(questions) > 3 or any(
            not isinstance(q, str) or not q.strip() or len(q) > 1000 for q in questions):
        issues.append({'stage': 'schema', 'field': ['questions'], 'code': 'QUESTIONS_INVALID'})
    if issues:
        return report
    seen = set()
    for index, proposal in proposals:
        source = (inputs['original'] if proposal.source_kind == 'original' and
                  proposal.source_id in (None, inputs['event_id']) else next(
                    (row['content'] for row in inputs.get('related_sources', [])
                     if row['kind'] == proposal.source_kind and row['id'] == proposal.source_id), None))
        signature = (proposal.source_kind, proposal.source_id, proposal.excerpt)
        if source is None:
            issues.append({'stage': 'source', 'fact_index': index, 'code': 'SOURCE_NOT_FOUND'})
        elif proposal.excerpt not in source:
            whitespace_match = ''.join(proposal.excerpt.split()) in ''.join(source.split())
            issues.append({'stage': 'source', 'fact_index': index, 'code': 'EXCERPT_NOT_EXACT',
                           'matches_after_removing_whitespace': whitespace_match})
        if signature in seen:
            issues.append({'stage': 'source', 'fact_index': index, 'code': 'DUPLICATE_SOURCE_EXCERPT'})
        seen.add(signature)
        if proposal.related_event_id and not event_valid(proposal.related_event_id):
            issues.append({'stage': 'relation', 'fact_index': index, 'code': 'RELATED_EVENT_INVALID'})
        elif not proposal.related_event_id and proposal.related_fact_id and not fact_valid(proposal.related_fact_id):
            issues.append({'stage': 'relation', 'fact_index': index, 'code': 'RELATED_FACT_INVALID'})
    report['checked_to'] = 'pre-write schema, source excerpt and related-ID checks'
    return report


class Captured(Exception):
    def __init__(self, report):
        self.report = report


def run(event_id, username):
    from sqlalchemy import event as sql_event, text
    from sqlalchemy.orm import Session, sessionmaker
    from app.database import SessionLocal
    from app.models import Event, User
    from app.models.workflow import FactIdentity
    from app.services import fact_analysis, llm_config
    from app.services.llm_service import llm_service, CALL_GUARD, USAGE_FACTORY, LAST_DIAGNOSTIC, LLMError
    from app.services.model_validation import controlled_error, provenance

    source_sha = hashlib.sha256(Path(fact_analysis.__file__).read_bytes()).hexdigest()
    check(source_sha == EXPECTED_SOURCE_SHA256, 'INSTALLED_SOURCE_CHANGED_STOP')
    with SessionLocal() as ordinary:
        engine = ordinary.get_bind()
    check(engine.dialect.name == 'postgresql', 'PRODUCTION_POSTGRESQL_REQUIRED')

    class ReadOnlySession(Session):
        pass

    @sql_event.listens_for(ReadOnlySession, 'after_begin')
    def read_only(db, transaction, connection):
        connection.execute(text('SET TRANSACTION READ ONLY'))

    factory = sessionmaker(bind=engine, class_=ReadOnlySession, autoflush=False)
    sends = 0
    transport = []
    stamp = {}
    original_json, original_chat = llm_service.chat_json, llm_service.chat

    def guard():
        nonlocal sends
        if sends:
            raise LLMError('MODEL_ATTEMPT_LIMIT')
        sends += 1

    def trace_chat(*args, **kwargs):
        raw = None
        try:
            raw = original_chat(*args, **kwargs)
            return raw
        finally:
            value = LAST_DIAGNOSTIC.get()
            if isinstance(value, dict):
                metadata = {k: value[k] for k in ('http_status', 'finish_reason', 'content_empty', 'has_other_output', 'usage') if k in value}
                if isinstance(raw, str):
                    try:
                        parsed = llm_service._parse_json(raw)
                        metadata['json_object_parseable'] = True
                        metadata['empty_json_object'] = not bool(parsed)
                    except LLMError:
                        metadata['json_object_parseable'] = False
                transport.append(metadata)

    with factory() as db:
        record = db.get(Event, event_id)
        check(record is not None, 'EVENT_NOT_FOUND')
        user = db.get(User, record.user_id)
        check(user.username == username and user.status == 'active', 'EVENT_OWNER_MISMATCH')
        check(record.ai_permission == 'allowed' and not record.is_deleted and not record.is_pure, 'EVENT_NOT_AUTHORIZED')
        db.info['user_id'] = user.id
        baseline = (record.content_version, record.ai_permission_version)
        owner_id = user.id

        def event_valid(identifier):
            row = db.get(Event, identifier)
            return bool(row and row.user_id == owner_id and row.record_kind != 'diary')

        def fact_valid(identifier):
            row = db.get(FactIdentity, identifier)
            return bool(row and row.user_id == owner_id)

        def intercepted(messages, *, config=None, **kwargs):
            stamp.update(provenance(config))
            inputs = json.loads(messages[-1]['content'])
            inputs['event_id'] = event_id
            result = original_json(messages, config=config, **kwargs)
            db.expire_all()
            current = db.get(Event, event_id)
            check(current.ai_permission == 'allowed' and not current.is_deleted and
                  (current.content_version, current.ai_permission_version) == baseline, 'SOURCE_CHANGED_DURING_CALL')
            llm_config.assert_current(db, config)
            report = validate_response(result, inputs, fact_analysis.Suggestion,
                                       event_valid=event_valid, fact_valid=fact_valid)
            # Always abort here, even if valid. Nothing after chat_json() in the
            # installed generate() executes; no facts, settings or awards created.
            raise Captured(report)

        guard_token = CALL_GUARD.set(guard)
        usage_token = USAGE_FACTORY.set(SessionLocal)
        llm_service.chat_json, llm_service.chat = intercepted, trace_chat
        try:
            job = SimpleNamespace(event_id=event_id, user_id=owner_id)
            fact_analysis.generate(db, job, lambda db: None)
            raise RuntimeError('DIAGNOSTIC_STOP_NOT_REACHED')
        except Captured as exc:
            result = {'status': 'DIAGNOSTIC_COMPLETE', 'current_response': exc.report}
        except LLMError as exc:
            code = str(exc).split('：', 1)[0]
            result = {'status': 'DIAGNOSTIC_STOPPED', 'safe_error_code':
                      code if code == 'MODEL_ATTEMPT_LIMIT' else controlled_error(exc)[0]}
        except Exception as exc:
            code = str(exc) if isinstance(exc, ValueError) and re.fullmatch(r'[A-Z_]{1,80}', str(exc)) else type(exc).__name__
            result = {'status': 'DIAGNOSTIC_STOPPED', 'code': code}
        finally:
            db.rollback()
            llm_service.chat_json, llm_service.chat = original_json, original_chat
            CALL_GUARD.reset(guard_token)
            USAGE_FACTORY.reset(usage_token)
    return {**result, 'event_id': event_id, 'installed_source_sha256': source_sha,
            'model': stamp, 'dispatches_allowed_by_guard': sends, 'max_supplier_calls': 1, 'transport': transport,
            'business_data_changed': False, 'model_usage_counter_may_increment': bool(sends),
            'historical_failure_recovered': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--event-id', type=int, default=36)
    parser.add_argument('--username', default='旭旭仔')
    parser.add_argument('--once', action='store_true', help='One supplier call may incur a charge; no booking')
    args = parser.parse_args()
    check(args.once, 'EXPLICIT_ONCE_FLAG_REQUIRED')
    print(json.dumps(run(args.event_id, args.username), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        code = str(exc) if isinstance(exc, ValueError) and re.fullmatch(r'[A-Z_]{1,80}', str(exc)) else type(exc).__name__
        print(json.dumps({'status': 'DIAGNOSTIC_STOPPED', 'code': code}), file=sys.stderr)
        sys.exit(1)
