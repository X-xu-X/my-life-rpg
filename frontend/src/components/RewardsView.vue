<script setup>
import { ref,onMounted } from 'vue'
import { api } from '../api'
import PageHeader from './ui/PageHeader.vue'
import RewardShop from './RewardShop.vue'
import TrialRules from './TrialRules.vue'
import PhaseBrief from './PhaseBrief.vue'
import HintCard from './HintCard.vue'
import HolidayGift from './HolidayGift.vue'
const ledger=ref([]),error=ref(''),version=ref(0),shop=ref(null)
async function refresh(){try{ledger.value=(await api.getCoins()).ledger||[];await shop.value?.reload()}catch(e){error.value=e.message}}
onMounted(refresh)
</script>
<template><div class="reading-page wide-page"><PageHeader title="奖励与休息" description="把努力留给值得的事，把休息还给自己。"/><HintCard id="rewards-help"><p>基础娱乐独立免费，额外奖励由本人模型定价；兑换始终需要你确认。</p></HintCard><p v-if="error" class="error">{{ error }}</p><div class="daily-columns"><div class="page-stack"><RewardShop ref="shop" @changed="refresh"/></div><aside class="page-stack"><TrialRules :key="'trial'+version" @changed="refresh"/><section class="card"><h2>娱乐券与计时</h2><RouterLink class="btn primary" to="/timers">使用额度 / 查看计时</RouterLink></section><PhaseBrief constraints/><HolidayGift/><details class="card"><summary>金币流水</summary><p v-for="r in ledger.slice(0,30)" :key="r.id">{{ r.delta>0?'+':'' }}{{ r.delta }} · {{ r.reason }}</p></details><RouterLink class="btn" to="/special-vouchers">特殊券与原有兑换历史 →</RouterLink></aside></div></div></template>
