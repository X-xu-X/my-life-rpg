<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'

const judgments = ref([])
const busy = ref(false)
const error = ref('')
const actionTarget = ref(null) // 正在操作的判定 id
const inputText = ref('')
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

const ACTION_LABEL = {
  create: '生成判定',
  confirm: '确认入账',
  supplement: '补充信息',
  dispute: '反驳',
  rejudge: '重新判定',
  maintain: '维持原判',
  delete: '删除事件',
}

async function load() {
  try {
    judgments.value = await api.listJudgments()
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
  try {
    auditLogs.value = await api.getJudgmentLogs(id)
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
    await load()
    alert('已删除' + (confirmed ? '，相关点数已回滚' : ''))
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
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
    alert('已保存。事件内容变更后未确认的判定已删除，可重新判定。')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
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

    <div class="field" v-if="judgments.length > 0">
      <input v-model="searchText" placeholder="🔍 搜索事件/判定（标题/类别/总结）…" />
    </div>

    <div v-for="j in filteredJudgments" :key="j.id" class="judgment-item">
      <div class="row" style="align-items: center; margin-bottom: 8px">
        <b>{{ j.event_title || j.category }}</b>
        <span class="tag">{{ j.event_type }}</span>
        <span class="tag">{{ STATUS_LABEL[j.status] || j.status }}</span>
        <span class="muted">置信度 {{ (j.confidence * 100).toFixed(0) }}%</span>
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

      <!-- 低置信度提示（v1.2） -->
      <p
        v-if="j.status !== 'confirmed' && (j.confidence || 0) < 0.8"
        class="muted"
        style="color: #b7791f; font-size: 12px; margin-top: 6px"
      >
        ⚠️ 置信度不足（{{ ((j.confidence || 0) * 100).toFixed(0) }}% < 80%），请先「补充信息」补充细节后重新判定，才能确认入账。
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
