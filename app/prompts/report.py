# 成长周报/月报 Prompt 模板（report.py）

"""AI 生成成长报告：基于用户一段时间内的事件、属性变化，给出温暖有洞察的总结与建议。"""

REPORT_SYSTEM_PROMPT = """你是「游戏人生」的成长顾问。根据用户的成长数据，生成一份温暖而有洞察的成长报告。

## 报告要点
1. 肯定成长与亮点：具体到事件和属性变化（引用数据，不空泛）。
2. 客观指出需要注意的方面：如某属性下降、负面事件增多等，但语气不评判。
3. 给出 2~3 条可执行的建议：结合数据给出，具体可行。
4. 整体基调：温暖、鼓励、真诚。

## 输出格式（严格 JSON，不要输出其他文字）
{
  "highlights": "亮点总结（1-2 句）",
  "concerns": "需要关注的方面（1-2 句，没有则写'整体平稳'）",
  "suggestions": ["建议1", "建议2", "建议3"],
  "tone": "一句话整体评价"
}
"""


def build_report_messages(period: str, start: str, end: str, stats: dict) -> list[dict[str, str]]:
    """构建生成报告的消息。

    :param period: week / month
    :param start: 起始日期 YYYY-MM-DD
    :param end: 结束日期 YYYY-MM-DD
    :param stats: 统计信息（事件数、类别分布、属性变化、判定数）
    """
    stats_text = (
        f"期间：{start} ~ {end}\n"
        f"事件总数：{stats.get('events_count', 0)}\n"
        f"类别分布：{stats.get('events_by_category', {})}\n"
        f"属性变化：{stats.get('attribute_changes', {})}\n"
        f"确认入账的判定数：{stats.get('confirmed_count', 0)}\n"
        f"纯享记录数：{stats.get('pure_count', 0)}\n"
        f"目标情况：{stats.get('goals', {})}\n"
    )
    user = (
        f"请为以下用户生成{'周报' if period == 'week' else '月报'}：\n{stats_text}\n"
        "请给出成长报告。"
    )
    return [
        {"role": "system", "content": REPORT_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
