<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'

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
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function resetCalibrate(a) {
  await api.calibrateAnchor(a.id, null)
  await load()
}

onMounted(load)
</script>

<template>
  <div class="card">
    <h2>量化锚点库</h2>
    <p class="muted">AI 判定以此为基准按强度/时长/质量加权。你可以校准基准值，校准后后续判定随之调整。</p>
    <p v-if="error" class="muted" style="color: #d33">{{ error }}</p>

    <table style="width: 100%; border-collapse: collapse; font-size: 14px">
      <thead>
        <tr style="text-align: left; border-bottom: 1px solid var(--border)">
          <th style="padding: 8px">标准事件</th>
          <th>基准量</th>
          <th>影响属性</th>
          <th>基准增减</th>
          <th>科学依据</th>
          <th>操作</th>
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
              <input v-model="editValue" style="width: 70px" />
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
          <td>
            <template v-if="editingId === a.id">
              <button class="btn small primary" :disabled="busy" @click="saveCalibrate(a)">保存</button>
            </template>
            <template v-else>
              <button class="btn small" @click="startEdit(a)">校准</button>
              <button v-if="a.calibrated_value != null" class="btn small" @click="resetCalibrate(a)">恢复</button>
            </template>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
