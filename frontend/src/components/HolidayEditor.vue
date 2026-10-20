<script setup>
import { ref,onMounted } from 'vue'
import { api } from '../api'
import { useWorkflowWrite } from '../composables/useWorkflowWrite'
const rows=ref([]),form=ref({name:'',region:'',local_date:'',enabled:true,reason:''}),editing=ref(null),error=ref(''),writes=useWorkflowWrite('holiday-admin')
async function load(){try{rows.value=(await api.flow('/admin/holidays')).items}catch(e){error.value=e.message}}
async function save(){try{await writes.send('/admin/holidays'+(editing.value?'/'+editing.value.id:''),{...form.value,expected_version:editing.value?.version||0},editing.value?'PUT':'POST');editing.value=null;await load()}catch(e){error.value=e.message}}
onMounted(load)
</script>
<template><section class="card"><h2>地区节日日历</h2><p class="muted">仅配置且匹配本人所选地区的当天生效；不自动追发，不推断现实节日日历。</p><p v-if="error" class="error">{{ error }}</p><form @submit.prevent="save"><label>名称<input v-model="form.name" maxlength="120" required/></label><label>地区标识<input v-model="form.region" maxlength="60" required/></label><label>日期<input type="date" v-model="form.local_date" required/></label><label><input type="checkbox" v-model="form.enabled"/>启用</label><label>操作原因<input v-model="form.reason" maxlength="2000" required/></label><button class="btn" :disabled="writes.busy.value">保存日历配置</button></form><article v-for="row in rows" :key="row.id"><p>{{ row.local_date }} · {{ row.region }} · {{ row.name }} · {{ row.enabled?'启用':'停用' }}</p><button class="btn" @click="editing=row;form={name:row.name,region:row.region,local_date:row.local_date,enabled:row.enabled,reason:''}">编辑 / 停用</button></article></section></template>
