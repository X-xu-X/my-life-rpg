<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import PageHeader from './ui/PageHeader.vue'
import RecordPreview from './ui/RecordPreview.vue'
import { api } from '../api'
const items=ref([]),error=ref(''),loading=ref(false),loaded=ref(false)
let reading=false
let timer,alive=true
const labels={saved:'尚未分析',queued:'排队中',running:'分析中',needs_input:'待补充',ready:'待确认',failed:'分析失败',cancelled:'已取消，可再次发起',superseded:'内容有变化，请重新分析'}
const groups=computed(()=>[
  {title:'待补充',states:['needs_input']},{title:'待确认',states:['ready']},
  {title:'稍后分析',states:['saved','queued','running','failed','cancelled','superseded']}
].map(group=>({...group,items:items.value.filter(item=>group.states.includes(item.state))})).filter(group=>group.items.length))
async function load(){if(reading)return;reading=true;if(!loaded.value)loading.value=true;try{const data=await api.pending();if(alive){items.value=data.items;error.value='';loaded.value=true}}catch(e){if(alive)error.value=e.message}finally{reading=false;if(alive)loading.value=false}}
onMounted(()=>{load();timer=setInterval(load,5000)})
onUnmounted(()=>{alive=false;clearInterval(timer)})
</script>
<template><div class="reading-page"><RouterLink class="btn" to="/">← 今天</RouterLink><PageHeader title="待处理" description="问题和建议还在原记录里。延后处理不会自动确认或扣分。" /><p v-if="loading" role="status">正在读取待处理记录…</p><div v-if="error" class="read-error" role="alert"><p>{{ error }}{{ loaded?' · 显示上次读取的数据，本次未刷新成功。':'' }}</p><button class="btn" :disabled="loading" @click="load">重新读取</button></div><p v-if="loaded && !error && !loading && !items.length" class="empty-note">暂时没有待处理的记录。安心过今天。</p><section v-for="group in groups" :key="group.title"><h2>{{ group.title }} · {{ group.items.length }}</h2><RecordPreview v-for="item in group.items" :key="item.event_id" :to="'/events/'+item.event_id" :title="item.title" :summary="item.content.slice(0,160)"><span class="state-stamp" :class="'state-'+item.state">{{ labels[item.state] || item.state }}</span></RecordPreview></section></div></template>
