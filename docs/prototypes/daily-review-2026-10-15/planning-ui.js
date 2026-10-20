// Included inline in index.html so the demo also works by double-clicking one HTML file.
function seedPlans(){return [
  {id:'study',name:'高数专项练习 45 分钟',goal:'考研复习',main:true,attribute:'智力',schedule:{type:'daily',anchor:'2026-10-12'},enabled:true},
  {id:'run',name:'跑步 30 分钟',goal:'恢复规律运动',main:false,attribute:'体能',schedule:{type:'weekdays',days:[1],anchor:'2026-10-12'},enabled:true},
  {id:'strength',name:'力量训练 20 分钟',goal:'恢复规律运动',main:false,attribute:'体能',schedule:{type:'interval',every:2,anchor:'2026-10-15'},enabled:true}
]}
function freshCare(){return {sleep:{state:'missing',choice:'',detail:''},meal:{state:'missing',choice:'',detail:''},move:{state:'missing',choice:'',detail:''}}}
function freshReview(){return {note:'',answers:[],complete:false}}
function initializePlanner(){
  state.date ||= '2026-10-15';state.plans ||= seedPlans();state.occurrences ||= {};state.ledger ||= [];
  state.careDays ||= {[state.date]:state.care};state.reviewDays ||= {[state.date]:state.review};state.drafts ||= {};state.diaryDrafts ||= {};state.recordKind='event';
  for(const record of state.records){record.date ||= '2026-10-15';if(record.id==='math')record.possiblePlanId='study';}
  for(const review of Object.values(state.reviewDays))delete review.mood;
  state.care=state.careDays[state.date] ||= freshCare();state.review=state.reviewDays[state.date] ||= freshReview();
}
function dayFacts(){return state.records.filter(record=>record.date===state.date)}
function eventFacts(){return dayFacts().filter(record=>record.kind!=='diary')}
function diaryFacts(){return dayFacts().filter(record=>record.kind==='diary')}
function saveComposerDraft(){(state.recordKind==='diary'?state.diaryDrafts:state.drafts)[state.date]=sessionDraft;}
function chooseRecordKind(kind){if(kind==='diary'){setPage('review');return;}captureDraft();saveComposerDraft();state.recordKind='event';sessionDraft=state.drafts[state.date]||'';persist();render();}
function recordDays(kind){
  const dates=[...new Set(state.records.filter(record=>kind==='diary'?record.kind==='diary':record.kind!=='diary').map(record=>record.date).filter(date=>date<=state.date))].sort();
  let longest=0,run=0,previous='';for(const date of dates){run=previous&&dateDifference(date,previous)===1?run+1:1;longest=Math.max(longest,run);previous=date;}
  const days=new Set(dates);let cursor=days.has(state.date)?state.date:new Date(Date.parse(state.date+'T00:00:00Z')-86400000).toISOString().slice(0,10),current=0;
  while(days.has(cursor)){current++;cursor=new Date(Date.parse(cursor+'T00:00:00Z')-86400000).toISOString().slice(0,10);}
  return {total:dates.length,current,longest};
}
function recordStatsHTML(){return `<section class="card stats-card"><details><summary>我的记录天数</summary><div class="record-stats">${[['event','事件'],['diary','日记']].map(([kind,label])=>{const s=recordDays(kind);return `<div><h3>${label}</h3><p>累计 <strong>${s.total}</strong> 天</p><p>当前连续 ${s.current} 天 · 最长连续 ${s.longest} 天</p></div>`}).join('')}</div><p class="small muted">同一天记多条只算一天。AI 问答草稿不单独计天；保存日记后计日记天数；今天尚未记录时，当前连续暂从昨天计。</p></details></section>`}

function dayCaption(date=state.date){const d=new Date(date+'T00:00:00Z');return `${d.getUTCFullYear()} 年 ${d.getUTCMonth()+1} 月 ${d.getUTCDate()} 日 · 星期${'日一二三四五六'[d.getUTCDay()]}`}
function dateDifference(a,b){return Math.round((Date.parse(a+'T00:00:00Z')-Date.parse(b+'T00:00:00Z'))/86400000)}
function due(plan,date=state.date){
  if(!plan.enabled||dateDifference(date,plan.schedule.anchor)<0)return false;
  if(plan.schedule.type==='daily')return true;
  if(plan.schedule.type==='weekdays')return plan.schedule.days.includes(new Date(date+'T00:00:00Z').getUTCDay());
  return dateDifference(date,plan.schedule.anchor)%plan.schedule.every===0;
}
function scheduleLabel(plan){const s=plan.schedule;if(s.type==='daily')return '每天';if(s.type==='weekdays')return '每周'+s.days.map(day=>'日一二三四五六'[day]).join('、');return `每隔 ${s.every} 天 · 从 ${s.anchor.slice(5).replace('-','/')} 开始`}
function occurrenceKey(plan,date=state.date){return `${plan.id}@${date}`}
const completionLabels={done:'完成',partial:'部分完成',missed:'未完成'};
let activePlanId=null,activeCompletion='done';
function amountLabel(suggestion){return `金币 +${suggestion.coins} · ${suggestion.attribute} +${suggestion.delta}`}
function plannedRow(plan){
  const item=state.occurrences[occurrenceKey(plan)],settled=item?.settled,confirmed=settled||item?.resultConfirmed;
  const status=settled?'已入账':item?`${completionLabels[item.status]} · ${confirmed?'已确认':'待确认'}`:'待记录';
  let action='';
  if(settled)action=`<div class="settled-line">${svg('check')}<span>${amountLabel(item.suggestion)} <small>（示例）</small></span></div><button class="link-btn" data-plan-view="${plan.id}">查看事实与入账</button>`;
  else if(confirmed)action=`<button class="link-btn" data-plan-view="${plan.id}">查看记录</button>`;
  else action=`<div class="plan-actions" role="group" aria-label="${esc(plan.name)} 完成状态">${Object.entries(completionLabels).map(([key,label])=>`<button class="btn small-btn ${key==='done'?'soft':''}" data-plan-action="${plan.id}" data-completion="${key}" aria-pressed="${item?.status===key}">${label}</button>`).join('')}</div>${item?.suggestion?`<div class="suggestion-strip"><div><span class="small muted">建议 · 示例数值</span><p>${amountLabel(item.suggestion)}</p></div><button class="btn primary small-btn" data-confirm-plan="${plan.id}">确认入账</button></div>`:item?.status==='missed'?`<div class="suggestion-strip"><span>本次选择：未完成</span><button class="btn primary small-btn" data-confirm-missed="${plan.id}">确认未完成</button></div>`:''}`;
  return `<article class="plan-row"><div class="row between"><h3>${esc(plan.name)}</h3><span class="plan-status ${confirmed?'settled':''}">${status}</span></div><p class="plan-meta">${esc(plan.goal||'独立计划')}${plan.main?' · <span class="main-tag">当前主线</span>':''} · ${esc(scheduleLabel(plan))}</p>${action}</article>`;
}
function ledgerHTML(){const rows=state.ledger.filter(row=>row.date===state.date);if(!rows.length)return '';return `<details class="ledger-details"><summary>今天的入账记录 · ${rows.length} 笔</summary>${rows.map(row=>`<div class="ledger-row"><strong>${esc(row.title)}</strong><span>${amountLabel(row.suggestion)}（示例）</span><small>${esc(row.goal||'独立计划')} · 关联同一条事实</small></div>`).join('')}</details>`}
function planCard(){const plans=state.plans.filter(plan=>due(plan));return `<section class="card plans-card"><div class="section-head"><h2>今日计划 <span class="count">${plans.length} 项</span></h2><button class="link-btn" data-nav="plans">管理计划 →</button></div><p class="care-intro">来自你自己设置的安排。</p>${plans.length?plans.map(plannedRow).join(''):'<p class="empty-note">今天没有到期的计划，按自己的节奏安排就好。</p>'}${ledgerHTML()}</section>`}
function today(){const logged=Object.values(state.care).filter(v=>v.state==='recorded').length;return `<header class="masthead"><p class="eyebrow">${dayCaption()}</p><h1>今天</h1><p>记一件事，也照顾一下自己。</p></header><div class="columns"><div class="stack today-primary"><section class="card composer"><h2>想留下什么？</h2><div class="record-kind row" role="group" aria-label="记录类型"><button class="btn small-btn" data-record-kind="event" aria-pressed="${state.recordKind==='event'}">记事件</button><button class="btn small-btn" data-record-kind="diary" aria-pressed="${state.recordKind==='diary'}">写日记</button></div><label for="event-input" class="small muted">${state.recordKind==='diary'?'给这一天留一篇日记。':'记下一件具体的事。'}</label><textarea id="event-input" maxlength="20000" placeholder="例如：下午整理了三道错题，终于弄懂了一个卡住很久的地方。">${esc(sessionDraft)}</textarea><div class="composer-foot"><span class="day-tag">${svg('date')}默认记在这一天</span><button class="btn primary" id="save-event">${state.recordKind==='diary'?'保存日记':'保存事件'}</button></div></section>${planCard()}<section class="card records-card"><div class="section-head"><h2>今天的事件 <span class="count">${eventFacts().length} 条</span></h2><span class="small muted">原文留在这里</span></div><div id="record-list">${eventFacts().map(recordHTML).join('')||'<p class="empty-note">还没有事件记录。</p>'}</div></section><section class="card records-card diary-card"><div class="section-head"><h2>今天的日记 <span class="count">${diaryFacts().length} 篇</span></h2><button class="link-btn" data-record-kind="diary">写日记 →</button></div>${diaryFacts().map(recordHTML).join('')||'<p class="empty-note">这一天还没有日记，事件记录会单独保留。</p>'}</section></div><div class="stack today-secondary"><section class="card" id="care-card"><div class="section-head"><h2>也记得照顾自己</h2><button class="toggle" id="toggle-care" role="switch" aria-label="显示生活清单" aria-checked="${state.showCare}"></button></div>${state.showCare?`<p class="care-intro">不是打卡要求，想记哪项就记哪项。</p><div id="care-items">${careHTML()}</div><p class="small muted" style="margin-top:18px">已记 ${logged} 项 · 可以跳过，不做扣分判断</p>`:'<p class="small muted">生活清单已收起，随时可以重新开启。</p>'}</section><section class="card night-card"><div class="night-head"><h2>${state.review.complete?'今天已经留下一页':'留几分钟，回看今天'}</h2><span class="night-mark">${svg('moon')}</span></div><p>${state.review.complete?'日记已经保存在这个示例里。想补充的话，随时回来。':'记录已经在这里，不用再抄一遍。写一点感受，或让 AI 陪你回想。'}</p><button class="btn ${state.review.complete?'soft':'primary'}" data-nav="review">${state.review.complete?'查看今日日记':'写晚间日记'} →</button></section>${recordStatsHTML()}</div></div>`}
function diaryIsSaved(){return diaryFacts().some(record=>record.id===state.review.diaryId&&record.content===state.review.note.trim());}
function prepareDiary(){
  if(!state.review.note&&state.diaryDrafts[state.date])state.review.note=state.diaryDrafts[state.date];
  const existing=diaryFacts().find(record=>record.id===state.review.diaryId)||diaryFacts()[0];
  if(existing){state.review.diaryId=existing.id;if(!state.review.note)state.review.note=existing.content;}
}
function saveDiary(){
  captureDraft();const text=state.review.note.trim();if(!text){toast('写下一点内容再保存日记，也可以稍后再来。');return;}
  let record=diaryFacts().find(record=>record.id===state.review.diaryId);
  if(!record){record={id:'diary@'+state.date,date:state.date,time:'刚刚',kind:'diary'};state.records.unshift(record);state.review.diaryId=record.id;}
  record.title=text.slice(0,30)+(text.length>30?'…':'');record.content=text;state.review.complete=true;
  if(persist()){render();toast('日记已保存在本机示例中。');}
}
function review(){return `<header class="masthead"><p class="eyebrow">${dayCaption()} · 晚间日记</p><h1>把今天，轻轻收好。</h1><p>日记原文、回顾问答和 AI 分析，在这里分开保留。</p></header><div class="review-layout"><div class="stack"><section class="card review-note"><div class="section-head"><label for="review-note"><h2>我的日记原文</h2></label>${state.review.complete?`<span class="saved-badge">${diaryIsSaved()?svg('check'):''}${diaryIsSaved()?'已保存':'草稿未保存'}</span>`:''}</div><textarea id="review-note" maxlength="20000" placeholder="今天有什么想留给自己？不需要把事件再抄一遍。">${esc(state.review.note)}</textarea><div class="row between wrap"><span class="small muted">不需要 AI 也可以保存日记。</span><button class="btn primary" id="save-review">保存日记</button></div><div class="review-divider"></div>${aiHTML()}</section></div><aside class="card review-source"><div class="section-head"><h2>今天的事件</h2><span class="count">${eventFacts().length} 条</span></div>${eventFacts().map(recordHTML).join('')||'<p class="empty-note">这一天还没有事件。</p>'}<div class="review-divider"></div><h2>今天的计划</h2>${state.plans.filter(plan=>due(plan)).map(plan=>`<div class="record"><h3>${esc(plan.name)}</h3><p class="small muted">${completionLabels[state.occurrences[occurrenceKey(plan)]?.status]||'待记录'}</p></div>`).join('')||'<p class="empty-note">今天没有到期安排。</p>'}<div class="mini-note"><span>还想到一件新的事？</span><button class="link-btn" data-nav="today">回到今天记一下 →</button></div></aside></div>`}
function planningPage(){return `<header class="masthead"><p class="eyebrow">计划与目标</p><h1>把想做的事，安排进日常。</h1><p>设置具体行动与周期，到那一天再提醒你。</p></header><div class="planning-layout"><section class="card"><div class="section-head"><h2>我的安排 <span class="count">共 ${state.plans.length} 项</span></h2><span class="page-label">主线 · 考研复习</span></div>${state.plans.map(plan=>`<article class="plan-row"><div class="row between"><h3>${esc(plan.name)}</h3><span class="small muted">${plan.enabled?'进行中':'已停用'}</span></div><p class="plan-meta">目标：${esc(plan.goal||'未关联')} ${plan.main?'· 当前主线':''}</p><p class="small">${esc(scheduleLabel(plan))}${due(plan)?' · 预览当天有安排':''}</p><button class="link-btn" data-toggle-plan="${plan.id}">${plan.enabled?'停用后续提醒':'重新启用'}</button></article>`).join('')}<div class="mini-note"><span>想看指定周几和隔天提醒？</span><button class="link-btn" data-preview-date="2026-10-19">切到周一看看 →</button></div></section><section class="card"><h2>添加一项安排</h2><div class="plan-form"><label>行动名称<input id="new-plan-name" maxlength="100" placeholder="例如：跑步 30 分钟"></label><label>关联目标（选填）<input id="new-plan-goal" maxlength="100" placeholder="例如：恢复规律运动"></label><label>提醒周期<select id="new-plan-type"><option value="daily">每天</option><option value="weekdays">指定周几</option><option value="interval">每隔 N 天</option></select></label><div id="weekday-fields" hidden><span class="small muted">选择日期</span><div class="weekdays">${[1,2,3,4,5,6,0].map(day=>`<label><input type="checkbox" name="weekday" value="${day}">周${'日一二三四五六'[day]}</label>`).join('')}</div></div><label id="interval-fields" hidden>间隔天数<input id="new-plan-interval" type="number" value="2" min="1" max="365" step="1"></label><label>从哪天开始<input id="new-plan-anchor" type="date" value="${state.date}" min="2020-01-01" max="2099-12-31"></label><label class="checkbox-label"><input id="new-plan-main" type="checkbox">这项行动关联我的当前主线</label><button class="btn primary" id="create-plan">保存安排</button></div><p class="small muted" style="margin-top:16px">这里设置的是行动安排，不会因为新建目标就直接发奖。</p></section></div>`}
function setDemoDate(date){if(!/^\d{4}-\d{2}-\d{2}$/.test(date)||!Number.isFinite(Date.parse(date+'T00:00:00Z')))return;captureDraft();saveComposerDraft();state.careDays[state.date]=state.care;state.reviewDays[state.date]=state.review;state.date=date;state.care=state.careDays[date] ||= freshCare();state.review=state.reviewDays[date] ||= freshReview();if(currentPage==='review')prepareDiary();sessionDraft=(state.recordKind==='diary'?state.diaryDrafts:state.drafts)[date]||'';aiDraft='';aiActive=false;aiDone=false;persist();render();}
function openPlanAction(id,status){
  captureDraft();const plan=state.plans.find(plan=>plan.id===id);if(!plan)return;if(status==='missed'){recordMissedPlan(plan);return;}activePlanId=id;activeCompletion=status||'done';
  const item=state.occurrences[occurrenceKey(plan)];if(status&&(item?.settled||item?.resultConfirmed))return;const candidate=dayFacts().find(record=>record.possiblePlanId===id&&!record.planOccurrence),settled=item?.settled||item?.resultConfirmed;
  document.getElementById('plan-dialog-content').innerHTML=`<div class="head"><h2>${esc(plan.name)}</h2><button class="close-btn" data-close-plan aria-label="关闭">×</button></div><p>${esc(plan.goal||'独立计划')} · ${dayCaption()}</p>${settled?`<div class="settled-line" style="margin-top:20px">${svg('check')}${item.status==='missed'?'已确认未完成':'已确认入账'}</div>${item.suggestion?`<p>${amountLabel(item.suggestion)}（示例数值）</p>`:''}<p>${esc(item.detail||'用户报告'+completionLabels[item.status])}</p><p class="small muted">本次结果已确认，不能直接切换状态。</p><div class="actions"><button class="btn" data-close-plan>关闭</button></div>`:`<p class="plan-outcome">本次记录：<strong>${completionLabels[activeCompletion]}</strong></p><label class="small muted" for="plan-detail">实际做了多少、完成了什么？（可补充）</label><textarea id="plan-detail" maxlength="2000" placeholder="例如：原计划跑 30 分钟，今天跑了 15 分钟。">${esc(item?.detail||'')}</textarea>${candidate?`<label class="checkbox-label"><input id="reuse-plan-record" type="checkbox">关联已有原文：${esc(candidate.title)}</label><p class="small muted">勾选后复用这条事实，不重复创建事件。</p>`:''}<p class="small muted">先保存完成情况，再查看奖励与属性建议。</p><div class="actions"><button class="btn quiet" data-close-plan>取消</button><button class="btn primary" id="save-plan-outcome">保存完成情况</button></div>`}`;
  document.getElementById('plan-dialog').showModal();
}
function recordMissedPlan(plan){
  const key=occurrenceKey(plan),prior=state.occurrences[key];if(prior?.settled||prior?.resultConfirmed)return;
  const history=prior?[...(prior.history||[]),{status:prior.status,detail:prior.detail,suggestion:prior.suggestion}]:[];
  state.occurrences[key]={...prior,key,planId:plan.id,date:state.date,status:'missed',detail:'',suggestion:null,settled:false,resultConfirmed:false,history};
  persist();render();
}
function confirmMissedPlan(id){
  const plan=state.plans.find(plan=>plan.id===id);if(!plan)return;const item=state.occurrences[occurrenceKey(plan)];
  if(!item||item.status!=='missed'||item.settled||item.resultConfirmed)return;
  item.resultConfirmed=true;if(!persist()){item.resultConfirmed=false;return;}render();
}
function savePlanOutcome(){
  const plan=state.plans.find(plan=>plan.id===activePlanId),key=occurrenceKey(plan),prior=state.occurrences[key];
  if(prior?.settled||prior?.resultConfirmed){toast('这项结果已经确认，不能直接切换。');return;}
  const detail=document.getElementById('plan-detail').value.trim();
  const candidate=document.getElementById('reuse-plan-record')?.checked?dayFacts().find(record=>record.possiblePlanId===plan.id&&!record.planOccurrence):null;
  const recordId=prior?.recordId||candidate?.id||'plan-'+key;
  let record=state.records.find(record=>record.id===recordId);
  if(!record){record={id:recordId,date:state.date,time:'刚刚',title:plan.name+' · '+completionLabels[activeCompletion],content:detail||'用户记录：'+completionLabels[activeCompletion]+'。未补充实际时长或成果。',kind:'plan',planOccurrence:key};state.records.unshift(record);}
  else if(record.kind==='plan'){record.title=plan.name+' · '+completionLabels[activeCompletion];record.content=detail||'用户记录：'+completionLabels[activeCompletion]+'。未补充实际时长或成果。';}
  if(candidate)record.planOccurrence=key;
  const full=activeCompletion==='done';
  const suggestion=activeCompletion==='missed'?null:{attribute:plan.attribute||'属性示例',delta:full?.6:.2,coins:2+(plan.main?(full?3:1):0),mainBonus:plan.main?(full?3:1):0};
  const history=prior?[...(prior.history||[]),{status:prior.status,detail:prior.detail,suggestion:prior.suggestion}]:[];
  state.occurrences[key]={key,planId:plan.id,date:state.date,recordId,status:activeCompletion,detail,suggestion,settled:false,history};
  const ok=persist();document.getElementById('plan-dialog').close();render();if(ok)toast(suggestion?'完成情况已保存；确认前不会入账。':'未完成已记下，没有自动扣分。');
}
function confirmPlan(id){
  captureDraft();const plan=state.plans.find(plan=>plan.id===id),key=occurrenceKey(plan),item=state.occurrences[key];
  if(!item?.suggestion)return;
  if(item.settled||state.ledger.some(row=>row.key===key)){toast('已确认过，不会重复入账。');return;}
  item.settled=true;item.resultConfirmed=true;state.ledger.push({key,date:state.date,recordId:item.recordId,title:plan.name,goal:plan.goal,suggestion:{...item.suggestion}});
  if(persist()){render();toast('已记入示例流水；正式数值规则仍待商定。');}
}
function createPlan(){
  const name=document.getElementById('new-plan-name').value.trim(),goal=document.getElementById('new-plan-goal').value.trim(),type=document.getElementById('new-plan-type').value,anchor=document.getElementById('new-plan-anchor').value;
  const days=[...document.querySelectorAll('input[name=weekday]:checked')].map(input=>Number(input.value)),every=Number(document.getElementById('new-plan-interval').value);
  if(!name){toast('先给行动起个名字。');document.getElementById('new-plan-name').focus();return;}
  if(!anchor||!Number.isFinite(Date.parse(anchor+'T00:00:00Z'))){toast('请选择开始日期。');return;}
  if(type==='weekdays'&&!days.length){toast('至少选一个星期几。');return;}
  if(type==='interval'&&(!Number.isInteger(every)||every<1||every>365)){toast('间隔填写 1～365 的整数。');return;}
  state.plans.push({id:'custom-'+crypto.randomUUID(),name,goal,main:document.getElementById('new-plan-main').checked,attribute:null,enabled:true,schedule:{type,anchor,...type==='weekdays'?{days}:{},...type==='interval'?{every}:{}}});
  if(persist()){render();toast('安排已保存，今日计划会按周期显示。');}
}
function nav(){const items=[['today','今天'],['plans','计划与目标'],['review','晚间日记'],['guide','AI 帮助']];for(const id of ['desktop-nav','mobile-nav'])document.getElementById(id).innerHTML=items.map(([key,label])=>`<button data-nav="${key}" ${currentPage===key?'aria-current="page"':''}>${svg(key==='plans'?'move':key)}<span>${label}</span></button>`).join('');}
function render(){nav();document.getElementById('demo-date').value=state.date;document.getElementById('app').innerHTML=currentPage==='plans'?planningPage():currentPage==='review'?review():currentPage==='guide'?guide():today();}
document.addEventListener('change',event=>{
  if(event.target.id==='demo-date'){setDemoDate(event.target.value);return;}
  if(event.target.id==='new-plan-type'){document.getElementById('weekday-fields').hidden=event.target.value!=='weekdays';document.getElementById('interval-fields').hidden=event.target.value!=='interval';}
});
document.addEventListener('click',event=>{
  const button=event.target.closest('button');if(!button)return;
  if(button.dataset.recordKind){chooseRecordKind(button.dataset.recordKind);return;}
  if(button.dataset.planAction){openPlanAction(button.dataset.planAction,button.dataset.completion);return;}
  if(button.dataset.planView){openPlanAction(button.dataset.planView);return;}
  if(button.dataset.confirmMissed){confirmMissedPlan(button.dataset.confirmMissed);return;}
  if(button.dataset.confirmPlan){confirmPlan(button.dataset.confirmPlan);return;}
  if(button.hasAttribute('data-close-plan')){document.getElementById('plan-dialog').close();return;}
  if(button.dataset.togglePlan){const plan=state.plans.find(plan=>plan.id===button.dataset.togglePlan);plan.enabled=!plan.enabled;persist();render();return;}
  if(button.dataset.previewDate){setDemoDate(button.dataset.previewDate);setPage('today');return;}
  if(button.id==='save-plan-outcome'){savePlanOutcome();return;}
  if(button.id==='create-plan')createPlan();
});

document.addEventListener('input',event=>{if(event.target.id==='review-note'){state.review.note=event.target.value;const badge=document.querySelector('.saved-badge');if(badge)badge.textContent=diaryIsSaved()?'已保存':'草稿未保存';}});
