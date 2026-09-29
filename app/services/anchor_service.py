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
        # v1.8：多属性——睡眠同时促进记忆巩固，故与「熬夜」扣智力形成对称（可恢复原则）
        "targets": [
            {"name": "健康", "base_delta": 0.5},
            {"name": "智力", "base_delta": 0.4},
        ],
        "intensity_note": "偶尔 1 次 中档（系数 1.0）；连续 ≥3 天规律早睡 强档（系数 1.5~2.0），注意力与记忆表现改善更明显。",
        "evidence": "睡眠研究：规律早睡与充足睡眠（7-9h）改善代谢、免疫与认知功能；睡眠期间的记忆巩固对学习效果有直接贡献。",
    },
    {
        "name": "熬夜",
        "description": "熬夜至凌晨 02:00 之后",
        "category": "作息",
        "target_attribute": "健康",
        "base_value": 1,
        "unit": "次",
        "base_delta": -0.5,
        # v1.8：多属性——原 evidence 已写"损害认知表现"，本次把"认知"落到结构化字段上
        "targets": [
            {"name": "健康", "base_delta": -0.5},
            {"name": "智力", "base_delta": -0.4},
        ],
        "intensity_note": "偶尔 1 次 弱档（系数 0.5，约 −0.25/−0.2，单次熬夜不等于能力被砍）；每周 ≥3 次 强档（系数 1.5~2.0）。",
        "evidence": "睡眠研究：长期熬夜扰乱昼夜节律，损害认知表现与内分泌稳态；睡眠剥夺抑制海马体依赖的记忆巩固。",
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
    # ---- 负面锚点补充（v1.2，判定精细组）----
    {
        "name": "拖延",
        "description": "明知该做却拖延不做/拖延重要任务",
        "category": "学习",
        "target_attribute": "规划力",
        "base_value": 1,
        "unit": "次",
        "base_delta": -0.5,
        "evidence": "拖延心理学（Steel）：拖延与自我控制不足、时间管理能力下降相关。",
    },
    {
        "name": "消极思维",
        "description": "自我否定、消极归因或持续性负向思考",
        "category": "心态",
        "target_attribute": "心理韧性",
        "base_value": 1,
        "unit": "次",
        "base_delta": -0.5,
        "evidence": "认知行为理论（Beck）：消极自动思维与心理韧性下降、抑郁风险增加相关。",
    },
    {
        "name": "社交回避",
        "description": "回避社交场合、自我封闭",
        "category": "社交",
        "target_attribute": "情商",
        "base_value": 1,
        "unit": "次",
        "base_delta": -0.5,
        "evidence": "社会隔离研究：长期社交回避与社会连接、情绪调节能力下降相关。",
    },
    {
        "name": "缺少运动",
        "description": "长期（连续多日）未进行任何运动",
        "category": "锻炼",
        "target_attribute": "体能",
        "base_value": 1,
        "unit": "次",
        "base_delta": -0.5,
        "evidence": "运动医学：长期缺乏运动导致心肺功能与肌肉适能下降（用进废退）。",
    },
    {
        "name": "迟到失约",
        "description": "无正当理由迟到或失约",
        "category": "社交",
        "target_attribute": "诚信",
        "base_value": 1,
        "unit": "次",
        "base_delta": -0.5,
        "evidence": "诚信品质研究：守时守信是诚信与责任感的直接体现，频繁失约反映诚信缺失。",
    },
    {
        "name": "情绪失控",
        "description": "发火、冲动或情绪失控",
        "category": "心态",
        "target_attribute": "情商",
        "base_value": 1,
        "unit": "次",
        "base_delta": -0.5,
        "evidence": "情绪调节研究：情绪失控反映情绪调节策略的不足，长期影响人际关系与心理健康。",
    },
    # ============================================================
    # v1.8 新增：能力类「有害行为」负面锚点（A2-3，按证据补、不强凑）
    # 说明：与既有「沉迷屏幕过久（规划力）」不同，以下锚点作用在能力/素养维度上。
    # 这些维度的下降只由**具体有害行为**驱动，绝不因"很久没记录"而自动衰减。
    # ============================================================
    {
        "name": "长时间碎片化刷屏",
        "description": "连续 ≥2 小时无目的地刷手机/短视频（非学习、非工作用途）",
        "category": "作息",
        "target_attribute": "智力",
        "base_value": 2,
        "unit": "小时",
        "base_delta": -0.3,
        "intensity_note": "2 小时 中档（系数 1.0，约 −0.3）；≥4 小时 强档（系数 1.5~2.0）。",
        "evidence": "注意力研究：注意力残留效应（attention residue）与注意力资源耗竭——长时间碎片化信息流削弱持续专注与深度加工能力。",
    },
    {
        "name": "连续多日无学习输入",
        "description": "用户如实记录「这几天什么都没学」等连续 ≥3 天无任何学习/认知输入",
        "category": "学习",
        "target_attribute": "智力",
        "base_value": 3,
        "unit": "天",
        "base_delta": -0.5,
        "intensity_note": "连续 3 天 中档（系数 1.0）；≥7 天 强档（系数 1.5~2.0）。",
        "evidence": "认知用进废退：与既有「缺少运动→体能」同构，认知能力依赖持续输入与练习维持。",
    },
    {
        "name": "长期机械重复无新尝试",
        "description": "长期只做机械重复的事、不做任何新尝试或新探索",
        "category": "心态",
        "target_attribute": "创造力",
        "base_value": 1,
        "unit": "次",
        "base_delta": -0.3,
        "intensity_note": "偶发 弱档（系数 0.5，约 −0.15）；持续 ≥2 周的状态 中档（系数 1.0）。",
        "evidence": "创造力三成分理论（Amabile）：创造力依赖持续的外部输入与试错经验，长期机械重复会抑制发散思维。",
    },
    {
        "name": "固守成见拒绝新体验",
        "description": "明显回避陌生事物、拒绝新体验、固守既有成见",
        "category": "心态",
        "target_attribute": "开放性",
        "base_value": 1,
        "unit": "次",
        "base_delta": -0.5,
        "intensity_note": "单次回避 中档（系数 1.0，约 −0.5）；长期固化状态 强档（系数 1.5~2.0）。",
        "evidence": "大五人格研究：开放性可由新体验维持与拓展，回避新体验会使其收缩。",
    },
    {
        "name": "空虚度过一天",
        "description": "长期无价值感产出、空虚度过一天、缺乏投入与联结",
        "category": "心态",
        "target_attribute": "意义感",
        "base_value": 1,
        "unit": "次",
        "base_delta": -0.5,
        "intensity_note": "偶尔一天 中档（系数 1.0）；长期如此 强档（系数 1.5~2.0）。",
        "evidence": "意义感研究：意义源于投入、联结与价值感产出，长期空虚与无产出会削弱意义体验。",
    },
    {
        # TODO(v1.8)：本锚点**科学依据相对较弱**——"不接触美的事物是否直接降低审美能力"缺乏
        # 强实证（审美更多是敏感度/体验积累，且"没记录"与"没接触"难以区分）。
        # 按 DEV_PLAN_v1.8 A2-3 的实现要求先建入并标注，后续若认为不妥可直接删除该锚点。
        "name": "长期不接触美好事物",
        "description": "长期不接触任何美的事物（音乐、艺术、自然、文学等）",
        "category": "审美",
        "target_attribute": "审美",
        "base_value": 1,
        "unit": "次",
        "base_delta": -0.3,
        "intensity_note": "依据较弱，一律按弱档（系数 0.5~1.0，约 −0.15~−0.3）处理，不宜加重。",
        "evidence": "审美教育研究（依据较弱）：审美敏感度依赖持续的体验积累，缺乏接触会使感知丰富度下降。",
    },
]


def seed_anchors(db: Session) -> int:
    """启动时幂等写入内置锚点（v1.8 扩展为**三级**）。返回本次新增+回填的条数。

    三级逻辑（务必严格）：
    1. 名字不存在 → 新增整条（沿用既有逻辑）
    2. 名字已存在、**`targets IS NULL`**、且 BUILTIN_ANCHORS 中该锚点已定义 `targets`
       → **回填 `targets` 与 `intensity_note`**（让老库里的锚点升级到多属性）
    3. 否则跳过

    **只填 NULL，绝不覆盖已有值，也绝不动 `calibrated_value`**
    ——用户校准结果不可被启动流程冲掉。
    """
    created = 0
    existing = {
        a.name: a
        for a in db.query(Anchor).filter(Anchor.is_builtin.is_(True)).all()
    }
    for item in BUILTIN_ANCHORS:
        row = existing.get(item["name"])
        if row is None:
            db.add(Anchor(**item, is_builtin=True))
            created += 1
            continue
        # 已有该锚点：仅在 targets 为空且内置定义里有多属性时回填（只填不覆盖）
        if row.targets is None and item.get("targets"):
            row.targets = item["targets"]
            if item.get("intensity_note") and not row.intensity_note:
                row.intensity_note = item["intensity_note"]
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
    """将锚点库格式化为文本，供 AI Prompt 注入。

    v1.8：有 `targets`（多属性）时逐条列出每个目标维度与基准值，并附 `intensity_note`；
    无 `targets` 时**保持原格式不变**（老锚点行为与升级前完全一致）。
    """
    lines = []
    for a in list_anchors(db):
        if a.targets:
            # 多属性：逐条列出，明确告知这是一条锚点作用于多个维度
            parts = "、".join(
                f"{t.get('name', '')} {float(t.get('base_delta', 0)):+g}"
                for t in a.targets
                if t.get("name")
            )
            line = f"- {a.name}：{a.description}；基准为 {_effective_value(a)}{a.unit} → {parts} 分。"
            if a.intensity_note:
                line += f"【强度梯度】{a.intensity_note}"
            line += f"依据：{a.evidence}"
        else:
            line = (
                f"- {a.name}：{a.description}；基准为 {_effective_value(a)}{a.unit} "
                f"→ {a.target_attribute} {a.base_delta:+g} 分。依据：{a.evidence}"
            )
            if a.intensity_note:
                line += f"【强度梯度】{a.intensity_note}"
        lines.append(line)
    if not lines:
        return "（暂无锚点）"
    return "\n".join(lines)
