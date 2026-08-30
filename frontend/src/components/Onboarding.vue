<script setup>
import { ref, nextTick } from 'vue'
import { api } from '../api'

const emit = defineEmits(['created'])

const sessionId = ref('')
const messages = ref([]) // {role:'ai'|'user', text}
const currentQuestions = ref([])
const answerInputs = ref({})
const panel = ref(null)
const busy = ref(false)
const error = ref('')
const chatEl = ref(null)

async function scrollToBottom() {
  await nextTick()
  if (chatEl.value) chatEl.value.scrollTop = chatEl.value.scrollHeight
}

async function start() {
  busy.value = true
  error.value = ''
  try {
    const data = await api.startOnboarding()
    sessionId.value = data.session_id
    currentQuestions.value = data.questions || []
    messages.value.push({ role: 'ai', text: data.hint || '你好，我们来聊聊你的情况吧。' })
    currentQuestions.value.forEach((q) => {
      messages.value.push({ role: 'ai', text: q })
    })
    await scrollToBottom()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function submit(finish) {
  if (!sessionId.value) return
  // 收集本轮回答
  const answers = currentQuestions.value
    .map((q) => ({ question: q, answer: answerInputs.value[q] || '' }))
    .filter((a) => a.answer.trim() !== '')
  if (answers.length === 0 && !finish) {
    error.value = '请先回答本轮问题。'
    return
  }
  // 展示用户回答
  answers.forEach((a) => messages.value.push({ role: 'user', text: a.answer }))
  answerInputs.value = {}
  currentQuestions.value = []

  busy.value = true
  error.value = ''
  try {
    const data = await api.submitAnswers(sessionId.value, answers, finish)
    if (data.finish && data.panel) {
      panel.value = data.panel
      messages.value.push({ role: 'ai', text: data.summary || '初始属性面板已生成。' })
      await scrollToBottom()
    } else if (data.questions) {
      currentQuestions.value = data.questions || []
      currentQuestions.value.forEach((q) => messages.value.push({ role: 'ai', text: q }))
      await scrollToBottom()
    }
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function confirmPanel() {
  // 确认存档已由后端完成，仅通知父组件刷新
  emit('created')
}

const disputeText = ref('')
async function disputePanel() {
  if (!disputeText.value.trim()) return
  busy.value = true
  error.value = ''
  try {
    const data = await api.disputePanel(sessionId.value, disputeText.value)
    panel.value = data.panel
    messages.value.push({ role: 'ai', text: '已复核：' + (data.explanation || '面板已更新') })
    disputeText.value = ''
    await scrollToBottom()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="card">
    <h2>角色档案（Onboarding）</h2>
    <p class="muted">AI 会问你一些关于体能、学习、作息、兴趣的问题，随后生成初始属性面板。</p>

    <button v-if="!sessionId" class="btn primary" :disabled="busy" @click="start">
      开始问卷
    </button>

    <div v-if="sessionId" class="chat" ref="chatEl">
      <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
        <div class="bubble">{{ m.text }}</div>
      </div>
    </div>

    <!-- 作答区 -->
    <div v-if="currentQuestions.length && !panel" class="card" style="margin-top: 12px">
      <div v-for="q in currentQuestions" :key="q" class="field">
        <label>{{ q }}</label>
        <input v-model="answerInputs[q]" placeholder="你的回答…" @keyup.enter="submit(false)" />
      </div>
      <div class="row" style="margin-top: 8px">
        <button class="btn primary" :disabled="busy" @click="submit(false)">提交并继续</button>
        <button class="btn" :disabled="busy" @click="submit(true)">信息够了，生成面板</button>
      </div>
    </div>

    <!-- 面板确认/异议 -->
    <div v-if="panel" class="card" style="margin-top: 12px">
      <h3>初始属性面板</h3>
      <div v-for="a in panel" :key="a.name" class="attr-bar">
        <div class="head">
          <span><b>{{ a.name }}</b>：{{ a.value }}/100</span>
        </div>
        <div class="track"><div class="fill" :style="{ width: a.value + '%' }"></div></div>
        <div class="muted">{{ a.reason }}</div>
      </div>

      <div class="field" style="margin-top: 12px">
        <label>对某属性有异议？说明理由，AI 会客观复核：</label>
        <input v-model="disputeText" placeholder="例如：我体能应该更高，因为我…" />
      </div>
      <div class="row">
        <button class="btn primary" :disabled="busy" @click="confirmPanel">确认存档</button>
        <button class="btn" :disabled="busy" @click="disputePanel">提交异议复核</button>
      </div>
    </div>

    <p v-if="error" class="muted" style="color: #d33">{{ error }}</p>
  </div>
</template>
