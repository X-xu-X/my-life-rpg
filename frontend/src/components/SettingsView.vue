<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { api } from '../api'
import { account } from '../session'
import { toast } from '../composables/useToast'
import ItemManager from './ItemManager.vue'
import ExportControls from './ExportControls.vue'
import ModelSettings from './ModelSettings.vue'
import PageHeader from './ui/PageHeader.vue'

const directory=[['models','AI 模型'],['data','数据导出'],['items','打卡项目'],['dimensions','属性维度'],['modules','旧扩展开关'],['reports','成长报告']]
async function locate(id){
  const target=document.getElementById('settings-'+id)
  if(!target)return
  if(target.tagName==='DETAILS')target.open=true
  await nextTick()
  const heading=target.querySelector('h2,h3,summary')
  target.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'})
  heading?.focus({preventScroll:true})
}
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
    toast.error(e.message)
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
    toast.success(`已保存「${name}」设置`)
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
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
    toast.error(e.message)
  }
}

async function doBackup() {
  backingUp.value = true
  error.value = ''
  try {
    const res = await api.backup()
    if (res.backup_file) toast.success(`备份完成：${res.backup_file}`)
    else toast.error('备份失败')
    await loadBackups()
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  } finally {
    backingUp.value = false
  }
}


const reportData = ref(null)
const reportBusy = ref(false)

async function genReport(period) {
  reportBusy.value = true
  error.value = ''
  try {
    reportData.value = await api.getReport(period)
    toast.success('报告已生成')
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
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
    toast.info(`「${MODULES[key]?.label || key}」已${mods[key] ? '开启' : '关闭'}`)
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  }
}

async function exportData(format) {
  exporting.value = true
  error.value = ''
  try {
    await api.exportData(format)
    toast.success('导出已开始下载')
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  } finally {
    exporting.value = false
  }
}

onMounted(() => {
  load()
  if (account.value?.mode !== 'cloud') loadBackups()
})
</script>

<template><div class="settings-page">
  <PageHeader title="设置" description="模型与数据放在前面，其他设置按需展开。" />
  <nav class="settings-directory" aria-label="设置目录"><button v-for="[id,label] in directory" :key="id" type="button" class="btn" @click="locate(id)">{{ label }}</button></nav>
    <ModelSettings />
    <ExportControls/>
    <div class="card backup-note">
      <h3>数据备份</h3><p v-if="account?.mode === 'cloud'" class="muted">服务器备份由运营者通过运维命令完成，数据库备份与加密主密钥需要分别保管。</p>
      <p v-if="account?.mode !== 'cloud'" class="muted">每次启动自动备份（保留最近 30 份），也可以手动备份。</p>
      <button v-if="account?.mode !== 'cloud'" class="btn primary" :disabled="backingUp" @click="doBackup">
        {{ backingUp ? '备份中…' : '立即备份' }}
      </button>
      <div v-if="backups.length" style="margin-top: 10px">
        <div class="muted" style="font-size: 13px; margin-bottom: 4px">最近备份：</div>
        <div v-for="b in backups.slice(0, 5)" :key="b.file" class="muted" style="font-size: 13px">
          {{ b.file }}（{{ (b.size / 1024).toFixed(1) }} KB，{{ b.created_at }}）
        </div>
      </div>
    </div>
  <details class="card settings-section" id="settings-items"><summary>打卡项目 · 项目管理</summary><ItemManager /></details>
    <details class="card settings-section" id="settings-dimensions">
      <summary>属性维度设置 · 修改 {{ changedAttrs.length }} 项</summary>
      <p class="muted">「隐藏」= AI 照判但面板不显示；「关闭判定」= AI 不分析不加点（值冻结，重开从当前值继续）。</p>

      <!-- v1.3：默认只展示改过状态的维度，其余收进折叠区，减少视觉噪音 -->
      <div v-if="changedAttrs.length">
        <div v-for="name in changedAttrs" :key="'c-' + name" class="judgment-item">
          <div class="action-group" style="align-items: center; justify-content: space-between">
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
            <div class="action-group" style="align-items: center; justify-content: space-between">
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

      <p v-if="saveHint" class="muted" style="color: var(--success); font-size: 13px; margin-top: 6px">✓ {{ saveHint }}</p>
    </details>
    <details class="card settings-section" id="settings-modules">
      <summary>旧扩展开关 · 暂不可操作</summary>
      <p class="muted">这组旧开关尚未接入已交付模块，暂不可操作。</p>
      <div v-for="(mod, key) in MODULES" :key="key" class="judgment-item">
        <div class="action-group" style="align-items: center; justify-content: space-between">
          <div>
            <b>{{ mod.label }}</b>
            <div class="muted">{{ mod.desc }}</div>
          </div>
          <button
            class="btn small"
            :class="{ primary: (settings?.gamification_modules || {})[key] }"
            disabled
            @click="toggleModule(key)"
          >
            {{ (settings?.gamification_modules || {})[key] ? '已开启' : '已关闭' }}
          </button>
        </div>
      </div>
    </details>
    <details class="card settings-section" id="settings-reports">
      <summary>成长报告</summary><RouterLink class="btn" to="/reports">查看历史报告 →</RouterLink>
      <p class="muted">AI 基于近期数据生成成长总结与建议，可能计费。展开不会调用模型。</p>
      <div class="action-group">
        <button class="btn primary" :disabled="reportBusy" @click="genReport('week')">{{ reportBusy ? '生成中…' : '生成周报' }}</button>
        <button class="btn" :disabled="reportBusy" @click="genReport('month')">
          <template v-if="reportBusy">生成中…</template>
          <template v-else>生成月报</template>
        </button>
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
    </details>
  <p v-if="error" class="error" role="alert">{{ error }}</p>
</div></template>
