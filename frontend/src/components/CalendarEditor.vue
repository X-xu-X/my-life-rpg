<script setup>
import { ref,onMounted } from 'vue'
import { api } from '../api'
import { useWorkflowWrite } from '../composables/useWorkflowWrite'
const year=ref(2026),data=ref(null),source=ref(''),json=ref(''),reason=ref(''),error=ref(''),notice=ref(''),writes=useWorkflowWrite('calendar')
async function load(){try{data.value=await api.flow('/calendar?year='+year.value);source.value=data.value.source_url||'';json.value=JSON.stringify(data.value.data,null,2)}catch(e){error.value=e.message}}
async function save(){try{await writes.send('/admin/calendars/'+year.value,{expected_version:data.value.persisted?data.value.version:0,source_url:source.value,data:JSON.parse(json.value),reason:reason.value});notice.value='年度日历已校验并保存，礼金资格没有增加。';error.value='';await load()}catch(e){error.value=e.message}}
onMounted(load)
</script>
<template><details class="card"><summary>官方年度日历与调休维护</summary><p>导入只更新展示数据；已配置礼金资格由下方独立管理，不把整段假期当作礼金日。</p><p v-if="notice" role="status">{{ notice }}</p><p v-if="error" class="error">{{ error }}</p><div class="form-grid"><label>年份<input type="number" min="1900" max="2200" v-model.number="year"/></label><button class="btn" :disabled="writes.busy.value" @click="load">读取年度资料</button></div><p>{{ data?.status==='missing'?'尚无已核对年度数据':data?.persisted?'已持久保存':'程序随附已核对资料' }}</p><label>官方政府HTTPS来源<input v-model="source" maxlength="1000"/></label><label>年度数据（节日、假期、调休工作日分别维护）<textarea v-model="json" rows="8"/></label><label>核对与操作原因<input v-model="reason" maxlength="2000"/></label><button class="btn" :disabled="writes.busy.value||!reason.trim()" @click="save">校验并保存年度日历</button></details></template>
