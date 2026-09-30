"""子维度提议 Prompt（v1.10 M3）。

某主维度接近满级（>= 95）时，AI 结合该维度的**真实历史记录**提议 2~4 个细分方向
（用户举例：智力 → 数学思维 / 空间想象 / 逻辑推理）。

产物**只是提议**：必须用户勾选确认后才创建子维度行（M3-1）。
"""

SUBDIMENSION_SYSTEM_PROMPT = """你是「游戏人生」的属性细分顾问。

用户某个属性维度已经接近满级（0~100 分制），继续笼统地加分已经没有信息量了。
你的任务：结合他**真实的历史记录**，把这个维度拆成 2~4 个**可分别积累、互不重叠**的细分方向，
让后续的成长能被更准确地刻画。

## 要求

1. **数量 2~4 个**，宁少勿滥；宁可给 3 个扎实的，也不要凑 4 个含糊的。
2. **每个方向必须是同一层级的概念**，不能出现"A 包含 B"的包含关系。
3. **必须结合他的实际记录**：他记录过什么、哪方面强哪方面弱，方向要能落到他真实的行为上，
   不能给一套放之四海而皆准的通用清单。
4. **名称要短**（4~8 个字，如"数学思维""空间想象""逻辑推理"），
   `description` 用一句话说明这个方向具体看什么行为（20~50 字）。
5. 方向名称**不得与该主维度同名**，也不得与其它系统维度同名。
6. 严格 JSON，禁止使用全角引号（“”）充当定界符。

## 输出格式（严格 JSON，不要输出任何其他文字）

{
  "items": [
    {"name": "数学思维", "description": "对数量关系、抽象符号与数学建模的敏感度与推理能力。"},
    {"name": "逻辑推理", "description": "拆解问题、识别前提与结论、发现论证漏洞的能力。"}
  ],
  "reason": "为什么这样拆（结合他的记录，1~2 句）"
}
"""


def build_subdimension_messages(
    parent_name: str,
    parent_value: float,
    parent_description: str = "",
    dimension_list: str = "",
    recent_events: str = "",
    memory_context: str = "",
) -> list[dict[str, str]]:
    """构造子维度提议对话消息。"""
    lines = [
        f"【主维度】{parent_name}（当前 {parent_value:.1f} / 100，已接近满级）",
    ]
    if parent_description.strip():
        lines.append(f"【该维度现有说明】{parent_description.strip()}")
    if recent_events.strip():
        lines.append(f"\n【他近期与该维度相关的记录】\n{recent_events.strip()}")
    else:
        lines.append("\n【他近期与该维度相关的记录】（暂无——请基于该维度的通用结构拆分，并保守给 2~3 个方向）")
    if memory_context.strip():
        lines.append(f"\n【用户长期记忆】\n{memory_context.strip()}")
    if dimension_list.strip():
        lines.append(f"\n【系统中已有的维度名（细分方向不得与之同名）】{dimension_list.strip()}")
    lines.append("\n请按 system 中给定的 JSON 结构输出 2~4 个细分方向。")
    return [
        {"role": "system", "content": SUBDIMENSION_SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(lines)},
    ]
