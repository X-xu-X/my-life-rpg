<script setup>
// Original small line drawings for LifeXP; no external icon package or assets.
defineProps({name:String})
const paths={today:'M12 3a9 9 0 1 0 9 9M12 7v5l3 2M17 3v5h5',journal:'M5 3h14v18H5zM9 3v18M12 8h4M12 12h4',plans:'M4 5h16v16H4zM8 3v4M16 3v4M4 10h16M8 15l2 2 5-4',growth:'M4 20h16M7 16v-4M12 16V8M17 16V4',me:'M8 7a4 4 0 1 0 8 0 4 4 0 1 0-8 0M4 21v-2a8 8 0 0 1 16 0v2'}
</script>
<template><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="paths[name] || paths.journal" /></svg></template>
