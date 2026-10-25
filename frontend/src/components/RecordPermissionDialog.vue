<script setup>
import { ref } from 'vue'
import ConfirmDialog from './ui/ConfirmDialog.vue'
import { useWorkflowWrite } from '../composables/useWorkflowWrite'
const props=defineProps({event:Object,open:Boolean}),emit=defineEmits(['changed','cancel'])
const acknowledge=ref(false),error=ref(''),writes=useWorkflowWrite('permission:'+props.event.id)
async function change(){if(props.event.ai_permission!=='allowed'&&!acknowledge.value){error.value='请先勾选同意将本篇用于分析。';return}try{await writes.send('/events/'+props.event.id+'/ai-permission',{permission:props.event.ai_permission==='allowed'?'private':'allowed',acknowledge:acknowledge.value,content_version:props.event.content_version,expected_version:props.event.ai_permission_version},'PUT');acknowledge.value=false;emit('changed')}catch(e){error.value=e.message}}
</script>
<template><ConfirmDialog :open="open" title="这条记录的 AI 权限" :confirm-label="event.ai_permission==='allowed'?'改为只保存':'开启本篇分析'" :busy="writes.busy.value" @cancel="emit('cancel')" @confirm="change"><p>{{ event.ai_permission==='allowed'?'本篇已允许用于 AI 分析。':'本篇目前只保存，不交给 AI。' }}</p><p class="entry-status-note">许可涵盖本篇原文及问答在之后主动分析、回顾等用途。关闭后停止新调用，已经发送的内容无法撤回；旧分析保留为本人历史。</p><label v-if="event.ai_permission!=='allowed'"><input type="checkbox" v-model="acknowledge"/>我同意将本篇用于分析</label><p v-if="error" class="error">{{ error }}</p></ConfirmDialog></template>
