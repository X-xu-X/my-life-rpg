<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { account } from '../session'
import { toast } from '../composables/useToast'
import { useDateGroups } from '../composables/useDateGroups'

const judgments = ref([])
const busy = ref(false)
const error = ref('')
const actionTarget = ref(null) // 正在操作的判定 id
const inputText = ref('')
const actionError = ref({ id: null, msg: '' }) // v1.4：操作失败的就近错误提示（不再只显示在卡片顶部）
const actionSuccess = ref({ id: null, msg: '' }) // v1.6 B1：保留式成功状态（不自动消失，下次操作/刷新清除）
const disputeResult = ref({ id: null, conclusion: '', explanation: '' }) // v1.5 A2：反驳复核结论就地展示
const myInputOpen = ref(null) // v1.5 A2：「我的补充/反驳」折叠区展开的判定 id
const notice = ref('') // v1.5 A2：卡片顶部轻提示（删除/保存成功等，2 秒消失）
let noticeTimer = null
const auditTarget = ref(null) // 正在查看审计的判定 id
const auditLogs = ref([])
const editTarget = ref(null) // 正在编辑的事件 id
const editForm = ref({ title: '', category: '', content: '' })
const searchText = ref('')

// ============ v1.7 C1：AI 正在分析状态 + 防重复点击 ============
// busyId = 正在跑请求的判定 id（null 表示空闲）。整个请求周期（含 LLM 内部重试）保持，
// 期间该卡片全部操作按钮 + 输入框 + 下拉禁用，按钮文案变「AI 正在分析…」并显示 spinner。
const busyId = ref(null)
const slowHintId = ref(null) // 超过 60 秒仍未返回时，提示"响应较慢"
let slowTimer = null
const SLOW_THRESHOLD_MS = 60000

function startBusy(id) {
  busyId.value = id
  slowHintId.value = null
  clearTimeout(slowTimer)
  slowTimer = setTimeout(() => {
    if (busyId.value === id) slowHintId.value = id
  }, SLOW_THRESHOLD_MS)
}

function endBusy() {
  busyId.value = null
  slowHintId.value = null
  clearTimeout(slowTimer)
  slowTimer = null
}

/** 某条判定是否正在处理中 */
function isBusy(id) {
  return busyId.value === id
}
/** 是否有任意请求在跑（用于禁用全局性操作） */
const anyBusy = computed(() => busyId.value !== null)

const filteredJudgments = computed(() => {
  const kw = searchText.value.trim().toLowerCase()
  if (!kw) return judgments.value
  return judgments.value.filter((j) =>
    (j.event_title || '').toLowerCase().includes(kw) ||
    (j.category || '').toLowerCase().includes(kw) ||
    (j.summary || '').toLowerCase().includes(kw)
  )
})

// ============ v1.5 B1 / v1.6 B2：按日期分组折叠（公共逻辑已抽到 useDateGroups） ============
const { groups: groupedJudgments, expanded: groupExpanded, toggleGroup } = useDateGroups(filteredJudgments, {
  storageKey: 'gol_judgment_group_expand',
})

const expandedItems = ref(new Set()) // 展开详情的判定（内存态，刷新复位）

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
    toast.error(e.message)
  }
}

async function refreshAudit(id) {
  // v1.3：审计拉取独立成函数，供操作成功后同步刷新（无需关闭重开）
  try {
    auditLogs.value = await api.getJudgmentLogs(id)
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  }
}

async function toggleAudit(id) {
  clearSuccess(id) // v1.6 B1：下一个操作清除保留式成功状态
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
  await runAction(id, () => api.confirmJudgment(id, judgments.value.find(j=>j.id===id)?.updated_at), '已确认入账')
}

async function supplement(id) {
  if (!inputText.value.trim()) return toast.error('请填写补充信息')
  await runAction(id, () => api.supplementJudgment(id, inputText.value.trim(), judgments.value.find(j=>j.id===id)?.updated_at), account.value?.mode === 'cloud' ? '补充已排队，可在待办查看结果' : '已重新判定')
}

async function dispute(id) {
  if (!inputText.value.trim()) return toast.error('请填写反驳理由')
  const res = await runAction(id, () => api.disputeJudgment(id, inputText.value.trim(), judgments.value.find(j=>j.id===id)?.updated_at), '已提交反驳复核，可在待办查看进度')
  if (res && res.state !== 'queued') {
    // v1.5 A2：复核结论就地展示（替代阻塞式 alert）
    disputeResult.value = { id, conclusion: res.conclusion, explanation: res.explanation || '' }
  }
}

// v1.1：删除事件（误提交兜底，含点数回滚）
async function removeEvent(jid, eventId, confirmed) {
  clearSuccess(jid) // v1.6 B1
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
    toast.error(e.message)
  } finally {
    busy.value = false
  }
}

function flash(msg) {
  // v1.5 A2：顶部轻提示，2 秒自动消失（替代成功场景的阻塞式 alert）
  notice.value = msg
  clearTimeout(noticeTimer)
  noticeTimer = setTimeout(() => (notice.value = ''), 2000)
  // v1.9 F2：同时接入全局 toast（统一规范）
  toast.success(msg)
}

function clearSuccess(id) {
  // v1.6 B1：用户在同一条判定上做下一个操作时，清除保留式成功状态
  if (actionSuccess.value.id === id) actionSuccess.value = { id: null, msg: '' }
}

async function runAction(id, fn, okMsg) {
  if (isBusy(id)) return // v1.7 C1：防重复点击（同一条判定处理中直接忽略）
  busy.value = true
  startBusy(id) // v1.7 C1：进入「AI 正在分析…」状态，覆盖整个请求周期
  error.value = ''
  actionError.value = { id: null, msg: '' }
  clearSuccess(id)
  try {
    const res = await fn()
    await load()
    // v1.3：若该判定的审计面板正展开，同步刷新轨迹（修复确认/补充/反驳后轨迹不更新）
    if (auditTarget.value === id) await refreshAudit(id)
    // v1.4：仅成功路径收起输入框并清空（失败时保留用户已输入内容）
    actionTarget.value = null
    inputText.value = ''
    // v1.6 B1：保留式成功状态——不自动消失，保留至用户在同一条判定上做下一个操作
    if (okMsg) {
      actionSuccess.value = { id, msg: okMsg }
    }
    return res
  } catch (e) {
    // v1.4：失败不收起输入框、不清空内容，错误就近显示在输入框上方
    if (e.status === 409) await load()
    actionError.value = { id, msg: e.message + (e.status === 409 ? ' 已重读最新结果；输入已保留，请比较后重新提交。' : '') }
  } finally {
    busy.value = false
    endBusy() // v1.7 C1：请求返回（成功或失败）才恢复
  }
}

// 编辑事件：回填事件详情
async function openEdit(jid, eventId) {
  clearSuccess(jid) // v1.6 B1
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
    toast.error(e.message)
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
    toast.error(e.message)
  } finally {
    busy.value = false
  }
}

function openAction(id, mode) {
  // v1.4：切换目标时清掉上一次的就近错误
  if (actionTarget.value !== id) actionError.value = { id: null, msg: '' }
  // v1.5 A2：切换目标时收起上一条的复核结论
  if (actionTarget.value !== id && disputeResult.value.id !== id) disputeResult.value = { id: null, conclusion: '', explanation: '' }
  clearSuccess(id) // v1.6 B1
  actionTarget.value = id
  inputText.value = ''
}

// v1.7 C2：输入型操作（补充/反驳）的「取消」——关闭输入区、清空输入、回到未操作态（不提交）
function cancelAction() {
  if (anyBusy.value) return // 处理中禁用取消（避免状态不一致）
  actionTarget.value = null
  inputText.value = ''
  actionError.value = { id: null, msg: '' }
}

// v1.10 M1：处理 AI 里程碑建议（追授 / 忽略）。
// **必须用户点按钮**——判定链路本身不会自动发放任何奖励。
async function handleMilestone(j, action) {
  const res = await runAction(
    `milestone-${j.id}`,
    async () => api.handleAchievement(j.id, action),
    action === 'grant' ? '已追授该里程碑' : '已忽略'
  )
  if (res && action === 'grant' && res.achievement) {
    toast.success(`🎖 已追授「${res.achievement.name}」，+${res.achievement.coin_reward} 币`)
  }
}

function toggleMyInput(id) {
  myInputOpen.value = myInputOpen.value === id ? null : id
}

onMounted(load)
</script>

<template>
  <header class="page-intro"><h1>判定与审计</h1></header>
  <div class="card">
    <h1>判定与审计</h1>
    <p class="muted">未入账判定可确认、补充或反驳。已入账后冻结正文与判定，可删除事件撤销属性；金币保留。挑战判定请在挑战页处理。</p>

    <p v-if="error" class="muted" style="color: var(--danger)">{{ error }}</p>
    <!-- v1.5 A2：轻提示（删除/保存等成功反馈，2 秒消失） -->
    <p v-if="notice" class="muted" style="color: var(--success); font-size: 13px">✓ {{ notice }}</p>
    <p v-if="judgments.length === 0 && !error" class="muted">暂无判定记录，先去「记录事件」打卡吧。</p>

    <div class="field" v-if="judgments.length > 0">
      <input v-model="searchText" placeholder="🔍 搜索事件/判定（标题/类别/总结）…" />
    </div>

    <!-- v1.5 B1：按日期分组折叠；每条判定默认收起为一行摘要 -->
    <p v-if="judgments.length > 0" class="muted" style="font-size: 13px">点击标题行展开详情；组头可折叠（搜索时自动展开命中项）。</p>

    <div v-for="g in groupedJudgments" :key="g.key" style="margin-bottom: 12px">
      <div
        class="action-group"
        style="align-items: center; cursor: pointer; padding: 6px 4px; border-bottom: 1px solid #eee; user-select: none"
        @click="toggleGroup(g.key)"
       role="button" tabindex="0" @keydown.enter.self.prevent="toggleGroup(g.key)" @keydown.space.self.prevent="toggleGroup(g.key)">
        <b>{{ g.label }}</b>
        <span class="muted" style="font-size: 13px">{{ g.dateRange }}</span>
        <span class="muted" style="font-size: 13px">{{ g.items.length }} 条</span>
        <span class="muted" style="margin-left: auto">{{ groupIsOpen(g.key) ? '▾' : '▸' }}</span>
      </div>

      <template v-if="groupIsOpen(g.key)">
        <div v-for="j in g.items" :key="j.id" class="judgment-item">
          <!-- 摘要行（点击展开/收起详情） -->
          <div class="action-group" style="align-items: center; cursor: pointer" @click="toggleItem(j.id)" role="button" tabindex="0" @keydown.enter.self.prevent="toggleItem(j.id)" @keydown.space.self.prevent="toggleItem(j.id)">
            <b>{{ j.event_title || j.category }}</b>
            <span v-if="j.origin === 'challenge'" class="tag" title="由挑战结算生成">挑战</span>
            <span class="tag">{{ j.event_type }}</span>
            <span class="tag">{{ STATUS_LABEL[j.status] || j.status }}</span>
            <span v-if="j.rejudge_count > 0" class="tag" title="从审计日志统计的重判次数">已重判 · 第 {{ j.rejudge_count }} 次</span>
            <span class="muted">置信度 {{ (j.confidence * 100).toFixed(0) }}%</span>
            <span class="muted" style="margin-left: auto; font-size: 13px">{{ new Date(j.created_at).toLocaleString('zh-CN') }}</span>
            <span class="muted">{{ itemIsOpen(j.id) ? '▾' : '▸' }}</span>
          </div>

          <template v-if="itemIsOpen(j.id)">
            <!-- v1.4：置信度说明（低置信度时 AI 给出的不确定点） -->
            <div v-if="j.confidence_reason && j.status !== 'confirmed'" class="muted" style="font-size: 13px; margin-bottom: 6px; color: var(--warn)">
              💡 {{ j.confidence_reason }}
            </div>

            <!-- v1.7：跨来源合并明细（已与 N 条记录合并，可反驳撤销） -->
            <div v-if="j.merged_with && j.merged_with.length" class="muted" style="font-size: 13px; margin-bottom: 6px; color: #7c5cbf">
              <span class="tag">疑似关联 {{ j.merged_with.length }} 条记录 · 尚未确认</span>
              <div v-for="(m, i) in j.merged_with" :key="i" style="margin-top: 2px">
                · {{ m.ref }}<template v-if="m.note">：{{ m.note }}</template>
              </div>
              <div style="margin-top: 2px">仅为模型候选，不代表原文或账目已合并；可通过复核说明不同事实。</div>
            </div>

            <!-- v1.10 M1：AI 发现型里程碑建议（必须用户点按钮才发放） -->
            <p v-if="j.event_record_kind&&j.achievement_suggestion?.name" class="muted">里程碑建议：{{ j.achievement_suggestion.name }}。<RouterLink to="/plans">到核实型候选核对指标与规则 →</RouterLink></p>
            <div
              v-if="!j.event_record_kind && j.achievement_suggestion && j.achievement_suggestion.name && j.achievement_suggestion.state === 'pending'"
              class="milestone-card"
            >
              <div>🎖 <b>AI 认为这是一个里程碑：</b>{{ j.achievement_suggestion.name }}</div>
              <div class="muted" style="margin-top: 4px">「{{ j.achievement_suggestion.reason }}」</div>
              <div class="action-group">
                <button class="btn small primary" :disabled="anyBusy" @click="handleMilestone(j, 'grant')">
                  <template v-if="isBusy(`milestone-${j.id}`)">处理中…</template>
                  <template v-else>追授（+50 币）</template>
                </button>
                <button class="btn small" :disabled="anyBusy" @click="handleMilestone(j, 'dismiss')">
                  忽略
                </button>
              </div>
            </div>

            <!-- v1.6：本次修订说明（重判改变了什么，无修订不显示） -->
            <div v-if="j.revision_notes && j.revision_notes.length" class="muted" style="font-size: 13px; margin-bottom: 6px; color: #2b6cb0">
              <span class="tag">本次修订</span>
              <div v-for="(n, i) in j.revision_notes" :key="i" style="margin-top: 2px">{{ n }}</div>
            </div>

            <!-- v1.5 A2：最近一次用户提交的补充/反驳（数据源=审计日志，默认收起） -->
            <div v-if="j.last_user_input" class="muted" style="font-size: 13px; margin-bottom: 6px">
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
        <span class="muted" style="font-size: 13px">
          → 入账 {{ (a.delta * (j.confidence || 1)).toFixed(1) }}（置信度 {{ ((j.confidence || 1) * 100).toFixed(0) }}%）
        </span>
        <div class="muted">{{ a.reason }}</div>
        <div class="evidence">依据：{{ a.evidence }}</div>
      </div>

      <!-- 操作区（v1.6 B1：成功状态整体替换主操作区；v1.7 C1：处理中显示「AI 正在分析…」） -->
      <div class="action-group" style="margin-top: 10px; align-items: center">
        <template v-if="actionSuccess.id === j.id">
          <span class="muted" style="flex: 1; color: var(--success); font-weight: 600; font-size: 14px">✓ {{ actionSuccess.msg }}</span>
        </template>
        <template v-else-if="isBusy(j.id)">
          <!-- v1.7 C1：AI 正在分析中——整卡操作禁用，文案即时变化 -->
          <span class="muted" style="flex: 1; color: var(--primary); font-weight: 600; font-size: 14px">
            <span class="spinner"></span> AI 正在分析…
          </span>
        </template>
        <template v-else>
          <div v-if="j.status !== 'confirmed' && j.origin !== 'challenge'" class="action-group" style="gap: 8px; flex: 1">
            <button
              class="btn small primary"
              :disabled="busy || (j.confidence || 0) < 0.8"
              @click="confirm(j.id)"
            >确认入账</button>
            <button class="btn small" :disabled="busy" @click="openAction(j.id, 'supplement')">补充信息</button>
            <button class="btn small danger" :disabled="busy" @click="openAction(j.id, 'dispute')">反驳</button>
          </div>
          <span v-else-if="j.status === 'confirmed'" class="muted" style="flex: 1">✓ 已入账</span>
          <span v-else-if="j.origin === 'challenge'" class="muted" style="flex: 1">待结算，前往挑战页处理</span>
          <span v-else class="muted" style="flex: 1">{{ STATUS_LABEL[j.status] || j.status }}</span>
        </template>
        <button v-if="j.status !== 'confirmed' && j.origin !== 'challenge'" class="btn small" :disabled="anyBusy" @click="openEdit(j.id, j.event_id)">编辑</button>
        <button class="btn small" :disabled="anyBusy" @click="toggleAudit(j.id)">审计</button>
        <!-- v1.1：误提交兜底，任何状态都可删除事件 -->
        <button class="btn small danger" :disabled="anyBusy" @click="removeEvent(j.id, j.event_id, j.status === 'confirmed')">
          删除事件
        </button>
      </div>

      <!-- v1.7 C1：响应较慢提示（超过 60 秒未返回；不自动清空状态） -->
      <p v-if="slowHintId === j.id" class="muted" style="color: var(--warn); font-size: 13px; margin-top: 6px">
        ⏳ AI 响应较慢，可继续等待或点「取消」。
      </p>

      <!-- v1.4：操作失败的就近错误提示（在输入框上方 / 操作按钮下方，不再跑到卡片顶部） -->
      <p
        v-if="actionError.id === j.id"
        class="muted"
        style="color: var(--danger); font-size: 13px; margin-top: 6px"
      >⚠️ {{ actionError.msg }}</p>

      <!-- v1.5 A2：反驳复核结论就地展示（替代 alert） -->
      <div
        v-if="disputeResult.id === j.id"
        class="muted"
        style="font-size: 13px; margin-top: 6px; padding: 6px 8px; background: #f7f7f9; border-radius: 6px"
      >⚖️ {{ disputeResult.conclusion === 'adjust' ? '复核已调整判定' : 'AI 坚持原判' }}<template v-if="disputeResult.explanation">：{{ disputeResult.explanation }}</template></div>

      <!-- 补充/反驳输入框（v1.4：就近渲染在操作按钮行正下方；v1.7 C2：加「取消」） -->
      <div v-if="actionTarget === j.id" class="field" style="margin-top: 10px">
        <label for="judgmentlist-field-1">{{ j.status === 'confirmed' ? '反驳理由（已入账，仅可反驳）' : '补充信息 / 反驳理由：' }}</label>
        <textarea id="judgmentlist-field-1" v-model="inputText" rows="2" placeholder="说明你的补充或反驳理由…" :disabled="isBusy(j.id)"></textarea>
        <div class="action-group" style="margin-top: 8px">
          <button class="btn small primary" :disabled="isBusy(j.id)" @click="supplement(j.id)">
            {{ isBusy(j.id) ? 'AI 正在分析…' : '提交补充' }}
          </button>
          <button class="btn small danger" :disabled="isBusy(j.id)" @click="dispute(j.id)">
            {{ isBusy(j.id) ? 'AI 正在分析…' : '提交反驳' }}
          </button>
          <!-- v1.7 C2：取消（关闭输入区、清空输入、不提交）；处理中禁用 -->
          <button class="btn small" :disabled="anyBusy" @click="cancelAction">取消</button>
        </div>
      </div>

      <!-- 低置信度提示（v1.2；v1.4 引用 AI 置信度说明） -->
      <p
        v-if="j.status !== 'confirmed' && (j.confidence || 0) < 0.8"
        class="muted"
        style="color: var(--warn); font-size: 13px; margin-top: 6px"
      >
        ⚠️ 置信度 {{ ((j.confidence || 0) * 100).toFixed(0) }}%<template v-if="j.confidence_reason">：{{ j.confidence_reason }}</template>，可补充信息后重判或直接反驳。
      </p>

      <!-- 编辑表单 -->
      <div v-if="editTarget === j.event_id" class="field" style="margin-top: 10px">
        <label for="judgmentlist-field-2">标题</label>
        <input id="judgmentlist-field-2" v-model="editForm.title" placeholder="事件标题" />
        <label for="judgmentlist-field-3">类别</label>
        <input id="judgmentlist-field-3" v-model="editForm.category" placeholder="锻炼/学习/作息/…" />
        <label for="judgmentlist-field-4">内容（日记原文，可选）</label>
        <textarea id="judgmentlist-field-4" v-model="editForm.content" rows="2" placeholder="事件内容"></textarea>
        <div class="action-group" style="margin-top: 8px">
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
          <div class="muted" style="font-size: 13px">{{ new Date(log.created_at).toLocaleString('zh-CN') }}</div>
        </div>
      </div>
          </template><!-- /itemIsOpen -->
        </div>
      </template><!-- /groupIsOpen -->
    </div>
  </div>
</template>
