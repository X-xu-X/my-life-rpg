<script setup>
import { ref,onMounted,onUnmounted,watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { localDate,storageKey,accountEpoch } from '../session'
import { useWorkflowWrite } from '../composables/useWorkflowWrite'
import FactAnalysis from './FactAnalysis.vue'
import RecordPermission from './RecordPermission.vue'
import PageHeader from './ui/PageHeader.vue'
import TipLine from './ui/TipLine.vue'
const route=useRoute(),day=ref(route.query.date||localDate()),data=ref(null),session=ref(null),text=ref(''),answers=ref({}),error=ref(''),notice=ref('')
const permission=ref('private'),correctionReason=ref('')
const writes=useWorkflowWrite('diary'),epoch=accountEpoch;let alive=true,timer=null,reader=null,serial=0,loadSerial=0
const current=()=>alive&&epoch===accountEpoch
const draftKey=()=>storageKey('diary:'+day.value)
watch(answers,value=>{if(current()&&session.value)localStorage.setItem(storageKey('diary-answers:'+session.value.id),JSON.stringify(value))},{deep:true})
watch(text,value=>{if(current())localStorage.setItem(draftKey(),value)})
async function loadSession(id){
 reader?.abort();reader=new AbortController();const version=++serial
 try{const result=await api.flow('/review-sessions/'+id,undefined,'GET',reader.signal);if(!current()||version!==serial)return;if(session.value?.id!==result.id){try{answers.value=JSON.parse(localStorage.getItem(storageKey('diary-answers:'+result.id))||'{}')}catch{answers.value={}}}
  session.value=result
  clearTimeout(timer);if(!document.hidden&&result.jobs.some(j=>['queued','running'].includes(j.state)))timer=setTimeout(()=>loadSession(id),2500)
 }catch(e){if(current()&&e.name!=='AbortError')error.value=e.message}
}
async function load(){
 const loadRevision=++loadSerial,capturedDay=day.value
 clearTimeout(timer);reader?.abort();session.value=null;data.value=null;error.value=''
 try{const result=await api.flow('/diaries/'+day.value);if(!current()||loadRevision!==loadSerial||capturedDay!==day.value)return;data.value=result;permission.value=result.diary?.ai_permission||'private';text.value=localStorage.getItem(draftKey())??result.diary?.content??'';if(result.sessions[0])await loadSession(result.sessions[0].id)}catch(e){if(current())error.value=e.message}
}
async function act(fn){if(writes.busy.value)return;error.value='';notice.value='';try{await fn()}catch(e){if(current())error.value=e.message}}
async function save(){await act(async()=>{const intended=writes.pending.value?.path==='/diaries/'+day.value?writes.pending.value.body.content:text.value;const saved=await writes.send('/diaries/'+day.value,{content:text.value,ai_permission:permission.value,correction_reason:correctionReason.value,expected_version:data.value?.diary?.content_version||0},'PUT');if(!current())return;if(text.value===intended)localStorage.removeItem(draftKey());let analysisError='';if(saved.diary?.ai_permission==='allowed'){try{await api.submitJob(saved.diary.id,{request_key:crypto.randomUUID(),event_version:saved.diary.content_version,operation:'facts'})}catch(e){analysisError=e.message}}await load();notice.value='原文已保存，问答不会改写原文。';if(analysisError)error.value='原文已保存；分析未完成：'+analysisError})}
async function start(){await act(async()=>{const result=await writes.send('/diaries/'+day.value+'/review-sessions',{expected_version:data.value.diary.content_version});if(current())await loadSession(result.id)})}
async function answer(turn,skip=false){await act(async()=>{await writes.send(`/review-sessions/${session.value.id}/turns/${turn.id}`,{expected_version:turn.version,session_version:session.value.version,answer:answers.value[turn.id]||'',skip},'PUT');if(current()){delete answers.value[turn.id];await loadSession(session.value.id)}})}
async function analyze(){await act(async()=>{await writes.send('/review-sessions/'+session.value.id+'/analyze',{expected_version:session.value.version});if(current())await loadSession(session.value.id)})}
function visibility(){clearTimeout(timer);reader?.abort();if(!document.hidden&&session.value)loadSession(session.value.id)}
onMounted(()=>{load();document.addEventListener('visibilitychange',visibility)})
onUnmounted(()=>{alive=false;serial++;clearTimeout(timer);reader?.abort();document.removeEventListener('visibilitychange',visibility)})
</script>
<template><div class="reading-page"><PageHeader title="日记" description="先留下自己的原文，再选择回顾。"/>
<label>内容所属日期<input type="date" v-model="day" @change="load" :disabled="writes.busy.value||!!writes.pending.value"/></label>
<p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
<p v-if="writes.pending.value" role="status">上次操作结果未知；再次操作会恢复原请求，保留当前输入。</p>
<section class="card"><h2>日记原文</h2><textarea v-model="text" rows="10" maxlength="20000" :disabled="writes.busy.value" aria-label="日记原文"/><TipLine id="diary.same-day" class="muted" label="不再显示「同一日期保存」这行提示">同一日期保存为同一原稿的新版，不新增第二篇。辅助回答独立保留。</TipLine><label>保存方式<select v-model="permission"><option value="private">只保存，不交给 AI</option><option value="allowed">保存并分析</option></select></label><label v-if="data?.has_bookings&&text!==data.diary.content">更正说明（原结算保留）<textarea v-model="correctionReason" maxlength="2000" rows="2"/></label><button class="btn primary" :disabled="writes.busy.value||!data" @click="save">{{ writes.pending.value?'恢复上次操作':'保存原文' }}</button><button v-if="data?.diary?.ai_permission==='allowed'" class="btn" :disabled="writes.busy.value||text!==data.diary.content" @click="start">帮我回顾一下 / 恢复问答</button></section>
<FactAnalysis :key="'facts:'+data.diary.id" v-if="data?.diary" :event="data.diary" :read-only="data.diary.ai_permission!=='allowed'"/><RecordPermission :key="'permission:'+data.diary.id" v-if="data?.diary" :event="data.diary" @changed="load"/><section v-if="session&&data?.diary?.ai_permission==='allowed'" class="card"><h2>辅助回顾 · 原文 v{{ session.source_version }}</h2><p v-if="session.source_changed" class="error">原文已有新版。旧问答可回看，开始新版回顾后继续。</p><p v-for="job in session.jobs.slice(0,1)" :key="job.id" role="status">任务：{{ {queued:'排队中',running:'处理中',ready:'已完成',failed:'失败',cancelled:'已取消',superseded:'来源已变化'}[job.state]||'待读取' }} {{ job.safe_error_code }} <button v-if="['queued','running'].includes(job.state)" class="btn" @click="act(async()=>{await api.cancelJob(job.id);await loadSession(session.id)})">取消</button></p>
<details v-for="turn in session.turns" :key="turn.id" class="review-turn" :open="turn.state==='unanswered'"><summary>问题 {{ turn.ordinal }} · {{ turn.state==='unanswered'?'待回答':turn.state==='skipped'?'已跳过':'已回答' }}</summary><p>{{ turn.question }}</p><template v-if="turn.state==='unanswered'"><label>对应回答<textarea v-model="answers[turn.id]" rows="3" maxlength="10000"/></label><button class="btn" :disabled="writes.busy.value||session.source_changed" @click="answer(turn)">保存回答</button><button class="btn" :disabled="writes.busy.value||session.source_changed" @click="answer(turn,true)">跳过这题</button></template><p v-else>{{ turn.state==='skipped'?'已跳过':turn.answer }}</p></details>
<p class="muted">未回答可以保留；下一次回来仍能继续。主动生成会发送原文、来源快照和问答至所选模型，可能计费。</p><button class="btn primary" :disabled="writes.busy.value||session.source_changed||session.jobs.some(j=>['queued','running'].includes(j.state))" @click="analyze">{{ session.turns.length?'生成回顾总结 / 继续':'生成辅助问题与回顾' }}</button>
<details v-for="analysis in session.analyses" :key="analysis.id"><summary>回顾分析 · 会话 v{{ analysis.session_version }}</summary><p>{{ analysis.payload.summary }}</p><p v-for="line in analysis.payload.analysis" :key="line">{{ line }}</p><p class="muted">{{ analysis.provenance.provider }} / {{ analysis.provenance.model }}</p></details></section>
<section v-if="session&&data?.diary?.ai_permission!=='allowed'" class="card"><h2>历史辅助回顾（只读）</h2><p class="muted">本篇现在只保存。以下历史仅供本人回看，不会发起分析或要求作答。</p><article v-for="turn in session.turns" :key="turn.id"><h3>{{ turn.question }}</h3><p>{{ turn.state==='answered'?turn.answer:turn.state==='skipped'?'当时已跳过':'当时未回答' }}</p></article><details v-for="analysis in session.analyses" :key="analysis.id"><summary>历史分析 · 会话 v{{ analysis.session_version }}</summary><p>{{ analysis.payload.summary }}</p><p v-for="line in analysis.payload.analysis" :key="line">{{ line }}</p></details></section><details v-if="data?.revisions.length"><summary>原文历史版本</summary><article v-for="rev in data.revisions" :key="rev.id"><h3>v{{ rev.version }}</h3><p v-if="rev.correction_reason">更正说明：{{ rev.correction_reason }}</p><p class="original-text">{{ rev.content }}</p></article></details>
<details v-if="data?.sessions.length"><summary>历史回顾会话</summary><button v-for="row in data.sessions" :key="row.id" class="btn" @click="loadSession(row.id)">原文 v{{ row.source_version }} · {{ {draft:'可继续',running:'处理中',needs_input:'等待补充',ready:'已生成'}[row.state]||'历史会话' }}</button></details>
</div></template>
