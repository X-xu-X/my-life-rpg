<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'

const records = ref([])
const error = ref('')

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

onMounted(load)
</script>

<template>
  <div class="card">
    <h2>纯享手账</h2>
    <p class="muted">这里是没有 AI 分析、没有加点的纯粹记录空间，随手记下生活的美好瞬间。</p>

    <p v-if="error" class="muted" style="color: #d33">{{ error }}</p>
    <p v-if="records.length === 0 && !error" class="muted">还没有纯享记录。去「记录事件」勾选「纯享记录」记一条吧。</p>

    <div v-for="r in records" :key="r.id" class="judgment-item">
      <div class="row" style="align-items: center; margin-bottom: 6px">
        <b>{{ r.title || '纯享记录' }}</b>
        <span class="muted" style="font-size: 12px">{{ new Date(r.created_at).toLocaleString('zh-CN') }}</span>
      </div>
      <div v-if="r.content" style="white-space: pre-wrap; margin-bottom: 6px">{{ r.content }}</div>
      <button class="btn small danger" @click="remove(r.id)">删除</button>
    </div>
  </div>
</template>
