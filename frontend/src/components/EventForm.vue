<script setup>
import { ref } from 'vue'
import { api } from '../api'

const emit = defineEmits(['judged'])

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

const categories = ['锻炼', '学习', '作息', '社交', '饮食', '理财', '其他']
const intensities = ['低', '中低', '中等', '中高', '高']

const busy = ref(false)
const error = ref('')
const result = ref(null)

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
  })
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
  })
  result.value = await api.judgeEvent(event.id)
  emit('judged')
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

    <div class="row">
      <button class="btn primary" :disabled="busy" @click="submit">{{ busy ? 'AI 处理中…' : '提交并判定' }}</button>
      <button class="btn" @click="reset">清空</button>
    </div>

    <p v-if="error" class="muted" style="color: #d33">{{ error }}</p>

    <!-- 判定结果预览 -->
    <div v-if="result" class="judgment-item" style="margin-top: 16px">
      <h3>AI 判定结果 <span class="tag">{{ result.status }}</span></h3>
      <p class="muted">置信度 {{ (result.confidence * 100).toFixed(0) }}%</p>
      <!-- AI 分析过程 -->
      <div v-if="result.analysis && result.analysis.length" class="analysis-box">
        <div class="analysis-title">🤖 AI 分析过程</div>
        <div v-for="(step, idx) in result.analysis" :key="idx" class="step">{{ step }}</div>
      </div>
      <div v-for="a in result.suggested_changes" :key="a.name" class="judgment-item">
        <span class="attr-name">{{ a.name }}</span>
        <span :class="a.delta >= 0 ? 'positive' : 'negative'">{{ a.delta >= 0 ? '+' : '' }}{{ a.delta }}</span>
        <div class="muted">{{ a.reason }}</div>
        <div class="evidence">依据：{{ a.evidence }}</div>
      </div>
      <p v-if="result.summary" class="muted">{{ result.summary }}</p>
      <p class="muted">请在「判定中心」确认入账 / 补充信息 / 反驳复核；录错了可删除该事件。</p>
    </div>
  </div>
</template>
