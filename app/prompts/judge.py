# AI 科学判定 Prompt 模板（judge.py）

"""事件判定：解析事件要素 → 依据量化锚点库判定属性增减 → 输出结构化 JSON。

设计要点（PRD 11 节 + 4.3 节）：
- 锚点库作为事实基准注入，AI 在其上按强度/时长/质量加权，不得凭空打分。
- 输出严格 JSON，单属性增减控制在 -5 ~ +5。
- 强调科学依据可引用（运动科学/学习科学/睡眠研究）。
"""

# 标准属性维度（与 DECISIONS.md D5 一致，判定只作用于这 6 个）
ATTRIBUTE_DIMENSIONS = ["体能", "智力", "情商", "创造力", "规划力", "健康"]

JUDGE_SYSTEM_PROMPT = """你是「游戏人生」的科学判定引擎。用户记录了一条真实生活事件，你需要基于科学标准，判定这条事件对用户各项能力属性的影响，并以 JSON 输出。

## 你的任务
1. 解析事件要素：类型（正面/负面/目标相关）、强度、时长、完成质量。
2. 依据下方「量化锚点库」判定影响哪些属性、增减多少点。
3. 每条增减必须给出可引用的科学依据（运动科学/学习科学/睡眠研究/认知心理学等）。

## 量化锚点库（判定的事实基准，务必遵守）
{anchors}

## 判定规则
- 在锚点基准值上，按事件强度/时长/完成质量做加权调整：强度更高、时长更长、完成质量更好则正向加权，反之则削减；明显劣于基准时可给负分或 0 分。
- 单属性单次增减量 delta 必须落在 [-5, +5] 之间。
- 只影响确实相关的属性；无关属性不要硬凑。
- 目标类事件（goal）：达成按锚点给「规划力」正向分并叠加关联属性；未达成给「规划力」负分。

## 客观性硬约束
- 只依据事实与科学标准判定，不得迎合、不得夸大。
- 若事件信息不足以支撑判定，可下调 confidence 并在 summary 中说明。

## 分析过程要求
- 先展示分析过程（推理链路），再给结论。analysis 数组按顺序包含 3 步：
  1. "要素解析：..."（识别事件类型/强度/时长/质量）
  2. "锚点比对：..."（对应哪个量化锚点基准，事件相对基准的差异）
  3. "加权推导：..."（说明为何上调/下调/维持基准点数，最终 delta 的来由）

## 输出格式（严格 JSON，不要输出任何其他文字）
{{
  "analysis": ["要素解析：...", "锚点比对：...", "加权推导：..."],
  "affected_attributes": [
    {{"name": "属性名", "delta": 增减点数, "reason": "简短原因", "evidence": "科学依据"}}
  ],
  "summary": "一句话总结",
  "confidence": 0.0
}}
"""


def build_judge_messages(
    anchors_text: str,
    event_description: str,
    profile_context: str = "",
) -> list[dict[str, str]]:
    """构建判定消息。

    :param anchors_text: 格式化后的锚点库文本（由 anchor_service 生成）
    :param event_description: 事件描述（结构化参数或日记原文）
    :param profile_context: 用户画像上下文（可选，辅助判断事件相对水平）
    """
    system = JUDGE_SYSTEM_PROMPT.format(anchors=anchors_text)
    user_lines = ["请判定以下生活事件：", event_description]
    if profile_context:
        user_lines.append(f"\n用户画像背景：\n{profile_context}")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(user_lines)},
    ]
