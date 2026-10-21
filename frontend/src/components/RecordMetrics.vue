<script setup>
import { ref,onMounted } from 'vue'
import { api } from '../api'
const data=ref(null),error=ref('')
onMounted(async()=>{try{data.value=await api.flow('/record-metrics')}catch(e){error.value=e.message}})
</script>
<template><section class="metrics-section"><p v-if="error" class="error">{{ error }}</p><div v-if="data" class="metric-cards"><article v-for="(label,kind) in {event:'事件记录',diary:'日记记录'}" :key="kind" class="card"><h2>{{ label }}</h2><div class="three-metrics"><div><strong>{{ data.metrics[kind+'_saved_days']?.count||0 }}</strong><span>累计记录日</span></div><div><strong>{{ data.metrics[kind+'_saved_days']?.current_contiguous_days||0 }}</strong><span>当前连续</span></div><div><strong>{{ data.metrics[kind+'_saved_days']?.longest_contiguous_days||0 }}</strong><span>最长连续</span></div></div></article></div><details v-if="data"><summary>记录日期口径与内容覆盖</summary><p>坚持按实际首次保存日计算；今天尚未记录时保留截至昨天的连续数，补记不补过去资格。</p><p v-for="kind in ['event','diary']" :key="kind">{{ kind==='event'?'事件':'日记' }}内容覆盖 {{ data.metrics[kind+'_content_days']?.count||0 }} 天 · 历史保存日不明 {{ data.metrics[kind+'_saved_days']?.unknown_saved_dates||0 }} 条</p></details></section></template>
