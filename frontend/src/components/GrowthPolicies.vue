<script setup>
import { ref,onMounted } from 'vue'
import { api } from '../api'
import { useWorkflowWrite } from '../composables/useWorkflowWrite'
const data=ref(null),candidates=ref(null),goals=ref([]),goalId=ref(null),error=ref(''),writes=useWorkflowWrite('growth-policies')
async function load(){try{const result=await Promise.all([api.flow('/mainlines'),Promise.resolve({items:[]}),api.listGoals()]);[data.value,candidates.value,goals.value]=result}catch(e){error.value=e.message}}
async function act(path,body,method='POST'){try{await writes.send(path,body,method);await load();error.value=''}catch(e){error.value=e.message}}
onMounted(async()=>{await act('/discoveries/refresh',{});await load()})
</script>
<template><div><p v-if="error" class="error">{{ error }}</p><section class="card"><h2>当前主线由你选择</h2><p class="muted">只影响已核对事实的金币倾斜，不放大属性。实际投入和档位由分析建议，确认前不入账。</p><label>本人进行中的目标<select v-model="goalId"><option :value="null">选择目标</option><option v-for="goal in goals.filter(g=>g.status==='active')" :key="goal.id" :value="goal.id">{{ goal.description }}</option></select></label><button class="btn" :disabled="writes.busy.value||!goalId" @click="act('/mainlines',{goal_id:goalId,active:true})">选择为当前主线</button><article v-for="row in data?.items" :key="row.id"><p>{{ goals.find(g=>g.id===row.goal_id)?.description||'历史目标' }} · {{ row.active?'当前主线':'历史关联' }}</p><button v-if="row.active" class="btn" :disabled="writes.busy.value" @click="act('/mainlines/'+row.id,{goal_id:row.goal_id,active:false,expected_version:row.version},'PUT')">暂不设主线</button></article></section></div></template>
