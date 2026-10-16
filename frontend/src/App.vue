<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from './api'
import { account, setAccount, clearAccount, accountEpoch } from './session'
import AuthView from './components/AuthView.vue'
import ToastHost from './components/ToastHost.vue'
import AppIcon from './components/ui/AppIcon.vue'
import { sectionRoot, returnTarget, beginReturn } from './navigation'
const loading = ref(true)
const error = ref('')
const route = useRoute()
const router = useRouter()
const personalTabs = [{ key:'today', path:'/', label:'今天' }, { key:'journal', path:'/journal', label:'手账' }, { key:'plans', path:'/plans', label:'计划' }, { key:'growth', path:'/growth', label:'成长' }, { key:'me', path:'/me', label:'我的' }]
const tabs=computed(()=>account.value?.role==='owner'?[{key:'today',path:'/admin',label:'概览'},{key:'journal',path:'/admin/users',label:'账号'},{key:'plans',path:'/admin/announcements',label:'公告'},{key:'growth',path:'/admin/site',label:'站点'},{key:'me',path:'/admin/audit',label:'记录'}]:personalTabs)
function selected(tab){return account.value?.role==='owner'?route.path===tab.path:route.meta.section===tab.key}
async function initialize() {
  loading.value = true; error.value = ''
  try { setAccount(await api.me());if(account.value.role==='owner'&&route.meta.workspace!=='admin')await router.replace('/admin');else if(account.value.role!=='owner'&&route.meta.workspace==='admin')await router.replace('/me') }
  catch (e) { clearAccount(); if (!e.message.includes('登录')) error.value = e.message }
  finally { loading.value = false }
}
function lost() { clearAccount(); loading.value = false }
onMounted(() => { window.addEventListener('gol-auth-lost', lost); initialize() })
onUnmounted(() => window.removeEventListener('gol-auth-lost', lost))
</script>
<template>
  <ToastHost />
  <div v-if="loading" class="auth-paper" role="status">正在打开你的手账…</div>
  <AuthView v-else-if="!account" @authenticated="initialize" />
  <div v-else class="app-shell" :key="account.id">
    <aside class="desktop-rail">
      <RouterLink class="brand" :to="account.role==='owner'?'/admin':'/'">游戏人生<span>LifeXP · {{ account.role==='owner'?'站点管理':'一页一日' }}</span></RouterLink>
      <nav aria-label="主要导航"><RouterLink v-for="tab in tabs" :key="tab.key" :to="tab.path" :class="{selected:selected(tab)}" :aria-current="selected(tab) ? 'page' : undefined"><AppIcon :name="tab.key" /> {{ tab.label }}</RouterLink></nav>
      <p class="muted">{{ account.username }}<br />{{ account.timezone }}</p>
    </aside>
    <div class="app-body">
      <header class="mobile-heading"><RouterLink :to="account.role==='owner'?'/admin':'/'">游戏人生</RouterLink><span class="muted">{{ account.role==='owner'?'站点管理':'一页一日' }}</span></header>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <nav v-if="route.meta.section === 'growth'" class="section-links" aria-label="成长功能"><RouterLink to="/growth">历史属性</RouterLink><RouterLink to="/challenges">挑战 · 商店 · 成就</RouterLink></nav>
      <main id="main-content"><RouterLink v-if="route.path!==sectionRoot(route)" class="btn page-back" :to="returnTarget(router,route)" @click="beginReturn(returnTarget(router,route))">← 返回上一页</RouterLink><RouterView :key="account.id + ':' + route.fullPath" /></main>
    </div>
    <nav class="mobile-nav" aria-label="主要导航"><RouterLink v-for="tab in tabs" :key="tab.key" :to="tab.path" :class="{selected:selected(tab)}" :aria-current="selected(tab) ? 'page' : undefined"><AppIcon :name="tab.key" />{{ tab.label }}</RouterLink></nav>
  </div>
</template>
