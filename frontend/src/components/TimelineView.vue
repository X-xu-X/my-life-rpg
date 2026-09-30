<script setup>
import { ref, onMounted, computed } from 'vue'
import { api } from '../api'
import { toast } from '../composables/useToast'
import { useDateGroups } from '../composables/useDateGroups'

const events = ref([])
const judgments = ref([])
const error = ref('')
const searchText = ref('')
// v1.9 F4-3：三态类型筛选（事件 = source='form'，含挑战来源；日记 = source='journal'）
const typeFilter = ref('all')

const TYPE_FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'form', label: '只看事件' },
  { key: 'journal', label: '只看日记' },
]

const STATUS_LABEL = { pending: '待确认', adjusted: '已调整', confirmed: '已入账', rejected: '已驳回', invalidated: '已作废' }

async function load() {
  try {
    events.value = await api.listEvents(false)
    judgments.value = await api.listJudgments()
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  }
}

function judgmentFor(eventId) {
  return judgments.value.find((j) => j.event_id === eventId)
}

// ============================================================
// v1.9 F4 建立搜索 / v1.10 N3 收敛范围
// 覆盖范围 = **只搜用户自己写的内容**（标题 / 正文 / 类别 / 参数值）。
// 全部在本地做（复用已加载的 events），不新增后端接口。
// ============================================================

/** 参数摘要（跳过 "_" 前缀的内部键，与后端 format_event_description 一致） */
function paramsSummary(e) {
  const p = e.params || {}
  return Object.entries(p)
    .filter(([k]) => !String(k).startsWith('_'))
    .map(([k, v]) => `${k}：${v}`)
    .join('，')
}

/** 文本化一条可能为字符串 / 对象 / 数组的字段 */
function asText(v) {
  if (v === null || v === undefined) return ''
  if (typeof v === 'string') return v
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  if (Array.isArray(v)) return v.map(asText).filter(Boolean).join('；')
  if (typeof v === 'object') {
    return Object.entries(v)
      .map(([k, x]) => `${k}：${asText(x)}`)
      .join('；')
  }
  return ''
}

/**
 * 构造一条记录的「可搜索字段」列表，每项带来源标签。
 * 顺序即命中优先级——用户最可能想看到"命中在哪"的地方排在前面。
 */
function searchFields(e) {
  const out = []
  const push = (label, text) => {
    const t = asText(text).trim()
    if (t) out.push({ label, text: t })
  }
  // v1.10（N3-1）：**只搜用户自己写的内容**——v1.9 F4 加进来的 8 类 AI 内容
  // （AI 总结 / 分析 / 加点理由 / 加点依据 / 入账理由 / 重判说明 / 置信度说明 / 合并说明）
  // 已全部移除。命中片段的来源标签从此只可能是这四类。
  push('标题', e.title)
  push('正文', e.content)
  push('类别', e.category)
  push('参数', paramsSummary(e))
  return out
}

const searchKw = computed(() => searchText.value.trim().toLowerCase())

/** 首个命中的字段 → 命中片段（关键词前后各约 20 字） */
function matchOf(e, kw) {
  for (const f of searchFields(e)) {
    const idx = f.text.toLowerCase().indexOf(kw)
    if (idx < 0) continue
    const start = Math.max(0, idx - 20)
    const end = Math.min(f.text.length, idx + kw.length + 20)
    return {
      label: f.label,
      before: (start > 0 ? '…' : '') + f.text.slice(start, idx),
      hit: f.text.slice(idx, idx + kw.length),
      after: f.text.slice(idx + kw.length, end) + (end < f.text.length ? '…' : ''),
    }
  }
  return null
}

/** 类型筛选 + 关键词搜索（两者与日期分组折叠同时生效） */
const filteredEvents = computed(() => {
  const kw = searchKw.value
  return events.value.filter((e) => {
    if (typeFilter.value === 'form' && e.source !== 'form') return false
    if (typeFilter.value === 'journal' && e.source !== 'journal') return false
    if (!kw) return true
    return searchFields(e).some((f) => f.text.toLowerCase().includes(kw))
  })
})

/** 命中片段表：仅在有关键词时构建（搜索词为空不显示片段，避免常态噪音） */
const snippets = computed(() => {
  const m = new Map()
  const kw = searchKw.value
  if (!kw) return m
  for (const e of filteredEvents.value) {
    const hit = matchOf(e, kw)
    if (hit) m.set(e.id, hit)
  }
  return m
})

// ============ v1.6 B2：与判定中心一致的四组日期折叠（公共逻辑 useDateGroups） ============
const { groups: groupedEvents, expanded: groupExpanded, toggleGroup } = useDateGroups(filteredEvents, {
  storageKey: 'gol_timeline_group_expand',
})

const expandedItems = ref(new Set()) // 展开详情的记录（内存态，刷新复位）

function groupIsOpen(key) {
  if (searchKw.value) return true // 搜索命中自动展开所在组
  return !!groupExpanded.value[key]
}
function toggleItem(id) {
  const s = new Set(expandedItems.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  expandedItems.value = s
}
function itemIsOpen(id) {
  if (searchKw.value) return true // 搜索命中直接展开详情
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
    toast.error(e.message)
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

    <template v-if="events.length > 0">
      <div class="field">
        <input v-model="searchText" placeholder="🔍 搜索你写过的标题、正文、类别与参数…" />
      </div>

      <!-- v1.9 F4-3：三态类型筛选 -->
      <div class="segmented" role="group" aria-label="记录类型筛选">
        <button
          v-for="f in TYPE_FILTERS"
          :key="f.key"
          class="seg-btn"
          :class="{ active: typeFilter === f.key }"
          @click="typeFilter = f.key"
        >
          {{ f.label }}
        </button>
        <span class="muted seg-count">{{ filteredEvents.length }} / {{ events.length }} 条</span>
      </div>

      <p class="muted" style="font-size: 12px">
        点击记录行展开详情；组头可折叠（搜索时自动展开命中项）。搜索范围为你自己写的内容（标题 / 正文 / 类别 / 参数），不含 AI 判定文字。
      </p>

      <p v-if="searchKw && filteredEvents.length === 0" class="muted" style="margin-top: 8px">
        没有找到包含「{{ searchText.trim() }}」的记录。
      </p>
      <p v-else-if="!searchKw && filteredEvents.length === 0" class="muted" style="margin-top: 8px">
        该筛选下暂无记录。
      </p>
    </template>

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
            <span v-if="e.origin === 'challenge'" class="tag" title="由挑战结算生成">挑战</span>
            <span class="tag">{{ e.category }}</span>
            <span class="muted" style="font-size: 12px">{{ changeSummary(e.id) }}</span>
            <span class="muted" style="margin-left: auto">{{ itemIsOpen(e.id) ? '▾' : '▸' }}</span>
          </div>

          <!-- v1.9 F4-4：命中片段（仅搜索时出现；关键词高亮 + 标注命中来源） -->
          <div v-if="snippets.get(e.id)" class="hit-snippet">
            <span class="hit-src">{{ snippets.get(e.id).label }}</span>
            <span>{{ snippets.get(e.id).before }}</span><mark>{{ snippets.get(e.id).hit }}</mark><span>{{ snippets.get(e.id).after }}</span>
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
