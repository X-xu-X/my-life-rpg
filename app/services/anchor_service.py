"""量化锚点库服务。

职责：
- 内置标准事件基准表（PRD 6.4 节），启动时幂等写入数据库。
- 提供查询、校准。
- 将锚点库格式化为文本，供 AI 判定 / 复核 Prompt 注入。
"""
from sqlalchemy.orm import Session

from app.models import Anchor

# 内置锚点种子数据（PRD 6.4 节基准表）
# 字段：name/description/category/target_attribute/base_value/unit/base_delta/evidence
BUILTIN_ANCHORS = [
    {
        "name": "中等强度有氧",
        "description": "慢跑/游泳/骑行等中等强度有氧运动",
        "category": "锻炼",
        "target_attribute": "体能",
        "base_value": 30,
        "unit": "分钟",
        "base_delta": 1.0,
        "evidence": "ACSM（美国运动医学会）建议成人每周≥150 分钟中等强度有氧，规律有氧提升心肺耐力与体能。",
    },
    {
        "name": "深度专注学习",
        "description": "无干扰的深度专注学习",
        "category": "学习",
        "target_attribute": "智力",
        "base_value": 60,
        "unit": "分钟",
        "base_delta": 1.0,
        "evidence": "认知心理学：深度工作/心流状态下的学习促进长期记忆巩固与知识内化。",
    },
    {
        "name": "早睡充足睡眠",
        "description": "23:00 前入睡且睡眠 7 小时以上",
        "category": "作息",
        "target_attribute": "健康",
        "base_value": 1,
        "unit": "次",
        "base_delta": 0.5,
        "evidence": "睡眠研究：规律早睡与充足睡眠（7-9h）改善代谢、免疫与认知功能。",
    },
    {
        "name": "熬夜",
        "description": "熬夜至凌晨 02:00 之后",
        "category": "作息",
        "target_attribute": "健康",
        "base_value": 1,
        "unit": "次",
        "base_delta": -0.5,
        "evidence": "睡眠研究：长期熬夜扰乱昼夜节律，损害认知表现与内分泌稳态。",
    },
    {
        "name": "目标达成",
        "description": "目标到期且达成量化指标",
        "category": "目标",
        "target_attribute": "规划力",
        "base_value": 1,
        "unit": "次",
        "base_delta": 2.0,
        "evidence": "目标设定理论：达成目标的正反馈强化自我效能与计划执行力。",
    },
    {
        "name": "目标未达成",
        "description": "目标到期但未达成指标",
        "category": "目标",
        "target_attribute": "规划力",
        "base_value": 1,
        "unit": "次",
        "base_delta": -1.0,
        "evidence": "自我调节学习理论：未兑现计划反映规划或执行力的不足。",
    },
]


def seed_anchors(db: Session) -> int:
    """启动时幂等写入内置锚点。返回本次写入数量。"""
    created = 0
    existing_names = {a.name for a in db.query(Anchor).filter(Anchor.is_builtin.is_(True)).all()}
    for item in BUILTIN_ANCHORS:
        if item["name"] in existing_names:
            continue
        db.add(Anchor(**item, is_builtin=True))
        created += 1
    if created:
        db.commit()
    return created


def list_anchors(db: Session) -> list[Anchor]:
    """返回全部锚点（内置 + 用户自定义）。"""
    return db.query(Anchor).order_by(Anchor.id).all()


def get_anchor(db: Session, anchor_id: int) -> Anchor | None:
    return db.get(Anchor, anchor_id)


def calibrate_anchor(db: Session, anchor_id: int, calibrated_value: float | None) -> Anchor | None:
    """校准锚点基准量。calibrated_value=None 表示恢复默认。"""
    anchor = db.get(Anchor, anchor_id)
    if anchor is None:
        return None
    anchor.calibrated_value = calibrated_value
    db.commit()
    db.refresh(anchor)
    return anchor


def _effective_value(anchor: Anchor) -> float:
    """返回锚点的有效基准量（优先校准值，否则默认）。"""
    if anchor.calibrated_value is not None:
        return anchor.calibrated_value
    return anchor.base_value


def format_anchors_text(db: Session) -> str:
    """将锚点库格式化为文本，供 AI Prompt 注入。"""
    lines = []
    for a in list_anchors(db):
        line = (
            f"- {a.name}：{a.description}；基准为 {_effective_value(a)}{a.unit} "
            f"→ {a.target_attribute} {a.base_delta:+g} 分。依据：{a.evidence}"
        )
        lines.append(line)
    if not lines:
        return "（暂无锚点）"
    return "\n".join(lines)
