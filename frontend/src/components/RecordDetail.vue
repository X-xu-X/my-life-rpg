<script setup>
import FactLinks from './FactLinks.vue'
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { account, accountEpoch, storageKey, displayTime, displayEventTime } from '../session'
const route = useRoute(), router = useRouter()
const event = ref(null), judgment = ref(null), job = ref(null)
const error = ref(''), notice = ref(''), detail = ref(''), editing = ref(false), text = ref('')
const busy = ref(false)
let alive=true,generation=0,timer=null,reader=null
const epoch=accountEpoch,modelConfigured=ref(null)
const current=()=>alive&&epoch===accountEpoch&&!document.hidden
function stop(){clearTimeout(timer);reader?.abort();generation++}
function schedule(){clearTimeout(timer);if(current()&&['queued','running'].includes(job.value?.state))timer=setTimeout(load,2500)}
function visibility(){stop();if(!document.hidden)load()}
const draftKey = storageKey('supplement:' + route.params.id)
try { detail.value = localStorage.getItem(draftKey) || '' } catch {}
watch(detail, value => { try { localStorage.setItem(draftKey, value) } catch {} })
const frozen = computed(()=>judgment.value?.status === 'confirmed')
async function load() {
  reader?.abort();reader=new AbortController();const revision=++generation
  try {
    let [saved,list,pending]=await Promise.all([api.getEvent(route.params.id,reader.signal),api.listJudgments(reader.signal),api.pending(reader.signal)])
    let next=pending.items.find(row=>row.event_id===saved.id)?.job || job.value
    if(next?.id)next=await api.getJob(next.id,reader.signal)
    if(next?.state==='ready')list=await api.listJudgments(reader.signal)
    if(!current()||revision!==generation)return
    event.value=saved;judgment.value=list.find(row=>row.event_id===saved.id)||null;job.value=next
    if(!editing.value)text.value=saved.content
  } catch(e) { if(current()&&revision===generation&&e.name!=='AbortError'){error.value=e.message;if(e.status===404)job.value=null} }
  finally{if(revision===generation)schedule()}
}
async function action(fn, message) {
  if (busy.value) return
  busy.value=true; error.value=''; notice.value=''
  try { await fn(); notice.value=message; await load() }
  catch(e) { error.value=e.message; if(e.status === 409) { await load(); error.value=e.message+' 你的输入已保留，请对照最新内容后再提交。' } }
  finally { busy.value=false }
}
function analyze(operation='judge') {
  return action(async()=>{
    if(account.value?.mode === 'local') {
      if(operation === 'judge') await api.judgeEvent(event.value.id,detail.value)
      else if(operation === 'supplement') await api.supplementJudgment(judgment.value.id, detail.value)
      else await api.disputeJudgment(judgment.value.id,detail.value)
    } else await api.submitJob(event.value.id,{request_key:crypto.randomUUID(),event_version:event.value.content_version,operation,detail:detail.value,
      question_job_id:job.value?.state === 'needs_input' ? job.value.id : null, judgment_version:judgment.value?.updated_at || null})
    detail.value=''
  },account.value?.mode === 'local' ? '分析已完成。' : '分析已排队，可稍后回来查看。供应商可能对重试计费。')
}
async function saveEdit() {
  await action(()=>api.updateEvent(event.value.id,{content:text.value,expected_version:event.value.content_version}),'原文已更新，旧分析将重新校验。')
  if(!error.value) editing.value=false
}
async function remove() {
  if(!window.confirm('撤销后原记录和审计仍保留，按实际属性流水回滚；已发金币保留。继续？')) return
  if(busy.value) return
  busy.value=true; error.value=''
  try { await api.deleteEvent(event.value.id,event.value.content_version); await router.push('/journal') }
  catch(e) { error.value=e.message }
  finally { busy.value=false }
}
onMounted(()=>{
 load();document.addEventListener('visibilitychange',visibility)
 Promise.all([api.getLLMConfig(),api.flow('/ai/preferences')]).then(([config,choice])=>{
  if(!alive||epoch!==accountEpoch)return
  const personal=!!((config.primary?.configured&&config.primary?.enabled)||(config.aux?.configured&&config.aux?.enabled)||config.env_fallback?.ready)
  modelConfigured.value=choice.mode==='hosted'?choice.hosted.available:choice.mode==='personal'&&personal
 }).catch(()=>{})
})
onUnmounted(()=>{alive=false;stop();document.removeEventListener('visibilitychange',visibility)})
</script>
<template>
  <div class="reading-page">
  <p v-if="error" class="error" role="alert">{{ error }}</p>
  <article v-if="event" class="record-detail">
    <p class="eyebrow">已保存 ✓ · {{ displayEventTime(event) }}</p><h1>{{ event.title }}</h1>
    <p class="muted small">发生时间与保存时间分开记录；保存于 {{ displayTime(event.created_at) }}</p>
    <textarea v-if="editing" v-model="text" rows="12" maxlength="20000" :disabled="busy" aria-label="编辑原文" />
    <p v-else class="original-text">{{ event.content }}</p>
    <div class="action-group" v-if="!frozen && event.origin !== 'challenge'"><button class="btn" :disabled="busy" @click="editing = !editing">{{ editing ? '取消编辑' : '编辑原文' }}</button><button v-if="editing" class="btn primary" :disabled="busy" @click="saveEdit">保存修改</button></div>
    <p v-if="notice" class="success" role="status">{{ notice }}</p>
    <section class="analysis-detail">
      <h2>{{ frozen ? '已入账 · 旧规则 v1.11' : '分析与建议' }}</h2>
      <p v-if="(event.is_pure || event.analysis_intent === 'never') && !job && !judgment" class="muted">原文已保存，尚未分析。</p>
      <p v-if="event.origin === 'challenge'"><RouterLink to="/challenges">挑战记录请前往挑战页处理 →</RouterLink></p>
      <template v-else-if="!frozen && !event.is_pure">
        <p v-if="job">分析状态：{{ {queued:'排队中',running:'处理中',needs_input:'待补充',ready:'建议已就绪',failed:'分析失败',cancelled:'已取消',superseded:'输入已变化'}[job.state] || job.state }} <span v-if="job.safe_error_code">（{{ job.safe_error_code }}）</span></p>
        <ul v-if="job?.result?.questions"><li v-for="question in job.result.questions" :key="question">{{ question }}</li></ul>
        <p v-if="modelConfigured===false" class="muted">尚无可用模型，仍可保留原文。<RouterLink to="/settings">配置自己的模型 →</RouterLink></p><p v-else-if="!judgment" class="muted">主动分析或重试可能产生供应商费用。</p>
        <button class="btn" :disabled="busy" @click="load">重新读取状态</button>
        <label>可稍后填写的补充 / 复核理由<textarea v-model="detail" rows="3" :disabled="busy" placeholder="可以离开，稍后从待处理回来。" /></label>
        <div class="action-group"><button class="btn" :class="{primary:!judgment}" :disabled="busy || ['running','queued'].includes(job?.state)" @click="analyze('judge')">{{ job?.state==='needs_input' && !judgment ? '提交补充' : judgment ? '再次分析' : '现在分析' }}</button><button v-if="judgment" class="btn" :class="{primary:job?.state==='needs_input'}" :disabled="busy || !detail.trim()" @click="analyze('supplement')">提交补充</button><button v-if="judgment" class="btn" :disabled="busy || !detail.trim()" @click="analyze('dispute')">复核</button><button v-if="['queued','running'].includes(job?.state)" class="btn" :disabled="busy" @click="action(()=>api.cancelJob(job.id),'已取消回写；已发出的模型请求仍可能计费。')">取消分析</button></div>
      </template>
      <div v-if="judgment"><p v-if="judgment.model_provenance" class="muted">本次模型：{{ judgment.model_provenance.provider }} / {{ judgment.model_provenance.model }} · 配置 v{{ judgment.model_provenance.config_version }}</p><p>{{ judgment.summary }}</p><p class="muted">AI 自评置信度：{{ Math.round(judgment.confidence * 100) }}%；不代表经过校准的真实概率。</p><ul><li v-for="change in (frozen ? judgment.final_changes : judgment.suggested_changes)" :key="change.name">{{ change.name }} {{ change.delta >= 0 ? '+' : '' }}{{ change.delta }} · {{ change.reason }}</li></ul><details><summary>查看依据</summary><p v-for="(line,index) in judgment.analysis" :key="index">{{ line }}</p></details><button v-if="!frozen && event.origin !== 'challenge'" class="btn" :class="{primary:job?.state!=='needs_input'}" :disabled="busy || judgment.confidence < 0.8 || ['running','queued'].includes(job?.state)" @click="action(()=>api.confirmJudgment(judgment.id,judgment.updated_at),'已确认入账。')">{{ judgment.confidence < 0.8 ? '需补充信息后确认' : '确认入账' }}</button><RouterLink to="/judgments">查看完整判定与审计 →</RouterLink></div>
    </section>
    <FactLinks :event="event"/>
    <section class="danger-zone"><h2>撤销记录</h2><p class="muted">原文与审计保留；属性按实际流水回滚，已发金币保留。</p><button class="btn danger" :disabled="busy" @click="remove">撤销这条记录</button></section>
  </article>
</div></template>
