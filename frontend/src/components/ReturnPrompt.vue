<script setup>
import { ref,onMounted } from 'vue'
import { api } from '../api'
import { useWorkflowWrite } from '../composables/useWorkflowWrite'
const data=ref(null),error=ref(''),writes=useWorkflowWrite('return-prompt')
onMounted(async()=>{try{data.value=await api.flow('/phase')}catch{}})
async function skip(){try{await writes.send('/phase',{skip_return:true,expected_version:data.value.phase?.version||0},'PUT');data.value.return_prompt=false}catch(e){error.value=e.message}}
</script>
<template><aside v-if="data?.return_prompt" class="card"><p>欢迎回来。愿意更新一下最近的安排吗？可以跳过，旧基线与资金保留。</p><RouterLink class="btn" to="/phase">更新近况</RouterLink><button class="btn" :disabled="writes.busy.value" @click="skip">暂时跳过</button><p v-if="error" class="error">{{ error }}</p></aside></template>
