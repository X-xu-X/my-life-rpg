<script setup>
import { ref, watch, onMounted } from 'vue'
import { api } from '../api'

const emit = defineEmits(['judged', 'go-judgments'])

// mode: form(结构化打卡) / journal(自由日记)
const mode = ref('form')

const form = ref({
  event_type: 'positive',
  category: '锻炼',
  title: '',
  duration: '',
  distance: '',
  intensity: '',
  note: '',
})

const journalContent = ref('')
const isPure = ref(false) // 纯享记录：只记录不加点、不走 AI 判定

const categories = ['锻炼', '学习', '作息', '社交', '饮食', '理财', '其他']
const intensities = ['低', '中低', '中等', '中高', '高']

const busy = ref(false)
const error = ref('')
const result = ref(null)

// ============ 草稿缓存：切换页面不丢内容 ============
const CACHE_KEY = 'game_of_life_event_draft'

onMounted(() => {
  try {
    const saved = JSON.parse(localStorage.getItem(CACHE_KEY) || 'null')
    if (saved) {
      if (saved.mode) mode.value = saved.mode
      if (saved.form) form.value = { ...form.value, ...saved.form }
      if (saved.journalContent) journalContent.value = saved.journalContent
      if (saved.isPure !== undefined) isPure.value = saved.isPure
    }
  } catch (e) { /* 忽略损坏的缓存 */ }
  // v1.3：恢复上次的判定结果/追问状态（切页返回不丢）
  restoreJudgeState()
})

watch([mode, form, journalContent, isPure], () => {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify({
      mode: mode.value,
      form: form.value,
      journalContent: journalContent.value,
      isPure: isPure.value,
    }))
  } catch (e) { /* 忽略存储失败 */ }
}, { deep: true })

function clearDraft() {
  try { localStorage.removeItem(CACHE_KEY) } catch (e) { /* 忽略 */ }
}

// ============ 判定结果/追问状态持久化（v1.3，v1.5 A3 升级）：切页返回不丢 ============
// 用 sessionStorage（关浏览器标签即清），避免跳转其他页面后结果重置。
// v1.5 A3 单一数据源：缓存只存 judgment_id，恢复时从 DB 拉现行判定展示——
// 重判就地更新（id 不变）→ 拉到的就是最新结果；判定被作废/不存在 → 丢弃预览并提示。
const JUDGE_CACHE_KEY = 'gol_last_judgment'
const previewStale = ref(false) // 恢复时发现缓存判定已失效

function saveJudgeState() {
  try {
    if (result.value || clarifyEvent.value) {
      sessionStorage.setItem(JUDGE_CACHE_KEY, JSON.stringify({
        result: result.value && result.value.status === 'pure' ? result.value : null, // 纯享无判定直接存
        judgmentId: result.value ? (result.value.judgment_id ?? result.value.id ?? null) : null, // v1.5 A3：判定只存 id（judge 响应键为 judgment_id，详情为 id）
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
    // 追问进行中的状态本地还原（尚未生成判定，无 DB 数据源）
    if (saved.clarifyEvent) {
      clarifyEvent.value = saved.clarifyEvent
      clarifyAnswer.value = saved.clarifyAnswer || ''
    }
    if (saved.judgmentId) {
      // v1.5 A3：从 DB 拉现行判定（校验是否仍有效）
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
      result.value = saved.result // 纯享记录等无判定的结果
    }
  } catch (e) { /* 忽略损坏的缓存 */ }
}



async function submitForm() {
  // 组装结构化参数（仅保留非空字段）
  const params = {}
  if (form.value.duration) params['时长'] = form.value.duration
  if (form.value.distance) params['距离'] = form.value.distance
  if (form.value.intensity) params['强度'] = form.value.intensity
  if (form.value.note) params['说明'] = form.value.note

  const event = await api.createEvent({
    event_type: form.value.event_type,
    category: form.value.category,
    source: 'form',
    title: form.value.title || `${form.value.category}打卡`,
    params,
    is_pure: isPure.value,
  })
  clearDraft()
  if (isPure.value) {
    result.value = { status: 'pure', summary: '已作为纯享记录保存，不参与 AI 判定。' }
    return
  }
  result.value = await api.judgeEvent(event.id)
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
    // AI 认为信息不足，先追问
    clarifyEvent.value = { id: event.id, questions: res.questions || [] }
    return
  }
  result.value = res
  emit('judged')
}

// 追问流程：用户回答 AI 的问题后，带补充信息重新判定
const clarifyEvent = ref(null)
const clarifyAnswer = ref('')

// v1.3：状态持久化 watch（须在 result/clarifyEvent/clarifyAnswer 声明之后）
watch([result, clarifyEvent, clarifyAnswer], saveJudgeState, { deep: true })

async function submitClarify() {
  busy.value = true
  error.value = ''
  try {
    const res = await api.judgeEvent(clarifyEvent.value.id, clarifyAnswer.value.trim())
    if (res.needs_clarify) {
      clarifyEvent.value.questions = res.questions || []
      clarifyAnswer.value = ''
      return
    }
    result.value = res
    clarifyEvent.value = null
    clarifyAnswer.value = ''
    emit('judged')
  } catch (e) {
    error.value = e.message
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
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

function reset() {
  form.value = { event_type: 'positive', category: '锻炼', title: '', duration: '', distance: '', intensity: '', note: '' }
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
</script>

<template>
  <div class="card">
    <h2>记录事件</h2>

    <!-- 模式切换 -->
    <div class="row" style="margin-bottom: 12px">
      <button class="btn small" :class="{ primary: mode === 'form' }" @click="mode = 'form'">结构化打卡</button>
      <button class="btn small" :class="{ primary: mode === 'journal' }" @click="mode = 'journal'">自由日记</button>
    </div>

    <!-- 结构化打卡 -->
    <template v-if="mode === 'form'">
      <div class="row">
        <div class="field">
          <label>事件类型</label>
          <select v-model="form.event_type">
            <option value="positive">正面事件（锻炼/学习/早睡…）</option>
            <option value="negative">负面行为（熬夜/久坐/暴食…）</option>
            <option value="goal">目标相关</option>
          </select>
        </div>
        <div class="field">
          <label>类别</label>
          <select v-model="form.category">
            <option v-for="c in categories" :key="c" :value="c">{{ c }}</option>
          </select>
        </div>
      </div>

      <div class="field">
        <label>简述</label>
        <input v-model="form.title" placeholder="例如：晨跑 5 公里" />
      </div>

      <div class="row">
        <div class="field">
          <label>时长（分钟）</label>
          <input v-model="form.duration" placeholder="如 30" />
        </div>
        <div class="field">
          <label>距离（公里）</label>
          <input v-model="form.distance" placeholder="如 5" />
        </div>
        <div class="field">
          <label>强度</label>
          <select v-model="form.intensity">
            <option value="">—</option>
            <option v-for="i in intensities" :key="i" :value="i">{{ i }}</option>
          </select>
        </div>
      </div>

      <div class="field">
        <label>补充说明</label>
        <textarea v-model="form.note" rows="2" placeholder="其他细节（可选）"></textarea>
      </div>
    </template>

    <!-- 自由日记 -->
    <template v-else>
      <div class="field">
        <label>写一段今天的生活记录</label>
        <textarea v-model="journalContent" rows="5" placeholder="例如：昨晚 9 点到 10 点在路边慢跑 5 公里，配速 6 分半，跑完挺轻松的。" ></textarea>
      </div>
      <p class="muted">AI 会自动解析事件类型、类别和关键参数，然后进入判定流程。</p>
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

    <!-- v1.5 A3：缓存的预览判定已失效（被重判/作废/删除），提示以判定中心为准 -->
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
        <h3>AI 判定结果 <span class="tag">{{ result.status }}</span></h3>
        <p class="muted">置信度 {{ (result.confidence * 100).toFixed(0) }}%</p>
        <!-- v1.4：置信度说明 -->
        <p v-if="result.confidence_reason" class="muted" style="font-size: 12px; color: #b7791f">💡 {{ result.confidence_reason }}</p>
        <!-- AI 分析过程 -->
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
</template>
