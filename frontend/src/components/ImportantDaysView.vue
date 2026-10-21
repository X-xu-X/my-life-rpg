<script setup>
import { ref,onMounted } from 'vue'
import { api } from '../api'
import { useWorkflowWrite } from '../composables/useWorkflowWrite'
import PageHeader from './ui/PageHeader.vue'
import ConfirmDialog from './ui/ConfirmDialog.vue'
const rows=ref([]),open=ref(false),editing=ref(null),error=ref(''),writes=useWorkflowWrite('important-days'),form=ref({})
const fresh=()=>({name:'',month:1,day:1,annual:true,year:null,remind_days:3,enabled:true})
async function load(){try{rows.value=(await api.flow('/important-days')).items}catch(e){error.value=e.message}}
function edit(row=null){editing.value=row;form.value=row?{...row}:fresh();open.value=true}
async function save(){try{const {name,month,day,annual,year,remind_days,enabled}=form.value;await writes.send('/important-days'+(editing.value?'/'+editing.value.id:''),{expected_version:editing.value?.version||0,name,month,day,annual,year:annual?null:year,remind_days,enabled},editing.value?'PUT':'POST');open.value=false;error.value='';await load()}catch(e){error.value=e.message}}
onMounted(load)
</script>
<template><div class="reading-page"><PageHeader title="重要日子" description="在日常里，给值得记住的日子留一个位置。"><template #actions><button class="btn primary" @click="edit()">添加日子</button></template></PageHeader><p v-if="error" class="error" role="alert">{{ error }}</p><section class="card"><p class="muted">支持公历；年度生日可不保存出生年。2月29日只在有该日期的年份提醒，重要日子不另发金币。</p><p v-if="!rows.length">还没有重要日子。</p><article v-for="r in rows" :key="r.id" class="project-row"><h3>{{ r.name }}</h3><p>{{ r.annual?'每年':r.year+'年' }} {{ r.month }}月{{ r.day }}日 · 提前 {{ r.remind_days }} 天 · {{ r.enabled?'提醒已开启':'已关闭' }}</p><button class="text-button" @click="edit(r)">编辑 / 关闭</button></article></section><ConfirmDialog :open="open" :title="editing?'编辑重要日子':'添加重要日子'" confirm-label="保存日子" :busy="writes.busy.value" @cancel="open=false" @confirm="save"><p v-if="error" class="error">{{ error }}</p><label>名称<input v-model="form.name" maxlength="120"/></label><label><input type="checkbox" v-model="form.annual"/>每年重复（不保存出生年）</label><div class="form-grid"><label v-if="!form.annual">年份<input type="number" min="1900" max="2200" v-model.number="form.year"/></label><label>月<input type="number" min="1" max="12" v-model.number="form.month"/></label><label>日<input type="number" min="1" max="31" v-model.number="form.day"/></label><label>提前几天提醒<input type="number" min="0" max="30" v-model.number="form.remind_days"/></label></div><label><input type="checkbox" v-model="form.enabled"/>开启提醒</label></ConfirmDialog></div></template>
