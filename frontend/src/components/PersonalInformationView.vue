<script setup>
import { ref,onMounted } from 'vue'
import { api } from '../api'
import { useWorkflowWrite } from '../composables/useWorkflowWrite'
import PageHeader from './ui/PageHeader.vue'
const expanded=ref({}),entries=ref([]),version=ref(0),error=ref(''),notice=ref(''),writes=useWorkflowWrite('personal-information'),labels={judge:'事件分析',review:'辅助回顾',report:'成长报告',pricing:'奖励定价'}
onMounted(async()=>{try{const r=await api.flow('/personal-information');entries.value=r.data?.entries||[];version.value=r.data?.version||0}catch(e){error.value=e.message}})
async function save(){try{const r=await writes.send('/personal-information',{expected_version:version.value,entries:entries.value.map(({id,text,uses})=>({id,text,uses}))},'PUT');entries.value=r.entries;version.value=r.version;expanded.value={};notice.value='长期信息已保存，不改变属性或启动资金。';error.value=''}catch(e){error.value=e.message}}
function add(){const id=crypto.randomUUID();expanded.value[id]=true;entries.value.push({id,text:'',uses:[]})}
async function remove(id){entries.value=entries.value.filter(e=>e.id!==id);await save()}
</script>
<template><div class="reading-page"><PageHeader title="长期信息" description="描述愿意留下的自己，按用途选择是否交给 AI。"/><p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p><section class="card"><p>兴趣、生活阶段、习惯或自述性格都可以。自述 INFP 是背景，不是能力测量。</p><details v-for="entry in entries" :key="entry.id" class="project-row" :open="!!expanded[entry.id]" @toggle="expanded[entry.id]=$event.target.open"><summary>{{ entry.text?entry.text.slice(0,60):'新增长期信息' }}</summary><label>本人补充<textarea v-model="entry.text" maxlength="4000" rows="3"/></label><div class="action-group"><label v-for="(label,key) in labels" :key="key"><input type="checkbox" v-model="entry.uses" :value="key"/>{{ label }}</label></div><button class="text-button danger" :disabled="writes.busy.value" @click="remove(entry.id)">删除这条信息</button></details><div class="action-group"><button class="btn" :disabled="writes.busy.value||entries.length>=30" @click="add">补充一条</button><button class="btn primary" :disabled="writes.busy.value||entries.some(e=>!e.text.trim())" @click="save">保存长期信息</button></div></section><RouterLink class="btn" to="/onboarding">回看建档问卷 →</RouterLink></div></template>
