<script setup>
import { ref, onMounted, computed } from 'vue'
import { api } from '../api'
import { useDateGroups } from '../composables/useDateGroups'

const events = ref([])
const judgments = ref([])
const error = ref('')
const searchText = ref('')

const STATUS_LABEL = { pending: '待确认', adjusted: '已调整', confirmed: '已入账', rejected: '已驳回', invalidated: '已作废' }

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

// ============ v1.6 B2：与判定中心一致的四组日期折叠（公共逻辑 useDateGroups） ============
const { groups: groupedEvents, expanded: groupExpanded, toggleGroup } = useDateGroups(filteredEvents, {
  storageKey: 'gol_timeline_group_expand',
})

const expandedItems = ref(new Set()) // 展开详情的记录（内存态，刷新复位）

function groupIsOpen(key) {
  if (searchText.value.trim()) return true // 搜索命中自动展开所在组
  return !!groupExpanded.value[key]
}
function toggleItem(id) {
  const s = new Set(expandedItems.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  expandedItems.value = s
}
function itemIsOpen(id) {
  if (searchText.value.trim()) return true // 搜索命中直接展开详情
  return expandedItems.value.has(id)
}

/** 加点概览（摘要行）：体能 +1 · 智力 +0.5；无判定/无加点显示"无加点" */
function changeSummary(eventId) {
  const j = judgmentFor(eventId)
  if (!j || !j.suggested_changes || !j.suggested_changes.length) return '无加点'
  return j.suggested_changes.map((c) => `${c.name} ${c.delta >= 0 ? '+' : ''}${c.delta}`).join(' · ')
}

function fmtTime(t) {
  return new Date(t).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

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

    <p v-if="events.length > 0" class="muted" style="font-size: 12px">点击记录行展开详情；组头可折叠（搜索时自动展开命中项）。</p>

    <div v-for="g in groupedEvents" :key="g.key" style="margin-bottom: 12px">
      <div
        class="row"
        style="align-items: center; cursor: pointer; padding: 6px 4px; border-bottom: 1px solid #eee; user-select: none"
        @click="toggleGroup(g.key)"
      >
        <b>{{ g.label }}</b>
        <span class="muted" style="font-size: 12px">{{ g.dateRange }}</span>
        <span class="muted" style="font-size: 12px">{{ g.items.length }} 条</span>
        <span class="muted" style="margin-left: auto">{{ groupIsOpen(g.key) ? '▾' : '▸' }}</span>
      </div>

      <template v-if="groupIsOpen(g.key)">
        <div v-for="e in g.items" :key="e.id" class="judgment-item">
          <!-- 摘要行（v1.6 B2：默认收起） -->
          <div class="row" style="align-items: center; cursor: pointer" @click="toggleItem(e.id)">
            <span class="muted" style="font-size: 12px">{{ fmtTime(e.created_at) }}</span>
            <b>{{ e.title || '未命名记录' }}</b>
            <span class="tag">{{ e.category }}</span>
            <span class="muted" style="font-size: 12px">{{ changeSummary(e.id) }}</span>
            <span class="muted" style="margin-left: auto">{{ itemIsOpen(e.id) ? '▾' : '▸' }}</span>
          </div>

          <template v-if="itemIsOpen(e.id)">
            <!-- 内容原文 -->
            <div v-if="e.content" style="white-space: pre-wrap; margin: 6px 0">{{ e.content }}</div>
            <div v-else-if="e.params && Object.keys(e.params).length" class="muted" style="margin: 6px 0">
              {{ Object.entries(e.params).map(([k, v]) => `${k}：${v}`).join('，') }}
            </div>

            <!-- 判定明细 -->
            <div v-if="judgmentFor(e.id)" class="judgment-item" style="margin-bottom: 6px">
              <span class="tag">{{ STATUS_LABEL[judgmentFor(e.id).status] || judgmentFor(e.id).status }}</span>
              <span class="muted" style="font-size: 12px">
                置信度 {{ ((judgmentFor(e.id).confidence || 1) * 100).toFixed(0) }}%
              </span>
              <div v-for="a in judgmentFor(e.id).suggested_changes" :key="a.name" style="margin-top: 4px">
                <span class="attr-name">{{ a.name }}</span>
                <span :class="a.delta >= 0 ? 'positive' : 'negative'">{{ a.delta >= 0 ? '+' : '' }}{{ a.delta }}</span>
                <span class="muted" style="font-size: 12px">{{ a.reason }}</span>
                <div class="evidence">依据：{{ a.evidence }}</div>
              </div>
              <!-- AI 分析过程 -->
              <div v-if="judgmentFor(e.id).analysis && judgmentFor(e.id).analysis.length" class="analysis-box">
                <div class="analysis-title">🤖 AI 分析过程</div>
                <div v-for="(step, idx) in judgmentFor(e.id).analysis" :key="idx" class="step">{{ step }}</div>
              </div>
            </div>
            <div v-else class="muted" style="font-size: 12px; margin-bottom: 6px">尚未判定</div>

            <button class="btn small danger" @click="remove(e.id)">删除</button>
          </template>
        </div>
      </template>
    </div>
  </div>
</template>
