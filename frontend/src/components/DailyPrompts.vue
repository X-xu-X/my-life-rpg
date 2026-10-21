<script setup>
import { ref,onMounted } from 'vue'
import { api } from '../api'
import { useWorkflowWrite } from '../composables/useWorkflowWrite'
const data=ref(null),error=ref(''),writes=useWorkflowWrite('daily-reflection')
onMounted(async()=>{try{data.value=await api.flow('/daily-prompts')}catch{}})
async function snooze(){try{const pref=await api.flow('/experience-preferences');await writes.send('/daily-prompts/snooze',{expected_version:pref.version});data.value.reflection=null}catch(e){error.value=e.message}}
</script>
<template><section v-if="data&&(data.important_days.length||data.reflection||data.today_calendar.statutory.length||data.today_calendar.breaks.length||data.today_calendar.working_day||data.calendar.status==='missing')" class="card"><h2>留意今天</h2><p v-if="data.calendar.status==='missing'" class="muted">{{ data.calendar.message }}</p><p v-for="r in data.important_days" :key="r.source+':'+r.id">{{ r.days_left===0?'今天':r.days_left+'天后' }} · {{ r.name }}<RouterLink v-if="r.source==='goal'" to="/plans"> 查看目标 →</RouterLink></p><p v-for="r in data.today_calendar.statutory" :key="r.date">{{ r.name }} · 官方节日</p><p v-if="!data.today_calendar.statutory.length&&data.today_calendar.breaks.length">{{ data.today_calendar.breaks[0].name }}假期</p><p v-if="data.today_calendar.working_day">今天为官方调休工作日。</p><template v-if="data.reflection"><p>{{ data.reflection }}</p><div class="action-group"><RouterLink class="btn" to="/diary">写进今天的手账</RouterLink><button class="text-button" :disabled="writes.busy.value" @click="snooze">先跳过，一周内不再提示</button></div></template><p v-if="error" class="error">{{ error }}</p></section></template>
