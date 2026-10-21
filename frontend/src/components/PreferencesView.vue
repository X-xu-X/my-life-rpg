<script setup>
import { ref,onMounted } from 'vue'
import { api } from '../api'
import { useWorkflowWrite } from '../composables/useWorkflowWrite'
import PageHeader from './ui/PageHeader.vue'
const prefs=ref(null),error=ref(''),notice=ref(''),writes=useWorkflowWrite('experience-preferences'),labels={'record-help':'记录说明','plans-help':'计划说明','rewards-help':'奖励说明','growth-help':'成长说明','daily-reflection':'今天的自然回顾提示','questionnaire-help':'问卷说明'}
onMounted(async()=>{try{prefs.value=await api.flow('/experience-preferences')}catch(e){error.value=e.message}})
async function save(restore=false){try{if(restore)prefs.value.suppressed=[];prefs.value=await writes.send('/experience-preferences',{expected_version:prefs.value.version,suppressed:prefs.value.suppressed,return_disabled:prefs.value.return_disabled},'PUT');notice.value='显示与提示偏好已保存，其他设备同样遵守。';error.value=''}catch(e){error.value=e.message}}
</script>
<template><div class="reading-page"><PageHeader title="显示与提示" description="一般说明按登录会话出现，必要状态一直为你保留。"/><p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p><section v-if="prefs" class="card"><h2>不再自动提示</h2><label v-for="(label,key) in labels" :key="key"><input type="checkbox" v-model="prefs.suppressed" :value="key"/>{{ label }}</label><label><input type="checkbox" v-model="prefs.return_disabled"/>不再自动打开久别回归向导</label><div class="action-group"><button class="btn primary" :disabled="writes.busy.value" @click="save()">保存提示偏好</button><button class="btn" :disabled="writes.busy.value" @click="save(true)">恢复一般提示</button></div><p class="muted">关闭教程不隐藏保存、等待、错误、真实价格或兑换确认。</p></section></div></template>
