<script setup>
import { siteFiling } from '../siteFiling'
</script>

<template>
  <footer v-if="siteFiling.icpNumber" class="site-footer" aria-label="网站备案信息">
    <a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer">{{ siteFiling.icpNumber }}</a>
  </footer>
</template>

<style scoped>
.site-footer {
  max-width: 100%;
  margin: 12px auto 0;
  padding: 8px 16px 16px;
  text-align: center;
  color: var(--text-sub);
  font-size: 13px;
  overflow-wrap: anywhere;
}
.site-footer a {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 44px;
  max-width: 100%;
  padding: 8px 4px;
  color: inherit;
  text-decoration: none;
}
.site-footer a:hover,
.site-footer a:focus-visible {
  color: var(--primary);
  text-decoration: underline;
}
</style>
