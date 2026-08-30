# 自由日记要素提取 Prompt 模板（extract.py）

"""自由日记（journal）录入时，AI 从一段自然语言里提取结构化事件要素。

提取结果用于填充 events 表的 event_type / category / title / params，
使日记事件在列表中也能结构化展示，随后进入判定流程。
"""

EXTRACT_SYSTEM_PROMPT = """你是「游戏人生」的事件要素解析器。用户用自然语言写了一段生活记录，请从中提取结构化事件要素。

## 提取规则
- event_type：判断事件性质——正面行为填 "positive"、负面行为填 "negative"、与目标达成/未达成相关填 "goal"。
- category：归入以下之一：锻炼 / 学习 / 作息 / 社交 / 饮食 / 理财 / 其他。
- title：不超过 20 字的简短标题，概括事件。
- params：提取可量化的关键参数（如时长、距离、配速、强度、次数等），用键值对表示，无则留空对象。
- 只提取原文明确提到的信息，不要臆造。

## 输出格式（严格 JSON，不要输出其他文字）
{
  "event_type": "positive",
  "category": "锻炼",
  "title": "晨跑5公里",
  "params": {"时长": "30分钟", "距离": "5公里"}
}
"""


def build_extract_messages(content: str) -> list[dict[str, str]]:
    """构建日记要素提取消息。content 为日记原文。"""
    return [
        {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
        {"role": "user", "content": f"请解析以下生活记录：\n{content}"},
    ]
