# Prompt 模板包：对外 re-export，业务层可用 `from app import prompts` 后直接调用
from app.prompts.judge import build_judge_messages
from app.prompts.dispute import build_dispute_messages
from app.prompts.extract import build_extract_messages
from app.prompts.report import build_report_messages
from app.prompts.onboarding import (
    build_panel_dispute_messages,
    build_panel_messages,
    build_question_messages,
    build_supplement_messages,
)

__all__ = [
    "build_judge_messages",
    "build_dispute_messages",
    "build_extract_messages",
    "build_report_messages",
    "build_question_messages",
    "build_panel_messages",
    "build_panel_dispute_messages",
    "build_supplement_messages",
]
