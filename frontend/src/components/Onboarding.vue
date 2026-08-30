<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { api } from '../api'

const emit = defineEmits(['created'])

// phase: init(未开始) / asking(问答中) / done(首次面板已生成) / completed(已完成，可补充)
const phase = ref('init')
const messages = ref([]) // {role:'ai'|'user', text}
const currentQuestions = ref([])
const answerInputs = ref({})
const panel = ref(null)
const summary = ref('')
const confidence = ref(0)
const busy = ref(false)
const error = ref('')
const chatEl = ref(null)

// 补充长期信息相关
const supplementText = ref('')
const pendingAdjustment = ref(null)
const supplementNote = ref('')

async function scrollToBottom() {
  await nextTick()
  if (chatEl.value) chatEl.value.scrollTop = chatEl.value.scrollHeight
}

async function loadStatus() {
  try {
    const st = await api.getOnboardingStatus()
    if (st.onboarding_completed) {
      phase.value = 'completed'
      const attr = await api.getAttributes()
      panel.value = attr.attributes || []
      summary.value = '你已完成首次属性建档，可随时补充长期信息。'
    } else if (st.in_progress) {
      await resume()
    }
    // 否则保持 init，等待用户点「开始」
  } catch (e) {
    error.value = e.message
  }
}

async function start() {
  busy.value = true
  error.value = ''
  try {
    const data = await api.startOnboarding()
    if (data.completed) {
      // 已完成（理论上不会走到这里，兜底）
      phase.value = 'completed'
      const attr = await api.getAttributes()
      panel.value = attr.attributes || []
      summary.value = data.message || ''
      return
    }
    if (data.done && data.panel) {
      panel.value = data.panel
      summary.value = data.summary || ''
      phase.value = 'done'
    } else {
      phase.value = 'asking'
      currentQuestions.value = data.questions || []
      confidence.value = data.confidence || 0
      messages.value.push({ role: 'ai', text: data.hint || '你好，我们来聊聊你的情况吧。' })
      currentQuestions.value.forEach((q) => messages.value.push({ role: 'ai', text: q }))
    }
    await scrollToBottom()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function resume() {
  busy.value = true
  try {
    const data = await api.startOnboarding()
    if (data.completed) {
      phase.value = 'completed'
      const attr = await api.getAttributes()
      panel.value = attr.attributes || []
      summary.value = data.message || ''
      return
    }
    if (data.done && data.panel) {
      panel.value = data.panel
      summary.value = data.summary || ''
      phase.value = 'done'
      return
    }
    phase.value = 'asking'
    currentQuestions.value = data.questions || []
    confidence.value = data.confidence || 0
    messages.value.push({ role: 'ai', text: data.hint || '我们继续刚才的问答。' })
    currentQuestions.value.forEach((q) => messages.value.push({ role: 'ai', text: q }))
    await scrollToBottom()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function submit() {
  const answers = currentQuestions.value
    .map((q) => ({ question: q, answer: answerInputs.value[q] || '' }))
    .filter((a) => a.answer.trim() !== '')
  if (answers.length === 0) {
    error.value = '请先回答本轮问题。'
    return
  }
  answers.forEach((a) => messages.value.push({ role: 'user', text: a.answer }))
  answerInputs.value = {}
  currentQuestions.value = []

  busy.value = true
  error.value = ''
  try {
    const data = await api.submitAnswers(answers)
    if (data.done && data.panel) {
      // 把握度达标，自动生成面板
      panel.value = data.panel
      summary.value = data.summary || ''
      confidence.value = data.confidence || 100
      phase.value = 'done'
      messages.value.push({ role: 'ai', text: `信息够了（把握度 ${data.confidence}%），已为你生成初始属性面板。` })
      emit('created')
    } else {
      phase.value = 'asking'
      currentQuestions.value = data.questions || []
      confidence.value = data.confidence || 0
      currentQuestions.value.forEach((q) => messages.value.push({ role: 'ai', text: q }))
    }
    await scrollToBottom()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function submitSupplement() {
  if (!supplementText.value.trim()) return
  busy.value = true
  error.value = ''
  try {
    const data = await api.supplementProfile(supplementText.value.trim())
    pendingAdjustment.value = data
    supplementNote.value = data.explanation || ''
    supplementText.value = ''
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function confirmSupplement() {
  busy.value = true
  error.value = ''
  try {
    const data = await api.confirmSupplement()
    pendingAdjustment.value = null
    supplementNote.value = data.message || '调整已生效。'
    const attr = await api.getAttributes()
    panel.value = attr.attributes || []
    emit('created')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

function ignoreSupplement() {
  pendingAdjustment.value = null
  supplementNote.value = '已忽略本次调整建议。'
}

onMounted(loadStatus)
</script>

<template>
  <div class="card">
    <h2>角色档案（Onboarding）</h2>
    <p class="muted">
      首次使用时 AI 会持续提问，直到对你有足够把握（≥95%）才自动生成初始属性面板；之后只能补充长期信息。
    </p>

    <!-- 未开始 -->
    <button v-if="phase === 'init'" class="btn primary" :disabled="busy" @click="start">
      开始建立角色档案
    </button>

    <!-- 对话流 -->
    <div v-if="phase === 'asking'" class="chat" ref="chatEl">
      <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
        <div class="bubble">{{ m.text }}</div>
      </div>
    </div>

    <!-- 把握度进度 -->
    <div v-if="phase === 'asking'" style="margin: 8px 0">
      <div class="muted" style="margin-bottom: 4px">AI 对你画像的把握度：{{ confidence }}%</div>
      <div class="track"><div class="fill" :style="{ width: confidence + '%' }"></div></div>
    </div>

    <!-- 作答区 -->
    <div v-if="phase === 'asking' && currentQuestions.length" class="card" style="margin-top: 12px">
      <div v-for="q in currentQuestions" :key="q" class="field">
        <label>{{ q }}</label>
        <input v-model="answerInputs[q]" placeholder="你的回答…" @keyup.enter="submit" />
      </div>
      <button class="btn primary" :disabled="busy" @click="submit">提交</button>
    </div>

    <!-- 属性面板展示（首次生成 / 已完成） -->
    <div v-if="phase === 'done' || phase === 'completed'" class="card" style="margin-top: 12px">
      <h3>当前属性面板</h3>
      <div v-for="a in panel" :key="a.name" class="attr-bar">
        <div class="head">
          <span><b>{{ a.name }}</b></span>
          <span>{{ a.value }} / 100</span>
        </div>
        <div class="track"><div class="fill" :style="{ width: a.value + '%' }"></div></div>
        <div class="muted">{{ a.reason || a.description }}</div>
      </div>
      <p v-if="summary" class="muted">{{ summary }}</p>

      <!-- 补充长期信息入口（仅首次完成后） -->
      <div v-if="phase === 'completed'" class="card" style="margin-top: 12px">
        <h3>补充长期信息</h3>
        <p class="muted">补充你的长期特质（性格、习惯、能力自评等），AI 会结合客观记录客观评估是否需要调整属性。</p>
        <div class="field">
          <textarea v-model="supplementText" rows="2" placeholder="例如：我性格偏内向，但自控力其实比看起来强…"></textarea>
        </div>
        <button class="btn primary" :disabled="busy" @click="submitSupplement">提交补充</button>

        <!-- 调整建议 -->
        <div v-if="pendingAdjustment" class="card" style="margin-top: 12px">
          <h4>AI 评估建议</h4>
          <p class="muted">{{ supplementNote }}</p>
          <div v-for="adj in pendingAdjustment.adjustments" :key="adj.name" class="judgment-item">
            <span class="attr-name">{{ adj.name }}</span>
            <span :class="adj.delta >= 0 ? 'positive' : 'negative'">{{ adj.delta >= 0 ? '+' : '' }}{{ adj.delta }}</span>
            <div class="muted">{{ adj.reason }}</div>
            <div class="evidence">依据：{{ adj.evidence }}</div>
          </div>
          <div v-if="pendingAdjustment.adjustments.length" class="row" style="margin-top: 8px">
            <button class="btn primary" :disabled="busy" @click="confirmSupplement">确认调整</button>
            <button class="btn" :disabled="busy" @click="ignoreSupplement">忽略</button>
          </div>
          <div v-else class="row" style="margin-top: 8px">
            <button class="btn" @click="ignoreSupplement">知道了</button>
          </div>
        </div>
      </div>
    </div>

    <p v-if="error" class="muted" style="color: #d33">{{ error }}</p>
  </div>
</template>
