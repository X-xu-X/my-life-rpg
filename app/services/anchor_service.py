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
    # ---- 生活质感维度（v1.2 新增，基于积极心理学）----
    {
        "name": "感恩/知足记录",
        "description": "记录一件值得感谢或感到知足的小事",
        "category": "心态",
        "target_attribute": "感恩",
        "base_value": 1,
        "unit": "次",
        "base_delta": 0.5,
        "evidence": "感恩练习研究（Emmons & McCullough）：定期记录感恩能显著提升主观幸福感与积极情绪。",
    },
    {
        "name": "发现生活之美",
        "description": "欣赏自然、艺术、音乐等美好事物",
        "category": "审美",
        "target_attribute": "审美",
        "base_value": 1,
        "unit": "次",
        "base_delta": 0.5,
        "evidence": "VIA 性格优势（Peterson & Seligman）：对美与卓越的鉴赏是 24 项核心性格优势之一。",
    },
    {
        "name": "有意义的活动",
        "description": "帮助他人或做一件自认为有价值的事",
        "category": "心态",
        "target_attribute": "意义感",
        "base_value": 1,
        "unit": "次",
        "base_delta": 0.5,
        "evidence": "生命意义感研究（Frankl / Steger）：意义感与更高的生活满意度、心理韧性正相关。",
    },
    {
        "name": "积极情绪体验",
        "description": "愉快的社交、享受生活等带来积极情绪的活动",
        "category": "心态",
        "target_attribute": "幸福感",
        "base_value": 1,
        "unit": "次",
        "base_delta": 0.5,
        "evidence": "积极心理学 PERMA 模型（Seligman）：积极情绪是主观幸福感的核心组成。",
    },
    {
        "name": "从容应对压力",
        "description": "在压力下保持平静、从挫折中恢复",
        "category": "心态",
        "target_attribute": "心理韧性",
        "base_value": 1,
        "unit": "次",
        "base_delta": 0.5,
        "evidence": "心理韧性研究：韧性能缓冲压力对身心健康的负面影响，是可培养的心理资本。",
    },
    {
        "name": "尝试新事物",
        "description": "探索未知、尝试新的体验或学习新领域",
        "category": "心态",
        "target_attribute": "开放性",
        "base_value": 1,
        "unit": "次",
        "base_delta": 0.5,
        "evidence": "大五人格（Big Five）开放性维度：对新体验的开放与创造力、认知灵活性相关。",
    },
    # ---- 负面行为锚点（v1.2 新增，减分，带科学依据）----
    {
        "name": "抽烟",
        "description": "吸烟",
        "category": "健康习惯",
        "target_attribute": "健康",
        "base_value": 1,
        "unit": "次",
        "base_delta": -1.0,
        "evidence": "WHO/CDC：吸烟是癌症、心血管疾病与慢性呼吸系统疾病的首要可预防风险因素。",
    },
    {
        "name": "酗酒",
        "description": "一次性过量饮酒",
        "category": "健康习惯",
        "target_attribute": "健康",
        "base_value": 1,
        "unit": "次",
        "base_delta": -1.0,
        "evidence": "饮酒指南：过量饮酒显著增加肝损伤、心血管疾病与意外伤害风险。",
    },
    {
        "name": "久坐不动",
        "description": "连续久坐 3 小时以上未起身活动",
        "category": "作息",
        "target_attribute": "健康",
        "base_value": 3,
        "unit": "小时",
        "base_delta": -0.5,
        "evidence": "久坐研究：长时间静态行为与代谢综合征、心血管疾病风险增加相关。",
    },
    {
        "name": "暴饮暴食",
        "description": "一餐过量进食/暴食",
        "category": "饮食",
        "target_attribute": "健康",
        "base_value": 1,
        "unit": "次",
        "base_delta": -0.5,
        "evidence": "饮食指南：暴饮暴食增加肥胖、代谢负担与胃肠道不适风险。",
    },
    {
        "name": "沉迷屏幕过久",
        "description": "娱乐性使用电子屏幕连续 4 小时以上",
        "category": "作息",
        "target_attribute": "规划力",
        "base_value": 4,
        "unit": "小时",
        "base_delta": -0.5,
        "evidence": "屏幕时间研究：过度的娱乐性屏幕时间与时间管理能力下降、久坐增加相关。",
    },
    {
        "name": "冲动消费",
        "description": "未经计划的冲动消费",
        "category": "理财",
        "target_attribute": "规划力",
        "base_value": 1,
        "unit": "次",
        "base_delta": -0.5,
        "evidence": "消费心理研究：冲动消费反映自我控制与财务规划能力的不足。",
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
