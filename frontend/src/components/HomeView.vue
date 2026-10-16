<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { api } from '../api'
import { localDate, displayTime, displayEventTime } from '../session'
import RecordComposer from './RecordComposer.vue'
import PageHeader from './ui/PageHeader.vue'
import RecordPreview from './ui/RecordPreview.vue'
const rows=ref([]),pending=ref(0),error=ref(''),loading=ref(false),loaded=ref(false)
const day=localDate()
let alive=true,generation=0
async function load(){
  const current=++generation;loading.value=true;error.value=''
  try{const [events,todo]=await Promise.all([api.records({date:day}),api.pending()]);if(alive&&current===generation){rows.value=events;pending.value=todo.items.length;loaded.value=true}}
  catch(e){if(alive&&current===generation)error.value=e.message}
  finally{if(alive&&current===generation)loading.value=false}
}
onMounted(load)
onUnmounted(()=>{alive=false;generation++})
</script>
<template><div class="reading-page today-page">
  <PageHeader title="今天" :eyebrow="day" description="留下一件小事，也算今天的一页。" />
  <RecordComposer @saved="load" />
  <div class="today-links"><RouterLink to="/pending">待处理 <b v-if="loaded">{{ pending }}</b><span>{{ loaded?'去看看 →':loading?'读取中…':'打开查看 →' }}</span></RouterLink><RouterLink to="/review">睡前回顾<span>留一句 →</span></RouterLink></div>
  <div class="section-heading"><h2>今日片段</h2><div class="action-group"><button class="btn" :disabled="loading" @click="load">重新读取</button><RouterLink to="/checkin">项目与目标</RouterLink></div></div>
  <p v-if="loading" role="status">正在读取今日记录…</p>
  <div v-if="error" class="read-error" role="alert"><p>{{ error }}{{ loaded?' · 显示上次读取的数据，本次未刷新成功。':'' }} 仍可记录原文。</p><button class="btn" :disabled="loading" @click="load">重新读取</button></div>
  <p v-if="loaded && !rows.length && !loading && !error" class="empty-note">今天还没有记录，先留下一句话。</p>
  <RecordPreview v-for="row in rows" :key="row.id" :title="row.title" :summary="row.content.slice(0,160)" :to="'/events/'+row.id"><time>{{ displayEventTime(row) }}</time><span>已保存{{ row.analysis_intent==='never'?' · 不分析':'' }}</span></RecordPreview>
</div></template>
