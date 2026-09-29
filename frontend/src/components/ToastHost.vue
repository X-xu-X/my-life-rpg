<script setup>
// v1.9 F2：全局轻提示渲染层。在 App.vue 挂载一次即可。
import { toast, dismiss } from '../composables/useToast'

const ICON = { success: '✓', error: '!', info: 'i' }
</script>

<template>
  <!-- 容器不拦截点击（pointer-events:none），单条卡片恢复可点（auto） -->
  <div class="toast-host">
    <transition-group name="toast">
      <div
        v-for="t in toast.state.items"
        :key="t.id"
        class="toast"
        :class="`toast-${t.type}`"
        role="status"
      >
        <span class="toast-icon">{{ ICON[t.type] || '' }}</span>
        <span class="toast-msg">{{ t.message }}</span>
        <button class="toast-close" title="关闭" @click="dismiss(t.id)">×</button>
      </div>
    </transition-group>
  </div>
</template>
