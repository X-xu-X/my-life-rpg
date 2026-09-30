"""全局常量：属性维度定义与别名映射。

属性维度从最初的 6 项（能力导向）扩展到 13 项（能力 + 生活质感 + 诚信），
新增维度均基于心理学研究（积极心理学 PERMA、大五人格、心理韧性、VIA 优势等）。
诚信为行为维度（基于行为判定，不参与 Onboarding 问卷自评，初始 50）。
"""

# 13 个标准属性维度（PRD 3 节 + 用户扩展）
ATTRIBUTE_DIMENSIONS = [
    "体能", "智力", "情商", "创造力", "规划力", "健康",
    "幸福感", "感恩", "意义感", "心理韧性", "开放性", "审美",
    "诚信",
]

# 维度集合（v1.10）：给需要"这个名字是不是合法维度"判断的地方用，避免各写一份 set(...)
ATTRIBUTE_DIMENSIONS_SET = frozenset(ATTRIBUTE_DIMENSIONS)

# 属性名规范化：AI 可能返回英文/变体，映射到标准维度（DECISIONS.md D5 扩展）
ATTRIBUTE_ALIASES = {
    # 原有 6 维
    "体能": "体能", "体力": "体能", "physical": "体能", "fitness": "体能", "endurance": "体能",
    "智力": "智力", "学习力": "智力", "intelligence": "智力", "intellect": "智力", "knowledge": "智力",
    "情商": "情商", "情绪": "情商", "社交": "情商", "eq": "情商", "emotional": "情商", "social": "情商",
    "创造力": "创造力", "creativity": "创造力", "creative": "创造力",
    "规划力": "规划力", "自律": "规划力", "执行力": "规划力", "planning": "规划力", "discipline": "规划力",
    "健康": "健康", "身体": "健康", "health": "健康", "vitality": "健康",
    # 生活质感 6 维
    "幸福感": "幸福感", "幸福": "幸福感", "快乐": "幸福感", "愉悦": "幸福感",
    "happiness": "幸福感", "wellbeing": "幸福感", "well-being": "幸福感", "well being": "幸福感",
    "感恩": "感恩", "知足": "感恩", "感激": "感恩", "gratitude": "感恩", "thankful": "感恩",
    "意义感": "意义感", "意义": "意义感", "价值感": "意义感", "meaning": "意义感", "purpose": "意义感",
    "心理韧性": "心理韧性", "韧性": "心理韧性", "抗压": "心理韧性", "resilience": "心理韧性", "grit": "心理韧性",
    "开放性": "开放性", "好奇": "开放性", "探索": "开放性", "openness": "开放性", "curiosity": "开放性", "open": "开放性",
    "审美": "审美", "美感": "审美", "beauty": "审美", "aesthetic": "审美", "appreciation": "审美",
    # 诚信（v1.2 新增）
    "诚信": "诚信", "诚实": "诚信", "诚实度": "诚信", "诚信度": "诚信", "可信": "诚信", "正直": "诚信",
    "integrity": "诚信", "honesty": "诚信", "trustworthy": "诚信",
}


# 段位（v1.8 A2-6）：0~100 分 5 档，用于回答"我的点数算多还是少"。
# 属性值封顶 100、下限 0，故最高档上界取 101 以包含 100.0 本身。
ATTRIBUTE_TIERS = [
    (0, 20, "入门"),
    (20, 40, "见习"),
    (40, 60, "熟练"),
    (60, 80, "精通"),
    (80, 101, "大师"),
]

# ---- 子维度（v1.10 M3） ----
# 属性硬上限：主维度与子维度一致（0~100）
ATTRIBUTE_FULL = 100.0
# 触发「拆子维度」的阈值。M3-1 原文是"接近/达到 100"，
# 用户 2026-09-30 拍板取 95（当前最高维度 ~73，取 100 会让功能长期闲置）。
SUBDIMENSION_THRESHOLD = 95.0
# 一次性提议的细分方向数量区间（M3-1：2~4 个）
SUBDIMENSION_MIN = 2
SUBDIMENSION_MAX = 4


def tier_of(value: float) -> str:
    """按当前值返回段位名（0~100 分 5 档）。

    边界归属：左闭右开（如 20.0 → 见习），仅最高档包含 100.0。
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ATTRIBUTE_TIERS[0][2]
    for low, high, name in ATTRIBUTE_TIERS:
        if low <= v < high:
            return name
    # 越界兜底：低于 0 归入门，高于等于上界归大师
    return ATTRIBUTE_TIERS[0][2] if v < 0 else ATTRIBUTE_TIERS[-1][2]
