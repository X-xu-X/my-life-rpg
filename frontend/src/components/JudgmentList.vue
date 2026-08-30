<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'

const judgments = ref([])
const busy = ref(false)
const error = ref('')
const actionTarget = ref(null) // 正在操作的判定 id
const inputText = ref('')

async function load() {
  try {
    judgments.value = await api.listJudgments()
  } catch (e) {
    error.value = e.message
  }
}

const STATUS_LABEL = {
  pending: '待确认',
  adjusted: '已调整',
  confirmed: '已入账',
  rejected: '已驳回',
}

async function confirm(id) {
  await runAction(id, () => api.confirmJudgment(id), '确认入账成功')
}

async function supplement(id) {
  if (!inputText.value.trim()) return alert('请填写补充信息')
  await runAction(id, () => api.supplementJudgment(id, inputText.value.trim()), '已重新判定')
}

async function dispute(id) {
  if (!inputText.value.trim()) return alert('请填写反驳理由')
  const res = await runAction(id, () => api.disputeJudgment(id, inputText.value.trim()))
  if (res) {
    alert(res.conclusion === 'adjust' ? '复核已调整判定' : 'AI 坚持原判定：' + res.explanation)
  }
}

async function runAction(id, fn, okMsg) {
  busy.value = true
  error.value = ''
  try {
    const res = await fn()
    await load()
    return res
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
    actionTarget.value = null
    inputText.value = ''
  }
}

function openAction(id, mode) {
  actionTarget.value = id
  inputText.value = ''
}

onMounted(load)
</script>

<template>
  <div class="card">
    <h2>判定中心</h2>
    <p class="muted">AI 对每条事件给出建议增减，你可以确认入账、补充信息重判、或反驳复核。</p>

    <p v-if="error" class="muted" style="color: #d33">{{ error }}</p>
    <p v-if="judgments.length === 0 && !error" class="muted">暂无判定记录，先去「记录事件」打卡吧。</p>

    <div v-for="j in judgments" :key="j.id" class="judgment-item">
      <div class="row" style="align-items: center; margin-bottom: 8px">
        <b>{{ j.event_title || j.category }}</b>
        <span class="tag">{{ j.event_type }}</span>
        <span class="tag">{{ STATUS_LABEL[j.status] || j.status }}</span>
        <span class="muted">置信度 {{ (j.confidence * 100).toFixed(0) }}%</span>
      </div>

      <div v-if="j.summary" class="muted" style="margin-bottom: 6px">{{ j.summary }}</div>

      <div v-for="a in j.suggested_changes" :key="a.name" class="judgment-item">
        <span class="attr-name">{{ a.name }}</span>
        <span :class="a.delta >= 0 ? 'positive' : 'negative'">{{ a.delta >= 0 ? '+' : '' }}{{ a.delta }}</span>
        <div class="muted">{{ a.reason }}</div>
        <div class="evidence">依据：{{ a.evidence }}</div>
      </div>

      <!-- 三选一操作 -->
      <div v-if="j.status !== 'confirmed'" class="row" style="margin-top: 10px">
        <button class="btn small primary" :disabled="busy" @click="confirm(j.id)">确认入账</button>
        <button class="btn small" :disabled="busy" @click="openAction(j.id, 'supplement')">补充信息</button>
        <button class="btn small danger" :disabled="busy" @click="openAction(j.id, 'dispute')">反驳</button>
      </div>
      <div v-else class="muted" style="margin-top: 6px">✓ 已入账</div>

      <!-- 补充/反驳输入框 -->
      <div v-if="actionTarget === j.id" class="field" style="margin-top: 10px">
        <label>补充信息 / 反驳理由：</label>
        <textarea v-model="inputText" rows="2" placeholder="说明你的补充或反驳理由…"></textarea>
        <div class="row" style="margin-top: 8px">
          <button class="btn small primary" :disabled="busy" @click="supplement(j.id)">提交补充</button>
          <button class="btn small danger" :disabled="busy" @click="dispute(j.id)">提交反驳</button>
        </div>
      </div>
    </div>
  </div>
</template>
