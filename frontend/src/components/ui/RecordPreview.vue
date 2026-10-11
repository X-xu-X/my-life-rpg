<script setup>
defineProps({title:String,summary:String,to:String})
</script>
<template><article class="event-row"><RouterLink :to="to" class="record-preview"><div class="record-meta"><slot /></div><h2 class="preview-title">{{ title }}</h2><p class="preview-summary">{{ (summary || '').slice(0,240) }}</p><span class="preview-link">查看原文与分析 →</span></RouterLink></article></template>
