"""请求会话的纵深归属保护；运维迁移会话不绑定用户。

入口仍显式校验资源，统一查询过滤补足旧按 ID 代码；before_flush 校验跨表引用。
禁止业务入口使用裸 SQL 绕过此边界。
"""
from fastapi import HTTPException
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session, with_loader_criteria
from app.database import Base


@event.listens_for(Session, "do_orm_execute")
def scope_queries(execution):
    if execution.session.info.get('ai_only') and not execution.execution_options.get('record_metadata'):
        from app.models import Event
        execution.statement=execution.statement.options(with_loader_criteria(Event,
            (Event.ai_permission=='allowed') & Event.is_deleted.is_(False) & Event.is_pure.is_(False),include_aliases=True))
        from app.services.ai_context import CURRENT
        from app.models import Attribute
        context=CURRENT.get()
        if context is not None:
            execution.statement=execution.statement.options(with_loader_criteria(Attribute,
                Attribute.parent_id.is_(None)|Attribute.id.in_(context['safe_children']),include_aliases=True))
    user_id = execution.session.info.get("user_id")
    if user_id is None:
        return
    statement = execution.statement
    for mapper in Base.registry.mappers:
        model = mapper.class_
        if model.__tablename__ in ('feedback','feedback_replies') and execution.session.info.get('manage_feedback'):continue
        if model.__tablename__=='auth_sessions' and execution.session.info.get('manage_auth_sessions'):continue
        if model.__tablename__=='hosted_usage' and execution.session.info.get('monitor_hosted_usage'):continue
        if model.__tablename__=='user_profiles' and execution.session.info.get('manage_profile_locks'):continue
        if hasattr(model, "user_id"):
            statement = statement.options(with_loader_criteria(model,
                model.user_id == user_id, include_aliases=True))
    execution.statement = statement


@event.listens_for(Session, "before_flush")
def validate_references(db, context, instances):
    user_id = db.info.get("user_id")
    if user_id is None:
        return
    models = {mapper.local_table.name: mapper.class_ for mapper in Base.registry.mappers}
    for row in set(db.new) | set(db.dirty) | set(db.deleted):
        if row.__tablename__ in ('feedback','feedback_replies') and db.info.get('manage_feedback'):
            from app.models import User
            from app.models.full_system import Feedback
            actor=db.get(User,user_id)
            if not actor or actor.role!='owner' or actor.status!='active':raise HTTPException(403,'管理权限已失效。')
            if row.__tablename__=='feedback_replies':
                parent=db.get(Feedback,row.feedback_id)
                if not parent or parent.user_id!=row.user_id or row.actor_id!=user_id:raise HTTPException(404,'反馈关联无效。')
            continue
        if hasattr(row, "user_id") and row.user_id != user_id:
            raise HTTPException(404, "资源不存在。")
        if row.__tablename__ == "anchors":
            raise HTTPException(403, "内置锚点只读，请使用个人校准。")
        for column in inspect(type(row)).columns:
            value = getattr(row, column.name)
            if value is None:
                continue
            for foreign_key in column.foreign_keys:
                target = models.get(foreign_key.column.table.name)
                if target and hasattr(target, "user_id"):
                    related = db.get(target, value)
                    if related is None or related.user_id != user_id:
                        raise HTTPException(404, "关联资源不存在。")


def get_owned(db, model, resource_id):
    row = db.get(model, resource_id)
    if row is None or row.user_id != db.info["user_id"]:
        raise HTTPException(404, "资源不存在。")
    return row
