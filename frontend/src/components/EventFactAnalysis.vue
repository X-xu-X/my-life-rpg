<script setup>
import { ref,computed,onMounted,onBeforeUnmount,watch } from 'vue'
import { api } from '../api'
import { accountEpoch,storageKey,displayTime } from '../session'
import { useWorkflowWrite } from '../composables/useWorkflowWrite'
import ConfirmDialog from './ui/ConfirmDialog.vue'
const props=defineProps({event:Object,readOnly:Boolean}),emit=defineEmits(['confirmed'])
const jobs=ref([]),bundles=ref([]),notes=ref([]),job=ref(null),loading=ref(true),error=ref(''),notice=ref('')
const writes=useWorkflowWrite('facts:'+props.event.id),epoch=accountEpoch
const supplement=ref(''),noteDialog=ref(false),options=ref(false),detailsOpen=ref(false)
const draftKey=storageKey('fact-note:'+props.event.id)
try{supplement.value=localStorage.getItem(draftKey)||''}catch{}
watch(supplement,v=>{try{localStorage.setItem(draftKey,v)}catch{}})
let alive=true,timer=null,serial=0
const group=computed(()=>bundles.value[0]||null)
const analyzing=computed(()=>!props.readOnly&&['queued','running'].includes(job.value?.state))
const confirmed=computed(()=>group.value?.state==='confirmed')
const coinTotal=computed(()=>confirmed.value?(group.value.applied_total??group.value.preview?.total):group.value?.preview?.total)
const suggestions=computed(()=>group.value?.payload.items||[])
const bookedCount=computed(()=>group.value?.preview?.items.filter(i=>i.booked).length||0)
const allBooked=computed(()=>bookedCount.value>0&&bookedCount.value===suggestions.value.length)
const allSkipped=computed(()=>suggestions.value.length>0&&suggestions.value.every(i=>i.decision==='skip'))
const lowConfidence=computed(()=>suggestions.value.filter(i=>i.confidence<.8&&i.decision!=='skip').length)
const status=computed(()=>loading.value?'读取中':analyzing.value?'AI 正在分析':job.value?.state==='failed'?'本次分析未完成':confirmed.value?(allBooked.value?'已关联':allSkipped.value?'暂不结算':'已入账'):group.value?.preview?'待确认入账':group.value?'建议已就绪':props.readOnly?'仅保存':'尚未分析')
function changes(item){const g=group.value;if(!g)return [];if(g.state==='confirmed')return g.applied_changes?.find(i=>i.fragment_id===item.fragment_id)?.changes||[];return g.preview?g.preview.items.find(i=>i.fragment_id===item.fragment_id)?.changes||[]:item.changes||[]}
const totals=computed(()=>{const byName=new Map();for(const item of suggestions.value){if(item.decision==='skip'||item.confidence<.8)continue;for(const c of changes(item))byName.set(c.name,(byName.get(c.name)||0)+c.delta)}return [...byName].map(([name,delta])=>({name,delta:Math.round(delta*100)/100})).filter(c=>c.delta!==0)})
function signed(n){return (n>0?'+':'')+n}
function previewItem(item){return group.value?.preview?.items.find(i=>i.fragment_id===item.fragment_id)}
const primaryLabel=computed(()=>analyzing.value?'AI 正在分析…':!group.value?'分析属性与金币':group.value.preview?(allBooked.value?'确认关联结果':allSkipped.value?'确认暂不结算':'确认入账'):'查看入账预览')
async function load(){const token=++serial;try{const [groups,tasks,savedNotes]=await Promise.all([api.flow('/events/'+props.event.id+'/fact-bundles'),api.flow('/events/'+props.event.id+'/analysis-jobs'),api.flow('/events/'+props.event.id+'/fact-notes')]);if(!alive||epoch!==accountEpoch||token!==serial)return;bundles.value=groups.items;notes.value=savedNotes.items;jobs.value=tasks.items.filter(j=>j.operation==='facts');job.value=jobs.value[0]||null;if(lowConfidence.value)detailsOpen.value=true;clearTimeout(timer);if(!props.readOnly&&!document.hidden&&['queued','running'].includes(job.value?.state))timer=setTimeout(load,1800)}catch(e){if(alive)error.value=e.message}finally{if(alive&&token===serial)loading.value=false}}
async function act(path,body={}){if(writes.busy.value)return false;error.value='';notice.value='';try{const result=await writes.send(path,body);await load();if(path.endsWith('/confirm')){notice.value='已入账，新增 '+result.coins_gained+' 币。';emit('confirmed')}return true}catch(e){error.value=e.message;return false}}
async function analyze(){options.value=false;return act('/events/'+props.event.id+'/analysis-jobs',{event_version:props.event.content_version,operation:'facts'})}
function primary(){if(!group.value)return analyze();return act('/fact-bundles/'+group.value.id+(group.value.preview?'/confirm':'/preview'),{expected_version:group.value.version})}
function decision(item,value,mainline=item.mainline,related_fact_id=null){return act('/fact-bundles/'+group.value.id+'/decision',{expected_version:group.value.version,fragment_id:item.fragment_id,decision:value,mainline,related_fact_id})}
async function saveNote(){if(!supplement.value.trim()){error.value='请填写补充内容。';return}const ok=await act('/events/'+props.event.id+'/fact-notes',{content:supplement.value,expected_version:props.event.content_version,bundle_id:group.value?.id||null});if(ok){supplement.value='';noteDialog.value=false;notice.value='补充已保存，原文未改。需要时可重新分析。'}}
function visibility(){clearTimeout(timer);if(!document.hidden)load()}
watch(()=>[props.event.content_version,props.event.ai_permission_version],load)
onMounted(()=>{load();document.addEventListener('visibilitychange',visibility)})
onBeforeUnmount(()=>{alive=false;serial++;clearTimeout(timer);document.removeEventListener('visibilitychange',visibility)})
</script>
<template>
<section v-if="!readOnly||group||notes.length" class="entry-result-card event-fact-analysis" :data-analysis-state="status">
 <header class="entry-section-title"><h2>{{ confirmed?(allBooked||allSkipped?'记录结果':'这次的积累'):readOnly?'保留的历史分析':'属性与金币' }}</h2><span class="entry-state" :class="{green:confirmed&&job?.state!=='failed',working:analyzing}"><i v-if="analyzing" class="spinner" aria-hidden="true"/>{{ status }}</span></header>
 <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="notice" class="entry-notice" role="status">{{ notice }}</p>
 <p v-if="analyzing" class="entry-status-note" role="status" aria-live="polite">AI 正在读取这条记录。可以稍后回来，原文已经保存。</p>
 <p v-else-if="job?.state==='failed'" class="entry-status-note" role="alert">{{ job.safe_error_message||'分析暂时没有完成。原文已保存，可以主动重试。' }}</p>
 <template v-if="group">
  <div class="entry-results">
   <div class="entry-coin"><span>{{ confirmed&&!allBooked&&!allSkipped?'本次已入账':'本次新增金币' }}</span><strong v-if="coinTotal!=null">{{ signed(coinTotal) }}<small> 币</small></strong><strong v-else class="entry-pending-value">待预览</strong></div>
   <div class="entry-attributes"><span>{{ confirmed?'实际属性变化':'AI 属性建议' }}</span><div v-if="totals.length" class="entry-change-list"><span v-for="c in totals" :key="c.name" class="entry-change-chip">{{ c.name }} <b>{{ signed(c.delta) }}</b></span></div><p v-else>{{ lowConfidence?'补充后再评估':confirmed?'本次无新增属性':suggestions.every(i=>i.decision==='skip')?'本次暂不结算':'暂无新增属性建议' }}</p></div>
  </div>
  <p v-if="!confirmed" class="entry-status-note">{{ group.preview?'核对后再确认，确认前不入账。':'先查看金币与属性预览，尚未入账。' }}<span v-if="totals.length"> 属性按现有规则加权，以实际入账结果为准。</span></p>
  <p v-if="bookedCount" class="entry-status-note">{{ bookedCount }} 项行动已在其他记录中计入，本篇不重复增加属性和金币。</p>
  <p v-if="allSkipped" class="entry-status-note">你选择了本次暂不结算，原文仍保留。</p>
  <p v-if="lowConfidence" class="entry-attention" role="status">有 {{ lowConfidence }} 项信息不足，未达到80%门槛；这些项目暂不入账。</p>
 </template>
 <p v-else-if="!loading&&!analyzing" class="entry-status-note">需要时让 AI 分析，核对建议后再计入属性和金币。</p>
 <div v-if="!readOnly" class="entry-main-actions">
  <button v-if="writes.pending.value" class="btn primary" :disabled="writes.busy.value" @click="act(writes.pending.value.path,writes.pending.value.body)">恢复上次请求</button>
  <button v-else-if="!confirmed" class="btn primary entry-primary" :disabled="loading||writes.busy.value||analyzing" @click="primary">{{ writes.busy.value?'正在处理…':primaryLabel }}</button>
  <button v-if="analyzing" class="text-button" @click="api.cancelJob(job.id).then(load).catch(e=>error=e.message)">取消本次分析</button>
  <button v-if="!analyzing" class="text-button" @click="noteDialog=true">补充这条记录</button>
  <button v-if="group&&!analyzing" class="text-button entry-more-link" @click="options=true" aria-label="更多分析操作">更多</button>
 </div>
 <button v-if="readOnly&&jobs.length" class="text-button" @click="options=true">查看分析历史</button>
 <details v-if="group" class="entry-evidence" :open="detailsOpen" @toggle="detailsOpen=$event.target.open">
  <summary>{{ lowConfidence?'查看需要补充的内容':'查看分析依据与明细' }} <span>{{ suggestions.length }} 项行动</span></summary>
  <article v-for="item in suggestions" :key="item.fragment_id" class="entry-fact-row">
   <h3>{{ item.summary }}</h3><blockquote>{{ item.excerpt }}</blockquote>
   <p v-if="previewItem(item)?.booked" class="entry-attention">这次行动已在其他记录中入账，本次不重复增加属性和金币。</p>
   <p v-else-if="item.decision==='skip'" class="entry-status-note">你已选择这项暂不结算。</p>
   <p v-else-if="item.confidence<.8" class="entry-attention">可信度 {{ Math.round(item.confidence*100) }}%，未达到80%门槛。补充后可以重新分析。</p>
   <p v-else class="entry-status-note">可信度 {{ Math.round(item.confidence*100) }}%<template v-if="group.preview"> · {{ confirmed?'本项入账':'本项预览' }} {{ confirmed?(group.applied_changes?.find(r=>r.fragment_id===item.fragment_id)?.coins??previewItem(item)?.breakdown.amount??0):(previewItem(item)?.breakdown.amount||0) }} 币<template v-if="previewItem(item)?.breakdown.reason"> · {{ previewItem(item).breakdown.reason }}</template></template></p>
   <p v-if="item.reason" class="entry-status-note">{{ item.reason }}</p><p v-for="c in changes(item)" :key="c.name" class="entry-status-note">{{ c.name }} {{ signed(c.delta) }} · {{ c.reason }}</p>
   <div v-if="!readOnly&&!confirmed&&item.decision==='unresolved'" class="entry-relation-actions"><p>若这确实是同一次行动，可在这里合并；不选择则按另一次行动结算。</p><button v-for="option in item.candidate_options||[]" :key="option.fact_id" class="btn" :disabled="writes.busy.value||!!writes.pending.value" @click="decision(item,'same',item.mainline,option.fact_id)">与这项相同：{{ option.excerpt }}</button><button v-if="item.candidate_fact_id" class="btn" :disabled="writes.busy.value||!!writes.pending.value" @click="decision(item,'same')">是同一次行动</button><button class="btn" :disabled="writes.busy.value||!!writes.pending.value" @click="decision(item,'distinct')">是另一次行动</button></div>
   <details v-if="!readOnly&&!confirmed" class="entry-adjust"><summary>调整这一项</summary><button class="text-button" :disabled="writes.busy.value||!!writes.pending.value" @click="decision(item,item.decision==='skip'?'keep':'skip')">{{ item.decision==='skip'?'恢复本项结算':'本项暂不结算' }}</button><button v-if="item.goal_id" class="text-button" :disabled="writes.busy.value||!!writes.pending.value" @click="decision(item,'keep',!item.mainline)">{{ item.mainline?'取消主线关联':'确认与当前主线有关' }}</button><template v-if="item.candidate_fact_id&&item.decision!=='unresolved'"><button class="text-button" @click="decision(item,'same')">与已有行动相同</button><button class="text-button" @click="decision(item,'distinct')">是另一次行动</button></template></details>
  </article>
  <details class="entry-technical"><summary>金币与模型信息</summary><p v-if="group.preview">原核对预览 {{ group.preview.total }} 币 · 今日已得 {{ group.preview.used }} 币</p><p v-if="confirmed&&coinTotal!==group.preview?.total">实际已入账 {{ coinTotal }} 币，含已完成的漏发补记；原预览作为历史保留。</p><p v-for="item in group.preview?.items||[]" :key="item.fragment_id">{{ item.breakdown.amount }} 币<template v-if="item.breakdown.reason"> · {{ item.breakdown.reason }}</template></p><p>{{ group.provenance.provider }} / {{ group.provenance.model }} · 原文 v{{ group.event_version }} · 建议 v{{ group.version }}</p></details>
 </details>
 <details v-if="notes.length" class="entry-evidence"><summary>另存的补充 <span>{{ notes.length }} 条</span></summary><p v-for="n in notes" :key="n.id" class="entry-status-note">{{ n.content }}</p></details>
</section>
<ConfirmDialog :open="noteDialog" title="补充这条记录" confirm-label="保存补充" :busy="writes.busy.value" @cancel="noteDialog=false" @confirm="saveNote"><p v-for="q in group?.payload.questions||[]" :key="q">{{ q }}</p><label>补充内容<textarea v-model="supplement" rows="4" maxlength="10000" placeholder="补充实际做了什么、投入或结果…"/></label><p class="entry-status-note">单独保存，不会改写原文；保存后可以重新分析。</p><p v-if="error" class="error">{{ error }}</p></ConfirmDialog>
<ConfirmDialog :open="options" title="更多分析操作" confirm-label="关闭" @cancel="options=false" @confirm="options=false"><button class="btn" :disabled="readOnly||writes.busy.value||!!writes.pending.value||analyzing" @click="analyze">重新分析当前文字</button><p class="entry-status-note">重新调用模型可能计费；已有结算不会重复发放。</p><details v-if="jobs.length" class="entry-evidence"><summary>分析记录 <span>{{ jobs.length }} 次</span></summary><p v-for="task in jobs" :key="task.id" class="entry-status-note">{{ displayTime(task.created_at) }} · {{ {queued:'排队中',running:'分析中',ready:'分析完成',failed:'失败',cancelled:'已取消',superseded:'来源已变化'}[task.state]||task.state }}<template v-if="task.safe_error_code"> · {{ task.safe_error_message||task.safe_error_code }}</template></p></details><details v-if="bundles.length>1" class="entry-evidence"><summary>历史分析 <span>{{ bundles.length-1 }} 份</span></summary><article v-for="g in bundles.slice(1)" :key="g.id"><p class="entry-status-note">原文 v{{ g.event_version }} · {{ g.state==='confirmed'?'已确认':'历史建议' }}</p><p v-for="i in g.payload.items" :key="i.fragment_id">{{ i.summary }}</p></article></details></ConfirmDialog>
</template>
