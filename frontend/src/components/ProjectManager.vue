<script setup>
import { ref,computed,onMounted,onBeforeUnmount,watch } from 'vue'
import { api } from '../api'
import { localDate,storageKey,accountEpoch } from '../session'
import { useWorkflowWrite } from '../composables/useWorkflowWrite'
import ConfirmDialog from './ui/ConfirmDialog.vue'
const props=defineProps({todayOnly:Boolean,category:String,focusKey:String}),emit=defineEmits(['saved'])
const day=ref(localDate()),items=ref([]),goals=ref([]),careConfig=ref(null),careEnabled=ref(false),error=ref(''),notice=ref('')
const editor=ref(false),editing=ref(null),removing=ref(null),filter=ref('all'),showRemoved=ref(false),drafts=ref({}),writes=useWorkflowWrite('projects'),epoch=accountEpoch
const expanded=ref({}),sorting=ref(false),advanced=ref(false),showAll=ref(false)
const visibleRows=computed(()=>showAll.value?rows.value:rows.value.slice(0,4))
const fresh=()=>({name:'',category:props.category||'plan',frequency:'daily',start:localDate(),effective_from:localDate(),weekdays:[],interval:1,planned_minutes:null,note:'',goal_id:null,enabled:true,position:0,removed:false})
const form=ref(fresh()),frequencies={daily:'每天',workdays:'工作日',weekends:'周末',weekdays:'指定星期',interval:'间隔日',once:'指定一次',manual:'自行安排'}
let alive=true,generation=0
const key=p=>day.value+':'+p.key
const rows=computed(()=>items.value.filter(p=>(!props.focusKey||p.key===props.focusKey)&&(props.todayOnly?p.show_today:showRemoved.value||!p.removed)&&(!props.category||p.result_category===props.category)&&(filter.value==='all'||p.category===filter.value)))
const visible=computed(()=>!props.todayOnly||props.category!=='care'||rows.value.length>0||!!error.value)
try{drafts.value=JSON.parse(localStorage.getItem(storageKey('project-drafts'))||'{}')}catch{}
watch(drafts,v=>{try{localStorage.setItem(storageKey('project-drafts'),JSON.stringify(v))}catch{}},{deep:true,flush:'sync'})
async function load(){
 const token=++generation,selected=day.value
 try{
  const [result,g]=await Promise.all([api.flow('/projects?day='+selected+(!props.todayOnly?'&include_removed=true':'')),api.listGoals()])
  if(!alive||epoch!==accountEpoch||token!==generation)return
  items.value=result.items;goals.value=g;careConfig.value=result.care_config;careEnabled.value=!!result.care_config?.enabled
  for(const p of result.items){
   const states=p.result_category==='care'?['recorded','skipped']:['done','partial','missed']
   if(!drafts.value[key(p)])drafts.value[key(p)]={state:p.entry?.state||p.entry?.outcome||states[0],content:p.entry?.facts?.content||p.entry?.history?.at(-1)?.content||'',ai_permission:'private',correction:false,reason:''}
   else if(!p.entry&&!states.includes(drafts.value[key(p)].state))drafts.value[key(p)].state=states[0]
  }
 }catch(e){if(alive&&epoch===accountEpoch)error.value=e.message}
}
watch(day,load);onMounted(load);onBeforeUnmount(()=>{alive=false;generation++})
function editable(p){
 const r=p.rule||{}
 return {name:p.name,category:p.category,frequency:r.frequency,start:r.start||localDate(),effective_from:[localDate(),p.effective_from||r.start||localDate()].sort().at(-1),weekdays:[...(r.weekdays||[])],interval:r.interval||1,planned_minutes:r.planned_minutes??null,note:r.note||'',goal_id:p.goal_id,enabled:p.enabled,position:p.position??0,removed:!!p.removed}
}
function edit(p=null){editing.value=p;form.value=p?editable(p):fresh();advanced.value=false;editor.value=true;error.value=''}
function allowedBody(value,p=null){
 const {name,category,frequency,start,weekdays,interval,goal_id,enabled,position,removed,note}=value
 return {name,category,frequency,start,weekdays,interval,goal_id,enabled,position,removed,note,planned_minutes:value.planned_minutes===''?null:value.planned_minutes,expected_version:p?.version||0,...(p?{effective_from:value.effective_from}:{})}
}
async function move(p,step){
 const shown=rows.value.filter(row=>!row.removed),index=shown.findIndex(row=>row.key===p.key),other=shown[index+step]
 if(!other)return
 const ordered=items.value.filter(row=>!row.removed),a=ordered.findIndex(row=>row.key===p.key),b=ordered.findIndex(row=>row.key===other.key)
 ;[ordered[a],ordered[b]]=[ordered[b],ordered[a]]
 try{await writes.send('/projects/reorder',{items:ordered.map(row=>({key:row.key,version:row.version}))});await load();notice.value='顺序已保存。';error.value=''}catch(e){error.value=e.message;await load()}
}
async function save(){
 if(!form.value.name.trim()){error.value='请填写项目名称。';return}
 try{await writes.send('/projects'+(editing.value?'/'+editing.value.origin+'/'+editing.value.id:''),allowedBody(form.value,editing.value),editing.value?'PUT':'POST');editor.value=false;await load();error.value='';notice.value='项目已保存。'}catch(e){error.value=e.message}
}
async function removeProject(){
 const p=removing.value;if(!p)return
 try{await writes.send('/projects/'+p.origin+'/'+p.id,allowedBody({...editable(p),removed:true,effective_from:localDate()},p),'PUT');removing.value=null;await load();notice.value='已移除项目；原记录、结果与结算仍可查看。';error.value=''}catch(e){error.value=e.message}
}
async function saveCareConfig(){
 try{await writes.send('/care/config',{expected_version:careConfig.value?.version||0,enabled:careEnabled.value,ai_allowed:!!careConfig.value?.ai_allowed},'PUT');await load();notice.value='首页照顾清单显示已保存。';error.value=''}catch(e){error.value=e.message}
}
async function recover(){const p=writes.pending.value;if(!p)return;try{await writes.send(p.path,p.body,p.method);editor.value=false;removing.value=null;await load();error.value='';notice.value='上次操作结果已恢复。'}catch(e){error.value=e.message}}
async function result(p){
 const d=drafts.value[key(p)];if(!d)return;error.value=''
 try{
  const common={expected_version:p.entry?.version||0,content:d.content,ai_permission:d.ai_permission,correction:d.correction,reason:d.reason}
  const path=p.origin==='care'?`/care/items/${p.id}/entries/${day.value}`:`/plan-schedules/${p.id}/occurrences/${day.value}`
  const body=p.origin==='care'?{...common,item_version:p.version,state:d.state}:{...common,schedule_version:p.version,outcome:d.state}
  const saved=await writes.send(path,body,'PUT');const event=saved.event||((saved.event_id)?await api.getEvent(saved.event_id):null)
  if(event&&d.ai_permission==='allowed'){try{await api.submitJob(event.id,{request_key:crypto.randomUUID(),event_version:event.content_version,operation:'facts'})}catch(e){error.value='实际记录已保存；'+e.message}}
  delete drafts.value[key(p)];expanded.value[p.key]=false;await load();emit('saved');notice.value=error.value?'当次结果已保存，分析尚未完成。':d.ai_permission==='allowed'?'结果已保存，AI 分析已提交；到原文查看属性与金币建议。':'当次结果已保存。'
 }catch(e){error.value=e.message}
}
</script>
<template>
 <section v-if="visible" class="card project-manager" :data-project-category="category||'all'">
  <div class="section-heading"><h2>{{ focusKey?'记录这次':todayOnly?(category==='care'?'照顾自己':'今天的安排'):'项目与安排' }}</h2><button v-if="!todayOnly&&!focusKey" class="btn primary" :disabled="writes.busy.value||!!writes.pending.value" @click="edit()">添加项目</button><RouterLink v-else to="/plans">管理项目 →</RouterLink></div>
  <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
  <button v-if="writes.pending.value" class="btn" :disabled="writes.busy.value" @click="recover">恢复上次保存</button>
  <template v-if="!todayOnly&&!focusKey">
   <div class="action-group project-filters"><label>查看日期<input type="date" v-model="day"/></label><label>项目类型<select v-model="filter"><option value="all">全部项目</option><option value="plan">行动计划</option><option value="care">照顾自己</option></select></label><button class="btn" :aria-pressed="sorting" @click="sorting=!sorting">{{ sorting?'完成排序':'调整顺序' }}</button></div>
   <details class="compact-options"><summary>显示选项与已移除项目</summary><label><input type="checkbox" v-model="showRemoved"/>查看已移除项目与历史</label><div class="action-group"><label><input type="checkbox" v-model="careEnabled"/>在今天显示照顾清单</label><button class="btn" :disabled="writes.busy.value||!!writes.pending.value" @click="saveCareConfig">保存清单显示</button></div></details>
  </template>
  <p v-if="!rows.length" class="muted">{{ todayOnly?'今天没有到期项目。':'还没有项目，按自己的节奏添加一个。' }}</p>
  <article v-for="p in visibleRows" :key="p.key" class="project-row" :data-project-key="p.key">
   <div class="section-heading"><h3>{{ todayOnly?p.effective?.name||p.name:p.name }}</h3><span class="tag">{{ (todayOnly?p.result_category:p.category)==='care'?'照顾自己':'行动计划' }}{{ p.removed?' · 已移除':'' }}</span></div>
   <p class="muted project-note">{{ frequencies[p.rule.frequency] }}<template v-if="!p.enabled"> · 已停用</template><template v-if="p.category==='plan'&&p.rule.planned_minutes"> · {{ p.rule.planned_minutes }} 分钟</template><template v-if="(todayOnly?p.effective?.rule:p.rule)?.note"> · {{ (todayOnly?p.effective?.rule:p.rule).note }}</template></p>
   <div v-if="sorting&&!p.removed" class="action-group"><button class="btn" :aria-label="'上移'+p.name" :disabled="writes.busy.value||!!writes.pending.value||rows.filter(r=>!r.removed)[0]?.key===p.key" @click="move(p,-1)">↑ 上移</button><button class="btn" :aria-label="'下移'+p.name" :disabled="writes.busy.value||!!writes.pending.value||rows.filter(r=>!r.removed).at(-1)?.key===p.key" @click="move(p,1)">↓ 下移</button></div>
   <p v-if="p.entry" class="result-summary">{{ {recorded:'已记录',skipped:'已跳过',done:'已完成',partial:'部分完成',missed:'未完成'}[p.entry.state||p.entry.outcome] }}<RouterLink v-if="p.entry.event_id" :to="'/events/'+p.entry.event_id"> 查看原文与分析 →</RouterLink></p>
   <details class="project-details" :open="!!expanded[p.key]" @toggle="expanded[p.key]=$event.target.open"><summary>{{ p.entry?'查看记录 / 更正':todayOnly?'记录这一次':'详情与记录' }}</summary>
   <div v-if="!todayOnly" class="action-group"><button class="text-button" :disabled="writes.busy.value||!!writes.pending.value" @click="edit(p)">{{ p.removed?'查看 / 恢复项目':'编辑项目' }}</button><button v-if="!p.removed" class="text-button danger" :disabled="writes.busy.value||!!writes.pending.value" @click="removing=p">移除项目</button></div>
   <template v-if="p.scheduled_due||p.entry">
    <template v-if="!p.removed&&drafts[key(p)]&&(!p.entry||drafts[key(p)].correction)">
     <label>实际结果<select v-model="drafts[key(p)].state"><template v-if="p.result_category==='care'"><option value="recorded">记一句</option><option value="skipped">今天跳过</option></template><template v-else><option value="done">完成</option><option value="partial">部分完成</option><option value="missed">未完成</option></template></select></label>
     <template v-if="!['skipped','missed'].includes(drafts[key(p)].state)"><label>实际发生了什么<textarea v-model="drafts[key(p)].content" rows="2" maxlength="10000"/></label><label>保存方式<select v-model="drafts[key(p)].ai_permission"><option value="private">只保存，不交给 AI</option><option value="allowed">保存并请 AI 分析</option></select></label></template>
     <label v-if="drafts[key(p)].correction">更正原因<input v-model="drafts[key(p)].reason" maxlength="2000"/></label><button class="btn" :disabled="writes.busy.value||!!writes.pending.value" @click="result(p)">{{ ['skipped','missed'].includes(drafts[key(p)].state)?'确认并保存结果':'保存实际记录' }}</button>
    </template><button v-else-if="!p.removed&&drafts[key(p)]" class="text-button" @click="drafts[key(p)].correction=true">明确更正这次结果</button>
   </template>
   <details v-if="!todayOnly&&p.history.length"><summary>项目历史</summary><p v-for="(h,n) in p.history" :key="n">{{ h.name||p.name }} · 排期 {{ h.rule?.start||'旧安排' }} · 生效 {{ h.effective_from||h.rule?.start||'旧安排' }} · {{ h.rule?.category==='care'?'照顾自己':'行动计划' }} · {{ h.rule?.category==='care'?(h.rule?.note||'未设补充信息'):(h.rule?.planned_minutes??'未设')+' 分钟' }}</p></details>
   </details>
  </article>
 <button v-if="rows.length>4" class="text-button" @click="showAll=!showAll">{{ showAll?'收起列表':'查看全部 '+rows.length+' 项' }}</button>
 </section>
 <ConfirmDialog :open="editor" :title="editing?'编辑项目':'添加项目'" confirm-label="保存项目" initial-focus="input[maxlength='80']" :busy="writes.busy.value" @cancel="editor=false" @confirm="save">
  <p v-if="error" class="error">{{ error }}</p><label>项目名称<input v-model="form.name" maxlength="80" required/></label>
  <div class="form-grid"><label>类型<select v-model="form.category" aria-label="项目类型"><option value="plan">行动计划</option><option value="care">照顾自己</option></select></label><label>排期<select v-model="form.frequency"><option v-for="(label,key) in frequencies" :key="key" :value="key">{{ label }}</option></select></label></div>
  <label v-if="form.category==='care'">补充信息（可空）<textarea v-model="form.note" maxlength="2000" rows="2" placeholder="例如：午饭后散步，或睡前放下手机"/></label><label v-else>预计分钟（可空）<input type="number" min="1" max="1440" v-model.number="form.planned_minutes"/></label>
  <details :open="form.frequency==='once'||form.frequency==='interval'||advanced" @toggle="advanced=$event.target.open"><summary>日期与关联目标</summary><div class="form-grid"><label>排期开始 / 间隔起算日<input type="date" v-model="form.start" aria-label="排期起算日" required/></label><label v-if="editing">修改生效日<input type="date" v-model="form.effective_from" :min="localDate()" aria-label="修改生效日" required/></label></div>
  <p v-if="editing" class="muted small">修改从生效日影响之后的安排，保留历史结果。</p>
  <label>目标（可不选）<select v-model="form.goal_id"><option :value="null">不关联目标</option><option v-for="g in goals.filter(g=>g.status==='active')" :key="g.id" :value="g.id">{{ g.description }}</option></select></label></details>
  <label v-if="form.frequency==='interval'">间隔天数<input type="number" min="1" max="366" v-model.number="form.interval"/></label>
  <div v-if="form.frequency==='weekdays'" class="action-group"><label v-for="(n,i) in ['一','二','三','四','五','六','日']" :key="i"><input type="checkbox" :value="i" v-model="form.weekdays"/>周{{ n }}</label></div>
  <label><input type="checkbox" v-model="form.enabled"/>启用项目</label><label v-if="editing?.removed"><input type="checkbox" v-model="form.removed"/>保留移除状态（取消勾选可恢复）</label>
 </ConfirmDialog>
 <ConfirmDialog :open="!!removing" title="移除项目" confirm-label="确认移除项目" :busy="writes.busy.value" @cancel="removing=null" @confirm="removeProject"><p>{{ removing?.name }}</p><p>从当前项目和首页隐藏，原记录、当次结果、事实身份及结算全部保留。可在管理入口查看已移除项目与历史。</p><p v-if="error" class="error">{{ error }}</p></ConfirmDialog>
</template>
