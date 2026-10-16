<script setup>
import { ref,onMounted } from 'vue'
import { api } from '../api'
import { localDate } from '../session'
import { useWorkflowWrite } from '../composables/useWorkflowWrite'
const day=localDate(),value=ref(null),error=ref(''),writes=useWorkflowWrite('checklist:'+day)
const labels=['作息','饮食','活动','与人联系']
async function load(){try{value.value=await api.flow('/life-checklists/'+day)}catch(e){error.value=e.message}}
async function save(){try{value.value=await writes.send('/life-checklists/'+day,{expected_version:value.value.version,...value.value.payload},'PUT');error.value=''}catch(e){error.value=e.message}}
onMounted(load)
</script>
<template><details class="card"><summary>可选生活清单</summary><p class="muted">可以关闭或跳过；清单状态不产生记录、日数或奖励。</p><p v-if="error" class="error">{{ error }}</p><template v-if="value"><label><input type="checkbox" v-model="value.payload.enabled"/>开启今天的清单</label><div v-if="value.payload.enabled"><label v-for="name in labels" :key="name">{{ name }}<select v-model="value.payload.entries[name]"><option value="not_recorded">待记录</option><option value="skipped">跳过</option><option value="recorded">已记录（另存原文）</option></select></label><RouterLink to="/">记一件事</RouterLink></div><button class="btn" :disabled="writes.busy.value" @click="save">保存清单状态</button></template></details></template>
