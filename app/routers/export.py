"""数据导出路由（个人数据主权，PRD 4.7）。

GET /api/export?format=json → 完整数据 JSON
GET /api/export?format=csv  → 事件列表 CSV
"""
from app.services.time_service import clock_now
import csv
import io
from datetime import datetime, date
from typing import Literal
from app import models

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AIJudgment, Anchor, Attribute, AttributeHistory, Event, Goal
from app.services.user_service import get_or_create_default_user
from app.services.auth_service import require_owner

router = APIRouter()


def _dt(v):
    """datetime 转字符串（JSON 可序列化）。"""
    return v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v


def _event(e: Event) -> dict:
    return {
        "id": e.id,
        "event_type": e.event_type,
        "category": e.category,
        "source": e.source,
        "title": e.title,
        "params": e.params,
        "content": e.content,
        "occurred_at": _dt(e.occurred_at),
        "occurred_on": e.occurred_on,
        "time_precision": e.time_precision,
        "created_at": _dt(e.created_at),
        "saved_on":e.saved_on,"saved_timezone":e.saved_timezone,
    }


def _collect_legacy(db: Session, user_id: int) -> dict:
    """收集用户全部数据。"""
    events = db.query(Event).filter(Event.user_id == user_id).order_by(Event.created_at).all()
    attrs = db.query(Attribute).filter(Attribute.user_id == user_id).all()
    history = db.query(AttributeHistory).filter(AttributeHistory.user_id == user_id).order_by(AttributeHistory.created_at).all()
    goals = db.query(Goal).filter(Goal.user_id == user_id).all()
    judgments = db.query(AIJudgment).filter(AIJudgment.user_id == user_id).order_by(AIJudgment.created_at).all()
    from app.services.anchor_service import list_anchors
    anchors = list_anchors(db)

    return {
        "exported_at": _dt(clock_now()),
        "events": [_event(e) for e in events],
        "attributes": [
            {"name": a.name, "value": a.current_value, "description": a.description} for a in attrs
        ],
        "attribute_history": [
            {
                "attribute_id": h.attribute_id,
                "delta": h.delta,
                "value_after": h.value_after,
                "reason": h.reason,
                "evidence": h.evidence,
                "created_at": _dt(h.created_at),
            }
            for h in history
        ],
        "goals": [
            {
                "id": g.id,
                "description": g.description,
                "metric": g.metric,
                "deadline": _dt(g.deadline),
                "related_attribute": g.related_attribute,
                "status": g.status,
                "audit": g.audit,
                "created_at": _dt(g.created_at),
            }
            for g in goals
        ],
        "judgments": [
            {
                "id": j.id,
                "event_id": j.event_id,
                "status": j.status,
                "suggested_changes": j.suggested_changes,
                "analysis": j.analysis,
                "final_changes": j.final_changes,
                "summary": j.summary,
                "confidence": j.confidence,
                "created_at": _dt(j.created_at),
            }
            for j in judgments
        ],
        "anchors": [
            {
                "name": a.name,
                "base_value": a.base_value,
                "unit": a.unit,
                "base_delta": a.base_delta,
                "calibrated_value": a.calibrated_value,
                "evidence": a.evidence,
            }
            for a in anchors
        ],
    }


EXPORT_WORKFLOW_TABLES = ['diary_revisions','review_sessions','review_turns','review_analyses','life_checklists','plan_schedules','plan_occurrences','fact_identities','event_facts','fact_settlements','fact_relations','mainlines','reward_previews','mainline_awards','dynamic_candidates','dynamic_awards','ai_preferences']
FULL_SYSTEM_TABLES=['trial_accounts','daily_entitlements','fact_fragments','fact_bundles','fact_notes','action_awards','care_configs','care_items','care_entries','pricing_quotes','pricing_checks','voucher_allowances','time_sessions','personal_phases','holiday_claims']
OPTIONAL_PERSONAL_TABLES=['personal_information','return_checkins','important_days','experience_preferences']

SAFE_EXPORT_SETTINGS = frozenset({"gamification_modules", "hidden_attributes", "disabled_attributes", "stagnation_checks", "unreal_count"})


def _encode_export(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _encode_export(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_encode_export(v) for v in value]
    return value


def _export_row(row):
    excluded = {"password_hash", "credentials_version", "lease_token"}
    return {c.name: _encode_export(getattr(row, c.name)) for c in row.__table__.columns if c.name not in excluded}


def _collect(db: Session, user_id: int,include_questionnaire=False,include_feedback=False,include_personal=False) -> dict:
    data = _collect_legacy(db, user_id)
    table_models = (models.UserProfile, models.Attribute, models.AttributeHistory,
        models.CheckinItem, models.Event, models.AIJudgment, models.JudgmentLog, models.Goal,
        models.CoinLedger, models.Challenge, models.ShopItem, models.Redemption,
        models.Achievement, models.Exemption)
    tables = {model.__tablename__: [_export_row(row) for row in db.query(model).filter(
        model.user_id == user_id).order_by(model.id).all()] for model in table_models}
    tables["users"] = [_export_row(row) for row in db.query(models.User).filter(models.User.id == user_id).all()]
    from app.services.anchor_service import list_anchors
    tables["anchors"] = [_export_row(row) for row in list_anchors(db)]
    tables["settings"] = [_export_row(row) for row in db.query(models.Setting).filter(
        models.Setting.user_id == user_id, models.Setting.key.in_(SAFE_EXPORT_SETTINGS)).order_by(models.Setting.id).all()]
    from app.models.access import AnchorOverride, EventDerivation
    from app.models.analysis import AnalysisJob, DailyReview, ReviewLink, GrowthReport
    for model in (AnchorOverride, EventDerivation, AnalysisJob, DailyReview, ReviewLink, GrowthReport):
        rows = [_export_row(row) for row in db.query(model).filter(model.user_id == user_id).order_by(model.id).all()]
        for row in rows:
            row.pop('lease_token', None)
            row.pop('config_version', None)
        tables[model.__tablename__] = rows
    from app.models import workflow
    for name in EXPORT_WORKFLOW_TABLES+FULL_SYSTEM_TABLES+(['questionnaires','personal_information','return_checkins'] if include_questionnaire else [])+(['important_days','experience_preferences'] if include_personal else [])+(['feedback','feedback_replies'] if include_feedback else []):
        model=next(mapper.class_ for mapper in models.Base.registry.mappers if mapper.local_table.name==name)
        tables[name]=[_export_row(row) for row in db.query(model).filter_by(user_id=user_id).order_by(model.id).all()]
    if not include_questionnaire:
        for row in tables['user_profiles']:
            for name in ('basic_profile','onboarding_state','pending_adjustment','long_term_memory','memory_sources'):row.pop(name,None)
            row.get('initial_attributes_snapshot',{}).pop('authorized_answers',None)
    for row in tables.get('pricing_quotes',[]):
        row.get('context',{}).pop('config',None);row.pop('fingerprint',None)
    return {**data, "format_version":5,"restore_supported":False,"tables":tables}


@router.get('/record-metrics')
def record_metrics(db:Session=Depends(get_db)):
    from app.services.record_metrics import metrics
    return metrics(db,get_or_create_default_user(db))


@router.get('/export')
def export_data(db:Session=Depends(get_db),format:Literal['json','csv','markdown','html']='json',
    kind:Literal['all','event','diary','legacy']='all',start:date|None=None,end:date|None=None,
    include_questions:bool=True,include_analysis:bool=True,include_deleted:bool=False,
    include_history:bool=True,include_game:bool|None=None,schema_version:int=5,
    include_questionnaire:bool=False,include_feedback:bool=False,include_personal:bool=False):
    user=get_or_create_default_user(db)
    if schema_version not in (3,4,5):raise HTTPException(422,'仅支持 JSON v3/v4/v5。')
    if start and end and start>end:raise HTTPException(422,'日期范围无效。')
    if format=='json':
        if schema_version in (3,4) and (kind!='all' or start or end):raise HTTPException(422,'旧结构投影不支持日期筛选。')
        data=_collect(db,user.id,include_questionnaire,include_feedback,include_personal)
        if schema_version==5:
            from app.services.readable_export import select,strip_questions
            selected=select(db,user,kind,start,end,include_deleted,include_history,include_questions,include_analysis)
            ids={r['record']['id'] for r in selected}
            data['records']=selected
            data['events']=[r['record'] for r in selected]
            data['judgments']=[j['judgment'] for r in selected for j in r.get('judgments',[])] if include_analysis else []
            for name in ('events','ai_judgments','attribute_history','judgment_logs','diary_revisions','review_sessions','event_facts','fact_fragments','fact_bundles','fact_notes'):
                rows=data['tables'].get(name,[])
                if name=='events':rows=[r for r in rows if r['id'] in ids]
                elif name!='judgment_logs':rows=[r for r in rows if (r.get('event_id') or r.get('diary_id')) in ids]
                data['tables'][name]=rows
            judgment_ids={r['id'] for r in data['tables']['ai_judgments']}
            data['tables']['judgment_logs']=[r for r in data['tables']['judgment_logs'] if r['judgment_id'] in judgment_ids]
            session_ids={r['id'] for r in data['tables']['review_sessions']}
            for name in ('review_turns','review_analyses'):data['tables'][name]=[r for r in data['tables'][name] if r['session_id'] in session_ids]
            from app.services.readable_export import project_record_tables
            project_record_tables(data['tables'],selected,include_history)
            if not include_questions:
                data['tables']['fact_notes']=[]
                data['tables']['review_turns']=[]
                data['tables']['review_analyses']=strip_questions(data['tables']['review_analyses'])
                for row in data['tables'].get('analysis_jobs',[]):row['detail']='';row['result']=strip_questions(row.get('result',{}))
                data['tables']['judgment_logs']=[r for r in data['tables']['judgment_logs'] if r.get('action') not in ('supplement','dispute')]
                for row in data['tables']['events']:row.get('params',{}).pop('_clarify_history',None)
            if not include_analysis:
                for name in ('review_analyses','ai_judgments','judgment_logs','fact_bundles','event_derivations','analysis_jobs'):data['tables'][name]=[]
            if include_game is False:
                keep={'users','events','diary_revisions','review_sessions','review_turns','review_analyses','ai_judgments','judgment_logs','fact_fragments','fact_bundles','fact_notes','fact_identities','event_facts','fact_settlements'}
                if include_questionnaire:keep.update(('questionnaires','personal_information','return_checkins'))
                if include_personal:keep.update(('important_days','experience_preferences'))
                if include_feedback:keep.update(('feedback','feedback_replies'))
                data['tables']={k:v for k,v in data['tables'].items() if k in keep}
                for name in ('attributes','attribute_history','goals','anchors'):data.pop(name,None)
            data['selection']={'kind':kind,'start':str(start) if start else None,'end':str(end) if end else None,'include_game':include_game is not False,'include_history':include_history,'include_questions':include_questions,'include_analysis':include_analysis,'include_questionnaire':include_questionnaire,'include_feedback':include_feedback,'include_personal':include_personal}
        else:
            for name in FULL_SYSTEM_TABLES:data['tables'].pop(name,None)
            data['format_version']=schema_version
        if schema_version==3:
            for name in EXPORT_WORKFLOW_TABLES:data['tables'].pop(name,None)
            data['format_version']=3
            data['compatibility_notice']='旧 v3 投影不含 P2 起新增实体，完整保留请使用 v4。'
        return data
    if format=='csv' and include_game:raise HTTPException(422,'CSV 不包含游戏表，请选择 JSON/Markdown/HTML。')
    from app.services.readable_export import select,render
    rows=select(db,user,kind,start,end,include_deleted,include_history,include_questions,include_analysis)
    game=export_data(db=db,format='json',kind=kind,start=start,end=end,include_questions=include_questions,
        include_analysis=include_analysis,include_deleted=include_deleted,include_history=include_history,
        include_game=True,schema_version=5,include_questionnaire=include_questionnaire,include_feedback=include_feedback,include_personal=include_personal)['tables'] if include_game else None
    content=render(rows,format,game)
    extension={'csv':'csv','markdown':'md','html':'html'}[format]
    return Response(content=content,media_type={'csv':'text/csv','markdown':'text/markdown','html':'text/html'}[format],
        headers={'Content-Disposition':f'attachment; filename=lifexp-records.{extension}','X-Content-Type-Options':'nosniff'})


# ============ 备份 ============

@router.post("/backup", dependencies=[Depends(require_owner)])
def create_backup():
    """手动触发数据库备份。"""
    from app.config import settings
    if settings.cloud:
        from fastapi import HTTPException
        raise HTTPException(409, "云端请使用运维备份命令，并单独保管加密主密钥。")
    from app.services.backup_service import backup_now

    dest = backup_now()
    return {"status": "ok", "backup_file": dest.name if dest else None}


@router.get("/backup/list", dependencies=[Depends(require_owner)])
def list_backups():
    """列出已有备份。"""
    from app.services.backup_service import list_backups

    return list_backups()
