<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { toast } from '../composables/useToast'
import ItemManager from './ItemManager.vue'

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

// ============ AI 模型配置（BYOK，v1.4） ============
const GROUP_META = {
  primary: {
    label: '判定模型组',
    desc: '日记/打卡判定、追问、要素提取、首次引导、长期记忆都走这一组',
    baseUrlPh: 'https://api.deepseek.com',
    modelPh: 'deepseek-chat',
  },
  aux: {
    label: '辅助模型组',
    desc: '周报/月报走这一组；判定组未配置时，判定自动降级用本组并标注「判定质量一般」——可填 SiliconFlow 等任何 OpenAI 兼容端点的免费模型作兜底',
    baseUrlPh: 'https://api.siliconflow.cn',
    modelPh: '例如免费档模型（OpenAI 兼容端点均可）',
  },
}

const llmRaw = ref(null) // 服务端原始配置（掩码回显 + .env 状态）
const llmForm = ref({
  primary: { enabled: false, api_key: '', base_url: '', model: '' },
  aux: { enabled: false, api_key: '', base_url: '', model: '' },
})
const llmBusy = ref(false)
const llmHint = ref('')

const envFallback = computed(() => llmRaw.value?.env_fallback || { ready: false, model: '' })
const anyConfigured = computed(
  () => llmRaw.value && (llmRaw.value.primary.configured || llmRaw.value.aux.configured)
)

async function loadLLMConfig() {
  try {
    const data = await api.getLLMConfig()
    llmRaw.value = data
    for (const g of ['primary', 'aux']) {
      const src = data[g] || {}
      llmForm.value[g] = {
        enabled: !!src.enabled,
        api_key: '', // 掩码安全：不回填明文，留空 = 不改
        base_url: src.base_url || '',
        model: src.model || '',
      }
    }
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  }
}

function keyPlaceholder(group) {
  const src = llmRaw.value?.[group]
  return src?.configured ? `已绑定（${src.api_key}），留空则不修改` : 'sk-…'
}

async function saveLLM(group) {
  const f = llmForm.value[group]
  const src = llmRaw.value?.[group] || {}
  if (!f.api_key.trim() && !src.configured) {
    toast.error('请先填写 API Key')
    return
  }
  if (!f.base_url.trim() || !f.model.trim()) {
    toast.error('请填写 Base URL 和模型名')
    return
  }
  // 口径变化确认（仅判定组）：模型端点/key 与旧值有差异时弹确认
  if (group === 'primary' && src.configured) {
    const changed =
      (f.api_key.trim() && f.api_key.trim() !== '__KEEP__') ||
      f.model.trim() !== (src.model || '') ||
      f.base_url.trim().replace(/\/+$/, '') !== (src.base_url || '').replace(/\/+$/, '')
    if (changed) {
      const ok = window.confirm(
        '更换判定模型后，后续加点口径可能与之前不同（历史数据全部保留；长期记忆会自动注入新模型衔接上下文）。确认更换？'
      )
      if (!ok) return
    }
  }
  llmBusy.value = true
  error.value = ''
  try {
    const payload = {
      group,
      enabled: f.enabled,
      base_url: f.base_url.trim(),
      model: f.model.trim(),
    }
    if (f.api_key.trim()) payload.api_key = f.api_key.trim()
    await api.putLLMConfig(payload)
    llmHint.value = `已保存「${GROUP_META[group].label}」`
    clearTimeout(hintTimer)
    hintTimer = setTimeout(() => (llmHint.value = ''), 2500)
    await loadLLMConfig()
    toast.success(`已保存「${GROUP_META[group].label}」`)
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  } finally {
    llmBusy.value = false
  }
}

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
  loadBackups()
  loadLLMConfig()
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
      <h3>AI 模型（自带 Key，BYOK）</h3>
      <p v-if="!anyConfigured && envFallback.ready" class="muted">
        当前使用服务端默认模型（.env）：{{ envFallback.model }}。可在此绑定你自己的 Key（任何 OpenAI 兼容端点均可）。
      </p>
      <p v-else-if="!anyConfigured && !envFallback.ready" class="muted" style="color: #b7791f">
        ⚠️ 尚未配置任何 AI 模型：提交日记/打卡会提示到本页绑定。可只配「辅助模型组」（免费模型兜底）。
      </p>
      <p class="muted" style="font-size: 12px">
        判定走「判定模型组」，周报走「辅助模型组」；判定组未启用时自动降级用辅助组并标注「判定质量一般」。Key 仅保存在本地数据库，导出数据不含 Key。
      </p>

      <div v-for="(meta, group) in GROUP_META" :key="group" class="judgment-item">
        <div class="row" style="align-items: center; justify-content: space-between">
          <b>{{ meta.label }}</b>
          <label style="display: flex; align-items: center; gap: 6px; font-size: 13px">
            <input type="checkbox" v-model="llmForm[group].enabled" style="width: auto" /> 启用
          </label>
        </div>
        <div class="muted" style="font-size: 12px">{{ meta.desc }}</div>
        <div class="row" style="margin-top: 6px">
          <div class="field" style="flex: 2">
            <label>Base URL</label>
            <input v-model="llmForm[group].base_url" :placeholder="meta.baseUrlPh" />
          </div>
          <div class="field" style="flex: 1">
            <label>模型名</label>
            <input v-model="llmForm[group].model" :placeholder="meta.modelPh" />
          </div>
        </div>
        <div class="field">
          <label>API Key</label>
          <input type="password" v-model="llmForm[group].api_key" :placeholder="keyPlaceholder(group)" autocomplete="new-password" />
        </div>
        <div class="row" style="margin-top: 6px">
          <button class="btn small primary" :disabled="llmBusy" @click="saveLLM(group)">
            <template v-if="llmBusy">保存中…</template>
            <template v-else>保存{{ meta.label }}</template>
          </button>
        </div>
      </div>

      <p v-if="llmHint" class="muted" style="color: #2a7f3e; font-size: 12px; margin-top: 6px">✓ {{ llmHint }}</p>
    </div>

    <!-- v1.7 B2：打卡项目管理（最贴近日常使用的配置，放在属性开关之后、导出之前） -->
    <ItemManager />

    <div class="card">
      <h3>数据导出（个人数据主权）</h3>
      <p class="muted">导出你的全部数据，随时可以带走。</p>
      <div class="row">
        <button class="btn primary" :disabled="exporting" @click="exportData('json')">
          <template v-if="exporting">导出中…</template>
          <template v-else>导出 JSON（全部数据）</template>
        </button>
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
    </div>


    <p v-if="error" class="muted" style="color: #d33">{{ error }}</p>
  </div>
</template>
