<script setup>
import { ref,onMounted } from 'vue'
import { api } from '../api'
import PageHeader from './ui/PageHeader.vue'
const rows=ref([]),error=ref(''),loaded=ref(false)
onMounted(async()=>{try{rows.value=(await api.flow('/announcements')).items;loaded.value=true}catch(e){error.value=e.message}})
</script>
<template><div class="reading-page"><PageHeader title="站内公告" description="只显示已发布的公告。"/><p v-if="error" class="error">{{ error }}</p><p v-if="loaded&&!rows.length">暂无已发布公告。</p><article class="card" v-for="row in rows" :key="row.id"><h2>{{ row.title }}</h2><p class="original-text">{{ row.content }}</p><p class="muted">版本 {{ row.version }}</p></article></div></template>
