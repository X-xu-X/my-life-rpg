<script setup>
import { ref } from 'vue'
import { api } from '../api'

const emit = defineEmits(['judged'])

const form = ref({
  event_type: 'positive',
  category: '锻炼',
  title: '',
  duration: '',
  distance: '',
  intensity: '',
  note: '',
})

const categories = ['锻炼', '学习', '作息', '社交', '饮食', '理财', '其他']
const intensities = ['低', '中低', '中等', '中高', '高']

const busy = ref(false)
const error = ref('')
const result = ref(null)

async function submit() {
  busy.value = true
  error.value = ''
  result.value = null
  try {
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

    // 录入后立即触发 AI 判定
    result.value = await api.judgeEvent(event.id)
    emit('judged')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

function reset() {
  form.value = { event_type: 'positive', category: '锻炼', title: '', duration: '', distance: '', intensity: '', note: '' }
  result.value = null
}
</script>

<template>
  <div class="card">
    <h2>记录事件（结构化打卡）</h2>

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

    <div class="row">
      <button class="btn primary" :disabled="busy" @click="submit">{{ busy ? 'AI 判定中…' : '提交并判定' }}</button>
      <button class="btn" @click="reset">清空</button>
    </div>

    <p v-if="error" class="muted" style="color: #d33">{{ error }}</p>

    <!-- 判定结果预览 -->
    <div v-if="result" class="judgment-item" style="margin-top: 16px">
      <h3>AI 判定结果 <span class="tag">{{ result.status }}</span></h3>
      <p class="muted">置信度 {{ (result.confidence * 100).toFixed(0) }}%</p>
      <div v-for="a in result.suggested_changes" :key="a.name" class="judgment-item">
        <span class="attr-name">{{ a.name }}</span>
        <span :class="a.delta >= 0 ? 'positive' : 'negative'">{{ a.delta >= 0 ? '+' : '' }}{{ a.delta }}</span>
        <div class="muted">{{ a.reason }}</div>
        <div class="evidence">依据：{{ a.evidence }}</div>
      </div>
      <p v-if="result.summary" class="muted">{{ result.summary }}</p>
      <p class="muted">请在「判定中心」确认入账 / 补充信息 / 反驳复核。</p>
    </div>
  </div>
</template>
