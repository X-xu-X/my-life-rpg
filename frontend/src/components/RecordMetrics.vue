<script setup>
import { ref,onMounted } from 'vue'
import { api } from '../api'
const data=ref(null),error=ref('')
const labels={event_saved_days:'事件 · 首次保存日',diary_saved_days:'日记 · 首次保存日',event_content_days:'事件 · 内容覆盖日',diary_content_days:'日记 · 内容覆盖日'}
onMounted(async()=>{try{data.value=await api.flow('/record-metrics')}catch(e){error.value=e.message}})
</script>
<template><section class="card"><h2>记录的日子</h2><p class="muted">坚持按首次保存日计算；今天还没记录时，保留截至昨天的连续天数。补记另计内容覆盖，不补过去的坚持。</p><p v-if="error" class="error">{{ error }}</p><div v-if="data" class="form-grid"><article v-for="(label,key) in labels" :key="key"><h3>{{ label }}</h3><p>累计 {{ data.metrics[key]?.count||0 }} 天 · 当前连续 {{ data.metrics[key]?.current_contiguous_days||0 }} 天 · 最长连续 {{ data.metrics[key]?.longest_contiguous_days||0 }} 天</p></article></div></section></template>
