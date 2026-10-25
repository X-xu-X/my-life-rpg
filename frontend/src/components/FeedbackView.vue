<script setup>
import { ref,onMounted,computed } from 'vue'
import { api } from '../api'
import { account } from '../session'
import { useWorkflowWrite } from '../composables/useWorkflowWrite'
import PageHeader from './ui/PageHeader.vue'
const admin=computed(()=>account.value.role==='owner'),rows=ref([]),error=ref(''),form=ref({kind:'problem',title:'',content:''}),replies=ref({}),offset=ref(0),writes=useWorkflowWrite('feedback')
async function load(){try{rows.value=(await api.flow((admin.value?'/admin':'')+'/feedback?offset='+offset.value)).items}catch(e){error.value=e.message}}
async function submit(){try{await writes.send('/feedback',form.value);form.value={kind:'problem',title:'',content:''};await load()}catch(e){error.value=e.message}}
async function reply(row){try{await writes.send((admin.value?'/admin':'')+'/feedback/'+row.id+'/reply',{content:replies.value[row.id],state:admin.value?'answered':'open',expected_version:row.version});delete replies.value[row.id];await load()}catch(e){error.value=e.message}}
onMounted(load)
</script>
<template><div class="reading-page"><PageHeader :title="admin?'私密反馈管理':'意见与问题'" description="仅提交者与授权管理员可见，站内回复，不公开发布。"/><p v-if="error" class="error">{{ error }}</p><form v-if="!admin" class="card" @submit.prevent="submit"><label>类型<select v-model="form.kind"><option value="problem">问题</option><option value="suggestion">建议</option><option value="question">咨询</option></select></label><label>标题<input v-model="form.title" maxlength="120" required/></label><label>内容<textarea v-model="form.content" maxlength="6000" required/></label><button class="btn" :disabled="writes.busy.value">提交私密反馈</button></form><details v-for="row in rows" :key="row.id" class="card"><summary>{{ row.title }}</summary><p class="muted">{{ row.state }} · {{ row.created_at }}</p><p class="original-text">{{ row.content }}</p><div v-for="reply in row.replies" :key="reply.id"><p>{{ reply.actor_id===row.user_id?'提交者':'管理员' }} · {{ reply.created_at }}</p><p class="original-text">{{ reply.content }}</p></div><label>站内回复<textarea v-model="replies[row.id]" maxlength="6000"/></label><button class="btn" :disabled="writes.busy.value||!replies[row.id]?.trim()" @click="reply(row)">保存回复</button></details><button class="btn" v-if="offset" @click="offset=Math.max(0,offset-30);load()">上一页</button><button class="btn" v-if="rows.length===30" @click="offset+=30;load()">下一页</button></div></template>
