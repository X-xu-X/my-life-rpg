<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick, reactive } from 'vue'
import * as echarts from 'echarts/core'
import { RadarChart, LineChart, HeatmapChart } from 'echarts/charts'
import { TooltipComponent, GridComponent, RadarComponent, CalendarComponent, VisualMapComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
echarts.use([RadarChart, LineChart, HeatmapChart, TooltipComponent, GridComponent, RadarComponent, CalendarComponent, VisualMapComponent, CanvasRenderer])
import PageHeader from './ui/PageHeader.vue'
import { api } from '../api'
import { toast } from '../composables/useToast'

const attrs = ref([])
const level = ref(1)
const exp = ref(0)
const history = ref([])
const heatmap = ref([])
const baseline = ref({completed:false,kind:'legacy'})
const radarEl = ref(null)
const growthEl = ref(null)
const heatmapEl = ref(null)
const loading=ref(false),loaded=ref(false),error=ref(''),subError=ref('')
const growthLayout=ref(null),radarOpen=ref(false),growthWide=ref(false)
let alive=true,generation=0,radarManual=false,observer=null
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
  const current=++generation; loading.value=true;error.value='';subError.value=''
  try {
    const [attrData,historyData,heatmapData,subData]=await Promise.all([
      api.getAttributes(),api.getAttributeHistory(),api.getHeatmap(),
      api.listSubdimensions().catch(e=>({readError:e.message})),
    ])
    if(!alive || current!==generation)return
    attrs.value=attrData.attributes || []
    baseline.value={completed:attrData.onboarding_completed,kind:attrData.baseline_kind}
    level.value=attrData.level || 1;exp.value=attrData.exp || 0
    history.value=historyData || [];heatmap.value=heatmapData || []
    if(subData.readError)subError.value=subData.readError
    else {
      subThreshold.value=subData.threshold ?? 95
      subCandidates.value=subData.candidates || [];subHierarchy.value=subData.hierarchy || {}
      for(const c of subCandidates.value)if(!(c.id in subChecked))subChecked[c.id]=[]
    }
    loaded.value=true
    await nextTick()
    if(!alive)return
    observeCharts();handleResize()
  } catch(e){if(alive && current===generation)error.value=e.message}
  finally {if(alive && current===generation)loading.value=false}
}
function available(el){return alive && el && el.clientWidth>0 && el.clientHeight>0}
function observeCharts(){
  observer?.disconnect()
  observer=new ResizeObserver(handleResize)
  for(const el of [growthLayout.value,radarEl.value,growthEl.value,heatmapEl.value])if(el)observer.observe(el)
}
async function radarToggle(e){radarOpen.value=e.target.open;await nextTick();if(alive)handleResize()}

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

const chartToken=name=>getComputedStyle(document.documentElement).getPropertyValue(name).trim()
function renderRadar() {
  if (!loaded.value || !radarOpen.value || !available(radarEl.value)) return
  if (!radarChart) radarChart = echarts.init(radarEl.value)
  const names = visibleAttrs.value.map((a) => a.name)
  const values = visibleAttrs.value.map((a) => a.value)
  // v1.10 P2-2（V1）：动态上界——取可见维度最大值，向上取整到 5 的倍数再 +5，下限 10。
  // 轴名附加真实值，避免「形状放大」被误读为绝对水平（文档给出的两个推荐做法之一）。
  const rawMax = values.reduce((m, v) => Math.max(m, Number(v) || 0), 0)
  const dynMax = Math.max(10, Math.ceil(rawMax / 5) * 5 + 5)
  radarChart.setOption({
    textStyle: {fontFamily:chartToken('--font')},
    color: [chartToken('--primary')],
    tooltip: {},
    radar: {
      indicator: names.map((n, i) => ({ name: `${n} ${Math.round(Number(values[i]) || 0)}`, max: dynMax })),
      radius: '58%', // 13 轴：收窄半径，给长轴名留空间
      axisName: { color: chartToken('--text'), fontSize: 13 },
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
  if (!loaded.value || !available(growthEl.value)) return
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
    textStyle: {fontFamily:chartToken('--font')},
    color: [chartToken('--primary')],
    tooltip: { trigger: 'axis' },
    grid: { left: 48, right: 24, top: 30, bottom: 40 },
    xAxis: { type: 'time', axisLabel: { color: chartToken('--text-sub') } },
    yAxis: { type: 'value', min: yMin, max: yMax, axisLabel: { color: chartToken('--text-sub') } },
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
  if (!loaded.value || !available(heatmapEl.value)) return
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
    itemStyle: h.date === todayStr ? { borderColor: chartToken('--positive'), borderWidth: 1.5 } : undefined,
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
      textStyle: { color: chartToken('--text-sub') },
    },
    calendar: {
      top: 30,
      left: 40,
      right: 20,
      bottom: 60,
      range: [rangeStart, rangeEnd],
      cellSize: ['auto', 16],
      yearLabel: { show: false },
      monthLabel: { nameMap: 'ZH', color: chartToken('--text') },
      dayLabel: { nameMap: 'ZH', color: chartToken('--text-sub'), firstDay: 1 },
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
  if(!alive)return
  growthWide.value=!!growthLayout.value && growthLayout.value.clientWidth>=860
  if(!radarManual)radarOpen.value=growthWide.value
  renderRadar();renderGrowth();renderHeatmap()
  if(radarOpen.value && available(radarEl.value))radarChart?.resize()
  if(available(growthEl.value))growthChart?.resize()
  if(available(heatmapEl.value))heatmapChart?.resize()
}
onMounted(()=>{load();window.addEventListener('resize',handleResize)})
onBeforeUnmount(()=>{
  alive=false;generation++;observer?.disconnect()
  window.removeEventListener('resize',handleResize)
  radarChart?.dispose();growthChart?.dispose();heatmapChart?.dispose()
})
</script>

<template>
  <div class="growth-page">
    <PageHeader title="成长" description="从记录里，看见慢慢发生的积累。"><template #actions><button class="btn" :disabled="loading" @click="load">重新读取</button><RouterLink class="btn" to="/reports">历史报告 →</RouterLink></template></PageHeader>
    <p v-if="loading" role="status">正在读取成长数据…</p>
    <div v-if="error" role="alert" class="read-error"><p>{{ error }}{{ loaded?' · 显示上次读取的数据，本次未刷新成功。':'' }}</p><button class="btn" :disabled="loading" @click="load">重新读取</button></div>
    <template v-if="loaded">
      <p v-if="!baseline.completed" class="card">尚未评估。这里的 50 为占位值，不能结算。<RouterLink to="/me">主动选择基线 →</RouterLink></p>
      <p v-else-if="baseline.kind==='neutral'" class="card">未评估基线：13 维各 50 是游戏起点，不是能力测量。以下沿用旧规则 v1.11。</p>
      <div class="level-strip card"><b>人生等级 Lv.{{ level }}</b><span>经验 {{ exp }}</span></div>
      <p v-if="subError" role="alert" class="error">细分方向未读取成功：{{ subError }}。可通过页面重新读取。</p>
    <!-- v1.10 M3：子维度提示卡（≥95 的主维度；用户拍板放在面板顶部） -->
    <div v-if="subCandidates.length > 0" class="card milestone-card">
      <div v-for="c in subCandidates" :key="c.id" style="margin-bottom: 8px">
        <div>
          🧩 <b>「{{ c.name }}」已达 {{ c.value }} / {{ c.max_value }}</b>
          <span class="muted">—— 继续笼统加分已无信息量，可以让 AI 结合你的记录提议细分方向。</span>
        </div>

        <!-- 未提议 / 已忽略 → 提议入口 -->
        <div v-if="c.state !== 'pending'" class="action-group" style="margin-top: 6px">
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
          <div class="action-group" style="margin-top: 8px">
            <button class="btn small primary" :disabled="subBusy || (subChecked[c.id] || []).length === 0" @click="confirmSub(c)">
              解锁所选（{{ (subChecked[c.id] || []).length }}）
            </button>
            <button class="btn small" :disabled="subBusy" @click="dismissSub(c)">忽略</button>
          </div>
        </template>
      </div>
    </div>


      <section class="card">
        <h2>记录活动 · 近四个月</h2>
        <p class="muted">按实际发生日落格，补记会落在对应日期；今天的格子带红色描边。</p>
        <p v-if="!heatmap.length" class="muted">暂无活动记录，去「今天」记一笔。</p>
        <div v-show="heatmap.length" class="heatmap-scroll" role="region" aria-label="近四个月活动图，可用左右方向键滚动" tabindex="0"><div ref="heatmapEl" data-chart="heatmap" class="chart-heatmap"></div></div>
        <p v-if="heatmap.length" class="muted">左右滑动或聚焦后用方向键查看近四个月。</p>
        <details v-if="heatmap.length"><summary>查看记录日期与数量</summary><ul class="chart-data"><li v-for="h in heatmap" :key="h.date">{{ h.date }} · {{ h.count }} 条</li></ul></details>
      </section>
      <div ref="growthLayout" class="growth-layout" :class="{'growth-wide':growthWide}">
        <section class="card">
          <h2>能力数值</h2><p class="muted">游戏分数用于观察积累，不是精确的能力测量。每项说明可展开查看。</p>
          <p v-if="!visibleAttrs.length" class="muted">暂无可见属性数据，请查看角色档案与维度设置。</p>
          <div v-for="a in visibleAttrs" :key="a.name" class="attr-bar">
            <div class="head"><span><b>{{ a.name }}</b> <span v-if="a.tier" class="tier-badge">{{ a.tier }}</span> <span v-if="a.visibility==='disabled'" class="tag">已关闭判定</span></span><span class="attr-value">{{ a.value }} / {{ a.max_value }}</span></div>
            <div class="track"><div class="fill" :style="{width:(a.value/a.max_value)*100+'%'}"></div></div>
            <details v-if="a.description"><summary>说明</summary><p class="muted">{{ a.description }}</p></details>
            <div v-if="subHierarchy[a.name]" class="sub-list"><div v-for="child in subHierarchy[a.name]" :key="child.name" class="sub-row"><span>{{ child.name }}</span><span class="attr-value">{{ child.value }} / {{ child.max_value }}</span></div></div>
          </div>
        </section>
        <details class="card radar-details" :open="radarOpen" @toggle="radarToggle"><summary @click="radarManual=true">能力雷达图</summary><p class="muted">轴上界随当前数值缩放，不能跨截图只比较面积。完整数值见能力列表。</p><p v-if="!visibleAttrs.length" class="muted">暂无数据。</p><div ref="radarEl" data-chart="radar" class="chart-radar"></div></details>
      </div>
      <section class="card">
        <h2>成长趋势</h2>
        <label v-if="growthDims.length" class="trend-mobile">维度<select :value="growthDim" @change="switchGrowth($event.target.value)"><option v-for="d in growthDims" :key="d.name" :value="d.name">{{ d.name }} · {{ d.value }}</option></select></label>
        <div v-if="growthDims.length" class="trend-desktop"><button v-for="d in growthDims" :key="d.name" class="seg-btn" :class="{active:growthDim===d.name}" :aria-pressed="growthDim===d.name" @click="switchGrowth(d.name)">{{ d.name }} {{ d.value }}</button></div>
        <p v-if="!history.length" class="muted">暂无成长记录，在「今天」记录并确认入账后可查看趋势。</p>
        <div v-show="history.length" ref="growthEl" data-chart="growth" class="chart-trend"></div>
        <details v-if="history.length"><summary>查看本维度数据</summary><ul class="chart-data"><li v-for="(h,i) in history.filter(h=>h.name===growthDim).slice().sort((a,b)=>new Date(a.created_at)-new Date(b.created_at))" :key="i">{{ h.created_at }} · {{ h.value_after }}</li></ul></details>
      </section>
    </template>
  </div>
</template>
