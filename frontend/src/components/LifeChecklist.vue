<script setup>
import { ref,onMounted } from 'vue'
import { api } from '../api'
import { localDate,storageKey } from '../session'
import { useWorkflowWrite } from '../composables/useWorkflowWrite'
const emit=defineEmits(['saved'])
const day=localDate(),value=ref(null),error=ref(''),drafts=ref({}),writes=useWorkflowWrite('care:'+day)
const key=storageKey('care-drafts:'+day)
try{drafts.value=JSON.parse(localStorage.getItem(key)||'{}')}catch{}
async function load(){try{value.value=await api.flow('/care?day='+day);for(const row of value.value.today)if(!drafts.value[row.item.id])drafts.value[row.item.id]={content:'',ai_permission:'private'}}catch(e){error.value=e.message}}
function cache(){localStorage.setItem(key,JSON.stringify(drafts.value))}
async function save(row,skip=false){try{const result=await writes.send(`/care/items/${row.item.id}/entries/${day}`,{expected_version:row.entry?.version||0,item_version:row.item.version,state:skip?'skipped':'recorded',...drafts.value[row.item.id]},'PUT');if(!skip)emit('saved');if(!skip&&result.event&&drafts.value[row.item.id].ai_permission==='allowed'){try{await api.submitJob(result.event.id,{request_key:crypto.randomUUID(),event_version:result.event.content_version,operation:'facts'})}catch(e){error.value='原文已保存；'+e.message}}delete drafts.value[row.item.id];cache();await load()}catch(e){error.value=e.message}}
onMounted(load)
</script>
<template><section v-if="value?.today?.length" class="card"><h2>照顾自己</h2><RouterLink to="/care">管理项目 →</RouterLink><p v-if="error" class="error">{{ error }}</p><article v-for="row in value.today" :key="row.item.id"><h3>{{ row.item.name }}</h3><p v-if="row.entry">{{ row.entry.state==='skipped'?'今天已跳过':'已保存记录' }} · v{{ row.entry.version }}</p><template v-if="drafts[row.item.id]"><label>简单记一句<textarea v-model="drafts[row.item.id].content" @input="cache" maxlength="20000" rows="2"/></label><label>保存方式<select v-model="drafts[row.item.id].ai_permission" @change="cache"><option value="private">只保存，不交给 AI</option><option value="allowed">保存并分析</option></select></label><button class="btn" :disabled="writes.busy.value" @click="save(row)">保存这一项</button><button class="btn" :disabled="writes.busy.value" @click="save(row,true)">今天跳过</button></template><RouterLink v-if="row.entry?.event_id" :to="'/events/'+row.entry.event_id">查看原文与建议 →</RouterLink></article><p class="muted">不记录不等于没做。跳过不奖罚；必要休息无需兑换。</p></section></template>
