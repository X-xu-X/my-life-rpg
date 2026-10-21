<script setup>
import HintCard from './HintCard.vue'
import DailyPrompts from './DailyPrompts.vue'
import ProjectManager from './ProjectManager.vue'
import HolidayGift from './HolidayGift.vue'
import TrialRules from './TrialRules.vue'
import { ref, onMounted, onUnmounted } from 'vue'
import { api } from '../api'
import { localDate, displayTime, displayEventTime } from '../session'
import PlanAgenda from './PlanAgenda.vue'
import LifeChecklist from './LifeChecklist.vue'
import RecordComposer from './RecordComposer.vue'
import PageHeader from './ui/PageHeader.vue'
import RecordPreview from './ui/RecordPreview.vue'
const savedVersion=ref(0),wallet=ref(null)
async function onSaved(){savedVersion.value++;await load()}
const rows=ref([]),pending=ref(0),error=ref(''),loading=ref(false),loaded=ref(false)
const day=localDate()
let alive=true,generation=0
async function load(){
  const current=++generation;loading.value=true;error.value=''
  try{const [events,todo,money]=await Promise.all([api.records({date:day}),api.pending(),api.getCoins()]);if(alive&&current===generation){rows.value=events;pending.value=todo.items.length;wallet.value=money;loaded.value=true}}
  catch(e){if(alive&&current===generation)error.value=e.message}
  finally{if(alive&&current===generation)loading.value=false}
}
onMounted(load)
onUnmounted(()=>{alive=false;generation++})
</script>
<template><div class="reading-page wide-page today-page">
  <PageHeader title="今天" :eyebrow="day" description="留下一件小事，也算今天的一页。" />
  <HintCard id="record-help"><p>先留下一件事。只保存无需模型；分析建议经过核对后才结算，首记资格独立保留。</p></HintCard><div class="daily-columns"><div class="page-stack"><RecordComposer @saved="onSaved"/><ProjectManager today-only category="plan" @saved="onSaved"/><section class="card diary-entry"><h2>给今天留一页</h2><p>原文、AI问题与自己的回答分开保存。</p><RouterLink class="btn" to="/diary">写晚间日记 →</RouterLink></section></div><aside class="page-stack"><section class="card wallet-summary"><span class="eyebrow">自己的小钱包</span><div class="wallet-number">{{ wallet?.balance??'—' }} <small>币</small></div><RouterLink to="/rewards">奖励与休息 →</RouterLink></section><TrialRules compact :key="savedVersion" @changed="load"/><ProjectManager today-only category="care" @saved="onSaved"/><DailyPrompts/><HolidayGift/></aside></div>
  <div class="today-links"><RouterLink to="/pending">待处理 <b v-if="loaded">{{ pending }}</b><span>{{ loaded?'去看看 →':loading?'读取中…':'打开查看 →' }}</span></RouterLink><RouterLink to="/diary">晚间日记<span>写原文与回顾 →</span></RouterLink></div>
  <div class="section-heading"><h2>今日片段</h2><div class="action-group"><button class="btn" :disabled="loading" @click="load">重新读取</button><RouterLink to="/checkin">项目与目标</RouterLink></div></div>
  <p v-if="loading" role="status">正在读取今日记录…</p>
  <div v-if="error" class="read-error" role="alert"><p>{{ error }}{{ loaded?' · 显示上次读取的数据，本次未刷新成功。':'' }} 仍可记录原文。</p><button class="btn" :disabled="loading" @click="load">重新读取</button></div>
  <p v-if="loaded && !rows.length && !loading && !error" class="empty-note">今天还没有记录，先留下一句话。</p>
  <RecordPreview v-for="row in rows" :key="row.id" :title="row.title" :summary="row.content.slice(0,160)" :to="row.record_kind==='diary'?'/diary?date='+row.occurred_on:'/events/'+row.id"><time>{{ displayEventTime(row) }}</time><span>已保存{{ row.analysis_intent==='never'?' · 不分析':'' }}</span></RecordPreview>
</div></template>
