"""Onboarding 路由：初始属性设定（AI 问卷制，v1.1 重设计）。

流程：
- 首次引导：POST /questions 开始/恢复 → POST /answer 逐轮作答，AI 自评把握度，
  达到阈值自动生成初始面板并归档。
- 首次后：只能 POST /supplement 补充长期信息，AI 客观评估后 POST /supplement/confirm 确认生效。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import OnboardingAnswerIn, SupplementProfileIn
from app.services import onboarding_service
from app.services.llm_service import LLMError

router = APIRouter()


@router.get("/onboarding/status")
def status(db: Session = Depends(get_db)):
    """查询首次引导状态（是否完成、是否有进行中会话）。"""
    return onboarding_service.get_status(db)


@router.post("/onboarding/questions")
def create_questions(db: Session = Depends(get_db)):
    """开始（或恢复）首次引导，AI 生成/继续提问。已完成则返回锁定提示。"""
    try:
        return onboarding_service.start_questions(db)
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/onboarding/answer")
def answer(body: OnboardingAnswerIn, db: Session = Depends(get_db)):
    """提交一轮回答。AI 评估把握度，达到阈值自动生成初始面板并归档。"""
    try:
        return onboarding_service.submit_answer(db, body.answers)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/onboarding/supplement")
def supplement(body: SupplementProfileIn, db: Session = Depends(get_db)):
    """补充长期信息，AI 客观评估并返回调整建议（待用户确认）。"""
    try:
        return onboarding_service.supplement_profile(db, body.detail)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/onboarding/supplement/confirm")
def confirm_supplement(db: Session = Depends(get_db)):
    """确认应用补充信息的属性调整建议。"""
    return onboarding_service.confirm_adjustment(db)


@router.post("/onboarding/reset")
def reset_onboarding(db: Session = Depends(get_db)):
    """重置角色档案：解锁首次引导，可重新走问卷生成新面板。"""
    try:
        return onboarding_service.reset_onboarding(db)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc


@router.post("/onboarding/reset-all")
def reset_all(db: Session = Depends(get_db)):
    """重置全部数据（测试用）：清空事件/判定/流水/目标，属性回中性值，解锁引导。"""
    raise HTTPException(409, "真实数据清空入口已停用；批量清理必须先整库备份并走事件删除接口。")
