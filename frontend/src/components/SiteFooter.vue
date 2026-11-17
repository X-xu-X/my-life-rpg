<script setup>
import { siteFiling } from '../siteFiling'
</script>

<template>
  <footer v-if="siteFiling.icpNumber" class="site-footer" aria-label="网站备案信息">
    <a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer">{{ siteFiling.icpNumber }}</a>
    <a v-if="siteFiling.policeNumber" class="police-filing" :href="siteFiling.policeUrl" target="_blank" rel="noopener noreferrer">
      <!-- TODO(备案): 换官方图标，等素材（自绘的圆+五角星大概率不符合备案系统要求，拿到图片后替换本行 svg） -->
      <svg class="police-emblem" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" stroke-width="1.2"/><path d="M8 3.6 9.5 6h2.6l-2.1 1.7.8 2.6L8 8.9l-2.8 1.4.8-2.6L3.9 6h2.6z" fill="currentColor"/></svg>{{ siteFiling.policeNumber }}
    </a>
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
.police-filing {
  gap: 5px;
}
.police-emblem {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
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
