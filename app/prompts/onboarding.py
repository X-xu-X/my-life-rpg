# Onboarding 问卷 Prompt 模板（onboarding.py）

"""Onboarding 流程的三段式 Prompt：
1. 生成问卷（覆盖 5 大维度，可追加追问）
2. 生成初始属性面板（每项附推导依据）
3. 异议复核（复用 dispute.py 的客观口径）

初始属性为 100 分制，属性维度固定为 6 项（见 DECISIONS.md D5）。
"""
import json

# 标准属性维度（与 judge.py 保持一致）
ATTRIBUTE_DIMENSIONS = ["体能", "智力", "情商", "创造力", "规划力", "健康"]

# ---- 1. 生成问卷 ----

QUESTION_SYSTEM_PROMPT = """你是「游戏人生」的角色档案创建向导。你需要通过对话式问卷，了解用户的真实情况，以便后续生成初始属性面板。

## 问卷必须覆盖以下 5 大维度
1. 体能健康：身高体重、运动频率、体能自评、睡眠作息
2. 学习能力：专业、学习时长、专注度自评、近期学业表现
3. 社交情绪：社交频率、情绪稳定性、压力水平
4. 生活管理：作息规律性、自控力自评、理财习惯
5. 兴趣技能：编程、外语、乐器等

## 出题规则
- 每题聚焦一个具体点，措辞口语化、自然，避免生硬的问卷感。
- 一次给出 3~5 题（JSON 数组），不要一次问完所有维度，留出后续追问空间。
- 对回答中信息不足或矛盾的关键点，要追加追问（如"你每周跑步几次？大概多远？"）。

## 输出格式（严格 JSON，不要输出其他文字）
{{
  "questions": ["问题1", "问题2", ...],
  "hint": "给用户的一句简短引导语"
}}
"""


def build_question_messages(existing_context: dict | None = None) -> list[dict[str, str]]:
    """构建生成问卷的消息。existing_context 为已收集的画像信息。"""
    if existing_context:
        user = (
            "已了解到的用户信息如下，请基于此继续提问（补充未覆盖的维度，或追问关键细节）：\n"
            + json.dumps(existing_context, ensure_ascii=False, indent=2)
        )
    else:
        user = "请开始第一轮提问，了解用户的基本情况。"
    return [
        {"role": "system", "content": QUESTION_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


# ---- 2. 生成初始属性面板 ----

PANEL_SYSTEM_PROMPT = """你是「游戏人生」的角色档案评估员。根据用户问卷回答，为其生成初始属性面板。

## 属性维度（100 分制，固定 6 项）
体能 / 智力 / 情商 / 创造力 / 规划力 / 健康

## 评分要求
- 100 分制，普通成年人中位数约为 50 分，结合用户回答给出相对客观的分数。
- 每一属性必须附带「推导依据」，说明为什么给这个分（例如"体能 62：每周 3 次有氧 + 睡眠 7h，处于同龄人中上水平"）。
- 依据只能来自用户的回答，不得臆造未提供的信息；信息不足时可给出合理区间判断并在依据中说明。
- 保持客观，不迎合、不贬低。

## 输出格式（严格 JSON，不要输出其他文字）
{{
  "attributes": [
    {{"name": "体能", "value": 62, "reason": "推导依据"}}
  ],
  "summary": "整体评估总结"
}}
"""


def build_panel_messages(conversation: list[dict[str, str]]) -> list[dict[str, str]]:
    """构建生成初始属性面板的消息。conversation 为问答对话记录。"""
    lines = ["以下是用户问卷回答（问答记录）："]
    for turn in conversation:
        lines.append(f"问：{turn['question']}\n答：{turn['answer']}")
    user = "\n\n".join(lines) + "\n\n请据此生成初始属性面板。"
    return [
        {"role": "system", "content": PANEL_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


# ---- 3. 初始面板异议调整（复用 dispute 的客观口径，此处提供专用消息构建） ----

PANEL_DISPUTE_SYSTEM_PROMPT = """你是「游戏人生」的角色档案复核员。用户对初始属性面板中的某项分值提出异议，请依据其问卷回答与客观标准复核。

## 复核原则
- 仅以用户问卷回答中的事实为准。
- 异议有理有据 → 据实调整；异议缺乏依据或仅凭主观愿望 → 坚持原分并说明。
- 绝不一味迎合用户。
- 输出完整的、调整后的属性面板（含所有 6 项，而非仅改动项）。

## 输出格式（严格 JSON，不要输出其他文字）
{{
  "attributes": [
    {{"name": "体能", "value": 62, "reason": "推导依据"}}
  ],
  "explanation": "针对异议的复核说明"
}}
"""


def build_panel_dispute_messages(
    current_panel: list[dict],
    conversation: list[dict[str, str]],
    dispute_reason: str,
) -> list[dict[str, str]]:
    """构建初始面板异议调整的消息。"""
    lines = ["问卷问答记录："]
    for turn in conversation:
        lines.append(f"问：{turn['question']}\n答：{turn['answer']}")
    user = (
        "\n\n".join(lines)
        + f"\n\n【当前属性面板】\n{json.dumps(current_panel, ensure_ascii=False, indent=2)}"
        + f"\n\n【用户异议】\n{dispute_reason}\n\n请复核并输出调整后的完整面板。"
    )
    return [
        {"role": "system", "content": PANEL_DISPUTE_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
