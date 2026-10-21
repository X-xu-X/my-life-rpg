<script setup>
import ProjectManager from './ProjectManager.vue'
import GrowthPolicies from './GrowthPolicies.vue'
import GoalsView from './GoalsView.vue'
import ItemManager from './ItemManager.vue'
import PhaseBrief from './PhaseBrief.vue'
import HintCard from './HintCard.vue'
import PageHeader from './ui/PageHeader.vue'
</script>
<template><div class="reading-page wide-page"><PageHeader title="计划" description="把想做的事，安排进适合自己的节奏。"><template #actions><RouterLink class="btn" to="/challenges">挑战与原有合同 →</RouterLink></template></PageHeader><HintCard id="plans-help"><p>行动计划与照顾自己在同一处管理；目标和时长都可不填，结果按实际记录。</p></HintCard><div class="daily-columns"><div class="page-stack"><GoalsView/><ProjectManager/></div><aside class="page-stack"><GrowthPolicies/><PhaseBrief/><details class="card"><summary>原有次数项目与历史</summary><p>继续沿用原每日／每周次数规则，不与周期结果相加。</p><RouterLink class="btn" to="/checkin">查看当期次数 →</RouterLink><ItemManager/></details></aside></div></div></template>
