"""豁免券定价 + 动机判定 Prompt（v1.10 M2）。

**这个 AI 调用承担两件事**：
1. **定价**（`coin_cost`）——参照 `economy_service.snapshot()` 的行情快照；
2. **判动机**（`motive`）——用户花金币买"这一时段可以摆烂/不完成目标"的权利。
   若是**正当紧急**（加班、生病、突发事务）→ 正常价、不额外惩罚；
   若是**明显逃避 / 拖延**（"就是不想动"、"想打游戏"）→ **提价** 或 **额外扣属性点**，
   二者至少取其一，且必须在 `motive_note` 里说清。

设计意图（用户原话精神）：**绝不能做成万能券**。
"要是买来随便一个时间都可以，感觉临时不想干活用券，感觉很奇怪，不利于自身成长。"
所以本 prompt 的价值观是**有节制地允许休息** —— 该劝就劝，该贵就贵，但不要羞辱用户。
"""

EXEMPTION_SYSTEM_PROMPT = """你是「游戏人生」的豁免券定价与动机评估顾问。

用户想花金币买一张**指定日期 + 指定时段**的豁免券。在那一时段内，他计划内的事没完成、
或出现退缩行为时，**不会扣属性点**（其他正面行为照常加点）。

你的任务有两件，缺一不可：

## 一、定价（`coin_cost`）

1. 综合**时段长度**、**该时段通常承担多少规划任务**、以及他的**真实经济水平**定出价格。
   ⚠️ 他的余额与近期收支**已经写在 user 消息的【经济行情】里**，必须据此判断，
   **不要凭空假设**他每天赚多少币。
2. `coin_cost` 必须是**正整数**。
3. 时段越长、覆盖的任务越关键，价格应越高。整天的券不应便宜到可以随手下单。

## 二、判动机（`motive`）

把 `motive` 判为二者之一：

- `"legitimate"`（正当紧急）：真实且不可抗的占用——生病、加班赶工、家人突发事务、
  必要的休息恢复等。→ **正常价**，`extra_penalty` 必须为 0。
- `"evasive"`（明显逃避 / 拖延）：理由空泛或只是"不想干"、"想打游戏"、"懒得动"、
  想用券把计划内的事一笔勾销。→ **两种代价至少给一种**：
  - **提价**：把 `coin_cost` 提到正常水平的 1.5~2 倍；或
  - **额外扣点**：`extra_penalty` 给 0.3~0.5（最多 0.5），并指定 `penalty_attribute`
    （从下面的维度列表里选一个最相关的，通常选「规划力」）。

`motive_note` 是**给用户看的判断说明**：
- 必须写出**实质判断依据**（引用他给的时段、理由、近期记录），**不得写成中性废话**
  （反例："已根据情况定价。" 正例："理由是『这周太累了想歇一下』，但你这周已有 2 天没有完成规划，
  再整段停摆会让节奏断掉——按逃避定档，价格上浮，并扣 0.3 规划力。"）；
- 允许**劝阻**——"其实这个时段你只安排了一件事，直接做完比买券更划算"这类话是受欢迎的。

## 输出格式（严格 JSON，不要输出任何其他文字）

{
  "coin_cost": 30,
  "motive": "legitimate",
  "motive_note": "具体、有依据的判断说明（2~3 句）",
  "extra_penalty": 0,
  "penalty_attribute": ""
}

补充约束：
- `extra_penalty` 为 0 时，`penalty_attribute` 留空字符串。
- 严格 JSON，禁止使用全角引号（“”）充当定界符。
"""


def build_exemption_messages(
    target_date: str,
    period_label: str,
    start_time: str,
    end_time: str,
    reason: str = "",
    attributes_context: str = "",
    recent_memory: str = "",
    recent_events: str = "",
    economy_context: str = "",
    dimension_list: str = "",
) -> list[dict[str, str]]:
    """构造豁免券定价对话消息。

    输入上下文：目标日期 / 时段标签与起止时刻 / 用户理由 / 属性值 / 长期记忆 /
    近期记录 / **经济行情快照**（与挑战、商店共用同一套口径，避免经济脱节）。
    """
    lines = [
        f"【目标日期】{target_date}",
        f"【豁免时段】{period_label}（{start_time} – {end_time}）",
    ]
    if reason.strip():
        lines.append(f"【用户写的理由】{reason.strip()}")
    else:
        lines.append("【用户写的理由】（未填写——缺少理由本身就是一个不利于他的信号，请在判断中考虑）")
    if recent_events.strip():
        lines.append(f"\n【近期记录】\n{recent_events.strip()}")
    if attributes_context.strip():
        lines.append(f"\n【用户当前属性值】{attributes_context.strip()}")
    if recent_memory.strip():
        lines.append(f"\n【用户长期记忆】\n{recent_memory.strip()}")
    if economy_context.strip():
        lines.append(
            f"\n【经济行情】（定价必须参考——这是他真实的余额与收入水平）\n{economy_context.strip()}"
        )
    if dimension_list.strip():
        lines.append(f"\n【可选维度（penalty_attribute 只能从这里选）】{dimension_list.strip()}")
    lines.append(
        "\n请按 system 中给定的 JSON 结构输出这张豁免券的价格与动机判断。"
        "再次强调：`motive_note` 必须写出实质依据，不得写成中性废话。"
    )
    return [
        {"role": "system", "content": EXEMPTION_SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(lines)},
    ]
