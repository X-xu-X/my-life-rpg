<script setup>
import { ref,onMounted,onBeforeUnmount,watch } from 'vue'
import { api } from '../api'
import { accountEpoch,storageKey,displayTime } from '../session'
import { useWorkflowWrite } from '../composables/useWorkflowWrite'
const props=defineProps({event:Object,readOnly:Boolean}),emit=defineEmits(['confirmed'])
const jobs=ref([]),bundles=ref([]),job=ref(null),error=ref(''),notice=ref(''),writes=useWorkflowWrite('facts:'+props.event.id),epoch=accountEpoch
const notes=ref([]),supplement=ref(''),draftKey=storageKey('fact-note:'+props.event.id)
try{supplement.value=localStorage.getItem(draftKey)||''}catch{}
watch(supplement,v=>{try{localStorage.setItem(draftKey,v)}catch{}})
async function saveNote(){const text=supplement.value;await act('/events/'+props.event.id+'/fact-notes',{content:text,expected_version:props.event.content_version,bundle_id:bundles.value[0]?.id||null});if(!error.value){supplement.value='';notice.value='补充已单独保存。点击分析会纳入本事件的原文和授权回答，旧账不重发。'}}
let alive=true,timer=null,serial=0
async function load(){const token=++serial;try{const [groups,taskList,savedNotes]=await Promise.all([api.flow('/events/'+props.event.id+'/fact-bundles'),api.flow('/events/'+props.event.id+'/analysis-jobs'),api.flow('/events/'+props.event.id+'/fact-notes')]);if(!alive||epoch!==accountEpoch||token!==serial)return;bundles.value=groups.items;notes.value=savedNotes.items;jobs.value=taskList.items.filter(j=>j.operation==='facts');job.value=jobs.value[0]||null;clearTimeout(timer);if(!props.readOnly&&!document.hidden&&['queued','running'].includes(job.value?.state))timer=setTimeout(load,2000)}catch(e){if(alive)error.value=e.message}}
async function act(path,body={}){if(writes.busy.value)return;error.value='';notice.value='';try{const result=await writes.send(path,body);await load();if(path.endsWith('/confirm')){notice.value='已确认本组事实，新增 '+result.coins_gained+' 币。';emit('confirmed')}}catch(e){error.value=e.message}}
function decision(group,item,value,mainline=item.mainline,related_fact_id=null){return act('/fact-bundles/'+group.id+'/decision',{expected_version:group.version,fragment_id:item.fragment_id,decision:value,mainline,related_fact_id})}
function changes(group,item){if(group.state==='confirmed')return group.applied_changes?.find(i=>i.fragment_id===item.fragment_id)?.changes||[];return group.preview?group.preview.items.find(i=>i.fragment_id===item.fragment_id)?.changes||[]:item.changes}
function signed(value){return (value>=0?'+':'')+value}
function entrySummary(group){
  const items=group.payload?.items||[]
  const preview=group.preview?.items||[]
  return {included:preview.filter(i=>i.eligible).length,skipped:items.filter(i=>i.decision==='skip').length,
    booked:preview.filter(i=>i.booked).length,low:items.filter(i=>i.confidence<0.8).length,
    coins:group.preview?.total||0,day:(group.preview?.used||0)+(group.preview?.total||0)}
}
function visibility(){clearTimeout(timer);if(!document.hidden)load()}
watch(()=>props.event.content_version,load)
onMounted(()=>{load();document.addEventListener('visibilitychange',visibility)})
onBeforeUnmount(()=>{alive=false;serial++;clearTimeout(timer);document.removeEventListener('visibilitychange',visibility)})
</script>
<template>
<section v-if="!readOnly||bundles.length||notes.length" class="card fact-analysis">
 <h2>{{ readOnly?'历史分析（只读）':'属性与金币分析' }}</h2>
 <p class="muted small">AI 建议属性变化与金币，核对预览后才入账。同一行动只结算一次。</p>
 <p v-if="notice" role="status">{{ notice }}</p>
 <template v-if="!readOnly">
  <button v-if="writes.pending.value" class="btn" :disabled="writes.busy.value" @click="act(writes.pending.value.path,writes.pending.value.body)">恢复上次请求</button>
  <p v-if="job" role="status" aria-live="polite"><span v-if="['queued','running'].includes(job.state)" class="spinner" aria-hidden="true"></span> {{ bundles[0]?.state==='confirmed'&&job.state==='ready'?'已确认入账':{queued:'AI 已排队，请稍候…',running:'AI 正在分析属性与金币，请稍候…',ready:'建议已生成，请核对',failed:'本次分析失败，原文已保留',superseded:'来源已变化，请重新分析',cancelled:'分析已取消'}[job.state] }}</p>
  <p v-if="job?.safe_error_code" class="error">{{ job.safe_error_message||job.safe_error_code }}</p>
  <div class="action-group"><button class="btn" :disabled="writes.busy.value||!!writes.pending.value||['queued','running'].includes(job?.state)" @click="act('/events/'+event.id+'/analysis-jobs',{event_version:event.content_version,operation:'facts'})">{{ ['queued','running'].includes(job?.state)?'AI 正在判定…':bundles.length?'重新分析当前文字':'分析属性与金币' }}</button><button v-if="['queued','running'].includes(job?.state)" class="btn" @click="api.cancelJob(job.id).then(load).catch(e=>error=e.message)">取消分析</button></div>
  <details class="fact-supplement" :open="!!bundles[0]?.payload.questions?.length"><summary>补充事实 / 回答问题（可选）</summary><form @submit.prevent="saveNote"><p v-for="question in bundles[0]?.payload.questions||[]" :key="question">{{ question }}</p><label>相关补充<textarea v-model="supplement" rows="2" maxlength="10000"/></label><p class="muted small">单独保存，不改原文；保存后可重新分析。</p><button class="btn" :disabled="writes.busy.value||!!writes.pending.value||!supplement.trim()">保存相关补充</button></form></details>
 </template>
 <details v-if="notes.length"><summary>已保存的相关补充 · {{ notes.length }}</summary><p v-for="note in notes" :key="note.id">{{ note.content }}</p></details>
 <details v-for="group in bundles.slice(0,1)" :key="group.id" class="fact-result" open>
  <summary>{{ group.state==='confirmed'?'已确认 · 查看属性与金币':'核对本次属性与金币' }}<span v-if="group.preview"> · {{ group.preview.total }} 币</span></summary>
  <div class="analysis-overview"><div v-for="item in group.payload.items" :key="item.fragment_id"><p><strong>{{ group.state==='confirmed'?'实际属性变化':'属性建议' }}：</strong><template v-if="changes(group,item).length"><span v-for="change in changes(group,item)" :key="change.name" class="attribute-chip">{{ change.name }} {{ signed(change.delta) }}</span></template><span v-else>{{ item.confidence<0.8?'待补充信息后评估':'本项无新增属性' }}</span></p><p v-for="change in changes(group,item)" :key="'why-'+change.name" class="muted small">{{ change.name }}：{{ change.reason }}</p></div><p v-if="group.preview"><strong>{{ group.state==='confirmed'?'已确认金币':'本次新增金币' }}：{{ group.preview.total }} 币</strong></p><p v-else class="muted small">先核对事实，再生成入账预览查看金币；属性实际变化以确认后的结果为准。</p><p v-if="group.state==='confirmed'">本组入账：计入 {{ entrySummary(group).included }} 项 · 未计入 {{ entrySummary(group).skipped+entrySummary(group).booked+entrySummary(group).low }} 项<template v-if="entrySummary(group).skipped">（暂不结算 {{ entrySummary(group).skipped }}）</template><template v-if="entrySummary(group).booked">（已有入账 {{ entrySummary(group).booked }}）</template><template v-if="entrySummary(group).low">（可信度不足 {{ entrySummary(group).low }}）</template> · 合计 {{ entrySummary(group).coins }} 币 · 当日累计 {{ entrySummary(group).day }} 币</p></div>
  <article v-for="item in group.payload.items" :key="item.fragment_id" class="fact-item">
   <p><strong>{{ item.summary }}</strong></p><p class="muted">{{ item.coins }} 币 · 可信度 {{ Math.floor(item.confidence*1000)/10 }}%</p>
   <p v-if="item.confidence<0.8" class="muted">尚未达到 80% 门槛，可补充真实行动和投入后重新分析。</p>
   <details><summary>原文引用与判断依据</summary><blockquote>{{ item.excerpt }}</blockquote><p>{{ item.reason }}</p><p class="muted">来源：{{ {original:'原文',note:'相关补充',review_answer:'辅助回顾回答'}[item.source_kind]||'原文' }}</p></details>
   <div v-if="!readOnly&&group.state!=='confirmed'&&(item.candidate_fact_id||(item.candidate_options||[]).length)" class="action-group fact-relation"><button v-for="option in item.candidate_options||[]" :key="option.fact_id" class="btn" :disabled="writes.busy.value||!!writes.pending.value" @click="decision(group,item,'same',item.mainline,option.fact_id)">与已结算事实相同：{{ option.excerpt }}</button><button v-if="item.candidate_fact_id" class="btn" :disabled="writes.busy.value||!!writes.pending.value" @click="decision(group,item,'same')">是同一次行动</button><button class="btn" :disabled="writes.busy.value||!!writes.pending.value" @click="decision(group,item,'distinct')">是另一件事</button></div>
   <details v-if="!readOnly&&group.state!=='confirmed'" class="fact-adjust"><summary>调整这一项</summary><button class="text-button" :disabled="writes.busy.value||!!writes.pending.value" @click="decision(group,item,'skip')">本项暂不结算</button><button v-if="item.goal_id" class="btn" :disabled="writes.busy.value||!!writes.pending.value" @click="decision(group,item,'keep',!item.mainline)">{{ item.mainline?'取消主线关联':'确认与当前主线有关' }}</button></details>
   <template v-if="group.preview"><p>{{ group.preview.items.find(i=>i.fragment_id===item.fragment_id)?.booked?'同一行动已入账，本次新增金币和属性均为 0':'本项新增 '+(group.preview.items.find(i=>i.fragment_id===item.fragment_id)?.breakdown.amount||0)+' 币' }}</p><p v-if="group.preview.items.find(i=>i.fragment_id===item.fragment_id)?.breakdown.reason" class="muted">{{ group.preview.items.find(i=>i.fragment_id===item.fragment_id)?.breakdown.reason }}</p></template>
  </article>
  <template v-if="!readOnly&&group.state!=='confirmed'"><p v-if="error" class="error" role="alert">{{ error }}</p><button class="btn" :disabled="writes.busy.value||!!writes.pending.value" @click="act('/fact-bundles/'+group.id+'/preview',{expected_version:group.version})">{{ group.preview?'刷新整组入账预览':'生成属性与金币入账预览' }}</button><div v-if="group.preview"><p>合计 {{ group.preview.total }} 币 · 今日已得 {{ group.preview.used }} 币</p><button class="btn primary" :disabled="writes.busy.value||!!writes.pending.value" @click="act('/fact-bundles/'+group.id+'/confirm',{expected_version:group.version})">确认本组新增事实</button></div></template>
  <details><summary>本次模型与版本</summary><p>原文 v{{ group.event_version }} · 建议 v{{ group.version }}</p><p>{{ group.provenance.provider }} / {{ group.provenance.model }} · 配置 v{{ group.provenance.config_version }}</p></details>
 </details>
 <details v-if="jobs.length"><summary>分析任务记录 · {{ jobs.length }}</summary><p v-for="task in jobs" :key="task.id">{{ displayTime(task.created_at) }} · {{ {queued:'排队中',running:'分析中',ready:'分析完成',failed:'失败',cancelled:'已取消',superseded:'来源已变化'}[task.state]||task.state }}<span v-if="task.safe_error_code"> · {{ task.safe_error_message||task.safe_error_code }}（{{ task.safe_error_code }}）</span></p></details>
 <details v-if="bundles.length>1"><summary>历史分析（只读）</summary><article v-for="group in bundles.slice(1)" :key="group.id"><p>原文 v{{ group.event_version }} · {{ {draft:'草稿',confirmed:'已确认'}[group.state]||group.state }}</p><p v-for="item in group.payload.items" :key="item.fragment_id">{{ item.excerpt }} · {{ item.summary }}</p></article></details>
</section>
</template>
