<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick, reactive } from 'vue'
import * as echarts from 'echarts'
import { api } from '../api'
import { toast } from '../composables/useToast'

const attrs = ref([])
const level = ref(1)
const exp = ref(0)
const history = ref([])
const heatmap = ref([])
const radarEl = ref(null)
const growthEl = ref(null)
const heatmapEl = ref(null)
let radarChart = null
let growthChart = null
let heatmapChart = null

// ===== 子维度（v1.10 M3）：属性面板顶部提示卡（用户拍板的入口位置） =====
const subThreshold = ref(95)
const subCandidates = ref([]) // 可拆分候选（≥阈值且未拆过，含提议状态）
const subHierarchy = ref({}) // 主维度名 → 子维度列表
const subChecked = reactive({}) // 候选 id → 已勾选的名称集合（多选后确认）
const subBusy = ref(false) // propose 是真实 LLM 调用（20~60s），必须防重复

// 可见维度：隐藏（hidden）的维度不显示，关闭判定（disabled）的仍显示但标记
const visibleAttrs = computed(() => attrs.value.filter((a) => a.visibility !== 'hidden'))

async function load() {
  const [attrData, historyData, heatmapData, subData] = await Promise.all([
    api.getAttributes(),
    api.getAttributeHistory(),
    api.getHeatmap(),
    api.listSubdimensions().catch(() => null), // 子维度加载失败不拖垮面板
  ])
  attrs.value = attrData.attributes || []
  level.value = attrData.level || 1
  exp.value = attrData.exp || 0
  history.value = historyData || []
  heatmap.value = heatmapData || []
  if (subData) {
    subThreshold.value = subData.threshold ?? 95
    subCandidates.value = subData.candidates || []
    subHierarchy.value = subData.hierarchy || {}
    for (const c of subCandidates.value) {
      if (!(c.id in subChecked)) subChecked[c.id] = []
    }
  }
  await nextTick()
  renderRadar()
  renderGrowth()
  renderHeatmap()
}

// ===== 子维度操作 =====
async function proposeSub(c) {
  if (subBusy.value) return
  subBusy.value = true
  try {
    await api.proposeSubdimension(c.id) // 真实 LLM 调用，可能要 20~60s
    toast.success(`AI 已给出「${c.name}」的细分方向提议`)
    await load()
  } catch (e) {
    toast.error(e.message)
  } finally {
    subBusy.value = false
  }
}

async function confirmSub(c) {
  if (subBusy.value) return
  const names = subChecked[c.id] || []
  if (names.length === 0) {
    toast.error('请至少勾选一个细分方向')
    return
  }
  subBusy.value = true
  try {
    const res = await api.acceptSubdimension(c.id, names)
    toast.success(`已解锁 ${res.created.length} 个「${c.name}」子维度`)
    await load()
  } catch (e) {
    toast.error(e.message)
  } finally {
    subBusy.value = false
  }
}

async function dismissSub(c) {
  if (subBusy.value) return
  subBusy.value = true
  try {
    await api.dismissSubdimension(c.id)
    toast.success('已忽略本次提议')
    await load()
  } catch (e) {
    toast.error(e.message)
  } finally {
    subBusy.value = false
  }
}

function renderRadar() {
  if (!radarEl.value) return
  if (!radarChart) radarChart = echarts.init(radarEl.value)
  const names = visibleAttrs.value.map((a) => a.name)
  const values = visibleAttrs.value.map((a) => a.value)
  // v1.10 P2-2（V1）：动态上界——取可见维度最大值，向上取整到 5 的倍数再 +5，下限 10。
  // 轴名附加真实值，避免「形状放大」被误读为绝对水平（文档给出的两个推荐做法之一）。
  const rawMax = values.reduce((m, v) => Math.max(m, Number(v) || 0), 0)
  const dynMax = Math.max(10, Math.ceil(rawMax / 5) * 5 + 5)
  radarChart.setOption({
    color: ['#4f6ef7'],
    tooltip: {},
    radar: {
      indicator: names.map((n, i) => ({ name: `${n} ${Math.round(Number(values[i]) || 0)}`, max: dynMax })),
      radius: '58%', // 13 轴：收窄半径，给长轴名留空间
      axisName: { color: '#2b2f3a', fontSize: 11 },
      splitArea: { areaStyle: { color: ['#fafbfe', '#f0f2f8'] } },
    },
    series: [
      {
        type: 'radar',
        data: [{ value: values, name: '当前属性' }],
        areaStyle: { opacity: 0.25 },
      },
    ],
  })
}

// v1.10 P2-2（V2）：趋势图改为**单维度可切换**，默认选当前值最低的维度
const growthDim = ref('')

function renderGrowth() {
  if (!growthEl.value) return
  if (!growthChart) growthChart = echarts.init(growthEl.value)
  const names = [...new Set(history.value.map((h) => h.name))]
  if (names.length === 0) {
    growthChart.clear()
    growthChart.setOption({})
    return
  }
  // 默认维度：当前值最低的主维度（有历史数据的那些里选）
  if (!growthDim.value || !names.includes(growthDim.value)) {
    const visible = visibleAttrs.value.filter((a) => names.includes(a.name))
    const pool = visible.length ? visible : attrs.value.filter((a) => names.includes(a.name))
    const lowest = pool.reduce((m, a) => (m === null || Number(a.value) < Number(m.value) ? a : m), null)
    growthDim.value = lowest ? lowest.name : names[0]
  }
  const dim = growthDim.value
  const pts = history.value
    .filter((h) => h.name === dim)
    .sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
    .map((h) => [h.created_at, h.value_after])
  // Y 轴按该维度实际区间缩放（下取整 -2 / 上取整 +2，并夹在 0~100）
  const vals = pts.map((p) => Number(p[1]) || 0)
  const yMin = Math.max(0, Math.floor(Math.min(...vals)) - 2)
  const yMax = Math.min(100, Math.ceil(Math.max(...vals)) + 2)
  growthChart.clear()
  growthChart.setOption({
    color: ['#4f6ef7'],
    tooltip: { trigger: 'axis' },
    grid: { left: 48, right: 24, top: 30, bottom: 40 },
    xAxis: { type: 'time', axisLabel: { color: '#7a7f8c' } },
    yAxis: { type: 'value', min: yMin, max: yMax, axisLabel: { color: '#7a7f8c' } },
    series: [{ name: dim, type: 'line', data: pts, smooth: true, showSymbol: true, areaStyle: { opacity: 0.08 } }],
  })
}

function switchGrowth(name) {
  growthDim.value = name
  renderGrowth()
}

/** 趋势图维度按钮组的数据源（有历史记录的维度，按当前值升序） */
const growthDims = computed(() => {
  const names = new Set(history.value.map((h) => h.name))
  return attrs.value
    .filter((a) => names.has(a.name))
    .slice()
    .sort((a, b) => Number(a.value) - Number(b.value))
})

function renderHeatmap() {
  if (!heatmapEl.value) return
  if (!heatmapChart) heatmapChart = echarts.init(heatmapEl.value)
  if (heatmap.value.length === 0) {
    heatmapChart.clear()
    heatmapChart.setOption({})
    return
  }
  const todayStr = (() => {
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  })()
  // v1.10 P2-2（V3）：今日格子加边框高亮（用逐项 itemStyle 覆盖）
  const data = heatmap.value.map((h) => ({
    value: [h.date, h.count],
    itemStyle: h.date === todayStr ? { borderColor: '#e0533d', borderWidth: 1.5 } : undefined,
  }))
  // 近 4 个月（文档建议 4 个月：兼顾习惯观察与格子可读性）
  const now = new Date()
  const start = new Date(now.getFullYear(), now.getMonth() - 3, 1)
  const fmtDay = (d) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  const rangeStart = fmtDay(start)
  const rangeEnd = fmtDay(now)
  heatmapChart.clear()
  heatmapChart.setOption({
    tooltip: {
      formatter: (p) => `${p.value[0]}：${p.value[1]} 条记录`,
    },
    // v1.10 P2-2（V3）：连续色阶 → 分段色阶（0 不上色 / 1-2 浅蓝 / 3-5 中蓝 / 6+ 深蓝）
    visualMap: {
      type: 'piecewise',
      show: true,
      selectedMode: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      pieces: [
        { min: 6, label: '6+ 条', color: '#2f4fd0' },
        { min: 3, max: 5, label: '3-5 条', color: '#5b7bf5' },
        { min: 1, max: 2, label: '1-2 条', color: '#b9c6fb' },
        { value: 0, label: '0 条', color: '#f4f6fd' },
      ],
      textStyle: { color: '#7a7f8c' },
    },
    calendar: {
      top: 30,
      left: 40,
      right: 20,
      bottom: 60,
      range: [rangeStart, rangeEnd],
      cellSize: ['auto', 16],
      yearLabel: { show: false },
      monthLabel: { nameMap: 'ZH', color: '#2b2f3a' },
      dayLabel: { nameMap: 'ZH', color: '#7a7f8c', firstDay: 1 },
      itemStyle: { borderColor: '#e6e9f2', borderWidth: 1 },
    },
    series: [
      {
        type: 'heatmap',
        coordinateSystem: 'calendar',
        data,
      },
    ],
  })
}

function handleResize() {
  radarChart && radarChart.resize()
  growthChart && growthChart.resize()
  heatmapChart && heatmapChart.resize()
}

onMounted(() => {
  load()
  window.addEventListener('resize', handleResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  radarChart && radarChart.dispose()
  growthChart && growthChart.dispose()
  heatmapChart && heatmapChart.dispose()
})
</script>

<template>
  <div>
    <div class="card">
      <div class="row" style="align-items: center">
        <h2 style="margin: 0">属性面板</h2>
        <span class="tag">人生等级 Lv.{{ level }}</span>
        <span class="tag">经验 {{ exp }}</span>
      </div>
    </div>

    <!-- v1.10 M3：子维度提示卡（≥95 的主维度；用户拍板放在面板顶部） -->
    <div v-if="subCandidates.length > 0" class="card milestone-card">
      <div v-for="c in subCandidates" :key="c.id" style="margin-bottom: 8px">
        <div>
          🧩 <b>「{{ c.name }}」已达 {{ c.value }} / {{ c.max_value }}</b>
          <span class="muted">—— 继续笼统加分已无信息量，可以让 AI 结合你的记录提议细分方向。</span>
        </div>

        <!-- 未提议 / 已忽略 → 提议入口 -->
        <div v-if="c.state !== 'pending'" class="row" style="margin-top: 6px">
          <button class="btn small primary" :disabled="subBusy" @click="proposeSub(c)">
            <template v-if="subBusy">AI 思考中（约 20~60 秒）…</template>
            <template v-else>{{ c.state === 'dismissed' ? '重新提议' : '让 AI 提议细分方向' }}</template>
          </button>
          <span v-if="c.state === 'dismissed'" class="muted">你已忽略过上次的提议。</span>
        </div>

        <!-- pending → 多选后确认 -->
        <template v-else>
          <div class="muted" style="margin-top: 6px">AI 的提议：{{ c.reason }}</div>
          <div v-for="it in c.items" :key="it.name" style="margin-top: 4px">
            <label style="cursor: pointer">
              <input type="checkbox" :value="it.name" v-model="subChecked[c.id]" />
              <b>{{ it.name }}</b>
              <span class="muted">—— {{ it.description }}</span>
            </label>
          </div>
          <div class="row" style="margin-top: 8px">
            <button class="btn small primary" :disabled="subBusy || (subChecked[c.id] || []).length === 0" @click="confirmSub(c)">
              解锁所选（{{ (subChecked[c.id] || []).length }}）
            </button>
            <button class="btn small" :disabled="subBusy" @click="dismissSub(c)">忽略</button>
          </div>
        </template>
      </div>
    </div>

    <!-- v1.10 P2-2（V3）：热力图移近顶部，不必滚到底部才看得到 -->
    <div class="card">
      <h3>月度活动热力图</h3>
      <p class="muted" style="font-size: 12px; margin: 0 0 6px">
        按<b>实际发生日</b>落格（补记昨天的事件会落在昨天）；今天的格子带红色描边。
      </p>
      <div v-if="heatmap.length === 0" class="muted">暂无记录，去「今日盘点」记一笔后这里会显示活动分布。</div>
      <div ref="heatmapEl" style="width: 100%; height: 200px"></div>
    </div>

    <div class="row">
      <div class="card" style="flex: 1">
        <h3>能力数值</h3>
        <div v-if="visibleAttrs.length === 0" class="muted">暂无属性数据，请先完成角色档案。</div>
        <div v-for="a in visibleAttrs" :key="a.name" class="attr-bar" :style="a.visibility === 'disabled' ? 'opacity: 0.55' : ''">
          <div class="head">
            <span>
              <b>{{ a.name }}</b>
              <!-- v1.8 C3：段位徽章（只加不改，不调整任何图表配置） -->
              <span v-if="a.tier" class="tier-badge" style="margin-left: 6px">{{ a.tier }}</span>
              <span v-if="a.visibility === 'disabled'" class="tag" style="margin-left: 6px">已关闭判定</span>
            </span>
            <span>{{ a.value }} / {{ a.max_value }}</span>
          </div>
          <div class="track">
            <div class="fill" :style="{ width: (a.value / a.max_value) * 100 + '%' }"></div>
          </div>
          <div class="muted" v-if="a.description">{{ a.description }}</div>
          <!-- v1.10 M3：子维度缩进展示（不上雷达图） -->
          <div v-if="subHierarchy[a.name]" class="sub-list">
            <div v-for="s in subHierarchy[a.name]" :key="s.name" class="sub-row">
              <span>└ {{ s.name }}</span>
              <span class="muted">{{ s.value }} / {{ s.max_value }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="card" style="flex: 1">
        <h3>能力雷达图</h3>
        <div v-if="visibleAttrs.length === 0" class="muted">暂无数据。</div>
        <div ref="radarEl" style="width: 100%; height: 320px"></div>
      </div>
    </div>

    <div class="card">
      <h3>成长趋势</h3>
      <!-- v1.10 P2-2（V2）：单维度可切换（默认当前值最低），Y 轴按该维度实际区间缩放 -->
      <div v-if="growthDims.length" class="row" style="flex-wrap: wrap; gap: 6px; margin-bottom: 8px">
        <button
          v-for="d in growthDims"
          :key="d.name"
          class="seg-btn"
          :class="{ active: growthDim === d.name }"
          @click="switchGrowth(d.name)"
        >
          {{ d.name }} {{ Math.round(Number(d.value) || 0) }}
        </button>
      </div>
      <div v-if="history.length === 0" class="muted">暂无成长记录，去「今日盘点」记一笔并确认入账后这里会显示趋势。</div>
      <div ref="growthEl" style="width: 100%; height: 340px"></div>
    </div>
  </div>
</template>
