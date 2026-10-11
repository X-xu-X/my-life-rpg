<script setup>
import { ref, onMounted } from 'vue'
import PageHeader from './ui/PageHeader.vue'
import { api } from '../api'
import { displayTime } from '../session'
const items=ref([]),report=ref(null),error=ref(''),busy=ref(false),loading=ref(false),loaded=ref(false)
async function load(){loading.value=true;error.value='';try{items.value=(await api.listReports()).items;loaded.value=true}catch(e){error.value=e.message}finally{loading.value=false}}
async function open(id){busy.value=true;try{report.value=await api.getSavedReport(id)}catch(e){error.value=e.message}finally{busy.value=false}}
async function generate(period){if(busy.value)return;busy.value=true;error.value='';try{const result=await api.getReport(period);await load();await open(result.id)}catch(e){error.value=e.message}finally{busy.value=false}}
onMounted(load)
</script>
<template>
  <div class="reading-page"><RouterLink class="btn" to="/growth">← 成长</RouterLink><PageHeader title="历史报告" description="每次生成独立保存。阅读历史不调用模型；来源保留生成时的版本。" />
  <div class="action-group"><button class="btn" :disabled="busy" @click="generate('week')">生成周报（可能计费）</button><button class="btn" :disabled="busy" @click="generate('month')">生成月报（可能计费）</button></div>
  <p v-if="loading" role="status">正在读取历史报告…</p><div v-if="error" class="read-error" role="alert"><p>{{ error }}{{ loaded?' · 保留上次读取内容。':'' }}</p><button class="btn" :disabled="loading" @click="load">重新读取</button></div><p v-if="loaded && !loading && !error && !items.length" class="empty-note">还没有保存的历史报告。</p>
  <button v-for="item in items" :key="item.id" class="btn" :disabled="busy" @click="open(item.id)">{{ item.period==='week'?'周报':'月报' }} · {{ displayTime(item.created_at) }} · #{{ item.id }}</button>
  <article v-if="report" class="card"><h2>{{ report.start }} — {{ report.end }}</h2><p>{{ report.timezone }} · {{ displayTime(report.created_at) }}</p><div class="original-text">{{ typeof report.report==='string'?report.report:JSON.stringify(report.report,null,2) }}</div><h3>引用的原记录</h3><ul><li v-for="source in report.sources" :key="source.id"><RouterLink v-if="source.state!=='unavailable'" :to="'/events/'+source.id">记录 #{{ source.id }}</RouterLink><span v-else>记录 #{{ source.id }}</span> · 来源版本 {{ source.version }} · {{ {original:'原版本可读',edited:'已编辑，当前内容与报告来源不同',deleted:'已撤销，保留审计',unavailable:'来源不可用'}[source.state] }}</li></ul></article>
</div></template>
