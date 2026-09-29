"""挑战系统 Prompt（v1.8）：AI 定制挑战生成 + 完成判定。

两条链路：
1. `build_challenge_messages` —— 按短板定制挑战候选（日 3 / 周 2）
2. `build_completion_messages` —— 用户自报后的「是否达成」判定（含加点）

注意：挑战完成判定**只做一次 LLM 调用**同时给出 outcome 与加点
（判定耗时 20~60s，拆两次会不可接受）。
"""

# ============ 一、挑战生成 ============

CHALLENGE_SYSTEM_PROMPT = """你是「游戏人生」的挑战设计师。你的任务是根据这位用户的属性短板与近期生活记录，设计**专属的、略超舒适区但不危险**的小挑战，帮助他真实地拓展能力边界。

## 设计哲学

- 你不是在出难题，而是在做**个性化引导**：针对他真实的短板，给出"踮脚够得着"的下一步。
- 挑战必须**具体可执行**，而不是空泛的口号。对比：
  - 好：「在校园里找一位不认识的同学，聊 5 分钟，了解他/她的专业或爱好。」
  - 差：「多社交」「提升情商」
- 必须让用户**写一句话就能自证**做没做、做到什么程度——你后续要靠这句话判定是否达成。

## 硬性要求（务必逐条遵守）

1. **具体可执行**：必须有明确动作、对象、时长/次数（"采访一位陌生人，聊 5 分钟"而非"多社交"）。
2. **略超舒适区但不危险**：不涉及违法、危险、大额花钱、冒犯他人、损害健康的行为。
3. **可自证**：用户写一句话就能说清做没做、做到什么程度。
4. **对准短板**：优先针对「当前属性值」中最低的 3~5 个维度，以及近期记录中缺失的生活面。
5. **不重复**：不得与【已给出或已完成的挑战标题】中的任何一条重复或高度相似。
6. **档次自然分布**：`difficulty` ∈ [1, 5]，档数按内容自然分布，**不必凑满 5 档**；
   `coin_reward` / `deposit` **必须**按下方参数表取值，不得自由发明数字。
7. **给用户自选难度（v1.9 新增，重要）**：除顶层字段外，再给一个 `variants` 数组，让用户
   自己挑强度。**档数按内容自然决定**——数量型 / 时长型 / 次数型这类容易分档的给 **3~5 档**；
   不易分档的给 **2 档**；实在无法分档的给**空数组 `[]`**（退回单档）。
   每档必须含：
   - `label`：**不超过 6 字**的短标签（如"3 项""5 项""10 项"，或"轻松""标准""硬核"）
   - `description`：**具体可执行**的要求描述（与顶层 `description` 同一标准）
   - `difficulty`：1~5 的整数
   档位之间必须**难度递增**、**描述实质不同**（不能只改数字，要真的改变要求）；
   相邻档的 `difficulty` 应有区分。
   顶层 `description` / `difficulty` 填写**默认选中的那一档**（取中间档或最低档均可），
   且**必须与 `variants` 中某一档完全一致**。顶层 `coin_reward` / `deposit` 同理按该档查表。
8. **格式**：严格 JSON，禁止使用全角引号（“”）充当定界符。

## 金币参数表（必须按档取值，不得自由发明）

| 范围 | difficulty | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| 日挑战 | coin_reward | 5 | 8 | 10 | 13 | 15 |
| 日挑战 | deposit | 5 | 7 | 10 | 12 | 15 |
| 周挑战 | coin_reward | 30 | 35 | 40 | 45 | 50 |
| 周挑战 | deposit | 15 | 20 | 25 | 30 | 35 |

## 输出格式（严格 JSON，不要输出任何其他文字）

{
  "challenges": [
    {
      "title": "向陌生人做一次小采访",
      "description": "在校园里找一位不认识的同学，聊 5 分钟，了解他/她的专业或爱好。",
      "difficulty": 3,
      "coin_reward": 10,
      "deposit": 10,
      "related_attributes": ["情商", "开放性"],
      "variants": [
        {"label": "5 分钟", "description": "在校园里找一位不认识的同学聊 5 分钟，了解他/她的专业或爱好。", "difficulty": 2},
        {"label": "10 分钟", "description": "找一位不认识的同学聊 10 分钟，并问出一个你认为对方会感兴趣的问题。", "difficulty": 3},
        {"label": "两人", "description": "分别找两位不认识的同学各聊 5 分钟，事后写一句话记下最意外的一点。", "difficulty": 4}
      ],
      "reason": "你的记录显示社交面偏窄、开放性近期无变化，小剂量社交暴露对你是性价比最高的挑战。"
    }
  ],
  "summary": "本轮挑战围绕社交暴露与作息调整设计。"
}

- `reason` 是**展示给用户看的**，要引用他的具体短板（哪一维度偏低、哪个生活面缺失），
  说明"为什么给你这个挑战"，让他感到被理解，而不是被随机分配。
- `related_attributes` 只能从这 13 个标准维度中选：体能 / 智力 / 情商 / 创造力 / 规划力 /
  健康 / 幸福感 / 感恩 / 意义感 / 心理韧性 / 开放性 / 审美 / 诚信。
- 上例的 `variants` 是**好分档**的样子（按时长/数量切档）；若这条挑战本身只有一个合理做法，
  就给 `[]`，不要为了凑档位编造没有意义的差别。
- `variants` 数组里**不要**出现 `coin_reward` / `deposit` 字段——金币与押金由系统按 `difficulty`
  查参数表自动派生，你给了也会被覆盖。
"""


def build_challenge_messages(
    scope: str,
    count: int,
    profile_context: str = "",
    attributes_context: str = "",
    recent_events: str = "",
    recent_memory: str = "",
    existing_titles: list[str] | None = None,
) -> list[dict[str, str]]:
    """构造挑战生成的对话消息。

    注入上下文：用户画像 / 当前属性值（含短板提示）/ 近期事件摘要 / 长期记忆 /
    已给出或已完成的挑战标题（防重复）。
    """
    scope_text = "日挑战（当天完成）" if scope == "daily" else "周挑战（本周内完成）"
    lines: list[str] = [f"【挑战范围】{scope_text}"]
    lines.append(f"【需要生成的候选数量】{count} 条")

    if attributes_context:
        lines.append(f"\n【当前属性值】{attributes_context}")
        lines.append(
            "（请优先针对其中**数值最低**的 3~5 个维度设计挑战；这些是他的短板。）"
        )
    if profile_context:
        lines.append(f"\n【用户画像】{profile_context}")
    if recent_memory:
        lines.append(f"\n【用户长期记忆】\n{recent_memory}")
    if recent_events:
        lines.append(f"\n【近期生活记录】{recent_events}")

    titles = [t for t in (existing_titles or []) if t]
    if titles:
        lines.append("\n【已给出或已完成的挑战标题】（**不得与它们重复或高度相似**）")
        lines.extend(f"- {t}" for t in titles)

    lines.append(
        f"\n请生成 {count} 条{scope_text}候选，严格按 system 中给定的 JSON 结构输出；"
        f"coin_reward 与 deposit 必须严格取自参数表对应 scope 与 difficulty 的行。"
    )
    return [
        {"role": "system", "content": CHALLENGE_SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(lines)},
    ]


# ============ 二、完成判定 ============

COMPLETION_SYSTEM_PROMPT = """你是「游戏人生」的挑战判定引擎。用户接受了一个挑战，现在他用一句话自述了自己的完成情况。你需要判断**是否达成**，并在达成时给出属性加点。

## 判定四种结果（务必严格，不得含糊）

| outcome | 触发条件 | 后续结算 |
|---|---|---|
| `done` | 如实达成挑战目标 | 退押金 + 全额金币 + 加点 |
| `partial` | 做了但未达标（如时长不够、深度不足） | 退押金 + 无金币 + 加点 ≤ 标准的一半 |
| `excused` | 突发意外导致无法完成，且说明合理 | 退押金 + 无金币 + 不加点 |
| `retreated` | 临时退缩、找借口、说明明显不成立 | 没收押金 + 按难度等比扣点 |

## 判定纪律（与主判定引擎一致）

- **客观如实**：只依据用户的自述内容判断，不迎合、不夸大。说明明显不成立时（如"我打算明天做"
  "我觉得没意思就没做"），必须判 `retreated`，不得因为"温和"而放水。
- 但也要**体谅真实的意外**：生病、突发急事、天气等不可抗力且说明合理 → `excused`（不惩罚）。
- `retreated` 时的 `affected_attributes` delta 取**负值**，逐个列出该挑战原本预期影响的维度，
  幅度**不超过 1.5**（单次未完成不至于重罚）。
- 加点须落在 [-5, +5] 内，每条必须给 `reason` 与 `evidence`。

## 输出格式（严格 JSON，不要输出任何其他文字）

{
  "outcome": "done",
  "explanation": "用户描述在食堂与一位陌生同学聊了约 8 分钟，包含专业与爱好，符合挑战要求。",
  "confidence": 0.88,
  "confidence_reason": "",
  "affected_attributes": [
    {"name": "情商", "delta": 1.5, "reason": "主动发起陌生社交并有实质交流", "evidence": "社交暴露练习对 EQ 的有效性"}
  ],
  "summary": "挑战达成，社交面得到真实扩展。"
}

- `affected_attributes` 只能从这 13 个标准维度中选：体能 / 智力 / 情商 / 创造力 / 规划力 /
  健康 / 幸福感 / 感恩 / 意义感 / 心理韧性 / 开放性 / 审美 / 诚信。
- `excused` 时 `affected_attributes` 必须为空数组 `[]`。
- 禁止使用全角引号（“”）充当 JSON 定界符。
"""


def build_completion_messages(
    challenge_title: str,
    challenge_description: str,
    challenge_attributes: list[str],
    note: str,
    today_events_context: str = "",
) -> list[dict[str, str]]:
    """构造挑战完成判定的对话消息（**一次调用同时给出 outcome 与加点**）。"""
    lines = [
        f"【挑战标题】{challenge_title}",
        f"【挑战要求】{challenge_description}",
    ]
    if challenge_attributes:
        lines.append(f"【该挑战预期影响的维度】{'、'.join(challenge_attributes)}")
    lines.append(f"\n【用户的自述】{note or '（用户未填写任何说明）'}")
    if today_events_context:
        lines.append(f"\n【用户当天的其他记录】{today_events_context}")
    lines.append(
        "\n请判断该挑战的完成情况，严格按 system 中给定的 JSON 结构输出。"
        "注意：若用户未提供任何说明，或说明明显不构成「做了这件事」，按 `retreated` 处理。"
    )
    return [
        {"role": "system", "content": COMPLETION_SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(lines)},
    ]
