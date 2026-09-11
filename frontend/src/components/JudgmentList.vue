<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { api } from '../api'

const judgments = ref([])
const busy = ref(false)
const error = ref('')
const actionTarget = ref(null) // 正在操作的判定 id
const inputText = ref('')
const actionError = ref({ id: null, msg: '' }) // v1.4：操作失败的就近错误提示（不再只显示在卡片顶部）
const actionSuccess = ref({ id: null, msg: '' }) // v1.5 A2：成功轻提示（2 秒自动消失）
const disputeResult = ref({ id: null, conclusion: '', explanation: '' }) // v1.5 A2：反驳复核结论就地展示
const myInputOpen = ref(null) // v1.5 A2：「我的补充/反驳」折叠区展开的判定 id
const notice = ref('') // v1.5 A2：卡片顶部轻提示（删除/保存成功等，2 秒消失）
let successTimer = null
let noticeTimer = null
const auditTarget = ref(null) // 正在查看审计的判定 id
const auditLogs = ref([])
const editTarget = ref(null) // 正在编辑的事件 id
const editForm = ref({ title: '', category: '', content: '' })
const searchText = ref('')

const filteredJudgments = computed(() => {
  const kw = searchText.value.trim().toLowerCase()
  if (!kw) return judgments.value
  return judgments.value.filter((j) =>
    (j.event_title || '').toLowerCase().includes(kw) ||
    (j.category || '').toLowerCase().includes(kw) ||
    (j.summary || '').toLowerCase().includes(kw)
  )
})

// ============ v1.5 B1：按日期分组折叠（今天/昨天/本周更早/更早） ============
const GROUP_KEY = 'gol_judgment_group_expand'
const groupExpanded = ref(JSON.parse(localStorage.getItem(GROUP_KEY) || 'null') || { today: true }) // 默认只展开「今天」
watch(groupExpanded, () => {
  try { localStorage.setItem(GROUP_KEY, JSON.stringify(groupExpanded.value)) } catch (e) { /* 忽略 */ }
}, { deep: true })

const expandedItems = ref(new Set()) // 展开详情的判定（内存态，刷新复位）

function toggleGroup(key) {
  groupExpanded.value[key] = !groupExpanded.value[key]
}
function groupIsOpen(key) {
  if (searchText.value.trim()) return true // 搜索命中时自动展开所在组
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

const groupedJudgments = computed(() => {
  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const startOfYesterday = new Date(startOfToday.getTime() - 86400000)
  const monday = new Date(startOfToday)
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7)) // 本周一 0 点
  const buckets = { today: [], yesterday: [], thisweek: [], earlier: [] }
  for (const j of filteredJudgments.value) {
    const d = new Date(j.created_at)
    if (d >= startOfToday) buckets.today.push(j)
    else if (d >= startOfYesterday) buckets.yesterday.push(j)
    else if (d >= monday) buckets.thisweek.push(j)
    else buckets.earlier.push(j)
  }
  const fmt = (d) => `${`${d.getMonth() + 1}`.padStart(2, '0')}-${`${d.getDate()}`.padStart(2, '0')}`
  const meta = [
    { key: 'today', label: '今天' },
    { key: 'yesterday', label: '昨天' },
    { key: 'thisweek', label: '本周更早' },
    { key: 'earlier', label: '更早' },
  ]
  return meta
    .map((m) => {
      const items = buckets[m.key]
      if (!items.length) return null
      // 组头日期：今天/昨天显示当天日期；范围组显示首尾日期（items 按时间倒序）
      const dateRange =
        m.key === 'today' || m.key === 'yesterday'
          ? fmt(new Date(items[0].created_at))
          : `${fmt(new Date(items[items.length - 1].created_at))} ~ ${fmt(new Date(items[0].created_at))}`
      return { ...m, items, dateRange }
    })
    .filter(Boolean)
})

const ACTION_LABEL = {
  create: '生成判定',
  confirm: '确认入账',
  supplement: '补充信息',
  dispute: '反驳',
  rejudge: '重新判定',
  maintain: '维持原判',
  delete: '删除事件',
  invalidate: '判定作废',
}

async function load() {
  try {
    judgments.value = await api.listJudgments()
  } catch (e) {
    error.value = e.message
  }
}

async function refreshAudit(id) {
  // v1.3：审计拉取独立成函数，供操作成功后同步刷新（无需关闭重开）
  try {
    auditLogs.value = await api.getJudgmentLogs(id)
  } catch (e) {
    error.value = e.message
  }
}

async function toggleAudit(id) {
  if (auditTarget.value === id) {
    auditTarget.value = null
    return
  }
  auditTarget.value = id
  auditLogs.value = []
  await refreshAudit(id)
}

const STATUS_LABEL = {
  pending: '待确认',
  adjusted: '已调整',
  confirmed: '已入账',
  rejected: '已驳回',
  invalidated: '已作废',
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
    // v1.5 A2：复核结论就地展示（替代阻塞式 alert）
    disputeResult.value = { id, conclusion: res.conclusion, explanation: res.explanation || '' }
  }
}

// v1.1：删除事件（误提交兜底，含点数回滚）
async function removeEvent(eventId, confirmed) {
  const ok = window.confirm(
    confirmed
      ? '该事件已确认入账，删除将回滚对应点数。确认删除？'
      : '确认删除该事件及其判定记录？'
  )
  if (!ok) return
  busy.value = true
  error.value = ''
  try {
    await api.deleteEvent(eventId)
    // v1.3：事件删除后判定消失，收起审计面板（避免残留旧轨迹）
    auditTarget.value = null
    auditLogs.value = []
    await load()
    // v1.5 A2：删除成功用轻提示（原为 alert）
    flash('已删除' + (confirmed ? '，相关点数已回滚' : ''))
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

function flash(msg) {
  // v1.5 A2：顶部轻提示，2 秒自动消失（替代成功场景的阻塞式 alert）
  notice.value = msg
  clearTimeout(noticeTimer)
  noticeTimer = setTimeout(() => (notice.value = ''), 2000)
}

async function runAction(id, fn, okMsg) {
  busy.value = true
  error.value = ''
  actionError.value = { id: null, msg: '' }
  try {
    const res = await fn()
    await load()
    // v1.3：若该判定的审计面板正展开，同步刷新轨迹（修复确认/补充/反驳后轨迹不更新）
    if (auditTarget.value === id) await refreshAudit(id)
    // v1.4：仅成功路径收起输入框并清空（失败时保留用户已输入内容）
    actionTarget.value = null
    inputText.value = ''
    // v1.5 A2：成功轻提示（真正使用 okMsg，2 秒自动消失）
    if (okMsg) {
      actionSuccess.value = { id, msg: okMsg }
      clearTimeout(successTimer)
      successTimer = setTimeout(() => (actionSuccess.value = { id: null, msg: '' }), 2000)
    }
    return res
  } catch (e) {
    // v1.4：失败不收起输入框、不清空内容，错误就近显示在输入框上方
    actionError.value = { id, msg: e.message }
  } finally {
    busy.value = false
  }
}

// 编辑事件：回填事件详情
async function openEdit(eventId) {
  try {
    const ev = await api.getEvent(eventId)
    editForm.value = {
      title: ev.title || '',
      category: ev.category || '',
      content: ev.content || '',
    }
    editTarget.value = eventId
  } catch (e) {
    error.value = e.message
  }
}

async function saveEdit() {
  busy.value = true
  error.value = ''
  try {
    await api.updateEvent(editTarget.value, {
      title: editForm.value.title,
      category: editForm.value.category,
      content: editForm.value.content,
    })
    editTarget.value = null
    await load()
    // v1.5 A4：编辑后旧判定作废归档（从列表消失），收起可能悬空的审计面板
    auditTarget.value = null
    auditLogs.value = []
    // v1.5 A2：保存成功用轻提示（原为 alert，且文案对齐 A1 作废语义）
    flash('已保存。事件内容变更后旧判定已作废，可重新判定。')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

function openAction(id, mode) {
  // v1.4：切换目标时清掉上一次的就近错误
  if (actionTarget.value !== id) actionError.value = { id: null, msg: '' }
  // v1.5 A2：切换目标时收起上一条的复核结论
  if (actionTarget.value !== id && disputeResult.value.id !== id) disputeResult.value = { id: null, conclusion: '', explanation: '' }
  actionTarget.value = id
  inputText.value = ''
}

function toggleMyInput(id) {
  myInputOpen.value = myInputOpen.value === id ? null : id
}

onMounted(load)
</script>

<template>
  <div class="card">
    <h2>判定中心</h2>
    <p class="muted">AI 对每条事件给出建议增减，你可以确认入账、补充信息重判、或反驳复核。</p>

    <p v-if="error" class="muted" style="color: #d33">{{ error }}</p>
    <!-- v1.5 A2：轻提示（删除/保存等成功反馈，2 秒消失） -->
    <p v-if="notice" class="muted" style="color: #2f855a; font-size: 13px">✓ {{ notice }}</p>
    <p v-if="judgments.length === 0 && !error" class="muted">暂无判定记录，先去「记录事件」打卡吧。</p>

    <div class="field" v-if="judgments.length > 0">
      <input v-model="searchText" placeholder="🔍 搜索事件/判定（标题/类别/总结）…" />
    </div>

    <!-- v1.5 B1：按日期分组折叠；每条判定默认收起为一行摘要 -->
    <p v-if="judgments.length > 0" class="muted" style="font-size: 12px">点击标题行展开详情；组头可折叠（搜索时自动展开命中项）。</p>

    <div v-for="g in groupedJudgments" :key="g.key" style="margin-bottom: 12px">
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
        <div v-for="j in g.items" :key="j.id" class="judgment-item">
          <!-- 摘要行（点击展开/收起详情） -->
          <div class="row" style="align-items: center; cursor: pointer" @click="toggleItem(j.id)">
            <b>{{ j.event_title || j.category }}</b>
            <span class="tag">{{ j.event_type }}</span>
            <span class="tag">{{ STATUS_LABEL[j.status] || j.status }}</span>
            <span v-if="j.rejudge_count > 0" class="tag" title="从审计日志统计的重判次数">已重判 · 第 {{ j.rejudge_count }} 次</span>
            <span class="muted">置信度 {{ (j.confidence * 100).toFixed(0) }}%</span>
            <span class="muted" style="margin-left: auto; font-size: 12px">{{ new Date(j.created_at).toLocaleString('zh-CN') }}</span>
            <span class="muted">{{ itemIsOpen(j.id) ? '▾' : '▸' }}</span>
          </div>

          <template v-if="itemIsOpen(j.id)">
            <!-- v1.4：置信度说明（低置信度时 AI 给出的不确定点） -->
            <div v-if="j.confidence_reason && j.status !== 'confirmed'" class="muted" style="font-size: 12px; margin-bottom: 6px; color: #b7791f">
              💡 {{ j.confidence_reason }}
            </div>

            <!-- v1.6：本次修订说明（重判改变了什么，无修订不显示） -->
            <div v-if="j.revision_notes && j.revision_notes.length" class="muted" style="font-size: 12px; margin-bottom: 6px; color: #2b6cb0">
              <span class="tag">本次修订</span>
              <div v-for="(n, i) in j.revision_notes" :key="i" style="margin-top: 2px">{{ n }}</div>
            </div>

            <!-- v1.5 A2：最近一次用户提交的补充/反驳（数据源=审计日志，默认收起） -->
            <div v-if="j.last_user_input" class="muted" style="font-size: 12px; margin-bottom: 6px">
              <span style="cursor: pointer; user-select: none" @click="toggleMyInput(j.id)">
                {{ myInputOpen === j.id ? '▾' : '▸' }} 我的{{ j.last_user_input.action === 'dispute' ? '反驳' : '补充' }}（{{ new Date(j.last_user_input.created_at).toLocaleString('zh-CN') }}）
              </span>
              <div v-if="myInputOpen === j.id" style="white-space: pre-wrap; margin-top: 4px; padding: 6px 8px; background: #f7f7f9; border-radius: 6px">{{ j.last_user_input.detail }}</div>
            </div>

      <div v-if="j.summary" class="muted" style="margin-bottom: 6px">{{ j.summary }}</div>

      <!-- AI 分析过程（v1.1） -->
      <div v-if="j.analysis && j.analysis.length" class="analysis-box">
        <div class="analysis-title">🤖 AI 分析过程</div>
        <div v-for="(step, idx) in j.analysis" :key="idx" class="step">{{ step }}</div>
      </div>

      <div v-for="a in j.suggested_changes" :key="a.name" class="judgment-item">
        <span class="attr-name">{{ a.name }}</span>
        <span :class="a.delta >= 0 ? 'positive' : 'negative'">{{ a.delta >= 0 ? '+' : '' }}{{ a.delta }}</span>
        <span class="muted" style="font-size: 12px">
          → 入账 {{ (a.delta * (j.confidence || 1)).toFixed(1) }}（置信度 {{ ((j.confidence || 1) * 100).toFixed(0) }}%）
        </span>
        <div class="muted">{{ a.reason }}</div>
        <div class="evidence">依据：{{ a.evidence }}</div>
      </div>

      <!-- 操作区 -->
      <div class="row" style="margin-top: 10px; align-items: center">
        <div v-if="j.status !== 'confirmed'" class="row" style="gap: 8px; flex: 1">
          <button
            class="btn small primary"
            :disabled="busy || (j.confidence || 0) < 0.8"
            @click="confirm(j.id)"
          >确认入账</button>
          <button class="btn small" :disabled="busy" @click="openAction(j.id, 'supplement')">补充信息</button>
          <button class="btn small danger" :disabled="busy" @click="openAction(j.id, 'dispute')">反驳</button>
        </div>
        <span v-else class="muted" style="flex: 1">✓ 已入账</span>
        <button class="btn small" :disabled="busy" @click="openEdit(j.event_id)">编辑</button>
        <button class="btn small" :disabled="busy" @click="toggleAudit(j.id)">审计</button>
        <!-- v1.1：误提交兜底，任何状态都可删除事件 -->
        <button class="btn small danger" :disabled="busy" @click="removeEvent(j.event_id, j.status === 'confirmed')">
          删除事件
        </button>
      </div>

      <!-- v1.4：操作失败的就近错误提示（在输入框上方 / 操作按钮下方，不再跑到卡片顶部） -->
      <p
        v-if="actionError.id === j.id"
        class="muted"
        style="color: #d33; font-size: 12px; margin-top: 6px"
      >⚠️ {{ actionError.msg }}</p>

      <!-- v1.5 A2：成功轻提示（2 秒消失） -->
      <p
        v-if="actionSuccess.id === j.id"
        class="muted"
        style="color: #2f855a; font-size: 12px; margin-top: 6px"
      >✓ {{ actionSuccess.msg }}</p>

      <!-- v1.5 A2：反驳复核结论就地展示（替代 alert） -->
      <div
        v-if="disputeResult.id === j.id"
        class="muted"
        style="font-size: 12px; margin-top: 6px; padding: 6px 8px; background: #f7f7f9; border-radius: 6px"
      >⚖️ {{ disputeResult.conclusion === 'adjust' ? '复核已调整判定' : 'AI 坚持原判' }}<template v-if="disputeResult.explanation">：{{ disputeResult.explanation }}</template></div>

      <!-- 补充/反驳输入框（v1.4：就近渲染在操作按钮行正下方，长卡片不再滚出视口） -->
      <div v-if="actionTarget === j.id" class="field" style="margin-top: 10px">
        <label>补充信息 / 反驳理由：</label>
        <textarea v-model="inputText" rows="2" placeholder="说明你的补充或反驳理由…"></textarea>
        <div class="row" style="margin-top: 8px">
          <button class="btn small primary" :disabled="busy" @click="supplement(j.id)">提交补充</button>
          <button class="btn small danger" :disabled="busy" @click="dispute(j.id)">提交反驳</button>
        </div>
      </div>

      <!-- 低置信度提示（v1.2；v1.4 引用 AI 置信度说明） -->
      <p
        v-if="j.status !== 'confirmed' && (j.confidence || 0) < 0.8"
        class="muted"
        style="color: #b7791f; font-size: 12px; margin-top: 6px"
      >
        ⚠️ 置信度 {{ ((j.confidence || 0) * 100).toFixed(0) }}%<template v-if="j.confidence_reason">：{{ j.confidence_reason }}</template>，可补充信息后重判或直接反驳。
      </p>

      <!-- 编辑表单 -->
      <div v-if="editTarget === j.event_id" class="field" style="margin-top: 10px">
        <label>标题</label>
        <input v-model="editForm.title" placeholder="事件标题" />
        <label>类别</label>
        <input v-model="editForm.category" placeholder="锻炼/学习/作息/…" />
        <label>内容（日记原文，可选）</label>
        <textarea v-model="editForm.content" rows="2" placeholder="事件内容"></textarea>
        <div class="row" style="margin-top: 8px">
          <button class="btn small primary" :disabled="busy" @click="saveEdit">保存</button>
          <button class="btn small" @click="editTarget = null">取消</button>
        </div>
      </div>

      <!-- 审计时间线 -->
      <div v-if="auditTarget === j.id" class="audit-box">
        <div class="audit-title">📜 审计轨迹</div>
        <div v-if="auditLogs.length === 0" class="muted">暂无审计记录。</div>
        <div v-for="log in auditLogs" :key="log.id" class="audit-item">
          <span class="tag">{{ ACTION_LABEL[log.action] || log.action }}</span>
          <span class="muted">{{ log.detail }}</span>
          <div class="muted" style="font-size: 12px">{{ new Date(log.created_at).toLocaleString('zh-CN') }}</div>
        </div>
      </div>
          </template><!-- /itemIsOpen -->
        </div>
      </template><!-- /groupIsOpen -->
    </div>
  </div>
</template>
