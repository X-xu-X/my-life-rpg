<script setup>
import { ref, computed, onActivated, onDeactivated } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { account, accountEpoch, clearAccount, localDate, storageKey } from '../session'
import AppIcon from './ui/AppIcon.vue'
import TrialRules from './TrialRules.vue'
import DailyPrompts from './DailyPrompts.vue'
import HolidayGift from './HolidayGift.vue'
defineOptions({name:'PageHub'})
const route=useRoute(),page=route.meta.section
const wallet=ref(null),records=ref([]),projects=ref([]),goals=ref([]),attrs=ref([]),history=ref([]),achievements=ref([]),pending=ref([]),loading=ref(true),error=ref('')
const abilityOpen=ref(false)
try{abilityOpen.value=sessionStorage.getItem(storageKey('ability-open'))==='true'}catch{}
function disclosure(e){abilityOpen.value=e.target.open;try{sessionStorage.setItem(storageKey('ability-open'),String(e.target.open))}catch{}}
const text={today:['今天','先记录眼前的小事。'],plans:['计划','安排与目标，各自清楚。'],growth:['成长','看见积累，需要时再看数字。'],rewards:['奖励','选一份想要的奖励。'],me:['我的','资料、偏好与账号设置。']}
const title=computed(()=>text[page]?.[0]||'人生手账'),subtitle=computed(()=>text[page]?.[1]||'')
const list=v=>Array.isArray(v)?v:v?.items||[]
let active=true,sequence=0
const epoch=accountEpoch
const requests={today:['wallet','records','projects','pending'],plans:['projects','goals'],growth:['attrs','history','achievements'],rewards:['wallet'],me:[]}
const loaders={wallet:()=>api.getCoins(),records:()=>api.records({date:localDate()}),projects:()=>api.flow('/projects?day='+localDate()),goals:()=>api.listGoals(),attrs:()=>api.getAttributes(),history:()=>api.getAttributeHistory(),achievements:()=>api.flow('/achievements'),pending:()=>api.pending()}
async function load(){
 active=true;const ticket=++sequence;loading.value=true;error.value=''
 const keys=requests[page]||[],results=await Promise.allSettled(keys.map(k=>loaders[k]()))
 if(!active||ticket!==sequence||epoch!==accountEpoch)return
 if(results.some(r=>r.status==='rejected'))error.value='有一部分摘要暂时没读到，可以重新读取。'
 const refs={wallet,records,projects,goals,attrs,history,achievements,pending}
 results.forEach((r,i)=>{if(r.status!=='fulfilled')return;const key=keys[i];refs[key].value=key==='wallet'?r.value:key==='attrs'?r.value.attributes||[]:key==='achievements'?list(r.value).filter(a=>a.unlocked):list(r.value)})
 loading.value=false
}
function visibility(){if(!document.hidden&&active)load()}
onActivated(()=>{load();document.addEventListener('visibilitychange',visibility)})
onDeactivated(()=>{active=false;sequence++;document.removeEventListener('visibilitychange',visibility)})
async function logout(){try{await api.logout();clearAccount()}catch(e){error.value=e.message}}
const todayProjects=computed(()=>projects.value.filter(p=>p.show_today&&!p.removed&&p.enabled))
const planRows=computed(()=>projects.value.filter(p=>p.category==='plan'&&!p.removed))
const careRows=computed(()=>projects.value.filter(p=>p.category==='care'&&!p.removed))
const activeGoals=computed(()=>goals.value.filter(g=>g.status==='active'))
const latest=computed(()=>records.value.filter(e=>e.record_kind!=='diary').slice(0,2))
const recentChanges=computed(()=>history.value.slice(0,3))
const completion=p=>({recorded:'已记下',skipped:'今天跳过',done:'已完成',partial:'部分完成',missed:'未完成'}[p.entry?.state||p.entry?.outcome]||'待记录')
const projectLink=p=>'/plans/item?key='+encodeURIComponent(p.key)
const sign=n=>Number(n)>0?'+':''
</script>
<template>
<div class="journal-page" :data-hub="page">
 <header class="hub-heading"><div><p class="hub-eyebrow">{{ page==='today'?localDate():'LifeXP · 一页一日' }}</p><h1>{{ title }}</h1><p class="hub-subtitle">{{ subtitle }}</p></div><RouterLink v-if="page==='today'" class="hub-round-link" to="/pending" aria-label="查看待确认事项"><AppIcon name="plans"/><span v-if="pending.length" class="hub-dot">{{ pending.length }}</span></RouterLink><RouterLink v-else-if="page==='me'" class="hub-round-link" to="/security" aria-label="账号安全"><AppIcon name="me"/></RouterLink></header>
 <p v-if="loading" class="hub-loading" role="status">正在读取摘要…</p><p v-if="error" class="error">{{ error }} <button class="text-button" @click="load">重新读取</button></p>

 <template v-if="page==='today'">
  <section class="hub-write-card"><div><span class="hub-kicker">留下一笔</span><h2>今天发生了什么？</h2><p>一件小事，或一篇晚间日记。</p></div><div class="hub-write-actions"><RouterLink class="btn primary" to="/capture">＋ 记一件事</RouterLink><RouterLink class="btn" to="/diary">写日记</RouterLink></div></section>
  <div class="hub-today-grid"><div class="hub-main-column">
   <section class="hub-card"><div class="hub-section-heading"><h2>今天的安排 <span class="hub-count">{{ todayProjects.filter(p=>p.category==='plan').length }}</span></h2><RouterLink to="/plans/today">查看全部 ›</RouterLink></div>
    <RouterLink v-for="p in todayProjects.filter(p=>p.category==='plan').slice(0,3)" :key="p.key" :to="projectLink(p)" class="hub-row"><span class="hub-row-icon"><AppIcon name="plans"/></span><span class="hub-row-text"><strong>{{ p.name }}</strong><small>{{ p.rule?.planned_minutes ? p.rule.planned_minutes+' 分钟 · ':'' }}{{ completion(p) }}</small></span><span class="hub-chevron">›</span></RouterLink><p v-if="!loading&&!todayProjects.some(p=>p.category==='plan')" class="hub-empty">今天没有排期，按自己的节奏来。</p>
   </section>
   <details class="hub-card hub-care-disclosure"><summary><span><AppIcon name="today"/> 照顾自己 <small>{{ todayProjects.filter(p=>p.category==='care').length }} 项</small></span><span class="hub-chevron">⌄</span></summary><div class="hub-disclosure-body"><RouterLink v-for="p in todayProjects.filter(p=>p.category==='care')" :key="p.key" :to="projectLink(p)" class="hub-row"><span class="hub-row-text"><strong>{{ p.name }}</strong><small>{{ p.rule?.note||completion(p) }}</small></span><span class="hub-chevron">›</span></RouterLink><RouterLink class="hub-inline-link" to="/plans/care">管理照顾清单 ›</RouterLink></div></details>
  </div><aside class="hub-side-column">
   <RouterLink class="hub-card hub-mini-card" to="/pending"><span class="hub-mini-icon violet"><AppIcon name="journal"/></span><div><strong>{{ pending.length }} 项待确认</strong><p>查看分析建议与入账</p></div><span class="hub-chevron">›</span></RouterLink>
   <RouterLink class="hub-card hub-mini-card" to="/rewards"><span class="hub-mini-icon peach"><AppIcon name="rewards"/></span><div><strong>{{ wallet?.balance??'—' }} 金币</strong><p>去看看想要的奖励</p></div><span class="hub-chevron">›</span></RouterLink>
   <section class="hub-card hub-latest"><div class="hub-section-heading"><h2>最近记下的</h2><RouterLink to="/journal">搜索 ›</RouterLink></div><RouterLink v-for="e in latest" :key="e.id" :to="'/events/'+e.id" class="hub-row"><span class="hub-row-text"><strong>{{ e.title||e.content }}</strong><small>{{ e.occurred_on||String(e.created_at).slice(0,10) }}</small></span><span class="hub-chevron">›</span></RouterLink></section>
   <TrialRules compact summary-only @changed="load"/><DailyPrompts/><HolidayGift/>
  </aside></div>
 </template>

 <template v-else-if="page==='plans'">
  <div class="hub-tabs" aria-label="计划快捷入口"><RouterLink to="/plans/today">今日安排</RouterLink><RouterLink to="/plans/all">全部计划</RouterLink><RouterLink to="/plans/care">照顾自己</RouterLink></div>
  <div class="hub-two-columns"><section class="hub-card"><div class="hub-section-heading"><h2>进行中的计划 <span class="hub-count">{{ planRows.length }}</span></h2><RouterLink to="/plans/all">管理 ›</RouterLink></div><RouterLink v-for="p in planRows.slice(0,3)" :key="p.key" :to="projectLink(p)" class="hub-row"><span class="hub-row-icon"><AppIcon name="plans"/></span><span class="hub-row-text"><strong>{{ p.name }}</strong><small>{{ p.rule?.planned_minutes?p.rule.planned_minutes+' 分钟 · ':'' }}{{ p.rule?.frequency==='daily'?'每天':'按排期出现' }}</small></span><span class="hub-chevron">›</span></RouterLink><RouterLink class="hub-inline-link" to="/plans/all">添加或管理计划 ›</RouterLink></section>
   <section class="hub-card"><div class="hub-section-heading"><h2>目标与主线</h2><RouterLink to="/plans/goals">查看 ›</RouterLink></div><RouterLink v-for="g in activeGoals.slice(0,2)" :key="g.id" to="/plans/goals" class="hub-row"><span class="hub-row-icon green"><AppIcon name="growth"/></span><span class="hub-row-text"><strong>{{ g.description }}</strong><small>{{ g.metric||'查看目标进度' }}</small></span><span class="hub-chevron">›</span></RouterLink><RouterLink class="hub-inline-link" to="/plans/mainline">查看当前主线与关联规则 ›</RouterLink></section></div>
  <section class="hub-card"><RouterLink class="hub-row" to="/plans/care"><span class="hub-row-icon peach"><AppIcon name="today"/></span><span class="hub-row-text"><strong>照顾自己的清单</strong><small>{{ careRows.length }} 项 · 内容与数量由你设置</small></span><span class="hub-chevron">›</span></RouterLink><RouterLink class="hub-row" to="/plans/timer"><span class="hub-row-icon"><AppIcon name="today"/></span><span class="hub-row-text"><strong>开始计划计时</strong><small>仅列出设置了时长的行动计划</small></span><span class="hub-chevron">›</span></RouterLink></section>
  <details class="hub-card hub-more"><summary>其他安排 <span class="hub-chevron">⌄</span></summary><div class="hub-disclosure-body"><RouterLink class="hub-row" to="/plans/context"><span>近期阶段与背景</span><span>›</span></RouterLink><RouterLink class="hub-row" to="/challenges"><span>挑战与原有合同</span><span>›</span></RouterLink><RouterLink class="hub-row" to="/plans/legacy"><span>原有次数项目与历史</span><span>›</span></RouterLink></div></details>
 </template>

 <template v-else-if="page==='growth'">
  <section class="hub-card hub-growth-intro"><span class="hub-kicker">最近的积累</span><h2>每一小步，都留得下来。</h2><p>{{ history.length? '已确认的变化会记录在这里，点开可以追溯到原事件。':'这里将显示你确认入账后的属性变化。' }}</p><RouterLink class="hub-inline-link" to="/growth/history">查看变化历史 ›</RouterLink></section>
  <div class="hub-two-columns"><section class="hub-card"><div class="hub-section-heading"><h2>最近变化</h2><RouterLink to="/growth/history">全部 ›</RouterLink></div><div v-for="(h,i) in recentChanges" :key="i" class="hub-row"><span class="hub-row-text"><strong>{{ h.attribute_name||h.name||'已确认的行动' }}</strong><small>{{ h.reason||'来自已确认的记录' }}</small></span><span class="hub-change">{{ sign(h.delta) }}{{ h.delta }}</span></div><p v-if="!history.length" class="hub-empty">还没有确认的属性变化。</p></section>
   <section class="hub-card"><div class="hub-section-heading"><h2>成就</h2><RouterLink to="/achievements">查看全部 ›</RouterLink></div><div class="hub-achievement-preview"><span class="hub-achievement-icon">✦</span><div><strong>{{ achievements.length?'已留下 '+achievements.length+' 项成就':'慢慢积累自己的里程碑' }}</strong><p>成就与奖励统一在这里回看。</p></div></div></section></div>
  <details class="hub-card hub-ability" :open="abilityOpen" @toggle="disclosure"><summary><span><AppIcon name="growth"/> 能力数值 <small>{{ attrs.filter(a=>a.visibility!=='hidden').length }} 项</small></span><span class="hub-chevron">⌄</span></summary><div class="hub-disclosure-body"><p class="hub-small-note">展开查看游戏数值，也可以继续追溯变化。</p><div class="hub-ability-grid"><div v-for="a in attrs.filter(a=>a.visibility!=='hidden')" :key="a.name" class="hub-ability-row"><span>{{ a.name }}</span><strong>{{ Number(a.value).toFixed(2) }}</strong></div></div><RouterLink class="hub-inline-link" to="/growth/attributes">完整数值、雷达图与维度设置 ›</RouterLink></div></details>
  <section class="hub-card hub-menu-group"><RouterLink class="hub-row" to="/growth/calendar"><span class="hub-row-text"><strong>记录日历与天数</strong><small>事件与日记分别统计</small></span><span class="hub-chevron">›</span></RouterLink><RouterLink class="hub-row" to="/reports"><span class="hub-row-text"><strong>成长报告</strong><small>按周期回看，不挤在当前页</small></span><span class="hub-chevron">›</span></RouterLink></section>
 </template>

 <template v-else-if="page==='rewards'">
  <section class="hub-wallet"><div><span>当前金币</span><strong>{{ wallet?.balance??'—' }}<small> 币</small></strong></div><RouterLink to="/rewards/ledger">收支明细 ›</RouterLink></section>
  <div class="hub-two-columns"><RouterLink class="hub-card hub-feature-link" to="/rewards/shop"><span class="hub-mini-icon peach"><AppIcon name="rewards"/></span><div><h2>选一份奖励</h2><p>自己的心愿，由 AI 评估金币价格。</p></div><span class="hub-chevron">›</span></RouterLink><RouterLink class="hub-card hub-feature-link" to="/rewards/vouchers"><span class="hub-mini-icon violet"><AppIcon name="journal"/></span><div><h2>我的券</h2><p>查看已兑换的券，再决定什么时候用。</p></div><span class="hub-chevron">›</span></RouterLink></div>
  <section class="hub-card"><RouterLink class="hub-row" to="/timers"><span class="hub-row-icon green"><AppIcon name="today"/></span><span class="hub-row-text"><strong>基础娱乐与娱乐计时</strong><small>基础额度、已兑换的计时娱乐</small></span><span class="hub-chevron">›</span></RouterLink><RouterLink class="hub-row" to="/rewards/history"><span class="hub-row-text"><strong>兑换记录</strong></span><span class="hub-chevron">›</span></RouterLink><RouterLink class="hub-row" to="/rewards/manage"><span class="hub-row-text"><strong>管理奖励</strong><small>调整展示、移除或恢复心愿</small></span><span class="hub-chevron">›</span></RouterLink></section>
  <details class="hub-card hub-more"><summary>娱乐约定与特殊奖励 <span class="hub-chevron">⌄</span></summary><div class="hub-disclosure-body"><RouterLink class="hub-row" to="/rewards/rules"><span>基础额度与首记领取</span><span>›</span></RouterLink><RouterLink class="hub-row" to="/rewards/agreements"><span>娱乐约定</span><span>›</span></RouterLink><RouterLink class="hub-row" to="/special-vouchers"><span>特殊券与原有历史</span><span>›</span></RouterLink></div></details>
 </template>

 <template v-else-if="page==='me'">
  <section v-if="!account.onboarding_completed" class="hub-card"><h2>选择游戏起点</h2><p class="hub-small-note">可以继续问卷，也可以先用未评估基线开始。</p><RouterLink class="hub-inline-link" to="/me/baseline">选择基线 ›</RouterLink></section><section class="hub-profile"><span class="hub-avatar">{{ account.username?.slice(0,1) }}</span><div><h2>{{ account.username }}</h2><p>一页一日，按自己的节奏。</p></div><RouterLink to="/me/account">账号 ›</RouterLink></section>
  <section class="hub-card hub-menu-group"><RouterLink class="hub-row" to="/me/personal"><span class="hub-row-icon"><AppIcon name="me"/></span><span class="hub-row-text"><strong>个人资料与问卷</strong><small>长期信息、问卷历史与近期近况</small></span><span class="hub-chevron">›</span></RouterLink><RouterLink class="hub-row" to="/settings"><span class="hub-row-icon"><AppIcon name="growth"/></span><span class="hub-row-text"><strong>AI 与数据</strong><small>模型配置、数据导出</small></span><span class="hub-chevron">›</span></RouterLink><RouterLink class="hub-row" to="/preferences"><span class="hub-row-icon"><AppIcon name="plans"/></span><span class="hub-row-text"><strong>显示与提示</strong><small>提示是否继续显示，由你决定</small></span><span class="hub-chevron">›</span></RouterLink><RouterLink class="hub-row" to="/important-days"><span class="hub-row-icon peach"><AppIcon name="today"/></span><span class="hub-row-text"><strong>重要日子</strong><small>生日、纪念日及其他日子</small></span><span class="hub-chevron">›</span></RouterLink></section>
  <section class="hub-card hub-menu-group"><RouterLink class="hub-row" to="/announcements"><span>站内公告</span><span>›</span></RouterLink><RouterLink class="hub-row" to="/feedback"><span>意见与问题</span><span>›</span></RouterLink><RouterLink class="hub-row" to="/security"><span>账号安全</span><span>›</span></RouterLink></section>
  <button v-if="account.mode==='cloud'" class="btn" @click="logout">退出登录</button>
 </template>
</div>
</template>
