<script setup>
import { ref } from 'vue'
import { api } from '../api'
import { useWorkflowWrite } from '../composables/useWorkflowWrite'
const props=defineProps({event:Object}),emit=defineEmits(['changed'])
const acknowledge=ref(false),error=ref(''),writes=useWorkflowWrite('permission:'+props.event.id)
async function change(){try{await writes.send('/events/'+props.event.id+'/ai-permission',{permission:props.event.ai_permission==='allowed'?'private':'allowed',acknowledge:acknowledge.value,content_version:props.event.content_version,expected_version:props.event.ai_permission_version},'PUT');acknowledge.value=false;emit('changed')}catch(e){error.value=e.message}}
</script>
<template><details class="card record-permission"><summary>{{ event.ai_permission==='allowed'?'本篇已允许用于 AI 分析':'只保存，不交给 AI' }}</summary><details><summary>{{ event.ai_permission==='allowed'?'改为只保存':'开启本篇分析' }}</summary><p class="muted">许可涵盖本篇原文及问答在之后主动分析、回顾等用途。关闭后停止新调用，已发送内容无法撤回；旧分析保留为本人历史。</p><label v-if="event.ai_permission!=='allowed'"><input type="checkbox" v-model="acknowledge"/>我同意将本篇用于分析</label><button class="btn" :disabled="writes.busy.value||(event.ai_permission!=='allowed'&&!acknowledge)" @click="change">{{ event.ai_permission==='allowed'?'关闭本篇 AI 许可':'确认开启本篇 AI 许可' }}</button></details><p v-if="error" class="error">{{ error }}</p></details></template>
