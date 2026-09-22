<script setup>
/**
 * 今日盘点（v1.7 B3）——一次性处理当天所有打卡项目。
 *
 * 设计要点：
 * - 展示当天 enabled 的 planned / optional 项目；负面项目**不强制罗列**（避免噪音），
 *   收进可折叠的「负面项」区供快速补记。
 * - 每行显示状态（本期已打卡次数 / 目标，如"1/3"）+ 一句话快速记录 + 提交。
 * - 未达标给**如实提示**（决策 5：只提示不扣分，扣分仍由 AI 判定）。
 * - 批量提交：逐条创建**独立事件**并各自判定（不合成一条，保证每条数据干净可追溯）。
 */
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'

const emit = defineEmits(['go-judgments'])

const items = ref([])
const stats = ref([])
const error = ref('')
const hint = ref('')
let hintTimer = null
const busy = ref(false)
const showNegative = ref(false)

// 每行的一句话输入（key = item_id）
const drafts = ref({})
const rowState = ref({}) // { item_id: {busy, ok, err} }

const NATURE_LABEL = { planned: '规划内', optional: '可选', negative: '负面', other: '其他' }

/** 统计查找表 */
const statMap = computed(() => {
  const m = {}
  for (const s of stats.value) m[s.item_id] = s
  return m
})

const plannedItems = computed(() => items.value.filter((i) => i.nature === 'planned'))
const optionalItems = computed(() => items.value.filter((i) => i.nature === 'optional'))
const negativeItems = computed(() => items.value.filter((i) => i.nature === 'negative'))
const otherItems = computed(() => items.value.filter((i) => i.nature === 'other'))

function statOf(id) {
  return statMap.value[id] || { this_period_count: 0, frequency_type: 'none', frequency_target: 0 }
}

/** 状态文案：如「本周 1/3」；不限频率则显示「本期已记 N 次」 */
function statusText(it) {
  const s = statOf(it.id)
  const done = s.this_period_count || 0
  if (it.frequency_type === 'weekly') return `本周 ${done}/${it.frequency_target || 0}`
  if (it.frequency_type === 'daily') return done > 0 ? '今天已打卡' : '今天还没打卡'
  return done > 0 ? `本期已记 ${done} 次` : '尚未记录'
}

/** 是否达标（只用于展示与提示，不用于扣分） */
function isReached(it) {
  const s = statOf(it.id)
  const done = s.this_period_count || 0
  if (it.frequency_type === 'daily') return done >= 1
  if (it.frequency_type === 'weekly') return done >= (it.frequency_target || 0)
  return false
}

/** 未达标提示（决策 5：只提示，不扣分） */
function shortfallText(it) {
  if (isReached(it)) return ''
  const s = statOf(it.id)
  const done = s.this_period_count || 0
  if (it.frequency_type === 'weekly') {
    const gap = (it.frequency_target || 0) - done
    return gap > 0 ? `本周 ${done}/${it.frequency_target} 未达标（还差 ${gap} 次）` : ''
  }
  if (it.frequency_type === 'daily') return '今天还没打卡'
  return ''
}

async function load() {
  try {
    items.value = await api.listItems({ enabled: true })
    stats.value = await api.getItemsStats()
    error.value = ''
  } catch (e) {
    error.value = e.message
  }
}

function flash(msg) {
  hint.value = msg
  clearTimeout(hintTimer)
  hintTimer = setTimeout(() => (hint.value = ''), 2500)
}

function setRow(id, patch) {
  rowState.value = { ...rowState.value, [id]: { ...(rowState.value[id] || {}), ...patch } }
}

/** 提交单个项目的一句话记录 */
async function submitOne(it) {
  const text = (drafts.value[it.id] || '').trim()
  if (!text) {
    setRow(it.id, { err: '请先写一句话' })
    return false
  }
  setRow(it.id, { busy: true, err: '', ok: false })
  try {
    const event = await api.createEvent({
      item_id: it.id,
      source: 'form',
      content: text,
      params: {},
      is_pure: false,
    })
    const res = await api.judgeEvent(event.id)
    const okMsg = res.needs_clarify
      ? '已记录，AI 有疑问（去判定中心补充）'
      : '已记录并判定'
    setRow(it.id, { busy: false, ok: true, err: '' })
    drafts.value = { ...drafts.value, [it.id]: '' }
    flash(`「${it.name}」${okMsg}`)
    return true
  } catch (e) {
    setRow(it.id, { busy: false, err: e.message, ok: false })
    return false
  }
}

/** 批量提交：所有填了一句话的项目逐个提交（各自独立事件 + 独立判定） */
async function submitAll() {
  const targets = allItems.value.filter((it) => (drafts.value[it.id] || '').trim())
  if (!targets.length) return alert('还没有填写任何记录')
  busy.value = true
  error.value = ''
  let okCount = 0
  for (const it of targets) {
    const ok = await submitOne(it)
    if (ok) okCount++
  }
  busy.value = false
  await load()
  flash(`已提交 ${okCount}/${targets.length} 条`)
}

const allItems = computed(() => [...plannedItems.value, ...optionalItems.value, ...otherItems.value, ...negativeItems.value])

/** 今日已填写条数（用于批量按钮文案） */
const filledCount = computed(() => allItems.value.filter((it) => (drafts.value[it.id] || '').trim()).length)

onMounted(load)
</script>

<template>
  <div class="card">
    <h2>今日盘点</h2>
    <p class="muted">
      一次性过一遍今天该做的事：每个项目写一句话就行，提交后各自独立判定。
      未达标只做如实提示，<b>不会自动扣分</b>。
    </p>

    <p v-if="error" class="muted" style="color: #d33">{{ error }}</p>
    <p v-if="hint" class="muted" style="color: #2a7f3e; font-size: 13px">✓ {{ hint }}</p>

    <p v-if="items.length === 0 && !error" class="muted">
      还没有启用中的打卡项目。先去「设置 → 打卡项目」建几个，再回来盘点。
    </p>

    <div class="row" v-if="allItems.length" style="margin: 10px 0">
      <button class="btn primary" :disabled="busy || !filledCount" @click="submitAll">
        {{ busy ? '提交中…' : `提交全部${filledCount ? `（${filledCount} 条）` : ''}` }}
      </button>
    </div>

    <!-- 规划内 -->
    <template v-if="plannedItems.length">
      <div class="muted" style="font-size: 12px; border-bottom: 1px solid #eee; padding-bottom: 4px; margin: 12px 0 8px">
        <b>规划内</b> · {{ plannedItems.length }} 个
      </div>
      <div v-for="it in plannedItems" :key="it.id" class="judgment-item">
        <div class="row" style="align-items: center">
          <b>{{ it.name }}</b>
          <span class="tag" :style="isReached(it) ? 'background:#eafaf1;color:#1f9e6a' : ''">{{ statusText(it) }}</span>
          <span v-if="it.category" class="muted" style="font-size: 12px">{{ it.category }}</span>
          <span v-if="isReached(it)" class="muted" style="margin-left: auto; font-size: 12px; color: #1f9e6a">✓ 已达标</span>
        </div>
        <p v-if="shortfallText(it)" class="muted" style="font-size: 12px; color: #b7791f; margin: 4px 0">⚠️ {{ shortfallText(it) }}</p>
        <div class="row" style="margin-top: 6px">
          <input v-model="drafts[it.id]" placeholder="一句话记录，如：跑了 5 公里" style="flex: 3" />
          <button class="btn small primary" style="flex: 0 0 auto" :disabled="rowState[it.id]?.busy" @click="submitOne(it)">
            {{ rowState[it.id]?.busy ? '判定中…' : '记录' }}
          </button>
        </div>
        <p v-if="rowState[it.id]?.err" class="muted" style="color: #d33; font-size: 12px">⚠️ {{ rowState[it.id].err }}</p>
      </div>
    </template>

    <!-- 可选 -->
    <template v-if="optionalItems.length">
      <div class="muted" style="font-size: 12px; border-bottom: 1px solid #eee; padding-bottom: 4px; margin: 12px 0 8px">
        <b>可选</b> · {{ optionalItems.length }} 个
      </div>
      <div v-for="it in optionalItems" :key="it.id" class="judgment-item">
        <div class="row" style="align-items: center">
          <b>{{ it.name }}</b>
          <span class="tag">{{ statusText(it) }}</span>
          <span v-if="it.category" class="muted" style="font-size: 12px">{{ it.category }}</span>
        </div>
        <div class="row" style="margin-top: 6px">
          <input v-model="drafts[it.id]" placeholder="一句话记录" style="flex: 3" />
          <button class="btn small primary" style="flex: 0 0 auto" :disabled="rowState[it.id]?.busy" @click="submitOne(it)">
            {{ rowState[it.id]?.busy ? '判定中…' : '记录' }}
          </button>
        </div>
        <p v-if="rowState[it.id]?.err" class="muted" style="color: #d33; font-size: 12px">⚠️ {{ rowState[it.id].err }}</p>
      </div>
    </template>

    <!-- 其他 -->
    <template v-if="otherItems.length">
      <div class="muted" style="font-size: 12px; border-bottom: 1px solid #eee; padding-bottom: 4px; margin: 12px 0 8px">
        <b>其他</b> · {{ otherItems.length }} 个
      </div>
      <div v-for="it in otherItems" :key="it.id" class="judgment-item">
        <div class="row" style="align-items: center">
          <b>{{ it.name }}</b>
          <span class="tag">{{ statusText(it) }}</span>
        </div>
        <div class="row" style="margin-top: 6px">
          <input v-model="drafts[it.id]" placeholder="一句话记录" style="flex: 3" />
          <button class="btn small primary" style="flex: 0 0 auto" :disabled="rowState[it.id]?.busy" @click="submitOne(it)">
            {{ rowState[it.id]?.busy ? '判定中…' : '记录' }}
          </button>
        </div>
        <p v-if="rowState[it.id]?.err" class="muted" style="color: #d33; font-size: 12px">⚠️ {{ rowState[it.id].err }}</p>
      </div>
    </template>

    <!-- 负面项：不强制罗列，折叠供快速补记 -->
    <template v-if="negativeItems.length">
      <div
        class="judgment-item"
        style="cursor: pointer; display: flex; align-items: center; margin-top: 12px"
        @click="showNegative = !showNegative"
      >
        <b>负面项 {{ negativeItems.length }} 个</b>
        <span class="muted" style="font-size: 12px; margin-left: 8px">如实记一次扣一次分（不会去重）</span>
        <span class="muted" style="margin-left: auto">{{ showNegative ? '▾' : '▸' }}</span>
      </div>
      <template v-if="showNegative">
        <div v-for="it in negativeItems" :key="it.id" class="judgment-item" style="margin-left: 12px">
          <div class="row" style="align-items: center">
            <b>{{ it.name }}</b>
            <span class="tag">{{ statusText(it) }}</span>
          </div>
          <div class="row" style="margin-top: 6px">
            <input v-model="drafts[it.id]" placeholder="如实记一笔，如：久坐 3 小时" style="flex: 3" />
            <button class="btn small danger" style="flex: 0 0 auto" :disabled="rowState[it.id]?.busy" @click="submitOne(it)">
              {{ rowState[it.id]?.busy ? '判定中…' : '记录' }}
            </button>
          </div>
          <p v-if="rowState[it.id]?.err" class="muted" style="color: #d33; font-size: 12px">⚠️ {{ rowState[it.id].err }}</p>
        </div>
      </template>
    </template>

    <div class="row" style="margin-top: 12px" v-if="items.length">
      <button class="btn small" @click="emit('go-judgments')">去判定中心确认入账 →</button>
      <button class="btn small" @click="load">刷新</button>
    </div>
  </div>
</template>
