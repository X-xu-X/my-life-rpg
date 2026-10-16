<script setup>
import { ref,onMounted } from 'vue'
import { api } from '../api'
import { useWorkflowWrite } from '../composables/useWorkflowWrite'
const data=ref(null),mode=ref('personal'),ack=ref(false),error=ref(''),writes=useWorkflowWrite('ai-choice')
async function load(){data.value=await api.flow('/ai/preferences');mode.value=data.value.mode}
async function save(){try{data.value=await writes.send('/ai/preferences',{expected_version:data.value.version,mode:mode.value,acknowledge:ack.value,hosted_version:data.value.hosted.version},'PUT');await load();error.value=''}catch(e){error.value=e.message}}
onMounted(()=>load().catch(e=>{error.value=e.message}))
</script>
<template><section class="card" id="ai-choice"><h2>AI 使用方式</h2><p v-if="error" class="error" role="alert">{{ error }}</p><template v-if="data"><p>当前：{{ {personal:'自己的模型',hosted:'站点默认模型',off:'关闭 AI'}[data.mode] }}</p><label>主动选择<select v-model="mode"><option value="personal">自己的模型与额度</option><option value="hosted" :disabled="!data.hosted.available">站点默认 · {{ data.hosted.available?'已开通':'未开通' }}</option><option value="off">关闭 AI，仅记录</option></select></label><template v-if="mode==='hosted'"><p>{{ data.hosted.provider }} / {{ data.hosted.model }} · v{{ data.hosted.version }}</p><p class="muted">有个人及全站调用/Token/费用上限；配额失败会停止，不暗中切换付费模型。</p><label><input type="checkbox" v-model="ack"/>我同意主动分析时将相关原文与问答发送给此供应商</label></template><button class="btn" :disabled="writes.busy.value" @click="save">保存 AI 选择</button><p class="muted">选择不会触发历史分析。原文保存不依赖 AI；模型及费用未配置时站点默认保持未开通。</p></template></section></template>
