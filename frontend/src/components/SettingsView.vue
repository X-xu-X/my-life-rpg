<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'

const settings = ref(null)
const error = ref('')
const exporting = ref(false)

const MODULES = {
  achievements: { label: '成就徽章', desc: '达成特定里程碑时颁发徽章' },
  streak: { label: '连续打卡 Streak', desc: '记录连续打卡天数，鼓励坚持' },
  tasks: { label: '每日任务清单', desc: '每日/待办任务管理' },
  coin_shop: { label: '金币奖励商店', desc: '用金币兑换自我奖励（如"看一集剧"）' },
}

async function load() {
  try {
    settings.value = await api.getSettings()
  } catch (e) {
    error.value = e.message
  }
}

async function toggleModule(key) {
  const mods = { ...(settings.value.gamification_modules || {}) }
  mods[key] = !mods[key]
  try {
    await api.updateSetting('gamification_modules', mods)
    settings.value.gamification_modules = mods
  } catch (e) {
    error.value = e.message
  }
}

async function exportData(format) {
  exporting.value = true
  error.value = ''
  try {
    await api.exportData(format)
  } catch (e) {
    error.value = e.message
  } finally {
    exporting.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="card">
      <h2>设置</h2>
      <p class="muted">游戏化扩展模块开关 + 数据导出。</p>
    </div>

    <div class="card">
      <h3>游戏化扩展模块</h3>
      <p class="muted">以下为可开关的扩展模块（重度功能，后续迭代开放），开启后对应入口才会出现。</p>
      <div v-for="(mod, key) in MODULES" :key="key" class="judgment-item">
        <div class="row" style="align-items: center; justify-content: space-between">
          <div>
            <b>{{ mod.label }}</b>
            <div class="muted">{{ mod.desc }}</div>
          </div>
          <button
            class="btn small"
            :class="{ primary: (settings?.gamification_modules || {})[key] }"
            @click="toggleModule(key)"
          >
            {{ (settings?.gamification_modules || {})[key] ? '已开启' : '已关闭' }}
          </button>
        </div>
      </div>
    </div>

    <div class="card">
      <h3>数据导出（个人数据主权）</h3>
      <p class="muted">导出你的全部数据，随时可以带走。</p>
      <div class="row">
        <button class="btn primary" :disabled="exporting" @click="exportData('json')">导出 JSON（全部数据）</button>
        <button class="btn" :disabled="exporting" @click="exportData('csv')">导出事件 CSV</button>
      </div>
    </div>

    <p v-if="error" class="muted" style="color: #d33">{{ error }}</p>
  </div>
</template>
