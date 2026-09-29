<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { api } from '../api'
import { toast } from '../composables/useToast'

const emit = defineEmits(['judged', 'go-judgments', 'go-items'])

// mode: form(打卡) / journal(自由日记)
const mode = ref('form')

// v1.7 打卡表单：选项目 + 写正文 + 可选数字键值对 + 实际发生时间
const form = ref({
  item_id: null,      // 打卡项目（可空 = 纯自由记一笔）
  content: '',        // 正文（必填）
  occurred_at: '',    // datetime-local 字符串
})

// 关键数字（可选，0~5 行可增删）
const kvRows = ref([]) // [{key, value}]

const journalContent = ref('')
const isPure = ref(false) // 纯享记录：只记录不加点、不走 AI 判定

const busy = ref(false)
const error = ref('')

// ============ 打卡项目数据源（v1.7） ============
const items = ref([])
const itemsError = ref('')

const NATURE_META = {
  planned: { label: '规划内', desc: '我定下要做的事' },
  optional: { label: '可选', desc: '可做可不做' },
  negative: { label: '负面', desc: '想少做/避免的事' },
  other: { label: '其他', desc: '杂项' },
}

// 按四类性质分组（下拉 optgroup）
const groupedItems = computed(() => {
  const order = ['planned', 'optional', 'negative', 'other']
  return order
    .map((n) => ({
      nature: n,
      label: NATURE_META[n].label,
      children: items.value.filter((i) => i.nature === n),
    }))
    .filter((g) => g.children.length)
})

const selectedItem = computed(() => items.value.find((i) => i.id === form.value.item_id) || null)

async function loadItems() {
  try {
    items.value = await api.listItems({ enabled: true })
    itemsError.value = ''
  } catch (e) {
    itemsError.value = e.message
    toast.error(e.message)
  }
}

// v1.7：老事件编辑回填时，若其 item 已停用/不存在，需要把该项补进下拉以免回填丢失
async function ensureItemInList(itemId) {
  if (!itemId || items.value.some((i) => i.id === itemId)) return
  try {
    const all = await api.listItems()
    const found = all.find((i) => i.id === itemId)
    if (found) items.value = [found, ...items.value]
  } catch (e) { /* 忽略 */ }
}

// ============ 草稿缓存：切换页面不丢内容 ============
const CACHE_KEY = 'game_of_life_event_draft'

function defaultOccurredAt() {
  // datetime-local 需要 YYYY-MM-DDTHH:mm（本地时区）
  const d = new Date()
  const pad = (n) => `${n}`.padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

onMounted(async () => {
  try {
    const saved = JSON.parse(localStorage.getItem(CACHE_KEY) || 'null')
    if (saved) {
      if (saved.mode) mode.value = saved.mode
      if (saved.form) form.value = { ...form.value, ...saved.form }
      if (saved.kvRows) kvRows.value = saved.kvRows
      if (saved.journalContent) journalContent.value = saved.journalContent
      if (saved.isPure !== undefined) isPure.value = saved.isPure
    }
  } catch (e) { /* 忽略损坏的缓存 */ }
  await loadItems()
  if (form.value.item_id) await ensureItemInList(form.value.item_id)
  if (!form.value.occurred_at) form.value.occurred_at = defaultOccurredAt()
  // v1.3：恢复上次的判定结果/追问状态（切页返回不丢）
  restoreJudgeState()
})

watch([mode, form, kvRows, journalContent, isPure], () => {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify({
      mode: mode.value,
      form: form.value,
      kvRows: kvRows.value,
      journalContent: journalContent.value,
      isPure: isPure.value,
    }))
  } catch (e) { /* 忽略存储失败 */ }
}, { deep: true })

function clearDraft() {
  try { localStorage.removeItem(CACHE_KEY) } catch (e) { /* 忽略 */ }
}

// ============ 关键数字编辑器 ============
function addKvRow() {
  if (kvRows.value.length >= 5) return
  kvRows.value.push({ key: '', value: '' })
}
function removeKvRow(idx) {
  kvRows.value.splice(idx, 1)
}

/** 组装 params：仅保留键非空的行，键名自由（不校验白名单） */
function buildParams() {
  const params = {}
  for (const row of kvRows.value) {
    const k = (row.key || '').trim()
    const v = (row.value || '').trim()
    if (k && v) params[k] = v
  }
  return params
}

// ============ 判定结果/追问状态持久化（v1.3，v1.5 A3 升级）：切页返回不丢 ============
const JUDGE_CACHE_KEY = 'gol_last_judgment'
const previewStale = ref(false) // 恢复时发现缓存判定已失效

function saveJudgeState() {
  try {
    if (result.value || clarifyEvent.value) {
      sessionStorage.setItem(JUDGE_CACHE_KEY, JSON.stringify({
        result: result.value && result.value.status === 'pure' ? result.value : null,
        judgmentId: result.value ? (result.value.judgment_id ?? result.value.id ?? null) : null,
        clarifyEvent: clarifyEvent.value,
        clarifyAnswer: clarifyAnswer.value,
      }))
    } else {
      sessionStorage.removeItem(JUDGE_CACHE_KEY)
    }
  } catch (e) { /* 忽略存储失败 */ }
}

async function restoreJudgeState() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(JUDGE_CACHE_KEY) || 'null')
    if (!saved) return
    if (saved.clarifyEvent) {
      clarifyEvent.value = saved.clarifyEvent
      clarifyAnswer.value = saved.clarifyAnswer || ''
    }
    if (saved.judgmentId) {
      try {
        const j = await api.getJudgment(saved.judgmentId)
        if (j && j.status !== 'invalidated') {
          result.value = j
          return
        }
      } catch (e) { /* 判定不存在（已删除） */ }
      previewStale.value = true
      result.value = null
    } else if (saved.result) {
      result.value = saved.result
    }
  } catch (e) { /* 忽略损坏的缓存 */ }
}

const result = ref(null)
const clarifyEvent = ref(null)
const clarifyAnswer = ref('')

// v1.3：状态持久化 watch（须在 result/clarifyEvent/clarifyAnswer 声明之后）
watch([result, clarifyEvent, clarifyAnswer], saveJudgeState, { deep: true })

/** occurred_at 转换：datetime-local 本地时间 → ISO（后端按本地时区存） */
function toOccurredIso() {
  const raw = form.value.occurred_at
  if (!raw) return null
  const d = new Date(raw)
  return isNaN(d.getTime()) ? null : d.toISOString()
}

async function submitForm() {
  // v1.7：正文必填
  if (!form.value.content.trim()) {
    error.value = '请先写点什么（这次打卡做了什么、感觉怎么样）。'
    return
  }
  const params = buildParams()
  const item = selectedItem.value
  const event = await api.createEvent({
    item_id: form.value.item_id || null,
    source: 'form',
    content: form.value.content.trim(),
    params,
    is_pure: isPure.value,
    occurred_at: toOccurredIso(),
  })
  clearDraft()
  if (isPure.value) {
    result.value = { status: 'pure', summary: '已作为纯享记录保存，不参与 AI 判定。' }
    return
  }
  // 打卡通道不追问（prompt 约定 form 恒 needs_clarify=false），但仍兼容追问返回
  const res = await api.judgeEvent(event.id)
  if (res.needs_clarify) {
    clarifyEvent.value = { id: event.id, questions: res.questions || [] }
    return
  }
  result.value = res
  emit('judged')
}

async function submitJournal() {
  if (!journalContent.value.trim()) {
    error.value = '请先写一段生活记录。'
    return
  }
  const event = await api.createEvent({
    source: 'journal',
    content: journalContent.value.trim(),
    event_type: 'positive', // 占位，后端 AI 会重新提取
    is_pure: isPure.value,
  })
  clearDraft()
  if (isPure.value) {
    result.value = { status: 'pure', summary: '已作为纯享记录保存，不参与 AI 判定。' }
    return
  }
  const res = await api.judgeEvent(event.id)
  if (res.needs_clarify) {
    clarifyEvent.value = { id: event.id, questions: res.questions || [] }
    return
  }
  result.value = res
  emit('judged')
}

// 追问流程：用户回答 AI 的问题后，带补充信息重新判定
async function submitClarify() {
  busy.value = true
  error.value = ''
  try {
    const res = await api.judgeEvent(clarifyEvent.value.id, clarifyAnswer.value.trim())
    if (res.needs_clarify) {
      clarifyEvent.value.questions = res.questions || []
      clarifyAnswer.value = ''
      toast.info('AI 还想再确认几点')
      return
    }
    toast.success('已按补充信息重新判定')
    result.value = res
    clarifyEvent.value = null
    clarifyAnswer.value = ''
    emit('judged')
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  } finally {
    busy.value = false
  }
}

async function submit() {
  busy.value = true
  error.value = ''
  result.value = null
  try {
    if (mode.value === 'form') await submitForm()
    else await submitJournal()
    // v1.9 F2：提交后的统一反馈（纯享保存 / 判定完成 / AI 还想追问）
    if (clarifyEvent.value) toast.info('AI 想再确认几点，请回答下方的追问')
    else if (result.value?.status === 'pure') toast.success('已保存为纯享记录')
    else if (result.value) toast.success('已提交并完成 AI 判定')
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  } finally {
    busy.value = false
  }
}

function reset() {
  form.value = { item_id: null, content: '', occurred_at: defaultOccurredAt() }
  kvRows.value = []
  journalContent.value = ''
  result.value = null
  clarifyEvent.value = null
  clarifyAnswer.value = ''
  previewStale.value = false
  clearDraft()
}

// v1.3：只清除判定结果/追问状态（保留表单草稿）
function clearResult() {
  result.value = null
  clarifyEvent.value = null
  clarifyAnswer.value = ''
  previewStale.value = false
}

// ============ v1.7 B4：记录页事件列表（按日期分组 + 日记/事件两栏 + 逐级折叠） ============
const listEvents = ref([])
const listJudgments = ref([])
const listError = ref('')
const showAll = ref(false) // 更早的记录是否展开（默认收进「查看全部」）
const dayExpanded = ref({}) // 各日期组的展开状态（默认全展开）
const eventsExpanded = ref({}) // 「事件」栏是否展开（默认收起为一行）
const detailOpen = ref({}) // 单条记录详情是否展开
const VALUE_KEYS = ['时长', '距离', '强度', '说明', '配速'] // 老事件参数展示用

const STATUS_LABEL = { pending: '待确认', adjusted: '已调整', confirmed: '已入账', rejected: '已驳回', invalidated: '已作废' }

async function loadList() {
  try {
    listEvents.value = await api.listEvents(false)
    listJudgments.value = await api.listJudgments()
    listError.value = ''
  } catch (e) {
    listError.value = e.message
    toast.error(e.message)
  }
}

function judgmentFor(eventId) {
  return listJudgments.value.find((j) => j.event_id === eventId)
}

function fmtTime(t) {
  return new Date(t).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function dayKey(t) {
  const d = new Date(t)
  return `${d.getFullYear()}-${`${d.getMonth() + 1}`.padStart(2, '0')}-${`${d.getDate()}`.padStart(2, '0')}`
}

function dayLabel(k) {
  const today = dayKey(new Date())
  const yest = dayKey(new Date(Date.now() - 86400000))
  const before = dayKey(new Date(Date.now() - 2 * 86400000))
  if (k === today) return '今天'
  if (k === yest) return '昨天'
  if (k === before) return '前天'
  const [, m, d] = k.split('-')
  return `${Number(m)} 月 ${Number(d)} 日`
}

/** 按日期分组 → 组内分「日记 / 事件」两栏（v1.7 B4 决策 10） */
const dayGroups = computed(() => {
  const map = new Map()
  for (const e of listEvents.value || []) {
    const k = dayKey(e.created_at)
    if (!map.has(k)) map.set(k, { key: k, label: dayLabel(k), journal: [], events: [] })
    const bucket = map.get(k)
    if (e.source === 'journal') bucket.journal.push(e)
    else bucket.events.push(e)
  }
  return [...map.values()].sort((a, b) => (a.key < b.key ? 1 : -1))
})

/** 近三天默认展示；更早的收进「查看全部」 */
const RECENT_DAYS = 3
const recentGroups = computed(() => dayGroups.value.filter((g, idx) => idx < RECENT_DAYS))
const olderGroups = computed(() => dayGroups.value.filter((g, idx) => idx >= RECENT_DAYS))

function isDayOpen(key) {
  return dayExpanded.value[key] !== false // 默认展开
}
function toggleDay(key) {
  dayExpanded.value = { ...dayExpanded.value, [key]: !isDayOpen(key) }
}
function isEventsOpen(key) {
  return !!eventsExpanded.value[key] // 事件栏默认收起为一行
}
function toggleEvents(key) {
  eventsExpanded.value = { ...eventsExpanded.value, [key]: !isEventsOpen(key) }
}
function isDetailOpen(id) {
  return !!detailOpen.value[id]
}
function toggleDetail(id) {
  detailOpen.value = { ...detailOpen.value, [id]: !isDetailOpen(id) }
}

/** 事件摘要：项目名 + 正文首行 + 加点概览 */
function eventSummary(e) {
  const text = (e.content || e.title || '').trim().split('\n')[0]
  return text.length > 40 ? text.slice(0, 40) + '…' : text
}
function changeSummary(eventId) {
  const j = judgmentFor(eventId)
  if (!j || !j.suggested_changes || !j.suggested_changes.length) return '无加点'
  return j.suggested_changes.map((c) => `${c.name} ${c.delta >= 0 ? '+' : ''}${c.delta}`).join(' · ')
}
/** 参数展示：跳过内部键 `_` */
function paramEntries(e) {
  const p = e.params || {}
  return Object.entries(p).filter(([k, v]) => !k.startsWith('_') && v !== null && v !== '')
}

watch(() => listEvents.value.length, loadItems, { immediate: false })

onMounted(loadList)
</script>

<template>
  <div class="card">
    <h2>记录事件</h2>

    <!-- 模式切换 -->
    <div class="row" style="margin-bottom: 12px">
      <button class="btn small" :class="{ primary: mode === 'form' }" @click="mode = 'form'">打卡</button>
      <button class="btn small" :class="{ primary: mode === 'journal' }" @click="mode = 'journal'">自由日记</button>
    </div>

    <!-- v1.7 打卡：选项目 → 写正文 → 可选数字 -->
    <template v-if="mode === 'form'">
      <div class="field">
        <label>打卡项目</label>
        <select v-model="form.item_id">
          <option :value="null">（不选项目，纯记一笔）</option>
          <optgroup v-for="g in groupedItems" :key="g.nature" :label="g.label">
            <option v-for="it in g.children" :key="it.id" :value="it.id">{{ it.name }}</option>
          </optgroup>
        </select>
        <p v-if="items.length === 0 && !itemsError" class="muted" style="font-size: 12px; margin-top: 4px">
          还没有打卡项目。
          <a href="#" @click.prevent="emit('go-items')" style="color: var(--primary)">去「设置」新建项目 →</a>
          也可以不选项目，直接写正文记录。
        </p>
        <p v-if="itemsError" class="muted" style="font-size: 12px; color: #d33; margin-top: 4px">加载项目失败：{{ itemsError }}</p>
        <p v-if="selectedItem" class="muted" style="font-size: 12px; margin-top: 4px">
          {{ NATURE_META[selectedItem.nature]?.label }}
          <template v-if="selectedItem.frequency_type === 'weekly'"> · 每周 {{ selectedItem.frequency_target }} 次</template>
          <template v-else-if="selectedItem.frequency_type === 'daily'"> · 每天</template>
          <template v-if="selectedItem.category"> · {{ selectedItem.category }}</template>
        </p>
      </div>

      <div class="field">
        <label>写点什么 *</label>
        <textarea v-model="form.content" rows="4" placeholder="今天做了哪些运动？现在感觉怎么样？"></textarea>
      </div>

      <div class="field">
        <label>关键数字（可选）</label>
        <div v-for="(row, idx) in kvRows" :key="idx" class="row" style="margin-bottom: 6px; align-items: center">
          <input v-model="row.key" placeholder="名称，如 时长(分钟)" style="flex: 1" />
          <input v-model="row.value" placeholder="数值，如 30" style="flex: 1" />
          <button class="btn small danger" style="flex: 0 0 auto; min-width: 0" @click="removeKvRow(idx)">删除</button>
        </div>
        <button v-if="kvRows.length < 5" class="btn small" @click="addKvRow">+ 加一行</button>
        <p v-if="kvRows.length === 0" class="muted" style="font-size: 12px; margin-top: 4px">例如「时长(分钟) = 30」；不需要就留空</p>
      </div>

      <div class="field">
        <label>实际发生时间（可选）</label>
        <input type="datetime-local" v-model="form.occurred_at" />
        <p class="muted" style="font-size: 12px; margin-top: 4px">默认现在；补记早先的事时改这里</p>
      </div>
    </template>

    <!-- 自由日记 -->
    <template v-else>
      <div class="field">
        <label>写一段今天的生活记录</label>
        <textarea v-model="journalContent" rows="5" placeholder="例如：昨晚 9 点到 10 点在路边慢跑 5 公里，配速 6 分半，跑完挺轻松的。" ></textarea>
      </div>
      <p class="muted">AI 会自动解析要素（运动/学习/作息/情绪…）并逐面核对，信息不足时会追问。</p>
    </template>

    <label class="field" style="margin-top: 12px; display: flex; align-items: center; gap: 8px">
      <input type="checkbox" v-model="isPure" style="width: auto" />
      <span>纯享记录（只记录，不做 AI 分析、不加点）</span>
    </label>

    <div class="row">
      <button class="btn primary" :disabled="busy" @click="submit">{{ busy ? '处理中…' : (isPure ? '保存纯享记录' : '提交并判定') }}</button>
      <button class="btn" @click="reset">清空</button>
    </div>

    <p v-if="error" class="muted" style="color: #d33">{{ error }}</p>

    <!-- v1.5 A3：缓存的预览判定已失效 -->
    <p v-if="previewStale && !result" class="muted" style="color: #b7791f">
      ℹ️ 上次的判定已更新或已失效，以「判定中心」的现行判定为准。
    </p>

    <!-- AI 追问区（日记信息不足时） -->
    <div v-if="clarifyEvent" class="card" style="margin-top: 12px">
      <h3>🤔 AI 想多了解一点</h3>
      <div v-for="(q, i) in clarifyEvent.questions" :key="i" class="muted" style="margin: 4px 0">• {{ q }}</div>
      <div class="field" style="margin-top: 8px">
        <textarea v-model="clarifyAnswer" rows="2" placeholder="补充回答，例如：坐了 4 小时，中间没起来…"></textarea>
      </div>
      <button class="btn primary" :disabled="busy" @click="submitClarify">{{ busy ? '判定中…' : '提交补充并判定' }}</button>
    </div>

    <!-- 结果预览：纯享 / 判定 两种 -->
    <div v-if="result" class="judgment-item" style="margin-top: 16px">
      <template v-if="result.status === 'pure'">
        <h3>已保存 <span class="tag">纯享记录</span></h3>
        <p class="muted">{{ result.summary }}</p>
      </template>
      <template v-else>
        <h3>AI 判定结果 <span class="tag">{{ STATUS_LABEL[result.status] || result.status }}</span></h3>
        <p class="muted">置信度 {{ (result.confidence * 100).toFixed(0) }}%</p>
        <p v-if="result.confidence_reason" class="muted" style="font-size: 12px; color: #b7791f">💡 {{ result.confidence_reason }}</p>

        <!-- v1.7：跨来源合并明细（已与 N 条记录合并） -->
        <div v-if="result.merged_with && result.merged_with.length" class="muted" style="font-size: 12px; color: #7c5cbf; margin-bottom: 6px">
          <span class="tag">已与 {{ result.merged_with.length }} 条记录合并</span>
          <div v-for="(m, i) in result.merged_with" :key="i" style="margin-top: 2px">
            · {{ m.ref }}<template v-if="m.note">：{{ m.note }}</template>
          </div>
          <div style="margin-top: 2px">如认为不该合并，可在「判定中心」反驳撤销。</div>
        </div>

        <div v-if="result.revision_notes && result.revision_notes.length" class="muted" style="font-size: 12px; color: #2b6cb0">
          <span class="tag">本次修订</span>
          <div v-for="(n, i) in result.revision_notes" :key="i" style="margin-top: 2px">{{ n }}</div>
        </div>

        <div v-if="result.analysis && result.analysis.length" class="analysis-box">
          <div class="analysis-title">🤖 AI 分析过程</div>
          <div v-for="(step, idx) in result.analysis" :key="idx" class="step">{{ step }}</div>
        </div>
        <div v-for="a in result.suggested_changes" :key="a.name" class="judgment-item">
          <span class="attr-name">{{ a.name }}</span>
          <span :class="a.delta >= 0 ? 'positive' : 'negative'">{{ a.delta >= 0 ? '+' : '' }}{{ a.delta }}</span>
          <span class="muted" style="font-size: 12px">
            → 预计入账 {{ (a.delta * (result.confidence || 1)).toFixed(1) }}
          </span>
          <div class="muted">{{ a.reason }}</div>
          <div class="evidence">依据：{{ a.evidence }}</div>
        </div>
        <p v-if="result.summary" class="muted">{{ result.summary }}</p>
        <div class="row" style="margin-top: 8px; align-items: center">
          <button class="btn small primary" @click="emit('go-judgments')">去判定中心确认 →</button>
          <button class="btn small" @click="clearResult">清除这条结果</button>
        </div>
        <p class="muted" style="font-size: 12px; margin-top: 6px">请在「判定中心」确认入账 / 补充信息 / 反驳复核；录错了可删除该事件。</p>
      </template>
    </div>
  </div>

  <!-- ============ v1.7 B4：记录列表（日期分组 + 日记/事件两栏 + 逐级折叠） ============ -->
  <div class="card">
    <h2>最近记录</h2>
    <p class="muted">近三天按日期展示；每天分「日记」与「事件」两栏，点开才看详情。</p>
    <p v-if="listError" class="muted" style="color: #d33">{{ listError }}</p>
    <p v-if="listEvents.length === 0 && !listError" class="muted">还没有记录。</p>

    <template v-for="g in recentGroups" :key="g.key">
      <div style="margin-bottom: 12px">
        <div
          class="row"
          style="align-items: center; cursor: pointer; padding: 6px 4px; border-bottom: 1px solid #eee; user-select: none"
          @click="toggleDay(g.key)"
        >
          <b>{{ g.label }}</b>
          <span class="muted" style="font-size: 12px">{{ g.key }}</span>
          <span class="muted" style="font-size: 12px">日记 {{ g.journal.length }} · 事件 {{ g.events.length }}</span>
          <span class="muted" style="margin-left: auto">{{ isDayOpen(g.key) ? '▾' : '▸' }}</span>
        </div>

        <template v-if="isDayOpen(g.key)">
          <!-- 日记栏：一条一行 -->
          <div v-if="g.journal.length" style="margin-top: 8px">
            <div class="muted" style="font-size: 12px; margin-bottom: 4px">日记 {{ g.journal.length }} 条</div>
            <div v-for="e in g.journal" :key="'j' + e.id" class="judgment-item">
              <div class="row" style="align-items: center; cursor: pointer" @click="toggleDetail(e.id)">
                <span class="muted" style="font-size: 12px">{{ fmtTime(e.created_at) }}</span>
                <b>{{ e.title || '自由日记' }}</b>
                <span class="muted" style="font-size: 12px">{{ changeSummary(e.id) }}</span>
                <span class="muted" style="margin-left: auto">{{ isDetailOpen(e.id) ? '▾' : '▸' }}</span>
              </div>
              <div v-if="isDetailOpen(e.id)" style="white-space: pre-wrap; margin-top: 6px">{{ e.content }}</div>
            </div>
          </div>

          <!-- 事件栏：默认一行，展开后才列出每条 -->
          <div v-if="g.events.length" style="margin-top: 8px">
            <div
              class="judgment-item"
              style="cursor: pointer; display: flex; align-items: center"
              @click="toggleEvents(g.key)"
            >
              <b>事件 {{ g.events.length }} 条</b>
              <span class="muted" style="margin-left: auto">{{ isEventsOpen(g.key) ? '▾' : '▸' }}</span>
            </div>
            <template v-if="isEventsOpen(g.key)">
              <div v-for="e in g.events" :key="'e' + e.id" class="judgment-item" style="margin-left: 12px">
                <div class="row" style="align-items: center; cursor: pointer" @click="toggleDetail(e.id)">
                  <span class="muted" style="font-size: 12px">{{ fmtTime(e.created_at) }}</span>
                  <b>{{ e.title || '未命名事件' }}</b>
                  <span v-if="e.origin === 'challenge'" class="tag" title="由挑战结算生成">挑战</span>
                  <span class="muted" style="font-size: 12px">{{ eventSummary(e) }}</span>
                  <span class="muted" style="font-size: 12px">{{ changeSummary(e.id) }}</span>
                  <span class="muted" style="margin-left: auto">{{ isDetailOpen(e.id) ? '▾' : '▸' }}</span>
                </div>
                <!-- 单条详情 -->
                <template v-if="isDetailOpen(e.id)">
                  <div v-if="e.content" style="white-space: pre-wrap; margin: 6px 0">{{ e.content }}</div>
                  <div v-if="paramEntries(e).length" class="muted" style="margin: 4px 0">
                    {{ paramEntries(e).map(([k, v]) => `${k}：${v}`).join('，') }}
                  </div>
                  <div v-if="judgmentFor(e.id)" class="judgment-item" style="margin-top: 6px">
                    <span class="tag">{{ STATUS_LABEL[judgmentFor(e.id).status] || judgmentFor(e.id).status }}</span>
                    <span class="muted" style="font-size: 12px">置信度 {{ ((judgmentFor(e.id).confidence || 1) * 100).toFixed(0) }}%</span>
                    <div v-for="a in judgmentFor(e.id).suggested_changes" :key="a.name" style="margin-top: 4px">
                      <span class="attr-name">{{ a.name }}</span>
                      <span :class="a.delta >= 0 ? 'positive' : 'negative'">{{ a.delta >= 0 ? '+' : '' }}{{ a.delta }}</span>
                      <span class="muted" style="font-size: 12px">{{ a.reason }}</span>
                    </div>
                  </div>
                  <div v-else class="muted" style="font-size: 12px">尚未判定</div>
                </template>
              </div>
            </template>
          </div>
        </template>
      </div>
    </template>

    <!-- 更早的记录：收进「查看全部」 -->
    <div v-if="olderGroups.length">
      <button class="btn small" @click="showAll = !showAll">
        {{ showAll ? '收起更早的记录 ▴' : `查看全部（更早 ${olderGroups.length} 天）▾` }}
      </button>
      <template v-if="showAll">
        <div v-for="g in olderGroups" :key="'o' + g.key" style="margin-top: 12px">
          <div
            class="row"
            style="align-items: center; cursor: pointer; padding: 6px 4px; border-bottom: 1px solid #eee; user-select: none"
            @click="toggleDay(g.key)"
          >
            <b>{{ g.label }}</b>
            <span class="muted" style="font-size: 12px">{{ g.key }}</span>
            <span class="muted" style="font-size: 12px">日记 {{ g.journal.length }} · 事件 {{ g.events.length }}</span>
            <span class="muted" style="margin-left: auto">{{ isDayOpen(g.key) ? '▾' : '▸' }}</span>
          </div>
          <template v-if="isDayOpen(g.key)">
            <div v-if="g.journal.length" style="margin-top: 8px">
              <div class="muted" style="font-size: 12px; margin-bottom: 4px">日记 {{ g.journal.length }} 条</div>
              <div v-for="e in g.journal" :key="'oj' + e.id" class="judgment-item">
                <div class="row" style="align-items: center; cursor: pointer" @click="toggleDetail(e.id)">
                  <span class="muted" style="font-size: 12px">{{ fmtTime(e.created_at) }}</span>
                  <b>{{ e.title || '自由日记' }}</b>
                  <span class="muted" style="font-size: 12px">{{ changeSummary(e.id) }}</span>
                  <span class="muted" style="margin-left: auto">{{ isDetailOpen(e.id) ? '▾' : '▸' }}</span>
                </div>
                <div v-if="isDetailOpen(e.id)" style="white-space: pre-wrap; margin-top: 6px">{{ e.content }}</div>
              </div>
            </div>
            <div v-if="g.events.length" style="margin-top: 8px">
              <div class="judgment-item" style="cursor: pointer; display: flex; align-items: center" @click="toggleEvents(g.key)">
                <b>事件 {{ g.events.length }} 条</b>
                <span class="muted" style="margin-left: auto">{{ isEventsOpen(g.key) ? '▾' : '▸' }}</span>
              </div>
              <template v-if="isEventsOpen(g.key)">
                <div v-for="e in g.events" :key="'oe' + e.id" class="judgment-item" style="margin-left: 12px">
                  <div class="row" style="align-items: center; cursor: pointer" @click="toggleDetail(e.id)">
                    <span class="muted" style="font-size: 12px">{{ fmtTime(e.created_at) }}</span>
                    <b>{{ e.title || '未命名事件' }}</b>
                    <span class="muted" style="font-size: 12px">{{ eventSummary(e) }}</span>
                    <span class="muted" style="font-size: 12px">{{ changeSummary(e.id) }}</span>
                    <span class="muted" style="margin-left: auto">{{ isDetailOpen(e.id) ? '▾' : '▸' }}</span>
                  </div>
                  <template v-if="isDetailOpen(e.id)">
                    <div v-if="e.content" style="white-space: pre-wrap; margin: 6px 0">{{ e.content }}</div>
                    <div v-if="paramEntries(e).length" class="muted" style="margin: 4px 0">
                      {{ paramEntries(e).map(([k, v]) => `${k}：${v}`).join('，') }}
                    </div>
                    <div v-if="judgmentFor(e.id)" class="judgment-item" style="margin-top: 6px">
                      <span class="tag">{{ STATUS_LABEL[judgmentFor(e.id).status] || judgmentFor(e.id).status }}</span>
                      <div v-for="a in judgmentFor(e.id).suggested_changes" :key="a.name" style="margin-top: 4px">
                        <span class="attr-name">{{ a.name }}</span>
                        <span :class="a.delta >= 0 ? 'positive' : 'negative'">{{ a.delta >= 0 ? '+' : '' }}{{ a.delta }}</span>
                        <span class="muted" style="font-size: 12px">{{ a.reason }}</span>
                      </div>
                    </div>
                    <div v-else class="muted" style="font-size: 12px">尚未判定</div>
                  </template>
                </div>
              </template>
            </div>
          </template>
        </div>
      </template>
    </div>
  </div>
</template>
