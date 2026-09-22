<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'

const goals = ref([])
const form = ref({ description: '', metric: '', deadline: '', related_attribute: '' })
const busy = ref(false)
const error = ref('')

const STATUS_LABEL = { active: '进行中', achieved: '已达成', failed: '未达成', cancelled: '已取消' }

// C3（v1.7）：目标进度展示。数据来自 GET /api/goals 的 progress 字段。
// 老目标没有关联打卡项目 → progress 为空数组，此时整块进度不渲染（不显示 0%）。
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

async function load() {
  try {
    goals.value = await api.listGoals()
  } catch (e) {
    error.value = e.message
  }
}

async function create() {
  if (!form.value.metric.trim()) return alert('请填写量化指标')
  busy.value = true
  error.value = ''
  try {
    await api.createGoal({
      description: form.value.description,
      metric: form.value.metric,
      deadline: form.value.deadline ? new Date(form.value.deadline).toISOString() : null,
      related_attribute: form.value.related_attribute,
    })
    form.value = { description: '', metric: '', deadline: '', related_attribute: '' }
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function setStatus(id, action) {
  busy.value = true
  error.value = ''
  try {
    if (action === 'achieve') {
      const res = await api.achieveGoal(id)
      const applied = res.applied || []
      if (applied.length) {
        const msg = applied.map((a) => `${a.name} ${a.delta >= 0 ? '+' : ''}${a.delta}`).join('、')
        alert(`目标达成，奖励已入账：${msg}`)
      } else {
        alert('目标已标记达成')
      }
    } else if (action === 'fail') {
      const res = await api.failGoal(id)
      const applied = res.applied || []
      if (applied.length) {
        const msg = applied.map((a) => `${a.name} ${a.delta >= 0 ? '+' : ''}${a.delta}`).join('、')
        alert(`目标未达成，扣分已入账：${msg}`)
      } else {
        alert('目标已标记未达成')
      }
    } else if (action === 'cancel') {
      await api.cancelGoal(id)
    }
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="card">
      <h2>目标系统</h2>
      <div class="row">
        <div class="field">
          <label>目标描述</label>
          <input v-model="form.description" placeholder="例如：养成跑步习惯" />
        </div>
        <div class="field">
          <label>量化指标 *</label>
          <input v-model="form.metric" placeholder="例如：本月跑步累计 50km" />
        </div>
      </div>
      <div class="row">
        <div class="field">
          <label>期限</label>
          <input type="date" v-model="form.deadline" />
        </div>
        <div class="field">
          <label>关联属性</label>
          <input v-model="form.related_attribute" placeholder="例如：体能" />
        </div>
      </div>
      <button class="btn primary" :disabled="busy" @click="create">创建目标</button>
      <p class="muted" style="margin-top: 8px">达成奖励规划力 +2 及关联属性，未达成扣规划力 -1，修改/取消均记审计。</p>
    </div>

    <div class="card">
      <h3>目标列表</h3>
      <p v-if="goals.length === 0" class="muted">暂无目标。</p>
      <div v-for="g in goals" :key="g.id" class="judgment-item">
        <div class="row" style="align-items: center; margin-bottom: 6px">
          <b>{{ g.description || g.metric }}</b>
          <span class="tag">{{ STATUS_LABEL[g.status] || g.status }}</span>
        </div>
        <div class="muted">指标：{{ g.metric }}</div>
        <div v-if="g.deadline" class="muted">期限：{{ new Date(g.deadline).toLocaleDateString('zh-CN') }}</div>
        <div v-if="g.audit && g.audit.length" class="muted" style="font-size: 12px; margin-top: 4px">
          最近操作：{{ g.audit[g.audit.length - 1].detail }}
        </div>
        <!-- C3（v1.7）：关联打卡项目的目标展示进度；无关联项目的老目标不显示此块 -->
        <div v-if="g.progress && g.progress.length" class="goal-progress">
          <div v-for="p in g.progress" :key="p.item_id" class="goal-progress-row">
            <div class="goal-progress-head">
              <span class="goal-progress-name">{{ p.name }}</span>
              <span class="muted">{{ progressText(p) }}</span>
            </div>
            <div v-if="p.target" class="progress-track">
              <div class="progress-fill" :style="{ width: progressPercent(p) + '%' }"></div>
            </div>
          </div>
        </div>
        <div v-if="g.status === 'active'" class="row" style="margin-top: 8px">
          <button class="btn small primary" @click="setStatus(g.id, 'achieve')">达成</button>
          <button class="btn small" @click="setStatus(g.id, 'fail')">未达成</button>
          <button class="btn small danger" @click="setStatus(g.id, 'cancel')">取消</button>
        </div>
      </div>
    </div>
  </div>
</template>
