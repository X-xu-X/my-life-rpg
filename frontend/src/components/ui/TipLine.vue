<script setup>
import { computed, onMounted } from 'vue'
import { useTipPrefs } from '../../composables/useTipPrefs'

const props = defineProps({ id: { type: String, required: true } })
const tips = useTipPrefs()
const shown = computed(() => !tips.hidden(props.id))
onMounted(tips.ensure)
async function dismiss() {
  await tips.hide(props.id)
}
</script>

<template>
  <p v-if="shown" class="tip-line">
    <span class="tip-line-text"><slot /></span>
    <button
      type="button"
      class="tip-line-close"
      aria-label="不再显示这行说明"
      title="不再显示这行说明"
      @click="dismiss"
    >
      ×
    </button>
  </p>
</template>
