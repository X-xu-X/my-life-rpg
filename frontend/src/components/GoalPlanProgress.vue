<script setup>
import { ref } from 'vue'
import { api } from '../api'
const props=defineProps({goalId:Number}),data=ref(null),error=ref('')
async function load(){try{data.value=await api.flow('/goals/'+props.goalId+'/plan-progress')}catch(e){error.value=e.message}}
</script>
<template><details @toggle="e=>e.target.open&&load()"><summary>周期计划的实际进展</summary><p v-if="error" class="error">{{ error }}</p><p v-if="data">完成 {{ data.done }} 次 · 部分完成 {{ data.partial }} 次 · 未完成 {{ data.missed }} 次；不默认换算成百分比。</p><p v-for="row in data?.items" :key="row.id">{{ row.local_date }} · {{ row.schedule_snapshot.name }} · {{ {done:'完成',partial:'部分完成',missed:'未完成'}[row.outcome] }} · {{ row.facts.actual??'未量化' }} {{ row.facts.unit }}</p></details></template>
