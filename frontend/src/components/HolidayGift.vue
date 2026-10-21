<script setup>
import { ref,onMounted } from 'vue'
import { api } from '../api'
import { useWorkflowWrite } from '../composables/useWorkflowWrite'
const data=ref(null),error=ref(''),writes=useWorkflowWrite('holiday-gift')
async function load(){try{data.value=await api.flow('/phase')}catch{}}
async function claim(){try{await writes.send('/holidays/claim',{expected_version:0});await load()}catch(e){error.value=e.message}}
onMounted(load)
</script>
<template><section v-if="data?.holidays?.length" class="card"><h2>今天的节日</h2><p v-for="h in data.holidays" :key="h.id">{{ h.name }}</p><p v-if="error" class="error">{{ error }}</p><button class="btn" :disabled="writes.busy.value||data.holiday_claimed" @click="claim">{{ data.holiday_claimed?'今日礼金已领取':'领取已配置节日礼金10币' }}</button></section></template>
