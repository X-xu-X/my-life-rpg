<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'

const records = ref([])
const error = ref('')
const editTarget = ref(null)
const editText = ref('')
const searchText = ref('')

const filteredRecords = computed(() => {
  const kw = searchText.value.trim().toLowerCase()
  if (!kw) return records.value
  return records.value.filter((r) =>
    (r.content || '').toLowerCase().includes(kw) || (r.title || '').toLowerCase().includes(kw)
  )
})

async function load() {
  try {
    records.value = await api.listEvents(true)
  } catch (e) {
    error.value = e.message
  }
}

async function remove(id) {
  if (!window.confirm('删除这条纯享记录？')) return
  try {
    await api.deleteEvent(id)
    await load()
  } catch (e) {
    error.value = e.message
  }
}

function openEdit(r) {
  editTarget.value = r.id
  editText.value = r.content || r.title || ''
}

async function saveEdit() {
  try {
    await api.updateEvent(editTarget.value, {
      content: editText.value,
      title: editText.value.slice(0, 20) || '纯享记录',
    })
    editTarget.value = null
    await load()
  } catch (e) {
    error.value = e.message
  }
}

onMounted(load)
</script>

<template>
  <div class="card">
    <h2>纯享手账</h2>
    <p class="muted">这里是没有 AI 分析、没有加点的纯粹记录空间，随手记下生活的美好瞬间。</p>

    <p v-if="error" class="muted" style="color: #d33">{{ error }}</p>
    <p v-if="records.length === 0 && !error" class="muted">还没有纯享记录。去「记录事件」勾选「纯享记录」记一条吧。</p>

    <div class="field" v-if="records.length > 0">
      <input v-model="searchText" placeholder="🔍 搜索手账…" />
    </div>

    <div v-for="r in filteredRecords" :key="r.id" class="judgment-item">
      <div class="row" style="align-items: center; margin-bottom: 6px">
        <b>{{ r.title || '纯享记录' }}</b>
        <span class="muted" style="font-size: 12px">{{ new Date(r.created_at).toLocaleString('zh-CN') }}</span>
      </div>

      <!-- 编辑态 -->
      <div v-if="editTarget === r.id" class="field">
        <textarea v-model="editText" rows="3" placeholder="记录内容…"></textarea>
        <div class="row" style="margin-top: 8px">
          <button class="btn small primary" @click="saveEdit">保存</button>
          <button class="btn small" @click="editTarget = null">取消</button>
        </div>
      </div>
      <div v-else>
        <div v-if="r.content" style="white-space: pre-wrap; margin-bottom: 6px">{{ r.content }}</div>
        <button class="btn small" @click="openEdit(r)">编辑</button>
        <button class="btn small danger" @click="remove(r.id)">删除</button>
      </div>
    </div>
  </div>
</template>
