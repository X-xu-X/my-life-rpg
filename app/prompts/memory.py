# 长期记忆 Prompt 模板（memory.py）

"""长期记忆（智能体式）：用 LLM 把历史事件压缩成五类摘要，跨会话记住用户。"""

MEMORY_SYSTEM_PROMPT = """你是「游戏人生」的记忆系统。根据用户的历史事件记录，提炼并维护一份长期记忆摘要，让 AI 在后续引导用户时能记住他的近况与长期脉络。

## 记忆内容（五类，输出 JSON）
1. long_term_goals：用户的长期目标/愿景（如考研、完成某个项目、养成某个习惯）。
2. key_experiences：关键经历/里程碑（重要事件、转折点、持续在做的事）。
3. personality：性格特点（从行为中推断，如自律、内向、追求完美）。
4. preferences：生活偏好（作息偏好、兴趣、喜欢的活动）。
5. current_status：当前状态/近期关注（最近在忙什么、情绪状态、压力来源）。

## 要求
- 基于事实推断，不编造；不确定的宁可不写。
- 精炼，每条一句话；每个类别 1~3 条。
- 若提供了已有长期记忆，请增量合并新信息，不要丢失旧的重要记忆。
- 输出严格 JSON，不要输出任何其他文字。
"""


def build_memory_messages(existing_memory: str, events_summary: str) -> list[dict[str, str]]:
    """构建记忆更新消息。

    :param existing_memory: 已有的长期记忆（JSON 文本，可能为空）
    :param events_summary: 近期事件摘要（用于提炼/更新记忆）
    """
    user = (
        f"已有长期记忆（可能为空）：\n{existing_memory or '（无）'}\n\n"
        f"近期事件记录：\n{events_summary}\n\n"
        f"请更新长期记忆（合并旧记忆 + 新事件，提炼五类摘要）。"
    )
    return [
        {"role": "system", "content": MEMORY_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
