<script setup>
import { computed,ref,onMounted,onUnmounted } from 'vue'
import { modelRequests } from '../requestStatus'
import { accountEpoch } from '../session'
const now=ref(Date.now()),requests=computed(()=>modelRequests.value.filter(r=>r.epoch===accountEpoch));let timer
onMounted(()=>timer=setInterval(()=>{now.value=Date.now()},1000));onUnmounted(()=>clearInterval(timer))
</script>
<template><aside v-if="requests.length" class="request-status" role="status" aria-live="polite"><span class="spinner" aria-hidden="true"/><div><b>{{ requests[0].label }}…</b><p v-if="now-requests[0].started>15000">响应较慢。请保留当前输入；结果未知时先恢复原请求，避免重复调用。</p><p v-else>请稍候，输入会为你保留。</p></div></aside></template>
