<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
import { useRoute } from 'vue-router'
import { displayTime, displayEventTime } from '../session'
import { strictDate } from '../dateInput'
import PageHeader from './ui/PageHeader.vue'
import RecordPreview from './ui/RecordPreview.vue'
import TipLine from './ui/TipLine.vue'
const rows=ref([]),query=ref(''),filter=ref(''),dateFilter=ref(useRoute().query.date||''),error=ref('')
const loading=ref(false),loaded=ref(false),exhausted=ref(false)
let generation=0,failedMore=false
async function load(more=false) {
  const current=++generation;loading.value=true;error.value='';failedMore=more
  if(dateFilter.value && !strictDate(dateFilter.value)){
    error.value='请填写有效的完整日期，例如 2026-10-22；留空可查看全部日期。'
    loading.value=false
    return
  }
  try {
    const data=await api.records({q:query.value,...(['pure','ordinary'].includes(filter.value)?{pure:filter.value==='pure'}:{kind:filter.value}),date:dateFilter.value,...(more&&rows.value.length?{cursor:rows.value.at(-1).id}:{})})
    if(current===generation){rows.value=more?[...rows.value,...data]:data;loaded.value=true;exhausted.value=more&&data.length===0}
  }catch(e){if(current===generation)error.value=e.message}
  finally{if(current===generation)loading.value=false}
}
function clearSearch(){query.value='';filter.value='';dateFilter.value='';load()}
onMounted(()=>load())
</script>
<template><div class="reading-page">
  <PageHeader title="手账" description="原文一直在这里。是否分析，都可以回看。" />
  <form class="record-search" @submit.prevent="load()"><label>搜索记录<input v-model="query" type="search" placeholder="一句话、一件事…" /></label><button class="btn" :disabled="loading">搜索</button><label class="search-filter">筛选<select v-model="filter" @change="load()"><option value="">全部</option><option value="event">事件</option><option value="diary">晚间日记</option><option value="legacy">旧记录 · 未分类</option><option value="pure">历史纯享记录</option><option value="ordinary">其他记录</option></select></label><label>内容日期<input type="text" v-model="dateFilter" maxlength="10" placeholder="全部日期" aria-label="内容日期" title="填写完整日期，例如 2026-10-22；留空查看全部日期" @change="load()"/></label><button v-if="dateFilter" type="button" class="btn" @click="dateFilter='';load()">清除日期</button></form>
  <TipLine id="journal.pure-flag" class="muted">历史纯享标记与当前是否分析是两种设置。</TipLine>
  <p v-if="loading" role="status">正在读取记录…</p>
  <div v-if="error" class="read-error" role="alert"><p>{{ error }}{{ loaded?' · 显示上次读取的记录，本次未刷新成功。':'' }}</p><button class="btn" :disabled="loading" @click="load(failedMore)">重新读取</button></div>
  <p v-if="loaded && !rows.length && !loading && !error" class="empty-note">{{ query || filter || dateFilter?'没有找到匹配的记录。':'这里还没有记录。从今天的一句话开始。' }}<button v-if="query || filter || dateFilter" type="button" class="btn" @click="clearSearch">清除搜索与筛选</button></p>
  <RecordPreview v-for="row in rows" :key="row.id" :to="row.record_kind==='diary'?'/diary?date='+row.occurred_on:'/events/'+row.id" :title="row.title" :summary="row.content"><time>{{ displayEventTime(row) }} · {{ row.record_kind==='diary'?'晚间日记':row.record_kind==='event'?'事件':'旧记录 · 类型未分类' }}</time><span>已保存{{ row.analysis_intent==='never'?' · 不分析':'' }}</span></RecordPreview>
  <button v-if="rows.length && !exhausted" class="btn" :disabled="loading" @click="load(true)">{{ loading?'读取中…':'继续回看' }}</button><p v-if="exhausted" class="muted">已经回看到这里。</p>
</div></template>
