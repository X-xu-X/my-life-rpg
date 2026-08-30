<script setup>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import { api } from '../api'

const attrs = ref([])
const level = ref(1)
const exp = ref(0)
const history = ref([])
const chartEl = ref(null)
let chart = null

async function load() {
  const [attrData, historyData] = await Promise.all([api.getAttributes(), api.getAttributeHistory()])
  attrs.value = attrData.attributes || []
  level.value = attrData.level || 1
  exp.value = attrData.exp || 0
  history.value = historyData || []
  await nextTick()
  renderRadar()
}

function renderRadar() {
  if (!chartEl.value) return
  if (!chart) chart = echarts.init(chartEl.value)
  const names = attrs.value.map((a) => a.name)
  const values = attrs.value.map((a) => a.value)
  chart.setOption({
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

function handleResize() {
  chart && chart.resize()
}

onMounted(() => {
  load()
  window.addEventListener('resize', handleResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chart && chart.dispose()
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
        <div v-if="attrs.length === 0" class="muted">暂无属性数据，请先完成角色档案。</div>
        <div v-for="a in attrs" :key="a.name" class="attr-bar">
          <div class="head">
            <span><b>{{ a.name }}</b></span>
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
        <div v-if="attrs.length === 0" class="muted">暂无数据。</div>
        <div ref="chartEl" style="width: 100%; height: 320px"></div>
      </div>
    </div>
  </div>
</template>
