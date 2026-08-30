"""Onboarding 路由：初始属性设定（AI 问卷制）。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import OnboardingAnswerIn, OnboardingDisputeIn
from app.services import onboarding_service
from app.services.llm_service import LLMError

router = APIRouter()


@router.post("/onboarding/questions")
def create_questions(db: Session = Depends(get_db)):
    """开始问卷，AI 生成首轮问题。"""
    try:
        return onboarding_service.start_questions(db)
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/onboarding/answer")
def answer(body: OnboardingAnswerIn, db: Session = Depends(get_db)):
    """提交回答。finish=false 返回追问，finish=true 生成初始面板并存档。"""
    if not body.session_id:
        raise HTTPException(status_code=400, detail="缺少 session_id，请先调用 /onboarding/questions 开始问卷。")
    try:
        return onboarding_service.submit_answer(db, body.session_id, body.answers, finish=body.finish)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/onboarding/dispute")
def dispute(body: OnboardingDisputeIn, db: Session = Depends(get_db)):
    """对初始属性面板提出异议，AI 客观复核后返回调整后的面板。"""
    try:
        return onboarding_service.dispute_panel(db, body.session_id, body.detail)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
