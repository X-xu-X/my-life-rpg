<script setup>
defineProps({title:String,description:String,eyebrow:String})
</script>
<template><header class="page-intro"><div><p v-if="eyebrow" class="eyebrow">{{ eyebrow }}</p><h1>{{ title }}</h1><p v-if="description" class="muted">{{ description }}</p></div><div v-if="$slots.actions" class="action-group"><slot name="actions" /></div></header></template>
