<script setup>
import { computed, onMounted, ref } from 'vue'
import { useTipPrefs } from '../../composables/useTipPrefs'

const props = defineProps({
  id: { type: String, required: true },
  // 关闭按钮的读屏名称；由各接入点传入，让 6 个 × 能被区分
  label: { type: String, default: '不再显示这行说明' },
})
const tips = useTipPrefs()
const shown = computed(() => !tips.hidden(props.id))
// 失败反馈：保持可见，并把按钮标题换成「这次没保存成功，再试一次」
const failed = ref(false)
const closeLabel = computed(() =>
  failed.value ? '这次没保存成功，再试一次' : props.label
)
let timer = null
onMounted(tips.ensure)
async function dismiss() {
  const ok = await tips.hide(props.id)
  failed.value = !ok
  clearTimeout(timer)
  if (!ok) timer = setTimeout(() => (failed.value = false), 4000)
}
</script>

<template>
  <p v-if="shown" class="tip-line">
    <span class="tip-line-text"><slot /></span>
    <button
      type="button"
      class="tip-line-close"
      :class="{ 'is-failed': failed }"
      :aria-label="closeLabel"
      :title="closeLabel"
      @click="dismiss"
    >
      ×
    </button>
  </p>
</template>

