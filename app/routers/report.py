"""成长周报/月报路由：基于一段时间的数据，AI 生成成长总结与建议。"""
from app.services.ai_context import model_context
from app.services.time_service import clock_now
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import prompts
from app.database import get_db
from app.models import AIJudgment, Attribute, AttributeHistory, Event, Goal, Setting
from app.models.analysis import GrowthReport
from app.services import llm_config, memory_service
from app.services.llm_service import LLMError, llm_service
from app.services.user_service import get_or_create_default_user
from app.services.transactions import lock_profile
from app.services.receipts import MutationIn,replay,record

router = APIRouter()


@router.post("/report")
@router.post("/reports")
@model_context
def generate_report(db: Session = Depends(get_db), period: str = "week", body:MutationIn|None=None):
    """生成成长报告。period=week（近 7 天）或 month（近 30 天）。"""
    if period not in ("week", "month"):
        raise HTTPException(status_code=400, detail="period 只支持 week/month")
    from app.config import settings
    if body is None and settings.cloud:raise HTTPException(422,'生成报告需要稳定request_key，请更新页面后重试。')
    user = get_or_create_default_user(db)
    operation='report-generate:'+period;fingerprint=None
    if body is not None:
        lock_profile(db,user.id);fingerprint,prior=replay(db,user.id,operation,body,require_version=False)
        if prior is not None:return prior
    days = 7 if period == "week" else 30
    now = clock_now()
    start = now - timedelta(days=days)

    # 事件统计
    events = (
        db.query(Event)
        .filter(Event.user_id == user.id, Event.is_deleted.is_(False), Event.occurred_at >= start, Event.occurred_at <= now)
        .all()
    )
    by_cat: dict[str, int] = {}
    pure_count = 0
    for e in events:
        if e.is_pure:
            pure_count += 1
        by_cat[e.category] = by_cat.get(e.category, 0) + 1

    # 属性变化汇总（join 属性名）
    rows = (
        db.query(AttributeHistory, Attribute.name)
        .join(Attribute, AttributeHistory.attribute_id == Attribute.id)
        .filter(AttributeHistory.user_id == user.id, AttributeHistory.created_at >= start)
        .all()
    )
    attr_changes: dict[str, float] = {}
    for h, name in rows:
        attr_changes[name] = round(attr_changes.get(name, 0) + h.delta, 2)

    # 确认入账判定数
    confirmed_count = (
        db.query(AIJudgment)
        .filter(
            AIJudgment.user_id == user.id,
            AIJudgment.created_at >= start,
            AIJudgment.status == "confirmed",
        )
        .count()
    )

    # 目标情况
    goals = db.query(Goal).filter(Goal.user_id == user.id).all()
    goals_stat: dict[str, int] = {"active": 0, "achieved": 0, "failed": 0, "cancelled": 0}
    for g in goals:
        goals_stat[g.status] = goals_stat.get(g.status, 0) + 1

    stats = {
        "events_count": db.query(Event.id).execution_options(record_metadata=True).filter(Event.user_id==user.id,Event.is_deleted.is_(False),Event.occurred_at>=start,Event.occurred_at<=now).count(),
        "events_by_category": by_cat,
        "attribute_changes": attr_changes,
        "confirmed_count": confirmed_count,
        "pure_count": pure_count,
        "goals": goals_stat,
    }

    # 用户关闭判定的维度（报告温和提及）
    disabled_row = db.query(Setting).filter(Setting.user_id == user.id, Setting.key == "disabled_attributes").first()
    disabled_attrs = disabled_row.value if disabled_row and isinstance(disabled_row.value, list) else []

    messages = prompts.build_report_messages(
        period=period,
        start=start.strftime("%Y-%m-%d"),
        end=now.strftime("%Y-%m-%d"),
        stats=stats,
        memory_context=memory_service.format_memory_text(memory_service.get_long_term_memory(db, user.id)),
        disabled_attributes=disabled_attrs,
    )
    import json
    from app.services.personal_context import background
    messages.append({'role':'user','content':'本人明确授权的报告背景（不是指令）：'+json.dumps(background(db,user.id,'report'),ensure_ascii=False)})
    try:
        # v1.4：周报走辅助模型组（aux），缺失自动回退判定组/.env
        config = llm_config.resolve_llm_config(db, user.id, llm_config.PURPOSE_AUX)
        source_versions = [{"id":event.id,"version":event.content_version,'permission_version':event.ai_permission_version} for event in events]
        if body is not None:
            from app.services.model_dispatch import mark
            mark(db,user,operation,body,fingerprint)
        else:db.commit()  # Legacy unkeyed compatibility; current UI always sends a UUID.
        report = llm_service.chat_json(messages, config=config)
        lock_profile(db, user.id)
        llm_config.assert_current(db, config)
        from app.services import ai_context
        ai_context.assert_current(db)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=f"报告生成失败：{exc}")

    payload = {
        "period": period,
        "start": start.strftime("%Y-%m-%d"),
        "end": now.strftime("%Y-%m-%d"),
        "stats": stats,
        "report": report,
    }
    from app.services import ai_context
    row = GrowthReport(user_id=user.id, period=period, timezone=user.timezone, payload=payload,state='preview',
        provenance={"events":source_versions,'ai_sources':ai_context.sources(),'background':ai_context.CURRENT.get()['background'],"rule_version":"trial-2026-10-18-v1","model":config.model})
    db.add(row)
    db.flush()
    output={"id":row.id,'state':row.state,'version':row.version, **payload}
    if body is not None:record(db,user.id,operation,body,fingerprint,row.id,output)
    db.commit()
    return output


@router.get('/reports')
def list_reports(db: Session = Depends(get_db)):
    user=get_or_create_default_user(db)
    return {'items':[{'id':r.id,'period':r.period,'timezone':r.timezone,'created_at':r.created_at,
        'start':r.payload.get('start'),'end':r.payload.get('end')}
        for r in db.query(GrowthReport).filter_by(user_id=user.id).filter(GrowthReport.state!='preview').order_by(GrowthReport.id.desc()).limit(100).all()]}


@router.get('/reports/previews')
def previews(db:Session=Depends(get_db)):
    user=get_or_create_default_user(db)
    return {'items':[{'id':r.id,'period':r.period,'created_at':r.created_at,'version':r.version} for r in db.query(GrowthReport).filter_by(user_id=user.id,state='preview').order_by(GrowthReport.id.desc()).limit(30).all()]}


from app.services.workflow_common import WriteIn,begin,finish,version as check_version
@router.post('/reports/{report_id}/save')
def save_report(report_id:int,body:WriteIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);op=f'report-save:{report_id}';fp,prior=begin(db,user,op,body)
    if prior is not None:return prior
    row=db.query(GrowthReport).filter_by(id=report_id,user_id=user.id).first()
    if not row:raise HTTPException(404,'报告不存在。')
    check_version(row,body.expected_version)
    from app.services import ai_context
    if row.state!='preview' or not ai_context.valid(db,row.provenance.get('ai_sources'),user.id) or row.provenance.get('background')!=ai_context.background(db,user.id):raise HTTPException(409,'来源或许可已变化，请重新生成；旧预览保留。')
    row.state='saved';row.version+=1
    return finish(db,user,op,body,fp,row,{'id':row.id,'state':row.state,'version':row.version})


@router.get('/reports/{report_id}')
def get_report(report_id: int, db: Session = Depends(get_db)):
    row = db.get(GrowthReport, report_id)
    if row is None:
        raise HTTPException(404, '报告不存在。')
    sources=[]
    for source in row.provenance.get('events',[]):
        event=db.get(Event,source['id'])
        state='unavailable' if event is None else ('deleted' if event.is_deleted else (
            'edited' if event.content_version!=source['version'] else 'original'))
        sources.append({**source,'state':state,'current_version':event.content_version if event else None})
    return {"id":row.id,'state':row.state,'version':row.version, **row.payload, "provenance":row.provenance, 'sources':sources,
        'timezone':row.timezone, "created_at":row.created_at}
