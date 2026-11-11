> **执行状态（2026-11-11 补记）：M1 已完成，M4 部分完成，其余未执行，M7 已撤销。**
>
> - 已完成：M1（`6d957ce`，做法见 M1 段末的「实际落地记录」）
> - 部分完成：M4（`6d957ce` 只加了 `title` 反馈，无颜色类、无 `label` prop）
> - 未执行：M2、M3、M5、M6、M8
> - **M7 撤销**：原判断有误，Vue 3 不使用 `onMounted` 回调的返回值作清理函数，详见 `UI_IA_FOLLOWUP2_SPEC_2026-11-11.md` 第七节
> - 另：`5c34625` 修正了两处旧名（成长报告 / 奖励）
>
> 未执行项由 `docs/UI_IA_FOLLOWUP2_SPEC_2026-11-11.md` 承接。本文档保留原文，不再修改正文。

# UI-IA 后续修补规格（Follow-up v1）

> 面向执行者（writer）的开发文档。
> 撰写时间：2026-11-10 23:40
> 上游依据：`docs/UI_IA_DEV_SPEC_2026-11-10.md`（已执行完毕）、`docs/review/UI_IA_SPEC_REVIEW_2026-11-10.md`（审查结论）
> 适用仓库：`my-life-rpg`，基线 commit `00d07da`

---

## 〇 三十秒速览

**这份文档不是新功能派发，是对已上线实现的缺陷修补。**

`UI_IA_DEV_SPEC_2026-11-10.md` 的批次 A/B/C 已于 2026-11-10 21:38–22:04 全部落地（8 个 commit，`c91e923` → `00d07da`）。审查这批落地结果后，发现 **1 个必修的视觉回归、4 个健壮性缺陷、2 个可访问性问题、1 个文档状态问题**，本规格只处理这些。

| 编号 | 优先级 | 一句话 | 涉及文件 | 规模 |
|---|---|---|---|---|
| M1 | **P0 必修** | 提示行下边距被清零，5 处内容贴死 | `tips.css` | 1 行 |
| M2 | P1 | 已关闭的提示每次刷新先闪一下 | `useTipPrefs.js`、`TipLine.vue` | ~6 行 |
| M3 | P1 | 手机上（局域网 HTTP）关不掉提示且不报错 | `useTipPrefs.js` | ~12 行 |
| M4 | P1 | 关闭失败时用户完全无感知 | `TipLine.vue`、`tips.css` | ~10 行 |
| M5 | P1 | 快速连点两条 × 会撞乐观锁静默失败 | `useTipPrefs.js` | ~8 行 |
| M6 | P2 | 6 个 × 的屏幕阅读器标签完全相同 | `TipLine.vue` + 6 处接入 | 6 行 + 组件 |
| M7 | P2 | `onMounted` 直接传异步函数 | `TipLine.vue` | 1 行 |
| M8 | P3 | 旧规格文档仍以"待执行"口吻留存 | 上游 md | 追加块 |

**共 4 个批次、8 个 commit，前端 4 个文件 + 1 个文档。不动后端、不动接口、不动业务逻辑、不改任何面向用户的文案。**

---

## 一 背景（动手前必读）

### 1.1 这次补的是什么

上一轮实现了"行级说明可以逐条永久关闭"（F7）。机制是：每条说明包成 `<TipLine id="...">`，行尾一个淡「×」，点击后把 id 写入服务端 `experience_preferences.suppressed_lines`，全站不再显示。

后端这套做得很稳（乐观锁、旧客户端兼容、老行 NULL 兜底都测过了）。**问题全在前端表现层**：

- 提示行换成了 flex 容器，顺手写了个 `margin: 0`，把原来段落自带的 12px 下边距干掉了；
- 状态是异步拉的，但渲染没等它，已关闭的提示会先画出来再消失；
- 幂等键用了 `crypto.randomUUID()`，这在局域网 HTTP 下不存在；
- 关闭失败只写了内部 `error`，界面上什么也没发生。

### 1.2 三个必须先知道的事实

**事实一：`.tip-line` 只有一个来源。**
全仓 `tip-line` 样式只在 `frontend/src/tips.css` 定义，`record-detail.css`、`navigation.css` 都没有同名规则。改这一个文件就够，不用担心别处覆盖。

**事实二：`tips.css` 是最后加载的样式表之一。**
`frontend/src/main.js` 的导入顺序是 `design-tokens → styles → ui-layout → daily-use → navigation → tips → record-detail`。`tips.css` 在第 9 行，**晚于** `ui-layout.css`（第 6 行）和 `navigation.css`（第 8 行）。所以 `.tip-line`（优先级 0,1,0）会盖掉 `p { margin: 0 0 12px }`（优先级 0,0,1），这就是 M1 的根因。

**事实三：`request_key` 必须是合法 UUID。**
`app/services/workflow_common.py:18` 写的是 `request_key: UUID`。任何"随手拼一个字符串"的降级方案都会被 422 拒绝。M3 必须生成符合 UUID v4 格式的字符串。

### 1.3 六个 TipLine 接入点（M1/M6 会用）

| id | 文件:行 | 所在位置 |
|---|---|---|
| `today.write-hint` | `PageHub.vue:56` | 今天页顶部写入卡 |
| `growth.ability-note` | `PageHub.vue:84` | 成长页「能力数值」折叠体 |
| `growth.baseline` | `PageHub.vue:96` | 成长页「选择游戏起点」卡 |
| `journal.pure-flag` | `RecordList.vue:32` | 手账列表「纯享标记」说明 |
| `diary.same-day` | `DiaryView.vue:43` | 日记页「日记原文」卡 |
| `calendar.dot` | `RecordCalendar.vue:12` | 记录日历底部 |

---

## 二 总原则与禁区

### 2.1 五条铁律

1. **只改本文档列出的位置。** 发现其他问题记进 `docs/DECISIONS.md` 的 backlog，不要顺手改。
2. **不改任何面向用户的文案。** 本规格里出现的文字（如"这次没保存成功"）是唯一例外，且必须逐字照抄。
3. **不动后端。** `app/` 下一行都不用改；接口契约、字段名、校验规则保持原样。
4. **不动业务逻辑。** 不碰金币、属性、挑战、奖励、写入协议（`useWorkflowWrite`）。
5. **一个 commit 一个逻辑单元。** 中文 message，格式 `类型: 简述`（沿用仓库既有风格，如 `fix(hints): 恢复提示行段落间距`）。

### 2.2 禁区清单

| 禁止 | 原因 |
|---|---|
| 改 `useWorkflowWrite.js` | 它第 10 行也有 `crypto.randomUUID()`，但那是全站写入协议，改动影响面远超本规格，已单独登记 backlog |
| 用 `localStorage` 存提示开关 | 权威状态在服务端，本地缓存会导致多设备不一致 |
| 把 `.tip-line` 改成 `display: block` 或加 `!important` | 会破坏「文字 + ×」同行布局；flex 是设计意图 |
| 改 `TIP` 的 6 条 id 命名 | `LineId` 正则是 `^[a-z][a-z0-9-]*(\.[a-z0-9-]+){1,2}$`，现有 6 条都合规，改了会让已关闭的记录失效 |
| 删除或改写 `UI_IA_DEV_SPEC_2026-11-10.md` 正文 | M8 只允许在文件头部**追加**状态块 |
| 引入新的 npm 依赖 | 本批全是原生 API，不需要 |

---

## 三 修改清单

### M1 [P0 必修] 恢复提示行的段落下边距

**位置**
- 文件：`frontend/src/tips.css`
- 行号：第 2–7 行，规则 `.tip-line`
- 锚点文本：`margin: 0;`（该文件内唯一一处裸 `margin: 0;`）

**现状**
```css
.tip-line {
  display: flex;
  gap: 8px;
  align-items: baseline;
  margin: 0;
}
```

**改为**
```css
.tip-line {
  display: flex;
  gap: 8px;
  align-items: baseline;
  margin: 0 0 12px;
}
```

**原因**

这些说明行原本是普通 `<p>`，靠 `ui-layout.css:14` 的 `p { margin: 0 0 12px; }` 拿到 12px 下边距。包成 `TipLine` 后，`.tip-line` 是类选择器（0,1,0），优先级高于元素选择器（0,0,1），`margin: 0` 直接把下边距清零。结果这些说明和它下方的元素贴死。

实测受影响的 **5 处**：

| 位置 | 贴死对象 |
|---|---|
| `growth.ability-note` | 与下方 `.hub-ability-grid`（能力数值网格）贴死 |
| `growth.baseline` | 与下方 `.hub-inline-link`（「选择基线 ›」）贴死 |
| `journal.pure-flag` | 与下方记录条目贴死 |
| `diary.same-day` | 与下方「保存方式」下拉的 label 贴死 |
| `calendar.dot` | 与卡片底边贴死，圆点日期格显得拥挤 |

**第 6 处 `today.write-hint` 不受影响，也不需要处理。** 因为 `navigation.css` 里有 `.hub-write-card p { font-size:13px; color:#84869b; margin:0 }`，选择器含一个类加一个元素（0,1,1），优先级高于 `.tip-line`（0,1,0），写入卡内始终保持 `margin: 0`。这正是设计意图（写入卡是紧凑横排）。

**预期效果**
- 上述 5 处的说明行与其下方元素之间出现约 12px 空隙，与全站其他段落间距一致；
- 今天页顶部写入卡的排版**完全不变**（若变了就是改错了，立刻回退检查优先级）；
- 提示行仍是「文字 + 行尾 ×」同一行，× 位置不变。

**自检**
1. 打开 `/`（今天页），写入卡内「一件小事，或一篇晚间日记。」与右侧按钮仍同一行、间距不变。
2. 打开 `/growth`，展开「能力数值」，说明行与数值网格之间有可见空隙。
3. 打开 `/growth`（未建档账号），「选择游戏起点」卡内说明与「选择基线 ›」之间有可见空隙。
4. 打开 `/journal`，纯享标记说明与列表之间有可见空隙。
5. 打开 `/diary`，说明行与「保存方式」之间有可见空隙。
6. 打开带记录日期的日历，说明行与卡片底边之间有可见空隙。

**实际落地记录（2026-11-11 补记）**

落地方式与本文档不同：`6d957ce` 直接**删除了** `.tip-line` 里的 `margin: 0`，而不是改成 `margin: 0 0 12px`。

结果等价（5 处恢复 12px 下边距），但上面「原因」一段的表述需要更正：这 12px 并非来自 `.muted` / `.hub-small-note`（这两个类都不定义 `margin`：`.muted` 见 `ui-layout.css:32`，`.hub-small-note` 见 `navigation.css:6`），而是来自 `ui-layout.css:14` 的全局 `p { margin: 0 0 12px }`。删除 `margin: 0` 后，`.tip-line` 不再覆盖该规则，12px 自然恢复。

后续排查间距问题时请按这个真实原因判断，不要去找 `.muted` 的 margin。

---

### M2 [P1] 消除已关闭提示的首帧闪烁

**位置**
- 文件 A：`frontend/src/composables/useTipPrefs.js`
  - 第 1 行 import
  - 第 10 行后（新增 `ready`）
  - 第 72–74 行 `useTipPrefs()` 的返回值
- 文件 B：`frontend/src/components/ui/TipLine.vue` 第 7 行

**现状**

`useTipPrefs.js`
```js
import { ref } from 'vue'
```
```js
const prefs = ref(null)
```
```js
export function useTipPrefs() {
  return { prefs, loading, error, ensure, hidden, hide, refresh }
}
```

`TipLine.vue`
```js
const shown = computed(() => !tips.hidden(props.id))
```

**改为**

`useTipPrefs.js`
```js
import { computed, ref } from 'vue'
```
```js
const prefs = ref(null)
// 就绪门：异步拉取完成前不渲染提示行，避免"已关闭的提示先闪一下再消失"
const ready = computed(() => prefs.value !== null)
```
```js
export function useTipPrefs() {
  return { prefs, loading, error, ready, ensure, hidden, hide, refresh }
}
```

`TipLine.vue`
```js
const shown = computed(() => tips.ready.value && !tips.hidden(props.id))
```

**原因**

`prefs` 初值是 `null`，而 `hidden()` 在 `prefs` 为 `null` 时返回 `false`（第 38 行 `(prefs.value?.suppressed_lines || []).includes(id)`），于是 `shown` 首帧为 `true` —— 用户已经关掉的 6 条说明会先渲染出来，等 `ensure()` 的 GET 回来才消失。

这个功能的全部诉求就是"别让我反复看到"，结果每次刷新都闪一下，等于没解决。实测在每次刷新、每次路由切换进含提示的页面时都会出现。

**关于失败路径**：`ensure()` 的 `catch`（第 25–29 行）会把 `prefs.value` 设成默认对象，所以 `ready` 会正常变 `true`，提示照常显示 —— 符合"失败时宁可继续显示，也不让内容凭空消失"的既定原则，不会因为断网就看不到提示。

**预期效果**
- **已关闭的提示：从头到尾不出现，无闪烁**（这是本条要解决的唯一问题）；
- 未关闭的提示：在 GET 返回后出现（本机通常 < 100ms），出现的一瞬间下方内容会被下推约 12px。**这是本方案接受的代价**：把"看到不想要的内容"换成"内容稍晚补齐"，前者更刺眼；
- 断网/接口失败：提示正常显示（不是隐藏），与改动前一致。

**为什么不用 sessionStorage 做首帧快照**（更彻底，但本轮不做）

理论上可以把上次的 `suppressed_lines` 同步读成初值，做到既不闪也不跳。代价是 `ensure()` 要区分"有缓存但未拉服务端"和"已拉过"，还要处理切换账号时清缓存，逻辑复杂度明显上升、出错面变大。本轮的判断是：**先用最简方案消除刺眼的那一半（闪烁），跳动留在可接受范围**。如果实测觉得跳动碍眼，再单独立项做快照，不要在本条里顺手加。

**自检**
1. 在偏好页关掉任意一条，刷新对应页面，肉眼确认该条从未出现（不是"出现后消失"）。
2. 强制让接口失败（DevTools → Network → 阻断 `/api/experience-preferences`），确认提示仍然显示。
3. 确认未关闭的提示最终出现，且页面无残留空白。

---

### M3 [P1] `crypto.randomUUID()` 加降级，手机端才能关提示

**位置**
- 文件：`frontend/src/composables/useTipPrefs.js`
- 行号：第 49 行
- 锚点文本：`request_key: crypto.randomUUID(),`

**现状**
```js
        // WriteIn 要求 request_key（幂等键）；缺了会 422
        request_key: crypto.randomUUID(),
```

**改为**

先在文件顶部（`let inflight = null` 之后、`async function ensure()` 之前）新增：
```js
/**
 * 生成 UUID v4。crypto.randomUUID 只在安全上下文（HTTPS / localhost）存在，
 * 手机通过局域网 http://10.x.x.x 访问时为 undefined，直接调用会抛错。
 * 后端 WriteIn.request_key 的类型是 UUID，降级结果必须是合法 UUID 格式。
 */
function uuid4() {
  if (globalThis.crypto?.randomUUID) return crypto.randomUUID()
  const b = new Uint8Array(16)
  if (globalThis.crypto?.getRandomValues) globalThis.crypto.getRandomValues(b)
  else for (let i = 0; i < 16; i += 1) b[i] = Math.floor(Math.random() * 256)
  b[6] = (b[6] & 0x0f) | 0x40
  b[8] = (b[8] & 0x3f) | 0x80
  const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('')
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`
}
```
再把第 49 行替换为：
```js
        request_key: uuid4(),
```

**原因**

`crypto.randomUUID()` 属于 Secure Context API。以下几种访问方式下它是 `undefined`，调用直接抛 `TypeError`：

- 手机通过局域网访问开发/自建服务：`http://10.205.200.71:5173`（本机实测 IP）；
- 任何非 localhost 的 `http://` 地址。

抛错被 `hide()` 的 `catch`（第 59 行）吞掉，只写进内部 `error` 并返回 `false`。而 `TipLine.dismiss()` 丢弃了这个返回值 —— 于是**用户在手机上点 × 完全没反应，也没有任何提示**。这是"关不掉且不知道为什么"的典型。

同时提醒：**不要用 `'rk-' + Date.now()` 这类字符串降级**，`request_key: UUID` 会直接 422。必须是标准 UUID v4 格式（36 位、含连字符、第 13 位为 4、第 17 位为 8/9/a/b）。

**预期效果**
- HTTPS 与 localhost：行为与现在完全一致（走 `randomUUID`）；
- 局域网 HTTP：`uuid4()` 走降级分支，生成合法 UUID，PUT 正常通过，× 可以点掉；
- 不改变任何重试/幂等语义（仍是每次点击一个新 key）。

**自检**
1. 桌面 localhost 下点 × 能关闭（回归）。
2. DevTools 控制台执行 `delete crypto.randomUUID` 后点 ×，网络面板应看到 PUT `/api/experience-preferences` 返回 200，该条消失。
3. 在响应里确认 `request_key` 是 36 位带连字符的标准格式。
4. 用手机（或改 host 为非 localhost 的 http 地址）实测点 ×，确认能关掉。

---

### M4 [P1] 关闭失败要给出反馈

**位置**
- 文件 A：`frontend/src/components/ui/TipLine.vue`（整个 `<script setup>` 与 `<template>` 的 button 部分）
- 文件 B：`frontend/src/tips.css`（在第 25 行 `:focus-visible` 规则之后追加）

**现状**

> 下面贴的是**基线状态**（commit `00d07da`）。若你已按顺序做完 M2，`shown` 那一行已经是 `tips.ready.value && ...`，属正常，不要改回去；本条只关心 `defineProps`、`dismiss` 和 button。

`TipLine.vue`
```js
const props = defineProps({ id: { type: String, required: true } })
const tips = useTipPrefs()
const shown = computed(() => !tips.hidden(props.id))
onMounted(tips.ensure)
async function dismiss() {
  await tips.hide(props.id)
}
```
```html
    <button
      type="button"
      class="tip-line-close"
      aria-label="不再显示这行说明"
      title="不再显示这行说明"
      @click="dismiss"
    >
      ×
    </button>
```

**改为**

`TipLine.vue` 的 script（**在 M2 改完的基础上**，只动 `props`、新增 `failed`/`closeLabel`、重写 `dismiss`）：

```js
import { computed, onMounted, ref } from 'vue'
import { useTipPrefs } from '../../composables/useTipPrefs'

const props = defineProps({
  id: { type: String, required: true },
  label: { type: String, default: '不再显示这行说明' },
})
const tips = useTipPrefs()
const failed = ref(false)
const shown = computed(() => tips.ready.value && !tips.hidden(props.id))
const closeLabel = computed(() =>
  failed.value ? '这次没保存成功，点一下再试' : props.label
)
onMounted(tips.ensure)          // ← 这一行本条不动，M7 单独改
async function dismiss() {
  failed.value = false
  const ok = await tips.hide(props.id)
  if (!ok) failed.value = true
}
```

对比 M2 之后的版本，本条的净变化只有三处：`defineProps` 增加了 `label`、新增 `failed` 与 `closeLabel` 两个声明、`dismiss` 从两行变成四行并处理返回值。**不要把 `onMounted` 一起改掉**，那是 M7 的内容，混在一起会让 commit 6 与 commit 7 的 diff 交叉。

`TipLine.vue` 的 button：
```html
    <button
      type="button"
      class="tip-line-close"
      :class="{ 'is-failed': failed }"
      :aria-label="closeLabel"
      :title="closeLabel"
      @click="dismiss"
    >
      ×
    </button>
```

`tips.css` 追加：
```css
.tip-line-close.is-failed {
  opacity: 1;
  color: var(--danger);
}
```

**原因**

`hide()` 返回 `false` 表示这次保存失败（网络错、409 乐观锁、422 校验），但 `dismiss()` 把返回值丢掉了。用户点 × 之后：提示还在、界面上没有任何变化、也不知道该不该再点。上游规格 4.3 明确要求"失败时按钮 title 改为『这次没保存成功』"，实现漏了这一条。

**注意 `label` prop 是本条与 M6 的共用改动**，先在这里加上，M6 只负责在 6 处接入点传值。

**预期效果**
- 成功：与原行为一致，提示消失；
- 失败：提示保留，× 变红并保持不透明，鼠标停留显示 `这次没保存成功，点一下再试`；再点一次会重试（`failed` 先归零）。

**自检**
1. 正常网络点 ×，提示消失，无红色残留。
2. DevTools 阻断 PUT 请求后点 ×：× 变红、显示失败 title、提示仍在。
3. 恢复网络后重试同一位置，能成功关闭。
4. 确认 `--danger` 变量已存在于 `design-tokens.css`（已确认存在，无需新增）。

---

### M5 [P1] 关闭操作串行化，避免连点撞乐观锁

**位置**
- 文件：`frontend/src/composables/useTipPrefs.js`
- 行号：第 41–63 行，函数 `hide`

**现状**
```js
async function hide(id) {
  const p = await ensure()
  const next = [...new Set([...(p.suppressed_lines || []), id])]
  try {
    const saved = await api.flow(
      '/experience-preferences',
      {
        // WriteIn 要求 request_key（幂等键）；缺了会 422
        request_key: crypto.randomUUID(),
        expected_version: p.version,
        suppressed: p.suppressed || [],
        suppressed_lines: next,
        return_disabled: !!p.return_disabled,
      },
      'PUT'
    )
    prefs.value = { ...saved, suppressed_lines: saved.suppressed_lines || [] }
    return true
  } catch (e) {
    error.value = e.message
    return false
  }
}
```

**改为**
```js
async function doHide(id) {
  const p = await ensure()
  const next = [...new Set([...(p.suppressed_lines || []), id])]
  try {
    const saved = await api.flow(
      '/experience-preferences',
      {
        // WriteIn 要求 request_key（幂等键）；缺了会 422
        request_key: uuid4(),
        expected_version: p.version,
        suppressed: p.suppressed || [],
        suppressed_lines: next,
        return_disabled: !!p.return_disabled,
      },
      'PUT'
    )
    prefs.value = { ...saved, suppressed_lines: saved.suppressed_lines || [] }
    return true
  } catch (e) {
    error.value = e.message
    return false
  }
}

// 串行队列：偏好接口是 PUT 全量替换 + 乐观锁，两次并发会用同一个 expected_version，
// 后到的那次必然 409。串行化后第二次能读到第一次返回的新 version。
let chain = Promise.resolve()
function hide(id) {
  const run = chain.then(() => doHide(id))
  chain = run.then(() => {}, () => {})
  return run
}
```

**原因**

接口是 `PUT` + `expected_version` 乐观锁。用户在成长页快速连点两个 ×（或先点一条再立刻点另一条），两次 `hide()` 会并发读到同一个 `p.version`，第一次 PUT 成功后 version 自增，第二次必然 `409`。当前没有重试，第二次静默失败 —— 用户看到的是"有一条关不掉"。

`doHide` 里的 `ensure()` 会返回同一个 `prefs` 引用，但 `p.version` 是在 `await` 之后读取的，串行执行时第二次能读到第一次更新后的 `prefs.value.version`，因此不会 409。

**注意**：`chain` 必须吞掉错误（`chain = run.then(() => {}, () => {})`），否则一次失败会让整条队列 reject，后续点击全部失效。`hide` 仍需返回原 promise，让调用方能拿到 `true/false`。

**依赖**：本条把 `crypto.randomUUID()` 换成了 `uuid4()`，因此**必须在 M3 之后执行**。若跳过 M3 先做本条，`uuid4` 未定义，关闭功能会整体报错。

**预期效果**
- 连点两个 ×：两次都成功，服务端 `suppressed_lines` 两条都在；
- 单点：行为不变；
- 任一次失败不影响后续点击。

**自检**
1. 在成长页连续快速点两个 ×，刷新页面，两条都不再出现。
2. 查数据库 `experience_preferences.suppressed_lines`，两条 id 都在。
3. DevTools 让第一次 PUT 失败，再点一条，第二条仍能成功。

---

### M6 [P2] 让 6 个 × 的屏幕阅读器标签可区分

**位置**
- 文件：`frontend/src/components/ui/TipLine.vue` —— 无需再改（M4 已加 `label` prop）
- 文件：6 处接入点，各加一个 `label` 属性

**现状**

6 处都是 `<TipLine id="xxx" class="yyy">文字</TipLine>`，组件内 `aria-label` 固定为「不再显示这行说明」。屏幕阅读器用户连续听到 6 次完全相同的按钮名，无法判断点的是哪一条。

**改为**

| 文件:行 | 现状 | 改为 |
|---|---|---|
| `PageHub.vue:56` | `<TipLine id="today.write-hint">` | `<TipLine id="today.write-hint" label="不再显示「今天发生了什么」这行提示">` |
| `PageHub.vue:84` | `<TipLine id="growth.ability-note" class="hub-small-note">` | `<TipLine id="growth.ability-note" class="hub-small-note" label="不再显示「能力数值」这行提示">` |
| `PageHub.vue:96` | `<TipLine id="growth.baseline" class="hub-small-note">` | `<TipLine id="growth.baseline" class="hub-small-note" label="不再显示「选择游戏起点」这行提示">` |
| `RecordList.vue:32` | `<TipLine id="journal.pure-flag" class="muted">` | `<TipLine id="journal.pure-flag" class="muted" label="不再显示「纯享标记」这行提示">` |
| `DiaryView.vue:43` | `<TipLine id="diary.same-day" class="muted">` | `<TipLine id="diary.same-day" class="muted" label="不再显示「同一日期保存」这行提示">` |
| `RecordCalendar.vue:12` | `<TipLine id="calendar.dot" class="hub-small-note">` | `<TipLine id="calendar.dot" class="hub-small-note" label="不再显示日历圆点说明">` |

**注意**：这 6 个文件里模板都压成单行，`label` 必须插在 `class` 之后、`>` 之前，不要重新格式化整行（避免产生无关 diff）。

**原因**

`aria-label` 相同 = 屏幕阅读器播报相同。工具栏式连续按钮若名称一致，用户无法定位目标，属于 WCAG 2.4.6 范畴。视觉用户靠位置区分，读屏用户只能靠名称。

**预期效果**
- 6 个 × 的 `aria-label` 各不相同，且与所在位置文字对应；
- 视觉上完全无变化（`label` 只用于 `aria-label` 和失败态 `title`）；
- 关闭成功后 `title` 不残留在页面上（元素已移除）。

**自检**
1. DevTools 逐个检查 6 个 `.tip-line-close` 的 `aria-label`，确认互不相同。
2. 确认 6 处页面视觉与改动前一致（对照截图）。
3. 确认 `git diff` 中这 6 个文件只有 `label` 一处新增，无格式变动。

---

### M7 [P2] `onMounted` 不直接传异步函数

**位置**
- 文件：`frontend/src/components/ui/TipLine.vue`
- 行号：第 8 行
- 锚点文本：`onMounted(tips.ensure)`

**现状**
```js
onMounted(tips.ensure)
```

**改为**
```js
onMounted(() => { tips.ensure() })
```

**原因**

Vue 会把 `onMounted` 回调的返回值当作清理函数。`tips.ensure` 是 `async`，返回 Promise，被当成卸载钩子保存；Vue 卸载时执行 `promise()` 会抛 `TypeError: xxx is not a function`。当前因为组件基本不卸载所以没暴露，但属于定时炸弹。顺带也让"这里是在触发请求、不是在注册清理"这层意图变清楚。

**注意**：这是本条的**唯一改动**，一个 1 行 commit。M4 特意保留了 `onMounted(tips.ensure)` 原样，就是为了让这条能独立提交、独立回滚。

**预期效果**
- 功能无变化；
- 组件卸载时不再产生控制台错误。

**自检**
1. 反复切换页面 10 次，控制台无报错。
2. 确认没有 Promise 泄漏警告。

---

### M8 [P3] 给旧规格文档补执行状态

**位置**
- 文件：`docs/UI_IA_DEV_SPEC_2026-11-10.md`
- 位置：文件**最开头**，第一个 `#` 标题之前插入

**现状**

该文档仍以"待执行"口吻描述 F1~F7，但代码早已落地。若后续有人拿它当任务单派发，会出现空操作，甚至误删相邻配置。

**改为**

在文件第一行之前插入：
```markdown
> **执行状态（2026-11-10 23:40 补记）：已执行完毕，本文档转为变更记录。**
>
> 批次 A/B/C 已全部落地，对应 commit：`c91e923`（导航）、`9b898ac`（今天页入口）、`a34a549`（今日安排）、`b61a441`（命名）、`305a043`（去重与返回）、`55cb175`（空状态）、`9c769cb`（偏好字段）、`00d07da`（行级提示）。
> **批次 D（新用户首用态）未执行**，仍待产品确认。
> 遗留缺陷的修补见 `docs/UI_IA_FOLLOWUP_SPEC_2026-11-10.md`。
> 阅读时请注意：本文档中的行号基于落地前基线，与当前代码已有偏移。

```

**原因**

这是上一轮审查的 P0 之一：文档与代码脱节比代码缺陷更危险，因为它会误导下一次执行。

**注意**：只允许在头部**追加**这段引用块，正文一个字都不许改。

**预期效果**
- 任何人打开该文档，第一眼就知道它已执行完毕；
- 批次 D 的待定状态被显式保留；
- 后续修补有明确指向。

**自检**
1. `git diff` 只显示新增 7 行（含末尾空行），无删除、无修改。
2. 渲染后的 Markdown 引用块显示正常。

---

## 四 约束条件

### 4.1 前端约束

1. **Vue 3 `<script setup>` 语法**，不引入 Options API 写法。
2. **不新增依赖**，`crypto`、`Promise` 都是原生能力。
3. **样式只改 `frontend/src/tips.css`**，不要往 `styles.css` / `ui-layout.css` 里加覆盖。
4. **保持 `tips.css` 在 `main.js` 的导入顺序不变**（必须在 `navigation.css` 之后、`record-detail.css` 之前）。
5. **模板单行文件不要重排格式**（`PageHub.vue`、`RecordList.vue`、`DiaryView.vue`、`RecordCalendar.vue` 的 template 都是压缩成单行的，改动只加属性）。

### 4.2 后端约束

**本规格不动后端任何代码。** 以下仅作为理解前提：

- `suppressed_lines` 校验规则：单个 id 需匹配 `^[a-z][a-z0-9-]*(\.[a-z0-9-]+){1,2}$`，最长 48；数组最多 40 项。
- 写入是 `PUT` 全量替换 + `expected_version` 乐观锁，冲突返回 409。
- `request_key` 类型是 `UUID`，非法格式返回 422。
- 读取时老行 `NULL` 已被 `or []` 兜底，前端不需要再处理。

### 4.3 工程约束

1. **一个 commit 一个逻辑单元**，粒度见第五节。
2. **只 add 指定文件**，禁止 `git add .`（工作区长期有 20+ 未跟踪文件）。
3. **commit 后必须 `git log` 回读验证**（历史上出现过"以为提交了其实没执行"）。
4. **不 push**，只 commit。

---

## 五 批次与 commit 切分

| 批次 | commit | 内容 | 涉及文件 | 可独立验证 |
|---|---|---|---|---|
| A | 1 | `fix(hints): 恢复提示行下边距` | `tips.css` | 是（M1） |
| B | 2 | `fix(hints): 提示就绪后再渲染，消除首帧闪烁` | `useTipPrefs.js`、`TipLine.vue` | 是（M2） |
| B | 3 | `fix(hints): 幂等键兼容非安全上下文` | `useTipPrefs.js` | 是（M3） |
| B | 4 | `fix(hints): 关闭失败给出可见反馈` | `TipLine.vue`、`tips.css` | 是（M4） |
| B | 5 | `fix(hints): 关闭操作串行化避免乐观锁冲突` | `useTipPrefs.js` | 是（M5） |
| C | 6 | `a11y(hints): 每条提示的关闭按钮独立命名` | 4 个 .vue 接入文件 | 是（M6） |
| C | 7 | `refactor(hints): 显式触发提示预加载` | `TipLine.vue` | 是（M7） |
| D | 8 | `docs: 标注 UI-IA 规格执行状态` | 上游 md | 是（M8） |

**执行顺序要求**
- **M1 必须第一个提交**，因为它是唯一影响视觉的改动，先落地便于比对后续截图。
- **M4 必须在 M6 之前**，因为 `label` prop 由 M4 引入。
- **M2 与 M4 都改 `TipLine.vue`**，建议按 B 批次顺序做，避免冲突。
- 批次 D 可最后单独做，与代码无关。

---

## 六 验收标准

### 6.1 功能验收

| 编号 | 验收项 | 通过标准 |
|---|---|---|
| A01 | 提示行间距 | 5 处（能力数值、选择起点、纯享标记、日记说明、日历说明）与下方元素有约 12px 空隙 |
| A02 | 写入卡不受影响 | 今天页顶部「一件小事，或一篇晚间日记。」与右侧按钮仍同一行、间距不变 |
| A03 | 无闪烁 | 已关闭的提示刷新后从未出现（不是出现后消失） |
| A04 | 未关闭的提示正常显示 | 清空 `suppressed_lines` 后，6 条全部重新出现 |
| A05 | 接口失败仍显示 | 阻断 GET 后，提示照常显示 |
| A06 | 正常关闭 | 桌面 localhost 点 ×，提示消失，刷新后仍消失 |
| A07 | 非安全上下文关闭 | `delete crypto.randomUUID` 后点 × 仍能关闭，请求 200 |
| A08 | UUID 格式 | 请求体 `request_key` 为 36 位标准 UUID v4 |
| A09 | 失败反馈 | 阻断 PUT 后点 ×，× 变红、title 为「这次没保存成功，点一下再试」、提示保留 |
| A10 | 失败可重试 | 恢复网络后再点同一位置，能成功关闭 |
| A11 | 连点不冲突 | 快速连点两条 ×，两次都成功，服务端两条都在 |
| A12 | 队列不被污染 | 让一次 PUT 失败，随后点另一条仍能成功 |
| A13 | 标签可区分 | 6 个 `.tip-line-close` 的 `aria-label` 互不相同 |
| A14 | 无卸载报错 | 反复切页 10 次，控制台无 `is not a function` 或 Promise 报错 |
| A15 | 恢复入口有效 | 偏好页「恢复一般提示」后，6 条全部回来，「已关闭 0 行说明」 |

### 6.2 回归验收

| 编号 | 回归项 | 通过标准 |
|---|---|---|
| R01 | 前端构建 | `cd frontend && npm run build` 成功，无新增 warning |
| R02 | 后端测试 | `python -m unittest tests.test_daily_use_redesign` 全部通过（本规格未动后端，必须保持通过） |
| R03 | 偏好往返 | `test_A27_tipline_suppressed_lines_roundtrip_and_backward_compat` 通过 |
| R04 | 校验边界 | `test_A27b_tipline_rejects_bad_id_and_over_limit` 通过 |
| R05 | 视觉无意外 | 今天、手账、成长、日记、奖励、我的 六页截图与改动前比对，除 M1 的 5 处间距外无差异 |
| R06 | diff 干净 | 每个 commit 的 `git diff` 只含该 commit 声明的文件与行 |
| R07 | 无残留调试代码 | 全文搜索 `console.log`、`debugger`、`XXX` 无新增 |

### 6.3 证据要求

每个 commit 完成后，在 commit message 正文或后续汇报中给出：
1. 改动文件的 `git diff` 摘要；
2. A0x / R0x 中对应条目的实测结果（不是"应该可以"）；
3. 涉及视觉的（M1/M6）附截图对照。

---

## 七 明确不做（本轮范围外）

| 项 | 为什么不做 |
|---|---|
| `useWorkflowWrite.js` 的同类 `crypto.randomUUID()` | 那是全站写入协议，改动影响面远超本规格。**已登记 backlog，需单独评估** |
| 首次关闭后提示"可在我的 › 显示与提示恢复" | 需要新增全局 toast 或视觉提示，与本轮"减少视觉噪音"目标冲突。偏好页已有「已关闭 N 行说明」可发现 |
| 多标签页实时同步 | `prefs` 是模块级缓存，只有在偏好页保存后才 `refresh()`。同设备另开标签页看不到别的设备刚关的提示。修它需要 BroadcastChannel 或轮询，成本大于收益 |
| 修复旧规格文档的行号偏移（F-2/F-3） | 只在 M8 里加一句提示说明，不逐条校正。校正成本高且无实际收益 |
| 后端接口任何改动 | 本规格是纯前端修补 |
| 批次 D（新用户首用态） | 上游文档已标"默认不做，待产品确认"，本次仍未获确认 |

---

## 八 风险与回滚

| 风险 | 触发条件 | 表现 | 处理 |
|---|---|---|---|
| M1 改多了 | 误把 `.tip-line` 改成 `block` 或加 `!important` | 写入卡内 × 掉到第二行 | 回退 M1，只保留 `margin` 一处改动 |
| M2 引入空窗 | `ready` 逻辑写错，例如用了 `loading` | 提示永远不显示 | 确认 `ready` 基于 `prefs.value !== null`，不是 `!loading` |
| M3 降级不合规 | 用了非 UUID 格式的降级串 | 所有关闭请求 422 | 检查返回字符串是否 36 位、第 13 位为 `4` |
| M5 队列死锁 | 忘了给 `chain` 加 catch 兜底 | 一次失败后所有 × 都点不动 | 确认 `chain = run.then(() => {}, () => {})` |
| M4 红字误报 | 成功路径也置了 `failed` | 正常关闭后 × 变红 | 确认 `dismiss()` 第一行先 `failed.value = false` |

**回滚粒度**：每个 commit 独立可回滚（`git revert <sha>`），无跨 commit 依赖，除 M4 → M6 的 `label` prop 顺序依赖（回滚 M4 前先回滚 M6）。

---

## 附录 A 变更文件清单

| 文件 | 操作 | 涉及条目 |
|---|---|---|
| `frontend/src/tips.css` | 改 1 行 + 追加 4 行 | M1、M4 |
| `frontend/src/composables/useTipPrefs.js` | 改 import、加 `ready`、加 `uuid4`、拆 `doHide` + 队列、改导出 | M2、M3、M5 |
| `frontend/src/components/ui/TipLine.vue` | 改 script 与 button | M2、M4、M7 |
| `frontend/src/components/PageHub.vue` | 3 处加 `label` | M6 |
| `frontend/src/components/RecordList.vue` | 1 处加 `label` | M6 |
| `frontend/src/components/DiaryView.vue` | 1 处加 `label` | M6 |
| `frontend/src/components/RecordCalendar.vue` | 1 处加 `label` | M6 |
| `docs/UI_IA_DEV_SPEC_2026-11-10.md` | 头部追加引用块 | M8 |

**不涉及**：`app/` 下任何文件、`tests/` 下任何文件、`frontend/src/App.vue`、`router.js`、`navigation.js`、`useWorkflowWrite.js`、任何 `.css` 除 `tips.css`。

---

## 附录 B 快速核对命令

开工前确认基线（在仓库根目录执行）：
```
git log --oneline -1
```
应为 `00d07da feat(hints): 行级说明句可逐条关闭`。

确认三个关键事实：
```
grep -n "margin: 0;" frontend/src/tips.css
grep -n "crypto.randomUUID" frontend/src/composables/useTipPrefs.js
grep -c "TipLine id=" frontend/src/components/PageHub.vue frontend/src/components/RecordList.vue frontend/src/components/DiaryView.vue frontend/src/components/RecordCalendar.vue
```

收工前自查（应在 M1 之后执行）：
```
grep -n "margin: 0 0 12px" frontend/src/tips.css
grep -c "uuid4()" frontend/src/composables/useTipPrefs.js
grep -c "label=\"不再显示" frontend/src/components/*.vue
```
预期：第一条命中 1 处，第二条命中 2 处（定义 1 + 调用 1），第三条合计 6 处。

---

**文档结束。** 有任何一条与实际代码对不上，先停下来说明，不要自行推断改法。
