<script setup>
/**
 * 打卡项目管理（v1.7 B2）——作为「设置」页的一个分区。
 *
 * 设计原则（决策 2）：**完全由用户自建，系统绝不预置任何项目**（尤其不预置负面项目，
 * 避免给没有该习惯的人造成噪音）。
 * 删除语义：**只停用、不物理删除**——历史事件通过 item_id 引用它，删了老记录会丢名称。
 */
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { toast } from '../composables/useToast'

const items = ref([])
const goals = ref([])
const error = ref('')
const hint = ref('')
let hintTimer = null
const busy = ref(false)
const editingId = ref(null) // 正在编辑的项目 id（null = 未编辑）

const NATURE_META = {
  planned: { label: '规划内', desc: '我定下要做的事（必做）。未完成不单独扣分，页面如实提示频率。' },
  optional: { label: '可选', desc: '可有可无。默认不加分——AI 会看内容，只有"额外主动投入"才可能小幅加分。' },
  negative: { label: '负面', desc: '久坐、熬夜这类，记一次扣一次分（不会去重）。' },
  other: { label: '其他', desc: '杂项兜底，按内容常规判定。' },
}
const NATURE_ORDER = ['planned', 'optional', 'negative', 'other']

const CATEGORIES = ['学习', '运动', '作息', '社交', '饮食', '情绪', '其他']
const ATTRIBUTES = [
  '', '体能', '智力', '情商', '创造力', '规划力', '健康',
  '幸福感', '感恩', '意义感', '心理韧性', '开放性', '审美', '诚信',
]

const blankForm = () => ({
  name: '',
  nature: 'planned',
  frequency_type: 'none',
  frequency_target: 3,
  category: '',
  related_attribute: '',
  goal_id: null,
  enabled: true,
  sort_order: 0,
})
const form = ref(blankForm())

/** 按性质分组展示（顺序按 NATURE_ORDER） */
const grouped = computed(() =>
  NATURE_ORDER.map((n) => ({
    nature: n,
    ...NATURE_META[n],
    children: items.value.filter((i) => i.nature === n),
  })).filter((g) => g.children.length)
)

function freqText(it) {
  if (it.frequency_type === 'daily') return '每天'
  if (it.frequency_type === 'weekly') return `每周 ${it.frequency_target} 次`
  return '不限频率'
}

function flash(msg) {
  // v1.9 F2：保留表单旁的内联提示（近场），同时接入全局 toast（统一规范）
  hint.value = msg
  clearTimeout(hintTimer)
  hintTimer = setTimeout(() => (hint.value = ''), 2500)
  toast.success(msg)
}

async function load() {
  try {
    items.value = await api.listItems() // 含停用项（管理页需要看到全部）
    goals.value = await api.listGoals()
    error.value = ''
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  }
}

function startCreate() {
  editingId.value = null
  form.value = blankForm()
}

function startEdit(it) {
  editingId.value = it.id
  form.value = {
    name: it.name,
    nature: it.nature,
    frequency_type: it.frequency_type,
    frequency_target: it.frequency_target || 3,
    category: it.category || '',
    related_attribute: it.related_attribute || '',
    goal_id: it.goal_id ?? null,
    enabled: it.enabled,
    sort_order: it.sort_order || 0,
  }
}

function cancelEdit() {
  editingId.value = null
  form.value = blankForm()
}

async function save() {
  if (!form.value.name.trim()) return toast.error('请填写项目名')
  if (form.value.frequency_type === 'weekly' && (!form.value.frequency_target || form.value.frequency_target < 1)) {
    return toast.error('每周频率需填写目标次数（≥1）')
  }
  busy.value = true
  error.value = ''
  try {
    const payload = {
      name: form.value.name.trim(),
      nature: form.value.nature,
      frequency_type: form.value.frequency_type,
      frequency_target: form.value.frequency_type === 'weekly' ? Number(form.value.frequency_target) : 0,
      category: form.value.category,
      related_attribute: form.value.related_attribute,
      goal_id: form.value.goal_id || null,
      enabled: form.value.enabled,
      sort_order: Number(form.value.sort_order) || 0,
    }
    if (editingId.value) {
      await api.updateItem(editingId.value, payload)
      flash(`已保存「${payload.name}」`)
    } else {
      await api.createItem(payload)
      flash(`已新建「${payload.name}」`)
    }
    cancelEdit()
    await load()
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  } finally {
    busy.value = false
  }
}

async function toggleEnabled(it) {
  busy.value = true
  error.value = ''
  try {
    const res = await api.toggleItem(it.id)
    flash(`「${it.name}」已${res.enabled ? '启用' : '停用'}`)
    await load()
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
    <h3>打卡项目</h3>
    <p class="muted">
      你自定义的打卡项目。记录事件时从这里选一个、写正文即可（无需再填固定的时长/距离/强度）。
      <b>停用不会删除</b>——历史记录仍会显示项目名称。
    </p>
    <p class="muted" style="font-size: 13px">
      项目完全由你自建，系统不预置任何项目；「负面」项目请按自己真实想改善的习惯来建。
    </p>

    <!-- 新建 / 编辑表单 -->
    <div class="judgment-item" style="margin-top: 10px; background: #fafbfd">
      <b>{{ editingId ? '编辑项目' : '新建项目' }}</b>
      <div class="form-grid" style="margin-top: 8px">
        <div class="field">
          <label for="itemmanager-field-1">项目名 *</label>
          <input id="itemmanager-field-1" v-model="form.name" placeholder="如 晨跑 / 背单词 / 久坐" />
        </div>
        <div class="field">
          <label for="itemmanager-field-2">性质</label>
          <select id="itemmanager-field-2" v-model="form.nature">
            <option v-for="n in NATURE_ORDER" :key="n" :value="n">{{ NATURE_META[n].label }}</option>
          </select>
        </div>
      </div>
      <p class="muted" style="font-size: 13px; margin-top: -6px">{{ NATURE_META[form.nature].desc }}</p>

      <div class="form-grid">
        <div class="field">
          <label for="itemmanager-field-3">期望频率</label>
          <select id="itemmanager-field-3" v-model="form.frequency_type">
            <option value="none">不限</option>
            <option value="daily">每天</option>
            <option value="weekly">每周 N 次</option>
          </select>
        </div>
        <div class="field" v-if="form.frequency_type === 'weekly'">
          <label for="itemmanager-field-4">每周目标次数</label>
          <input id="itemmanager-field-4" type="number" min="1" v-model.number="form.frequency_target" placeholder="如 3" />
        </div>
      </div>
      <p class="muted" style="font-size: 13px; margin-top: -6px">
        频率只做**如实提示**（如"本周运动 1/3"），不达标本系统不会自动扣分——扣分由 AI 判定。
      </p>

      <div class="form-grid">
        <div class="field">
          <label for="itemmanager-field-5">生活面</label>
          <select id="itemmanager-field-5" v-model="form.category">
            <option value="">—</option>
            <option v-for="c in CATEGORIES" :key="c" :value="c">{{ c }}</option>
          </select>
        </div>
        <div class="field">
          <label for="itemmanager-field-6">主要影响维度</label>
          <select id="itemmanager-field-6" v-model="form.related_attribute">
            <option v-for="a in ATTRIBUTES" :key="a" :value="a">{{ a || '—' }}</option>
          </select>
        </div>
      </div>

      <div class="field">
        <label for="itemmanager-field-7">关联目标（可选）</label>
        <select id="itemmanager-field-7" v-model="form.goal_id">
          <option :value="null">不挂目标</option>
          <option v-for="g in goals" :key="g.id" :value="g.id">{{ g.description || g.metric }}</option>
        </select>
        <p class="muted" style="font-size: 13px; margin-top: 4px">
          挂了目标后，目标的进度条会自动按本项目的打卡完成率计算（无需手动更新）。
        </p>
      </div>

      <div class="action-group" style="margin-top: 6px">
        <button class="btn primary" :disabled="busy" @click="save">
          <template v-if="busy">保存中…</template>
          <template v-else>{{ editingId ? '保存修改' : '新建项目' }}</template>
        </button>
        <button class="btn" @click="cancelEdit" v-if="editingId">取消</button>
        <button class="btn" @click="startCreate" v-else>重置</button>
      </div>
    </div>

    <p v-if="error" class="muted" style="color: var(--danger)">{{ error }}</p>
    <p v-if="hint" class="muted" style="color: var(--success); font-size: 13px">✓ {{ hint }}</p>

    <!-- 列表（按性质分组） -->
    <p v-if="items.length === 0" class="muted" style="margin-top: 12px">还没有项目，用上面的表单建第一个吧。</p>

    <div v-for="g in grouped" :key="g.nature" style="margin-top: 14px">
      <div class="muted" style="font-size: 13px; border-bottom: 1px solid #eee; padding-bottom: 4px; margin-bottom: 6px">
        <b>{{ g.label }}</b> · {{ g.children.length }} 个
      </div>
      <div v-for="it in g.children" :key="it.id" class="judgment-item">
        <div class="action-group" style="align-items: center">
          <b>{{ it.name }}</b>
          <span class="tag">{{ freqText(it) }}</span>
          <span v-if="it.category" class="tag">{{ it.category }}</span>
          <span v-if="it.related_attribute" class="tag">{{ it.related_attribute }}</span>
          <span v-if="!it.enabled" class="tag" style="background: #f0f0f0; color: var(--text-sub)">已停用</span>
          <span v-if="it.goal_id" class="muted" style="margin-left: auto; font-size: 13px">已挂目标</span>
        </div>
        <div class="action-group" style="margin-top: 8px">
          <button class="btn small" :disabled="busy" @click="startEdit(it)">编辑</button>
          <button class="btn small" :class="{ danger: it.enabled }" :disabled="busy" @click="toggleEnabled(it)">
            {{ it.enabled ? '停用' : '启用' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
