<script setup>
import { ref,computed,onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { displayTime,localDate } from '../session'
import PageHeader from './ui/PageHeader.vue'
import ProjectManager from './ProjectManager.vue'
import GoalsView from './GoalsView.vue'
import GrowthPolicies from './GrowthPolicies.vue'
import PhaseBrief from './PhaseBrief.vue'
import ItemManager from './ItemManager.vue'
import RecordComposer from './RecordComposer.vue'
import HintCard from './HintCard.vue'
import AttributePanel from './AttributePanel.vue'
import RecordMetrics from './RecordMetrics.vue'
import RewardShop from './RewardShop.vue'
import TrialRules from './TrialRules.vue'
import RecordCalendar from './RecordCalendar.vue'
import ConfirmDialog from './ui/ConfirmDialog.vue'
const route=useRoute(),view=route.meta.detail
const rows=ref([]),wallet=ref(null),loading=ref(true),error=ref('')
const selectedVoucher=ref(null),busy=ref(false)
const title=computed(()=>route.meta.title||'详情')
// 属性变化历史：近 7 天总览 + 属性筛选 + 按天分组。数据全部来自 /attributes/history，不额外请求。
const HISTORY_WINDOW=30
const expanded=ref(false),picked=ref('')
function toDate(v){if(!v)return new Date(0);const raw=typeof v==='string'&&!/(Z|[+-]\d{2}:\d{2})$/.test(v)?v+'+08:00':v;const d=new Date(raw);return Number.isNaN(d.getTime())?new Date(0):d}
function windowStart(anchor,days){const d=new Date(anchor);d.setHours(0,0,0,0);d.setDate(d.getDate()-(days-1));return d}
function fmtNum(v){const n=Number(v);if(!Number.isFinite(n))return '—';const r=Math.round(n*100)/100;return Number.isInteger(r)?String(r):r.toFixed(2).replace(/0$/,'')}
function signed(v){return (v>0?'+':'')+fmtNum(v)}
function clockOf(v){const m=displayTime(v).match(/(\d{1,2}:\d{2})/);return m?m[1]:''}
function dayLabel(d){const key=localDate(d);if(key===localDate())return '今天';const y=new Date();y.setDate(y.getDate()-1);if(key===localDate(y))return '昨天';return displayTime(d,true)}
const attrName=r=>r.name||r.attribute_name||'属性变化'
const historyAll=computed(()=>rows.value.map(r=>({...r,_t:toDate(r.created_at)})).sort((a,b)=>b._t-a._t))
const historyAnchor=computed(()=>historyAll.value[0]?._t||new Date())
const anchorIsToday=computed(()=>localDate(historyAnchor.value)===localDate())
const weekRows=computed(()=>{const start=windowStart(historyAnchor.value,7);return historyAll.value.filter(r=>r._t>=start)})
const weekNet=computed(()=>Math.round(weekRows.value.reduce((s,r)=>s+(Number(r.delta)||0),0)*100)/100)
const historyVisible=computed(()=>{if(expanded.value)return historyAll.value;const start=windowStart(historyAnchor.value,HISTORY_WINDOW);return historyAll.value.filter(r=>r._t>=start)})
const olderCount=computed(()=>{const start=windowStart(historyAnchor.value,HISTORY_WINDOW);return historyAll.value.filter(r=>r._t<start).length})
const attrChips=computed(()=>{const map=new Map();historyVisible.value.forEach(r=>{const n=attrName(r);const c=map.get(n)||{name:n,delta:0,count:0};c.delta+=Number(r.delta)||0;c.count+=1;map.set(n,c)});return [...map.values()].map(c=>({...c,delta:Math.round(c.delta*100)/100})).sort((a,b)=>Math.abs(b.delta)-Math.abs(a.delta))})
const historyFiltered=computed(()=>picked.value?historyVisible.value.filter(r=>attrName(r)===picked.value):historyVisible.value)
const historyGroups=computed(()=>{const out=[];historyFiltered.value.forEach(r=>{const key=localDate(r._t);let g=out[out.length-1];if(!g||g.key!==key){g={key,label:dayLabel(r._t),net:0,rows:[]};out.push(g)}g.rows.push(r);g.net+=Number(r.delta)||0});return out.map(g=>({...g,net:Math.round(g.net*100)/100}))})
function toggleOlder(){expanded.value=!expanded.value;picked.value=''}
// 金币流水：一天一张卡；日记只出当日总额，事件各一行，旧数据（kind 缺失）归其他。
const ledgerGroups=computed(()=>{
  const map=new Map()
  for(const r of wallet.value?.ledger||[]){
    const day=r.day||localDate(r.created_at)
    if(!map.has(day))map.set(day,{day,total:0,diaries:[],events:[],others:[]})
    const g=map.get(day);g.total+=Number(r.delta)||0
    if(r.kind==='diary')g.diaries.push(r);else if(r.kind==='event')g.events.push(r);else g.others.push(r)
  }
  const today=localDate(),d=new Date();d.setDate(d.getDate()-1);const yesterday=localDate(d)
  return [...map.values()].sort((a,b)=>b.day.localeCompare(a.day)).map(g=>({
    ...g,label:g.day===today?'今天':g.day===yesterday?'昨天':g.day,
    diaryTotal:Math.round(g.diaries.reduce((s,r)=>s+(Number(r.delta)||0),0)*100)/100,
    open:g.day===today||g.day===yesterday}))
})
async function load(){try{
 if(view==='ledger'){wallet.value=await api.getCoins(200);rows.value=wallet.value.ledger||[]}
 if(['vouchers','redemptions'].includes(view)){const [result,timers]=await Promise.all([api.listRedemptions(),api.flow('/timers')]);rows.value=(result.redemptions||[]).map(r=>({...r,duration_seconds:timers.vouchers.find(v=>v.redemption.id===r.id)?.redemption.duration_seconds}))}
 if(view==='history')rows.value=await api.getAttributeHistory()
}catch(e){error.value=e.message}finally{loading.value=false}}
onMounted(load)
async function fulfill(){busy.value=true;try{await api.fulfillRedemption(selectedVoucher.value.id,'本人确认已使用');selectedVoucher.value=null;await load()}catch(e){error.value=e.message}finally{busy.value=false}}
</script>
<template><div class="journal-page detail-page"><PageHeader :title="title"/><p v-if="error" class="error">{{ error }}</p>
 <template v-if="view==='capture'"><HintCard id="record-help"><p>先留下一件事。只保存无需模型；分析建议经过核对后才结算，首记资格独立保留。</p></HintCard><RecordComposer/></template>
 <ProjectManager v-else-if="view==='projects'" :category="route.query.category||undefined"/>
 <ProjectManager v-else-if="view==='today-projects'" today-only :category="route.query.category||'plan'"/>
 <ProjectManager v-else-if="view==='care'" category="care"/>
 <ProjectManager v-else-if="view==='project'" :focus-key="route.query.key"/>
 <GoalsView v-else-if="view==='goals'"/>
 <GrowthPolicies v-else-if="view==='mainline'"/>
 <PhaseBrief v-else-if="view==='context'"/>
 <ItemManager v-else-if="view==='legacy'"/>
 <AttributePanel v-else-if="view==='attributes'"/>
 <template v-else-if="view==='calendar'"><RecordCalendar/><RecordMetrics/></template>
 <RewardShop v-else-if="view==='shop'||view==='reward-management'" :management="view==='reward-management'"/>
 <TrialRules v-else-if="view==='rules'"/>
 <PhaseBrief v-else-if="view==='agreements'" constraints/>
 <section v-else-if="view==='personal'" class="hub-card hub-menu-group"><RouterLink class="hub-row" to="/personal-information"><span class="hub-row-text"><strong>补充长期信息</strong><small>兴趣、偏好与自愿提供的背景</small></span><span>›</span></RouterLink><RouterLink class="hub-row" to="/onboarding"><span>回看问卷</span><span>›</span></RouterLink><RouterLink class="hub-row" to="/returning"><span>更新近期近况</span><span>›</span></RouterLink><RouterLink class="hub-row" to="/anchors"><span>AI 如何判断</span><span>›</span></RouterLink></section>
 <template v-else-if="view==='ledger'">
  <section class="hub-wallet"><span>当前余额</span><strong>{{ wallet?.balance??'—' }}<small> 币</small></strong></section>
  <p v-if="loading">正在读取收支…</p>
  <p v-else-if="!ledgerGroups.length" class="hub-empty">还没有金币记录。</p>
  <section v-for="g in ledgerGroups" :key="g.day" class="hub-card">
   <details :open="g.open">
    <summary class="hub-row"><span class="hub-row-text"><strong>{{ g.label }}</strong></span><span :class="g.total>=0?'hub-change':'hub-spend'">{{ g.total>0?'+':'' }}{{ g.total }}</span></summary>
    <RouterLink v-if="g.diaries.length" class="hub-row" :to="'/diary?date='+g.day"><span class="hub-row-text"><strong>日记</strong><small>查看原文 ›</small></span><span :class="g.diaryTotal>=0?'hub-change':'hub-spend'">{{ g.diaryTotal>0?'+':'' }}{{ g.diaryTotal }}</span></RouterLink>
    <div v-for="r in g.events" :key="r.id" class="hub-row"><span class="hub-row-text"><strong>{{ r.reason||'事件' }}</strong></span><span :class="r.delta>0?'hub-change':'hub-spend'">{{ r.delta>0?'+':'' }}{{ r.delta }}</span></div>
    <div v-for="r in g.others" :key="r.id" class="hub-row"><span class="hub-row-text"><strong>{{ r.reason||r.source }}</strong></span><span :class="r.delta>0?'hub-change':'hub-spend'">{{ r.delta>0?'+':'' }}{{ r.delta }}</span></div>
   </details>
  </section>
 </template>
 <template v-else-if="view==='history'">
  <p v-if="loading">正在读取变化…</p>
  <p v-else-if="!rows.length" class="hub-empty">还没有确认的属性变化。</p>
  <template v-else>
   <section class="hub-card attr-summary">
    <div class="attr-summary-main"><span>最近 7 天净变化</span><strong :class="weekNet>=0?'hub-change':'hub-spend'">{{ signed(weekNet) }}</strong><small>{{ weekRows.length }} 条变化<template v-if="!anchorIsToday"> · 截至 {{ displayTime(historyAnchor,true) }}</template></small></div>
    <div v-if="attrChips.length>1" class="attr-chips">
     <button type="button" class="attr-chip" :class="{active:!picked}" @click="picked=''">全部<em>{{ historyVisible.length }}</em></button>
     <button v-for="c in attrChips" :key="c.name" type="button" class="attr-chip" :class="{active:picked===c.name}" @click="picked= picked===c.name?'':c.name">{{ c.name }}<em :class="c.delta>=0?'is-up':'is-down'">{{ signed(c.delta) }}</em></button>
    </div>
   </section>
   <p v-if="!historyFiltered.length" class="hub-empty">这段时间没有变化。<button v-if="!expanded&&olderCount" type="button" class="attr-link" @click="toggleOlder">查看更早的记录 ›</button></p>
   <section v-for="g in historyGroups" :key="g.key" class="hub-card attr-group">
    <header class="attr-day"><strong>{{ g.label }}</strong><span :class="g.net>=0?'hub-change':'hub-spend'">{{ signed(g.net) }}</span></header>
    <article v-for="(h,i) in g.rows" :key="g.key+'-'+i" class="hub-row attr-row">
     <span class="hub-row-text">
      <strong>{{ attrName(h) }} <span :class="h.delta>=0?'hub-change':'hub-spend'">{{ signed(h.delta) }}</span></strong>
      <small v-if="h.reason">{{ h.reason }}</small>
      <small v-if="h.value_after!==null&&h.value_after!==undefined" class="attr-value">{{ fmtNum(h.value_after-(Number(h.delta)||0)) }} → {{ fmtNum(h.value_after) }}</small>
      <RouterLink v-if="h.event_id" :to="'/events/'+h.event_id" class="hub-inline-link">查看原记录 ›</RouterLink>
     </span>
     <small class="attr-time">{{ clockOf(h.created_at) }}</small>
    </article>
   </section>
   <button v-if="expanded||olderCount" type="button" class="btn attr-more" @click="toggleOlder">{{ expanded?'收起，只看近 30 天':'查看更早的 '+olderCount+' 条记录' }}</button>
  </template>
 </template>
 <template v-else-if="view==='vouchers'||view==='redemptions'"><section class="hub-card"><p v-if="loading">正在读取兑换记录…</p><p v-if="!loading&&!rows.length" class="hub-empty">还没有兑换记录。<RouterLink to="/rewards/shop">去挑一份奖励 ›</RouterLink></p><article v-for="r in rows.filter(r=>view==='redemptions'||r.status!=='fulfilled')" :key="r.id" class="hub-row"><span class="hub-row-text"><strong>{{ r.item_name||'已兑换的奖励' }}</strong><small>{{ r.coin_spent }} 币 · {{ r.status==='fulfilled'?'已使用':'待使用' }}<template v-if="r.duration_seconds"> · {{ r.duration_seconds/60 }} 分钟</template></small></span><RouterLink v-if="r.duration_seconds&&r.status!=='fulfilled'" class="btn" to="/timers">去使用</RouterLink><button v-else-if="r.status!=='fulfilled'" class="btn" @click="selectedVoucher=r">确认已使用</button></article><p v-if="!loading&&view==='vouchers'&&rows.length&&!rows.some(r=>r.status!=='fulfilled')" class="hub-empty">当前没有未使用的券。</p></section></template>
 <ConfirmDialog :open="!!selectedVoucher" title="确认这份奖励已使用？" confirm-label="确认已使用" :busy="busy" @cancel="selectedVoucher=null" @confirm="fulfill"><p>{{ selectedVoucher?.item_name }}</p><p>这里只记录已使用，不再扣金币。</p></ConfirmDialog>
</div></template>
