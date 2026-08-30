"""Onboarding 问卷服务。

流程（PRD 4.1 节）：
开始问卷 → AI 出题 → 对话式作答（可追问）→ AI 生成初始属性面板（附推导依据）
→ 用户可异议调整 → 存档初始快照。

会话状态说明：V1 单用户本地自用，问答中间态存于进程内存（重启即清）；
最终面板会持久化到 user_profiles 与 attributes 表。TODO：如需断点续答，可将
会话落库（settings 表或独立 onboarding_sessions 表）。
"""
import uuid

from sqlalchemy.orm import Session

from app import prompts
from app.models import Attribute, UserProfile
from app.services.llm_service import llm_service
from app.services.user_service import get_or_create_default_user

# 进程内会话存储：session_id -> {"conversation": [{question, answer}], "questions": [...]}
_sessions: dict[str, dict] = {}


def start_questions(db: Session) -> dict:
    """开始问卷，AI 生成首轮问题。返回 {session_id, questions, hint}。"""
    messages = prompts.build_question_messages(existing_context=None)
    result = llm_service.chat_json(messages)
    questions = result.get("questions", [])
    hint = result.get("hint", "")

    session_id = uuid.uuid4().hex
    _sessions[session_id] = {"conversation": [], "questions": questions}
    return {"session_id": session_id, "questions": questions, "hint": hint}


def _get_session(session_id: str) -> dict:
    """获取会话；不存在则报错。"""
    if session_id not in _sessions:
        raise ValueError("会话不存在或已过期，请重新开始问卷。")
    return _sessions[session_id]


def submit_answer(db: Session, session_id: str, answers: list[dict], finish: bool) -> dict:
    """提交一轮回答。

    :param finish: True 表示信息已足够，直接生成初始属性面板并存档。
    :return: 若 finish 则返回 {panel, summary}；否则返回 {questions, hint} 继续追问。
    """
    session = _get_session(session_id)
    # 追加本轮问答到会话
    for item in answers:
        session["conversation"].append(
            {"question": item.get("question", ""), "answer": item.get("answer", "")}
        )

    if finish:
        return _generate_panel(db, session)

    # 继续追问：基于已有上下文，让 AI 补充未覆盖维度或追问关键细节
    context = {"conversation": session["conversation"]}
    messages = prompts.build_question_messages(existing_context=context)
    result = llm_service.chat_json(messages)
    questions = result.get("questions", [])
    hint = result.get("hint", "")
    session["questions"] = questions
    return {"questions": questions, "hint": hint, "finish": False}


def _generate_panel(db: Session, session: dict) -> dict:
    """AI 生成初始属性面板，并持久化到画像快照与 attributes 表。"""
    user = get_or_create_default_user(db)
    conversation = session["conversation"]
    messages = prompts.build_panel_messages(conversation)
    result = llm_service.chat_json(messages)

    panel = result.get("attributes", [])
    summary = result.get("summary", "")

    # 存档：画像快照 + 基础信息
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if profile is None:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
    profile.initial_attributes_snapshot = {"attributes": panel, "summary": summary}
    # 基础画像暂存原始问答记录（V1 保守，不额外 AI 提炼；TODO 可优化为结构化画像）
    profile.basic_profile = {"conversation": conversation}

    # 同步 attributes 表当前值
    for item in panel:
        name = item.get("name", "")
        value = float(item.get("value", 0.0))
        attr = (
            db.query(Attribute)
            .filter(Attribute.user_id == user.id, Attribute.name == name)
            .first()
        )
        if attr is None:
            attr = Attribute(user_id=user.id, name=name, description=item.get("reason", ""))
            db.add(attr)
        attr.current_value = value
        attr.description = item.get("reason", "")

    db.commit()
    # 会话可保留以备后续异议调整
    return {"panel": panel, "summary": summary, "finish": True}


def dispute_panel(db: Session, session_id: str, detail: str) -> dict:
    """用户对初始面板提出异议，AI 客观复核并返回调整后的完整面板。"""
    session = _get_session(session_id)
    user = get_or_create_default_user(db)
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    current_panel = []
    if profile and profile.initial_attributes_snapshot:
        current_panel = profile.initial_attributes_snapshot.get("attributes", [])

    messages = prompts.build_panel_dispute_messages(
        current_panel=current_panel,
        conversation=session["conversation"],
        dispute_reason=detail,
    )
    result = llm_service.chat_json(messages)
    panel = result.get("attributes", [])
    explanation = result.get("explanation", "")

    # 更新快照与 attributes
    if profile:
        profile.initial_attributes_snapshot = {
            "attributes": panel,
            "summary": profile.initial_attributes_snapshot.get("summary", ""),
        }
    for item in panel:
        name = item.get("name", "")
        value = float(item.get("value", 0.0))
        attr = (
            db.query(Attribute)
            .filter(Attribute.user_id == user.id, Attribute.name == name)
            .first()
        )
        if attr:
            attr.current_value = value
            attr.description = item.get("reason", "")
    db.commit()

    return {"panel": panel, "explanation": explanation}
