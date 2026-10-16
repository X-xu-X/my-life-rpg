<script setup>
import { ref,onMounted } from 'vue'
import { api } from '../api'
import { useWorkflowWrite } from '../composables/useWorkflowWrite'
const props=defineProps({event:Object}),target=ref(null),targetVersion=ref(null),reason=ref(''),rows=ref([]),error=ref(''),writes=useWorkflowWrite('fact:'+props.event.id)
async function load(){rows.value=(await api.flow('/fact-relations')).filter(r=>r.source_id===props.event.id||r.target_id===props.event.id)}
async function act(fn){if(writes.busy.value)return;try{await fn();await load();error.value=''}catch(e){error.value=e.message}}
onMounted(()=>load().catch(e=>{error.value=e.message}))
</script>
<template><details class="card"><summary>同事实关联 · 由你确认</summary><p class="muted">关联保留两份原文。同一事实只能入账一次；已有结算的新增成果差额暂未开启。</p><p v-if="error" class="error">{{ error }}</p><form @submit.prevent="act(()=>writes.send('/fact-relations',{source_id:event.id,source_version:event.content_version,target_id:target,target_version:targetVersion,reason}))"><label>本人目标事件 ID<input type="number" v-model.number="target" required/></label><label>目标内容版本<input type="number" v-model.number="targetVersion" required/></label><label>相似事实依据<input v-model="reason" maxlength="2000" required/></label><button class="btn" :disabled="writes.busy.value">保存候选</button></form><article v-for="row in rows" :key="row.id"><p>#{{ row.source_id }} → #{{ row.target_id }} · {{ row.state }} · {{ row.reason }}</p><div v-if="row.state==='candidate'" class="action-group"><button class="btn" :disabled="writes.busy.value" @click="act(()=>writes.send('/fact-relations/'+row.id+'/decision',{expected_version:row.version,accept:true}))">确认同一事实</button><button class="btn" :disabled="writes.busy.value" @click="act(()=>writes.send('/fact-relations/'+row.id+'/decision',{expected_version:row.version,accept:false}))">拒绝关联</button></div></article></details></template>
