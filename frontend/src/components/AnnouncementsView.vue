<script setup>
import { ref,onMounted } from 'vue'
import { api } from '../api'
import PageHeader from './ui/PageHeader.vue'
const rows=ref([]),error=ref(''),loaded=ref(false)
onMounted(async()=>{try{rows.value=(await api.flow('/announcements')).items;loaded.value=true}catch(e){error.value=e.message}})
</script>
<template><div class="reading-page"><PageHeader title="站内公告" description="只显示已发布的公告。"/><p v-if="error" class="error">{{ error }}</p><p v-if="loaded&&!rows.length">站点公告会在这里出现，由管理员发布。</p><details class="card" v-for="row in rows" :key="row.id"><summary>{{ row.title }}</summary><p class="original-text">{{ row.content }}</p><p class="muted">版本 {{ row.version }}</p></details></div></template>
