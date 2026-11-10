<script setup>
import { computed, onMounted, ref } from 'vue'
import { useTipPrefs } from '../../composables/useTipPrefs'

const props = defineProps({ id: { type: String, required: true } })
const tips = useTipPrefs()
const shown = computed(() => !tips.hidden(props.id))
// 失败反馈：保持可见，并把按钮标题换成「这次没保存成功，再试一次」
const failed = ref(false)
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
      aria-label="不再显示这行说明"
      :title="failed ? '这次没保存成功，再试一次' : '不再显示这行说明'"
      @click="dismiss"
    >
      ×
    </button>
  </p>
</template>

