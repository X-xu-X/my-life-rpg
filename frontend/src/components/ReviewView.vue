<script setup>
import { ref, watch, onMounted } from 'vue'
import PageHeader from './ui/PageHeader.vue'
import RecordPreview from './ui/RecordPreview.vue'
import { api } from '../api'
import { account, localDate, storageKey } from '../session'
const day=ref(localDate()),data=ref(null),note=ref(''),error=ref(''),notice=ref(''),busy=ref(false)
const zone=ref(account.value?.timezone || 'Asia/Shanghai'),history=ref([]),conflict=ref(false)
const expectedVersion=ref(0),zoneOpen=ref(false),loading=ref(false)
let loadedDay='',generation=0
const draftKey=value=>storageKey('review-draft:'+value+':'+zone.value)
watch([note,conflict],()=>{if(!loadedDay)return;try{localStorage.setItem(draftKey(loadedDay),JSON.stringify({note:note.value,version:expectedVersion.value,conflict:conflict.value}))}catch{}})
async function load(){
  const selected=day.value,current=++generation;loadedDay='';notice.value='';loading.value=true
  try{
    const result=await api.getReview(selected,zone.value);if(current!==generation)return
    let draft;try{draft=JSON.parse(localStorage.getItem(draftKey(selected))||'null')}catch{}
    data.value=result;expectedVersion.value=result.version;conflict.value=!!draft && (draft.conflict || draft.version!==result.version)
    loadedDay=selected;note.value=typeof draft?.note==='string'?draft.note:result.note;error.value=''
    history.value=(await api.listReviews()).items
  }catch(e){if(current===generation)error.value=e.message}finally{if(current===generation)loading.value=false}
}
async function compare(){const text=note.value;await load();note.value=text;conflict.value=true}
async function selectReview(row){if(busy.value)return;day.value=row.date;zone.value=row.timezone;await load()}
async function save(){if(busy.value||loadedDay!==day.value||conflict.value)return;busy.value=true;error.value='';try{await api.putReview(loadedDay,{note:note.value,completion:true,expected_version:expectedVersion.value,timezone:data.value.timezone});loadedDay='';try{localStorage.removeItem(draftKey(day.value))}catch{}await load();notice.value='回顾已保存。今天就到这里。'}catch(e){error.value=e.message;if(e.status===409)await compare()}finally{busy.value=false}}
onMounted(load)
</script>
<template>
  <div class="reading-page"><PageHeader title="睡前回顾" description="把今天轻轻收好。" />
  <div class="review-options"><label>回顾日期<input v-model="day" type="date" :disabled="busy" @change="load" /></label><details><summary>更多日期选项</summary><button type="button" class="btn" :disabled="busy" :aria-expanded="zoneOpen" @click="zoneOpen=!zoneOpen">修改时区</button><label v-if="zoneOpen">回顾时区<input v-model="zone" :disabled="busy" @change="load" /></label></details></div>
  <details v-if="history.length"><summary>已保存的回顾</summary><button v-for="row in history" :key="row.id" class="btn" :disabled="busy" @click="selectReview(row)">{{ row.date }} · {{ row.timezone }}</button></details>
  <p v-if="loading" role="status">正在读取回顾…</p><div v-if="error" class="read-error" role="alert"><p>{{ error }}</p><button class="btn" :disabled="busy || loading" @click="load">重新读取</button></div>
  <template v-if="data"><p class="muted">{{ day }} · {{ zone }}，你留下了 {{ data.events.length }} 段记录。回顾引用原事实，不会再次发奖。</p>
    <RecordPreview v-for="event in data.events" :key="event.id" :to="'/events/'+event.id" :title="event.title" :summary="event.content.slice(0,200)"><span>{{ data.judgments.find(j=>j.event_id===event.id)?.status==='confirmed'?'已入账 · 只读引用':'回原记录补充或确认' }}</span></RecordPreview>
    <section v-if="conflict" class="card review-conflict" role="alert"><p>服务器回顾已变化。你的输入已保留，请比较后决定是否重新提交。</p><p>你的当前输入完整保留在下方；服务器内容：</p><p class="original-text">{{ data.note || '（空）' }}</p><button class="btn" @click="conflict=false">比较后提交我的输入</button><button class="btn" @click="note=data.note;conflict=false">使用服务器内容</button></section>
    <label>值得记住的一件事（可选）<textarea v-model="note" rows="5" maxlength="20000" :disabled="busy" placeholder="不用 AI，也可以给今天留一句话。" /></label>
    <div class="review-controls"><button class="btn primary" :disabled="busy || loading || conflict" @click="save">{{ busy?'保存中…':'结束回顾' }}</button><RouterLink class="btn" to="/">补记新事情</RouterLink><button class="btn" :disabled="busy || loading" @click="compare">保留输入并读取最新版本</button></div><p role="status" class="success">{{ notice }}</p>
  </template>
</div></template>
