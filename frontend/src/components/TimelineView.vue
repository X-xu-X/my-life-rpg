<script setup>
import { ref, onMounted, computed } from 'vue'
import { api } from '../api'

const events = ref([])
const judgments = ref([])
const error = ref('')
const searchText = ref('')

const STATUS_LABEL = { pending: '待确认', adjusted: '已调整', confirmed: '已入账', rejected: '已驳回' }

async function load() {
  try {
    events.value = await api.listEvents(false)
    judgments.value = await api.listJudgments()
  } catch (e) {
    error.value = e.message
  }
}

function judgmentFor(eventId) {
  return judgments.value.find((j) => j.event_id === eventId)
}

const filteredEvents = computed(() => {
  const kw = searchText.value.trim().toLowerCase()
  if (!kw) return events.value
  return events.value.filter((e) =>
    (e.title || '').toLowerCase().includes(kw) ||
    (e.content || '').toLowerCase().includes(kw) ||
    (e.category || '').toLowerCase().includes(kw)
  )
})

async function remove(id) {
  if (!window.confirm('删除这条记录及其判定？')) return
  try {
    await api.deleteEvent(id)
    await load()
  } catch (e) {
    error.value = e.message
  }
}

onMounted(load)
</script>

<template>
  <div class="card">
    <h2>手账本</h2>
    <p class="muted">你的生活时间线——日记、事件和 AI 判定都在这里，按时间回顾你的每一天。</p>

    <p v-if="error" class="muted" style="color: #d33">{{ error }}</p>
    <p v-if="events.length === 0 && !error" class="muted">还没有记录，去「记录事件」写第一条吧。</p>

    <div class="field" v-if="events.length > 0">
      <input v-model="searchText" placeholder="🔍 搜索记录…" />
    </div>

    <div v-for="e in filteredEvents" :key="e.id" class="judgment-item">
      <div class="row" style="align-items: center; margin-bottom: 6px">
        <b>{{ e.title || '未命名记录' }}</b>
        <span class="tag">{{ e.category }}</span>
        <span class="muted" style="font-size: 12px">{{ new Date(e.created_at).toLocaleString('zh-CN') }}</span>
      </div>

      <!-- 内容 -->
      <div v-if="e.content" style="white-space: pre-wrap; margin-bottom: 6px">{{ e.content }}</div>
      <div v-else-if="e.params && Object.keys(e.params).length" class="muted" style="margin-bottom: 6px">
        {{ Object.entries(e.params).map(([k, v]) => `${k}：${v}`).join('，') }}
      </div>

      <!-- 判定结果 -->
      <div v-if="judgmentFor(e.id)" class="judgment-item" style="margin-bottom: 6px">
        <span class="tag">{{ STATUS_LABEL[judgmentFor(e.id).status] || judgmentFor(e.id).status }}</span>
        <span class="muted" style="font-size: 12px">
          置信度 {{ ((judgmentFor(e.id).confidence || 1) * 100).toFixed(0) }}%
        </span>
        <div v-for="a in judgmentFor(e.id).suggested_changes" :key="a.name" style="margin-top: 4px">
          <span class="attr-name">{{ a.name }}</span>
          <span :class="a.delta >= 0 ? 'positive' : 'negative'">{{ a.delta >= 0 ? '+' : '' }}{{ a.delta }}</span>
          <span class="muted" style="font-size: 12px">{{ a.reason }}</span>
        </div>
      </div>
      <div v-else class="muted" style="font-size: 12px; margin-bottom: 6px">尚未判定</div>

      <button class="btn small danger" @click="remove(e.id)">删除</button>
    </div>
  </div>
</template>
