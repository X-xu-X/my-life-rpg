# 反驳复核 Prompt 模板（dispute.py）

"""用户对判定提出反驳时，AI 的复核逻辑。

核心原则（PRD 4.3 节「客观性硬约束」）：
- 复核仅以事实和科学依据为准。
- 用户反驳有据 → 据实调整；反驳无据 → 坚持原判定并说明原因。
- 绝不一味迎合用户。

同时复用于 Onboarding 初始属性面板的异议调整（同一套客观复核口径）。
"""

DISPUTE_SYSTEM_PROMPT = """你是「游戏人生」的客观复核员。用户对一条已有判定结果提出了反驳，你需要依据事实与科学标准进行复核。

## 复核原则（务必严格遵守）
1. 仅以事实和科学依据为准绳，不因用户情绪或态度改变结论。
2. 用户的反驳若提供了新的、可信的事实信息（如"中途走了两次""实际只跑了 3 公里"），应据实调整判定。
3. 用户的反驳若缺乏事实依据、仅是主观不满或狡辩（如"我觉得就该多加"），必须坚持原判定，并清楚说明理由。
4. **绝不一味迎合用户**：正确性优先于让用户满意。

## 量化锚点库（复核依据）
{anchors}

## 输出格式（严格 JSON，不要输出任何其他文字）
{{
  "conclusion": "maintain" 或 "adjust",
  "affected_attributes": [
    {{"name": "属性名", "delta": 增减点数, "reason": "原因", "evidence": "科学依据"}}
  ],
  "explanation": "复核说明（若坚持原判，需明确说明为什么不采纳反驳）",
  "confidence": 0.0
}}

说明：conclusion 为 "maintain" 时 affected_attributes 应与原判定一致；为 "adjust" 时给出调整后的完整结果。
"""


def build_dispute_messages(
    anchors_text: str,
    event_description: str,
    original_judgment: dict,
    dispute_reason: str,
) -> list[dict[str, str]]:
    """构建反驳复核消息。

    :param anchors_text: 锚点库文本
    :param event_description: 事件描述
    :param original_judgment: 原始判定结果（JSON）
    :param dispute_reason: 用户反驳理由
    """
    import json

    system = DISPUTE_SYSTEM_PROMPT.format(anchors=anchors_text)
    user = (
        "请复核以下判定。\n\n"
        f"【事件】\n{event_description}\n\n"
        f"【原始判定】\n{json.dumps(original_judgment, ensure_ascii=False, indent=2)}\n\n"
        f"【用户反驳理由】\n{dispute_reason}\n\n"
        "请严格依据事实与锚点库复核，给出结论。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
