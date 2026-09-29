<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import { api } from '../api'

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

// 可见维度：隐藏（hidden）的维度不显示，关闭判定（disabled）的仍显示但标记
const visibleAttrs = computed(() => attrs.value.filter((a) => a.visibility !== 'hidden'))

async function load() {
  const [attrData, historyData, heatmapData] = await Promise.all([
    api.getAttributes(),
    api.getAttributeHistory(),
    api.getHeatmap(),
  ])
  attrs.value = attrData.attributes || []
  level.value = attrData.level || 1
  exp.value = attrData.exp || 0
  history.value = historyData || []
  heatmap.value = heatmapData || []
  await nextTick()
  renderRadar()
  renderGrowth()
  renderHeatmap()
}

function renderRadar() {
  if (!radarEl.value) return
  if (!radarChart) radarChart = echarts.init(radarEl.value)
  const names = visibleAttrs.value.map((a) => a.name)
  const values = visibleAttrs.value.map((a) => a.value)
  radarChart.setOption({
    color: ['#4f6ef7'],
    radar: {
      indicator: names.map((n) => ({ name: n, max: 100 })),
      radius: '65%',
      axisName: { color: '#2b2f3a' },
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

function renderGrowth() {
  if (!growthEl.value) return
  if (!growthChart) growthChart = echarts.init(growthEl.value)
  const names = [...new Set(history.value.map((h) => h.name))]
  if (names.length === 0) {
    growthChart.setOption({})
    return
  }
  const series = names.map((name) => {
    const pts = history.value
      .filter((h) => h.name === name)
      .sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
      .map((h) => [h.created_at, h.value_after])
    return { name, type: 'line', data: pts, smooth: true, showSymbol: true }
  })
  growthChart.setOption({
    color: ['#4f6ef7', '#1f9e6a', '#e0533d', '#d97706', '#8b5cf6', '#0ea5e9'],
    tooltip: { trigger: 'axis' },
    legend: { data: names, textStyle: { color: '#2b2f3a' } },
    grid: { left: 40, right: 20, top: 40, bottom: 40 },
    xAxis: { type: 'time', axisLabel: { color: '#7a7f8c' } },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: { color: '#7a7f8c' } },
    series,
  })
}

function renderHeatmap() {
  if (!heatmapEl.value) return
  if (!heatmapChart) heatmapChart = echarts.init(heatmapEl.value)
  if (heatmap.value.length === 0) {
    heatmapChart.setOption({})
    return
  }
  const data = heatmap.value.map((h) => [h.date, h.count])
  // 最近 12 个月的日历范围
  const now = new Date()
  const start = new Date(now.getFullYear(), now.getMonth() - 11, 1)
  const end = new Date(now.getFullYear(), now.getMonth() + 1, 0)
  const fmt = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
  const maxCount = Math.max(1, ...heatmap.value.map((h) => h.count))
  heatmapChart.setOption({
    tooltip: {
      formatter: (p) => `${p.value[0]}：${p.value[1]} 条记录`,
    },
    visualMap: {
      min: 0,
      max: maxCount,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      inRange: { color: ['#eef1fe', '#a8b9f9', '#4f6ef7'] },
      textStyle: { color: '#7a7f8c' },
    },
    calendar: {
      top: 30,
      left: 40,
      right: 20,
      bottom: 60,
      range: [`${fmt(start)}`, `${fmt(end)}`],
      cellSize: ['auto', 14],
      yearLabel: { show: false },
      monthLabel: { nameMap: 'ZH', color: '#2b2f3a' },
      dayLabel: { nameMap: 'ZH', color: '#7a7f8c', firstDay: 1 },
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
      <div v-if="history.length === 0" class="muted">暂无成长记录，去「记录事件」并确认入账后这里会显示趋势。</div>
      <div ref="growthEl" style="width: 100%; height: 340px"></div>
    </div>

    <div class="card">
      <h3>月度活动热力图</h3>
      <div v-if="heatmap.length === 0" class="muted">暂无记录，去「记录事件」打卡后这里会显示活动分布。</div>
      <div ref="heatmapEl" style="width: 100%; height: 200px"></div>
    </div>
  </div>
</template>
