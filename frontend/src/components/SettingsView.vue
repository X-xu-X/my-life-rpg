<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'

const settings = ref(null)
const error = ref('')
const exporting = ref(false)
const backups = ref([])
const backingUp = ref(false)

// 属性维度开关
const attributes = ref([])
const hiddenAttrs = ref([])
const disabledAttrs = ref([])

const MODULES = {
  achievements: { label: '成就徽章', desc: '达成特定里程碑时颁发徽章' },
  streak: { label: '连续打卡 Streak', desc: '记录连续打卡天数，鼓励坚持' },
  tasks: { label: '每日任务清单', desc: '每日/待办任务管理' },
  coin_shop: { label: '金币奖励商店', desc: '用金币兑换自我奖励（如"看一集剧"）' },
}

async function load() {
  try {
    settings.value = await api.getSettings()
    hiddenAttrs.value = settings.value.hidden_attributes || []
    disabledAttrs.value = settings.value.disabled_attributes || []
    const attrData = await api.getAttributes()
    attributes.value = (attrData.attributes || []).map((a) => a.name)
  } catch (e) {
    error.value = e.message
  }
}

function stateOf(name) {
  if (disabledAttrs.value.includes(name)) return 'disabled'
  if (hiddenAttrs.value.includes(name)) return 'hidden'
  return 'show'
}

async function setState(name, state) {
  const hidden = hiddenAttrs.value.filter((n) => n !== name)
  const disabled = disabledAttrs.value.filter((n) => n !== name)
  if (state === 'hidden') hidden.push(name)
  if (state === 'disabled') disabled.push(name)
  hiddenAttrs.value = hidden
  disabledAttrs.value = disabled
  error.value = ''
  try {
    await api.updateSetting('hidden_attributes', hidden)
    await api.updateSetting('disabled_attributes', disabled)
    // v1.3：轻提示（2 秒后消失）
    saveHint.value = `已保存「${name}」设置`
    clearTimeout(hintTimer)
    hintTimer = setTimeout(() => (saveHint.value = ''), 2000)
  } catch (e) {
    error.value = e.message
  }
}

// v1.3：非默认状态（隐藏/关闭判定）的维度，前置展示
const changedAttrs = computed(() => attributes.value.filter((n) => stateOf(n) !== 'show'))

const saveHint = ref('')
let hintTimer = null

async function loadBackups() {
  try {
    backups.value = await api.listBackups()
  } catch (e) {
    error.value = e.message
  }
}

async function doBackup() {
  backingUp.value = true
  error.value = ''
  try {
    const res = await api.backup()
    alert(res.backup_file ? `备份完成：${res.backup_file}` : '备份失败')
    await loadBackups()
  } catch (e) {
    error.value = e.message
  } finally {
    backingUp.value = false
  }
}

async function resetAll() {
  if (!window.confirm('⚠️ 重置全部数据？将清空所有事件/判定/属性流水/目标，属性回中性值，并解锁角色档案。此操作不可恢复！')) return
  if (!window.confirm('再次确认：真的要清空所有数据重新开始吗？（建议先备份）')) return
  error.value = ''
  try {
    await api.resetAllData()
    alert('已重置，可重新开始（请刷新页面）。')
  } catch (e) {
    error.value = e.message
  }
}

const reportData = ref(null)
const reportBusy = ref(false)

async function genReport(period) {
  reportBusy.value = true
  error.value = ''
  try {
    reportData.value = await api.getReport(period)
  } catch (e) {
    error.value = e.message
  } finally {
    reportBusy.value = false
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

onMounted(() => {
  load()
  loadBackups()
})
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
      <h3>属性维度开关</h3>
      <p class="muted">「隐藏」= AI 照判但面板不显示；「关闭判定」= AI 不分析不加点（值冻结，重开从当前值继续）。</p>

      <!-- v1.3：默认只展示改过状态的维度，其余收进折叠区，减少视觉噪音 -->
      <div v-if="changedAttrs.length">
        <div v-for="name in changedAttrs" :key="'c-' + name" class="judgment-item">
          <div class="row" style="align-items: center; justify-content: space-between">
            <b>{{ name }}</b>
            <select :value="stateOf(name)" @change="setState(name, $event.target.value)">
              <option value="show">显示</option>
              <option value="hidden">隐藏</option>
              <option value="disabled">关闭判定</option>
            </select>
          </div>
        </div>
      </div>
      <p v-else class="muted">所有维度均为默认「显示」状态。</p>

      <details style="margin-top: 8px">
        <summary class="muted" style="cursor: pointer">全部 {{ attributes.length }} 个维度</summary>
        <div style="margin-top: 8px">
          <div v-for="name in attributes" :key="name" class="judgment-item">
            <div class="row" style="align-items: center; justify-content: space-between">
              <b>{{ name }}</b>
              <select :value="stateOf(name)" @change="setState(name, $event.target.value)">
                <option value="show">显示</option>
                <option value="hidden">隐藏</option>
                <option value="disabled">关闭判定</option>
              </select>
            </div>
          </div>
        </div>
      </details>

      <p v-if="saveHint" class="muted" style="color: #2a7f3e; font-size: 12px; margin-top: 6px">✓ {{ saveHint }}</p>
    </div>

    <div class="card">
      <h3>数据导出（个人数据主权）</h3>
      <p class="muted">导出你的全部数据，随时可以带走。</p>
      <div class="row">
        <button class="btn primary" :disabled="exporting" @click="exportData('json')">导出 JSON（全部数据）</button>
        <button class="btn" :disabled="exporting" @click="exportData('csv')">导出事件 CSV</button>
      </div>
    </div>

    <div class="card">
      <h3>数据备份</h3>
      <p class="muted">每次启动自动备份（保留最近 30 份），也可以手动备份。</p>
      <button class="btn primary" :disabled="backingUp" @click="doBackup">
        {{ backingUp ? '备份中…' : '立即备份' }}
      </button>
      <div v-if="backups.length" style="margin-top: 10px">
        <div class="muted" style="font-size: 12px; margin-bottom: 4px">最近备份：</div>
        <div v-for="b in backups.slice(0, 5)" :key="b.file" class="muted" style="font-size: 13px">
          {{ b.file }}（{{ (b.size / 1024).toFixed(1) }} KB，{{ b.created_at }}）
        </div>
      </div>
    </div>

    <div class="card">
      <h3>成长报告</h3>
      <p class="muted">AI 基于近期数据生成成长总结与建议。</p>
      <div class="row">
        <button class="btn primary" :disabled="reportBusy" @click="genReport('week')">{{ reportBusy ? '生成中…' : '生成周报' }}</button>
        <button class="btn" :disabled="reportBusy" @click="genReport('month')">生成月报</button>
      </div>
      <div v-if="reportData" style="margin-top: 12px">
        <div class="muted" style="margin-bottom: 6px">{{ reportData.start }} ~ {{ reportData.end }}</div>
        <div class="judgment-item"><b>✨ 亮点</b><div class="muted">{{ reportData.report.highlights }}</div></div>
        <div class="judgment-item"><b>⚠️ 关注</b><div class="muted">{{ reportData.report.concerns }}</div></div>
        <div class="judgment-item">
          <b>💡 建议</b>
          <ul v-if="reportData.report.suggestions && reportData.report.suggestions.length" style="margin: 6px 0 0; padding-left: 20px">
            <li v-for="(s, i) in reportData.report.suggestions" :key="i">{{ s }}</li>
          </ul>
        </div>
        <p class="muted" style="margin-top: 6px">{{ reportData.report.tone }}</p>
      </div>
    </div>

    <div class="card">
      <h3>测试 / 重置</h3>
      <p class="muted">⚠️ 清空所有数据（事件/判定/流水/目标），属性回中性值，解锁角色档案。用于测试，操作前建议先备份。</p>
      <button class="btn danger" @click="resetAll">重置全部数据</button>
    </div>

    <p v-if="error" class="muted" style="color: #d33">{{ error }}</p>
  </div>
</template>
