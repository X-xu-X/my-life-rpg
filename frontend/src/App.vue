<script setup>
import { ref, onMounted } from 'vue'
import { api } from './api'
import Onboarding from './components/Onboarding.vue'
import AttributePanel from './components/AttributePanel.vue'
import EventForm from './components/EventForm.vue'
import TodayCheckin from './components/TodayCheckin.vue'
import TimelineView from './components/TimelineView.vue'
import JournalView from './components/JournalView.vue'
import JudgmentList from './components/JudgmentList.vue'
import GoalsView from './components/GoalsView.vue'
import ChallengeView from './components/ChallengeView.vue'
import AnchorsView from './components/AnchorsView.vue'
import SettingsView from './components/SettingsView.vue'

const tabs = [
  { key: 'panel', label: '属性面板' },
  { key: 'today', label: '今日盘点' },
  { key: 'event', label: '记录事件' },
  { key: 'timeline', label: '手账本' },
  { key: 'judgments', label: '判定中心' },
  { key: 'goals', label: '目标' },
  { key: 'challenge', label: '挑战' },
  { key: 'anchors', label: '锚点库' },
  { key: 'onboarding', label: '角色档案' },
  { key: 'journal', label: '纯享记录' },
  { key: 'settings', label: '设置' },
]

const activeTab = ref('panel')
const hasProfile = ref(false)
const attrCount = ref(0)
const backendOk = ref(false) // v1.1：后端连接状态
const backendChecked = ref(false)

async function refreshProfile() {
  try {
    const data = await api.getAttributes()
    attrCount.value = data.attributes?.length || 0
    hasProfile.value = attrCount.value > 0
  } catch (e) {
    console.warn('获取属性失败', e)
  }
}

async function checkHealth() {
  try {
    await api.health()
    backendOk.value = true
  } catch {
    backendOk.value = false
  } finally {
    backendChecked.value = true
  }
}

function onProfileCreated() {
  refreshProfile()
  activeTab.value = 'panel'
}

onMounted(() => {
  refreshProfile()
  checkHealth()
})
</script>

<template>
  <header>
    <h1>游戏人生 <span class="muted">· Game of Life</span></h1>
    <p class="muted">记录真实生活事件，AI 依据科学标准判定属性点增减，把成长变成一场可量化的 RPG。</p>
  </header>

  <!-- 后端连接状态提示（v1.1） -->
  <div
    v-if="backendChecked && !backendOk"
    class="conn-banner conn-error"
  >
    ⚠️ 后端未连接（无法访问 /api/health）。请先运行 <code>start.bat</code> 启动后端，再刷新本页。
  </div>
  <div v-else-if="backendChecked && backendOk" class="conn-banner conn-ok">
    ✓ 后端已连接
  </div>

  <nav class="nav">
    <button
      v-for="t in tabs"
      :key="t.key"
      class="btn"
      :class="{ active: activeTab === t.key }"
      @click="activeTab = t.key"
    >
      {{ t.label }}
    </button>
  </nav>

  <!-- 首次使用引导 -->
  <div v-if="!hasProfile && activeTab !== 'onboarding'" class="card">
    <p class="muted">你还没有建立角色档案。先完成一次「角色档案」问卷，AI 会为你生成初始属性面板。</p>
    <button class="btn primary" @click="activeTab = 'onboarding'">开始建立角色档案 →</button>
  </div>

  <Onboarding v-if="activeTab === 'onboarding'" @created="onProfileCreated" />
  <AttributePanel v-else-if="activeTab === 'panel'" />
  <TodayCheckin v-else-if="activeTab === 'today'" @go-judgments="activeTab = 'judgments'" />
  <EventForm
    v-else-if="activeTab === 'event'"
    @go-judgments="activeTab = 'judgments'"
    @go-items="activeTab = 'settings'"
  />
  <TimelineView v-else-if="activeTab === 'timeline'" />
  <JudgmentList v-else-if="activeTab === 'judgments'" />
  <GoalsView v-else-if="activeTab === 'goals'" />
  <ChallengeView v-else-if="activeTab === 'challenge'" />
  <AnchorsView v-else-if="activeTab === 'anchors'" />
  <JournalView v-else-if="activeTab === 'journal'" />
  <SettingsView v-else-if="activeTab === 'settings'" />
</template>
