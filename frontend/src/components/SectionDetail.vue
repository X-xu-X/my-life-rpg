<script setup>
import { ref,computed,onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { displayTime } from '../session'
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
 <template v-else-if="view==='ledger'"><section class="hub-wallet"><span>当前余额</span><strong>{{ wallet?.balance??'—' }}<small> 币</small></strong></section><section class="hub-card"><p v-if="loading">正在读取收支…</p><div v-for="r in rows" :key="r.id" class="hub-row"><span class="hub-row-text"><strong>{{ r.reason||r.source }}</strong><small>{{ displayTime(r.created_at) }}</small></span><span :class="r.delta>0?'hub-change':'hub-spend'">{{ r.delta>0?'+':'' }}{{ r.delta }}</span></div></section></template>
 <template v-else-if="view==='history'"><section class="hub-card"><p v-if="loading">正在读取变化…</p><p v-if="!loading&&!rows.length" class="hub-empty">还没有确认的属性变化。</p><article v-for="(h,i) in rows" :key="i" class="hub-row"><span class="hub-row-text"><strong>{{ h.attribute_name||h.name||'属性变化' }} <span class="hub-change">{{ h.delta>0?'+':'' }}{{ h.delta }}</span></strong><small>{{ h.reason }}</small><RouterLink v-if="h.event_id" :to="'/events/'+h.event_id" class="hub-inline-link">查看原记录 ›</RouterLink></span><small>{{ displayTime(h.created_at) }}</small></article></section></template>
 <template v-else-if="view==='vouchers'||view==='redemptions'"><section class="hub-card"><p v-if="loading">正在读取兑换记录…</p><p v-if="!loading&&!rows.length" class="hub-empty">还没有兑换记录。<RouterLink to="/rewards/shop">去挑一份奖励 ›</RouterLink></p><article v-for="r in rows.filter(r=>view==='redemptions'||r.status!=='fulfilled')" :key="r.id" class="hub-row"><span class="hub-row-text"><strong>{{ r.item_name||'已兑换的奖励' }}</strong><small>{{ r.coin_spent }} 币 · {{ r.status==='fulfilled'?'已使用':'待使用' }}<template v-if="r.duration_seconds"> · {{ r.duration_seconds/60 }} 分钟</template></small></span><RouterLink v-if="r.duration_seconds&&r.status!=='fulfilled'" class="btn" to="/timers">去使用</RouterLink><button v-else-if="r.status!=='fulfilled'" class="btn" @click="selectedVoucher=r">确认已使用</button></article><p v-if="!loading&&view==='vouchers'&&rows.length&&!rows.some(r=>r.status!=='fulfilled')" class="hub-empty">当前没有未使用的券。</p></section></template>
 <ConfirmDialog :open="!!selectedVoucher" title="确认这份奖励已使用？" confirm-label="确认已使用" :busy="busy" @cancel="selectedVoucher=null" @confirm="fulfill"><p>{{ selectedVoucher?.item_name }}</p><p>这里只记录已使用，不再扣金币。</p></ConfirmDialog>
</div></template>
