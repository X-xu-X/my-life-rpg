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
import { ref, computed, watch, onMounted } from 'vue'
import { api } from '../api'
import { storageKey,localDate,account } from '../session'
import { toast } from '../composables/useToast'
import RecordComposer from './RecordComposer.vue'
import GoalsView from './GoalsView.vue'
import ItemManager from './ItemManager.vue'

const emit = defineEmits(['go-judgments'])

const items = ref([])
const stats = ref([])
const goals = ref([]) // v1.10 P2-1：【规划内】展示目标任务 + 关联打卡项目子进度
const showPlanning = ref(false) // v1.10 P2-1：【规划设置】折叠面板（目标 CRUD + 打卡项目管理）
const error = ref('')
const hint = ref('')
let hintTimer = null
const busy = ref(false)
const permission = ref('private')
const showNegative = ref(false)

// 每行的一句话输入（key = item_id）
const drafts = ref({})
const rowState = ref({}) // { item_id: {busy, ok, err} }
const draftKey=storageKey('checkin-drafts')
try {
  const saved=JSON.parse(localStorage.getItem(draftKey)||'null')
  if(saved?.drafts && saved?.rows){drafts.value=saved.drafts;rowState.value=Object.fromEntries(Object.entries(saved.rows).map(([key,value])=>[key,{...value,busy:false}]))}
} catch {}
watch([drafts,rowState],()=>{try{localStorage.setItem(draftKey,JSON.stringify({drafts:drafts.value,rows:rowState.value}))}catch{}},{deep:true})

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
    // v1.10 P2-1：目标进度（只展示，不自动达成——v1.7 决策 7 不变）
    goals.value = await api.listGoals().catch(() => [])
    error.value = ''
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  }
}

// v1.10 P2-1：【规划内】目标子进度（文案与 GoalsView 一致）
const activeGoals = computed(() => (Array.isArray(goals.value) ? goals.value : []).filter((g) => g.status === 'active'))

function periodLabel(frequencyType) {
  if (frequencyType === 'daily') return '今日'
  if (frequencyType === 'weekly') return '本周'
  return ''
}

function progressText(p) {
  const prefix = periodLabel(p.frequency_type)
  if (!p.target) return `${prefix}已完成 ${p.this_period_count} 次`.trim()
  return `${prefix} ${p.this_period_count}/${p.target}`.trim()
}

function progressPercent(p) {
  if (!p.target) return 0
  return Math.min(100, Math.round((p.this_period_count / p.target) * 100))
}

function flash(msg) {
  // v1.9 F2：保留页内提示（近场），同时接入全局 toast（统一规范）
  hint.value = msg
  clearTimeout(hintTimer)
  hintTimer = setTimeout(() => (hint.value = ''), 2500)
  toast.success(msg)
}

function setRow(id, patch) {
  rowState.value = { ...rowState.value, [id]: { ...(rowState.value[id] || {}), ...patch } }
}

/** 提交单个项目的一句话记录 */
async function submitOne(it) {
  const previous = rowState.value[it.id] || {}
  if (previous.busy) return false
  const text = previous.body?.content || (drafts.value[it.id] || '').trim()
  if (!text) {
    setRow(it.id, { err: '请先写一句话' })
    return false
  }
  setRow(it.id, { busy: true, err: '', ok: false })
  try {
    let eventId = previous.eventId || null
    if (!eventId) {
      const requestKey=previous.requestKey || crypto.randomUUID()
      const body=previous.body || {client_request_id:requestKey,item_id:it.id,source:'form',content:text,params:{},is_pure:false,record_kind:'event',occurred_on:localDate(),time_precision:'date',timezone:account.value?.timezone||'Asia/Shanghai',intent:permission.value==='allowed'?'now':'never',ai_permission:permission.value}
      setRow(it.id,{requestKey,savedText:text,body})
      let event
      if(previous.requestKey){
        try{event=await api.submission(requestKey)}catch(e){if(e.status!==404)throw e}
      }
      if(!event) event = await api.createEvent(body)
      eventId = event.id
      setRow(it.id, { eventId, savedText: text })
    }
    const saved=await api.getEvent(eventId)
    if(saved.ai_permission==='allowed'){
      const jobKey=previous.jobKey||crypto.randomUUID();setRow(it.id,{jobKey})
      await api.submitJob(eventId,{request_key:jobKey,event_version:saved.content_version,operation:'facts'})
    }
    const okMsg=saved.ai_permission==='allowed'?'原文已保存，逐事实分析已排队':'原文已保存，仅保存不分析'
    setRow(it.id, { busy: false, ok: true, err: '', eventId: null, savedText: null, requestKey:null,body:null,jobKey:null })
    if((drafts.value[it.id]||'').trim()===text)drafts.value = { ...drafts.value, [it.id]: '' }
    await load()
    flash(`「${it.name}」${okMsg}`)
    return true
  } catch (e) {
    setRow(it.id, { busy: false, err: `${e.message}；再次提交将恢复原请求，已保存的原文不会重复创建`, ok: false })
    toast.error(`「${it.name}」${e.message}`)
    return false
  }
}

/** 批量提交：所有填了一句话的项目逐个提交（各自独立事件 + 独立判定） */
async function submitAll() {
  const targets = allItems.value.filter((it) => (drafts.value[it.id] || '').trim())
  if (!targets.length) return toast.error('还没有填写任何记录')
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
    <h1>项目与目标</h1>
    <p class="muted">
      过一遍今天该做的事，原文先保存；主动选择分析后，再核对逐事实建议。
      未达标只做如实提示，<b>不会自动扣分</b>。
    </p>
    <label>本批记录的保存方式<select v-model="permission"><option value="private">仅保存，不分析</option><option value="allowed">保存并允许分析</option></select></label>

    <!-- v1.10 P2-1：【规划内】目标任务 + 关联打卡项目子进度（只展示，不自动达成） -->
    <template v-if="activeGoals.length">
      <div class="muted" style="font-size: 13px; border-bottom: 1px solid #eee; padding-bottom: 4px; margin: 12px 0 8px">
        <b>规划内</b> · 目标任务 {{ activeGoals.length }} 个
      </div>
      <div v-for="g in activeGoals" :key="g.id" class="judgment-item">
        <div class="action-group" style="align-items: center">
          <b>{{ g.description || g.metric }}</b>
          <span class="tag">{{ g.metric }}</span>
          <span v-if="g.deadline" class="muted" style="font-size: 13px; margin-left: auto">
            截止 {{ String(g.deadline).slice(0, 10) }}
          </span>
        </div>
        <div v-for="p in (g.progress || [])" :key="p.item_id" style="margin-top: 6px">
          <div class="action-group" style="align-items: center; font-size: 13px">
            <span>{{ p.name }}</span>
            <span class="muted" style="margin-left: auto">{{ progressText(p) }}</span>
          </div>
          <div v-if="p.rate !== null && p.rate !== undefined" class="track">
            <div class="fill" :style="{ width: progressPercent(p) + '%' }"></div>
          </div>
        </div>
      </div>
    </template>

    <p v-if="error" class="muted" style="color: var(--danger)">{{ error }}</p>
    <p v-if="hint" class="muted" style="color: var(--success); font-size: 13px">✓ {{ hint }}</p>

    <p v-if="items.length === 0 && !error" class="muted">
      还没有启用中的打卡项目。展开下面的【规划设置 → 打卡项目】建几个，再回来盘点；
      也可以直接在【自由记一笔】里写点什么。
    </p>

    <div class="action-group" v-if="allItems.length" style="margin: 10px 0">
      <button class="btn primary" :disabled="busy || !filledCount" @click="submitAll">
        {{ busy ? '提交中…' : `提交全部${filledCount ? `（${filledCount} 条）` : ''}` }}
      </button>
    </div>

    <!-- 规划内 -->
    <template v-if="plannedItems.length">
      <div class="muted" style="font-size: 13px; border-bottom: 1px solid #eee; padding-bottom: 4px; margin: 12px 0 8px">
        <b>规划内</b> · {{ plannedItems.length }} 个
      </div>
      <div v-for="it in plannedItems" :key="it.id" class="judgment-item">
        <div class="action-group" style="align-items: center">
          <b>{{ it.name }}</b>
          <span class="tag" :style="isReached(it) ? 'background:#eafaf1;color:#1f9e6a' : ''">{{ statusText(it) }}</span>
          <span v-if="it.category" class="muted" style="font-size: 13px">{{ it.category }}</span>
          <span v-if="isReached(it)" class="muted" style="margin-left: auto; font-size: 13px; color: #1f9e6a">✓ 已达标</span>
        </div>
        <p v-if="shortfallText(it)" class="muted" style="font-size: 13px; color: var(--warn); margin: 4px 0">⚠️ {{ shortfallText(it) }}</p>
        <div class="action-group" style="margin-top: 6px">
          <input v-model="drafts[it.id]" placeholder="一句话记录，如：跑了 5 公里" style="flex: 3" />
          <button class="btn small primary" style="flex: 0 0 auto" :disabled="rowState[it.id]?.busy" @click="submitOne(it)">
            {{ rowState[it.id]?.busy ? '判定中…' : '记录' }}
          </button>
        </div>
        <p v-if="rowState[it.id]?.err" class="muted" style="color: var(--danger); font-size: 13px">⚠️ {{ rowState[it.id].err }}</p>
      </div>
    </template>

    <!-- 可选 -->
    <template v-if="optionalItems.length">
      <div class="muted" style="font-size: 13px; border-bottom: 1px solid #eee; padding-bottom: 4px; margin: 12px 0 8px">
        <b>可选</b> · {{ optionalItems.length }} 个
      </div>
      <div v-for="it in optionalItems" :key="it.id" class="judgment-item">
        <div class="action-group" style="align-items: center">
          <b>{{ it.name }}</b>
          <span class="tag">{{ statusText(it) }}</span>
          <span v-if="it.category" class="muted" style="font-size: 13px">{{ it.category }}</span>
        </div>
        <div class="action-group" style="margin-top: 6px">
          <input v-model="drafts[it.id]" placeholder="一句话记录" style="flex: 3" />
          <button class="btn small primary" style="flex: 0 0 auto" :disabled="rowState[it.id]?.busy" @click="submitOne(it)">
            {{ rowState[it.id]?.busy ? '判定中…' : '记录' }}
          </button>
        </div>
        <p v-if="rowState[it.id]?.err" class="muted" style="color: var(--danger); font-size: 13px">⚠️ {{ rowState[it.id].err }}</p>
      </div>
    </template>

    <!-- 其他 -->
    <template v-if="otherItems.length">
      <div class="muted" style="font-size: 13px; border-bottom: 1px solid #eee; padding-bottom: 4px; margin: 12px 0 8px">
        <b>其他</b> · {{ otherItems.length }} 个
      </div>
      <div v-for="it in otherItems" :key="it.id" class="judgment-item">
        <div class="action-group" style="align-items: center">
          <b>{{ it.name }}</b>
          <span class="tag">{{ statusText(it) }}</span>
        </div>
        <div class="action-group" style="margin-top: 6px">
          <input v-model="drafts[it.id]" placeholder="一句话记录" style="flex: 3" />
          <button class="btn small primary" style="flex: 0 0 auto" :disabled="rowState[it.id]?.busy" @click="submitOne(it)">
            {{ rowState[it.id]?.busy ? '判定中…' : '记录' }}
          </button>
        </div>
        <p v-if="rowState[it.id]?.err" class="muted" style="color: var(--danger); font-size: 13px">⚠️ {{ rowState[it.id].err }}</p>
      </div>
    </template>

    <!-- 负面项：不强制罗列，折叠供快速补记 -->
    <template v-if="negativeItems.length">
      <div
        class="judgment-item"
        style="cursor: pointer; display: flex; align-items: center; margin-top: 12px"
        @click="showNegative = !showNegative"
       role="button" tabindex="0" @keydown.enter.self.prevent="showNegative = !showNegative" @keydown.space.self.prevent="showNegative = !showNegative">
        <b>负面项 {{ negativeItems.length }} 个</b>
        <span class="muted" style="font-size: 13px; margin-left: 8px">如实记一次扣一次分（不会去重）</span>
        <span class="muted" style="margin-left: auto">{{ showNegative ? '▾' : '▸' }}</span>
      </div>
      <template v-if="showNegative">
        <div v-for="it in negativeItems" :key="it.id" class="judgment-item" style="margin-left: 12px">
          <div class="action-group" style="align-items: center">
            <b>{{ it.name }}</b>
            <span class="tag">{{ statusText(it) }}</span>
          </div>
          <div class="action-group" style="margin-top: 6px">
            <input v-model="drafts[it.id]" placeholder="如实记一笔，如：久坐 3 小时" style="flex: 3" />
            <button class="btn small danger" style="flex: 0 0 auto" :disabled="rowState[it.id]?.busy" @click="submitOne(it)">
              {{ rowState[it.id]?.busy ? '判定中…' : '记录' }}
            </button>
          </div>
          <p v-if="rowState[it.id]?.err" class="muted" style="color: var(--danger); font-size: 13px">⚠️ {{ rowState[it.id].err }}</p>
        </div>
      </template>
    </template>

    <div class="action-group" style="margin-top: 12px" v-if="items.length">
      <button class="btn small" @click="emit('go-judgments')">去判定中心确认入账 →</button>
      <button class="btn small" @click="load">刷新</button>
    </div>
  </div>

  <!-- ============ v1.10 P2-1：自由记一笔（原「记录事件」页，组件原样复用） ============ -->
  <RecordComposer @saved="load" />

  <!-- ============ v1.10 P2-1：规划设置（折叠；目标 + 打卡项目管理） ============ -->
  <div class="card">
    <div
      class="action-group"
      style="align-items: center; cursor: pointer; user-select: none"
      @click="showPlanning = !showPlanning"
     role="button" tabindex="0" @keydown.enter.self.prevent="showPlanning = !showPlanning" @keydown.space.self.prevent="showPlanning = !showPlanning">
      <h2 style="margin: 0">规划设置</h2>
      <span class="muted" style="font-size: 13px; margin-left: 8px">目标与打卡项目（增删改停用、给项目选所属目标）</span>
      <span class="muted" style="margin-left: auto">{{ showPlanning ? '▾' : '▸' }}</span>
    </div>
    <template v-if="showPlanning">
      <GoalsView />
      <ItemManager />
    </template>
  </div>
</template>
