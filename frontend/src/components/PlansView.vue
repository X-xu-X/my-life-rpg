<script setup>
import GrowthPolicies from './GrowthPolicies.vue'
import PlanAgenda from './PlanAgenda.vue'
import { ref, onMounted } from 'vue'
import { api } from '../api'
import PageHeader from './ui/PageHeader.vue'
import GoalsView from './GoalsView.vue'
import ItemManager from './ItemManager.vue'
const count=ref(null),error=ref('')
onMounted(async()=>{try{count.value=(await api.listItems()).length}catch(e){error.value=e.message}})
</script>
<template><div class="reading-page"><PageHeader title="计划" description="目标和日程放在这里，按自己的节奏安排。" /><PlanAgenda/><GrowthPolicies/>
<p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="count!==null" class="muted">读取时共有 {{ count }} 个项目</p>
<p class="muted">上方为新版日程与当次结果。下方旧项目继续沿用每日／每周次数规则，不自动改期。</p>
<RouterLink class="btn" to="/checkin">查看现有当期项目 →</RouterLink><GoalsView /><details class="card"><summary>管理所有项目</summary><ItemManager /></details>
</div></template>
