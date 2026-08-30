<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'

const goals = ref([])
const form = ref({ description: '', metric: '', deadline: '', related_attribute: '' })
const busy = ref(false)
const error = ref('')

const STATUS_LABEL = { active: '进行中', achieved: '已达成', failed: '未达成', cancelled: '已取消' }

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
  try {
    if (action === 'achieve') await api.achieveGoal(id)
    else if (action === 'fail') await api.failGoal(id)
    else if (action === 'cancel') await api.cancelGoal(id)
    await load()
  } catch (e) {
    error.value = e.message
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
      <p class="muted" style="margin-top: 8px">达成默认奖励规划力 +2，未达成扣规划力 -1（结算逻辑 M2 完善）。</p>
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
        <div v-if="g.status === 'active'" class="row" style="margin-top: 8px">
          <button class="btn small primary" @click="setStatus(g.id, 'achieve')">达成</button>
          <button class="btn small" @click="setStatus(g.id, 'fail')">未达成</button>
          <button class="btn small danger" @click="setStatus(g.id, 'cancel')">取消</button>
        </div>
      </div>
    </div>
  </div>
</template>
