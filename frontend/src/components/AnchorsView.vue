<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
import { toast } from '../composables/useToast'

const anchors = ref([])
const busy = ref(false)
const error = ref('')
const editingId = ref(null)
const editValue = ref('')

async function load() {
  try {
    anchors.value = await api.getAnchors()
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  }
}

function startEdit(a) {
  editingId.value = a.id
  editValue.value = a.calibrated_value != null ? a.calibrated_value : a.base_value
}

async function saveCalibrate(a) {
  busy.value = true
  try {
    const val = parseFloat(editValue.value)
    await api.calibrateAnchor(a.id, isNaN(val) ? null : val)
    editingId.value = null
    await load()
    toast.success(`已保存「${a.name}」的校准值`)
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  } finally {
    busy.value = false
  }
}

async function resetCalibrate(a) {
  busy.value = true
  try {
    await api.calibrateAnchor(a.id, null)
    await load()
    toast.success(`已恢复「${a.name}」的默认基准`)
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="card">
    <h1>AI 如何判断</h1>
    <p class="muted">AI 根据你主动提供的实际事实、投入与成果、当前基线提出建议，并标明依据和不确定性。以下是历史内部参考，不是只能识别这些活动；主线只影响金币，属性由事实决定。</p>
    <p v-if="error" class="muted" style="color: var(--danger)">{{ error }}</p>

    <div class="table-scroll" role="region" aria-label="锚点基准与校准表" tabindex="0"><table style="width: 100%; border-collapse: collapse; font-size: 14px">
      <thead>
        <tr style="text-align: left; border-bottom: 1px solid var(--border)">
          <th style="padding: 8px">标准事件</th>
          <th>基准量</th>
          <th>影响属性</th>
          <th>基准增减</th>
          <th>科学依据</th>
          <th>历史状态</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="a in anchors" :key="a.id" style="border-bottom: 1px solid var(--border)">
          <td style="padding: 8px">
            <b>{{ a.name }}</b>
            <div class="muted">{{ a.description }}</div>
          </td>
          <td>
            <template v-if="editingId === a.id">
              <input :aria-label="'校准 '+a.name+' 的基准量'" v-model="editValue" style="width: 70px" />
            </template>
            <template v-else>
              {{ a.calibrated_value != null ? a.calibrated_value : a.base_value }} {{ a.unit }}
              <span v-if="a.calibrated_value != null" class="tag">已校准</span>
            </template>
          </td>
          <td>{{ a.target_attribute }}</td>
          <td>
            <span :class="a.base_delta >= 0 ? 'positive' : 'negative'">
              {{ a.base_delta >= 0 ? '+' : '' }}{{ a.base_delta }}
            </span>
          </td>
          <td class="muted" style="max-width: 260px">{{ a.evidence }}</td>
          <td><span>{{ a.calibrated_value!=null?'旧校准记录已保留':'内部参考' }}</span></td>
        </tr>
      </tbody>
    </table></div>
  </div>
</template>
