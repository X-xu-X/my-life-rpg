// Included inline in index.html. Fictional review sessions, never a real model call.
function ensureReviewLog(){
  state.review.sessions ||= [];
  if(!state.review.sessions.length&&state.review.answers.length){
    state.review.sessions.push({id:'legacy-review',state:'finished',startedAt:'',model:'旧版示例',snapshot:null,
      turns:state.review.answers.map((answer,index)=>({id:'legacy-'+index,question:answer.question,answer:answer.answer,state:answer.skipped?'skipped':'answered',askedAt:'',answeredAt:''})),analysis:null});
  }
}
function activeReviewSession(){ensureReviewLog();return state.review.sessions.find(session=>session.id===state.review.activeSessionId);}
function reviewTime(value){return value?new Date(value).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'}):'历史记录';}
function answerHTML(){
  ensureReviewLog();
  return state.review.sessions.map((session,index)=>{
    const turns=session.turns.filter(turn=>!(aiActive&&session.id===state.review.activeSessionId&&turn.state==='asked'));
    if(!turns.length&&!session.analysis)return '';
    return `<details class="review-session" ${index===state.review.sessions.length-1?'open':''}><summary>辅助回顾 ${index+1} · ${esc(reviewTime(session.startedAt))} · ${session.state==='finished'?'已结束':'可继续'}</summary><div class="answer-list">${turns.map((turn,i)=>`<article class="answer-item"><p class="speaker ai-speaker">AI 提问 ${i+1} <span>${esc(reviewTime(turn.askedAt))}</span></p><p>${esc(turn.question)}</p><p class="speaker user-speaker">我的回答</p><p>${turn.state==='skipped'?'<span class="muted">已跳过</span>':turn.state==='asked'?'<span class="muted">尚未回答</span>':esc(turn.answer)}</p></article>`).join('')}${session.analysis?`<article class="analysis-item"><p class="speaker ai-speaker">AI 分析 · 脚本示例</p><p>${esc(session.analysis.text)}</p></article>`:''}</div>${session.snapshot?`<details class="review-basis"><summary>查看本次参考的日记版本</summary><p class="small muted">${session.snapshot.saved?'已保存的日记':'当时的日记草稿'} · ${esc(reviewTime(session.startedAt))}</p><p>${esc(session.snapshot.diary||'当时没有日记正文，参考当天记录。')}</p></details>`:''}</details>`;
  }).join('');
}
function aiHTML(){
  const log=answerHTML();
  const history=log?`<div class="review-history"><h3>已保存的回顾问答与分析</h3>${log}</div>`:'';
  if(!aiActive)return `<div class="row between wrap"><div><div class="ai-title"><span class="spark">${svg('spark')}</span><h3>AI 辅助回顾</h3></div><p class="small muted" style="margin-top:6px">问答与分析单独保留，日记原文由你自己写。</p></div><button class="btn soft" id="start-ai">${activeReviewSession()?.state==='active'?'继续这次回顾':'让 AI 帮我回顾'}</button></div>${history}`;
  const q=questionList[questionIndex];
  return `<div class="ai-area"><div class="ai-top"><span>AI 辅助回顾 · 脚本示例，不调用模型</span><button class="link-btn" id="finish-ai">结束问答</button></div><p class="speaker ai-speaker">AI 提问</p><p class="ai-question">${esc(q.text)}</p><label class="small muted" for="ai-answer">我的回答</label><textarea id="ai-answer" maxlength="4000" placeholder="想到多少写多少，也可以跳过。">${esc(aiDraft)}</textarea><div class="row between"><span class="small muted">第 ${questionIndex+1} 个问题</span><div class="row"><button class="btn quiet" id="skip-question">跳过</button><button class="btn primary" id="answer-question">保存回答，继续</button></div></div></div>${history}`;
}
function saveAskedQuestion(session){
  const q=session.queue[session.index];
  if(q&&!session.turns.some(turn=>turn.index===session.index))session.turns.push({id:crypto.randomUUID(),index:session.index,question:q.text,state:'asked',answer:'',askedAt:new Date().toISOString(),answeredAt:''});
}
function startAI(){
  captureDraft();ensureReviewLog();
  let session=activeReviewSession();
  if(!session||session.state!=='active'){
    // Deliberately limited topic matching for fictional preview, not semantic model QA.
    const context=[...dayFacts().map(record=>record.content),state.review.note,...state.review.answers.filter(answer=>!answer.skipped).map(answer=>answer.answer),...Object.values(state.occurrences).filter(item=>item.date===state.date).map(item=>item.detail||'')].join(' ');
    questionList=[];
    if(/沮丧|失落|挫败|难过/.test(context)&&!/开心|振作|轻松|鼓励|支持|清醒/.test(context))questionList.push({kind:'balance',text:'除了写下的困难，今天有没有一个稍微轻松、得到支持或觉得有希望的瞬间？想不到也没关系，可以跳过。'});
    for(const [key,item] of Object.entries(state.care)){
      const mentioned={sleep:/睡|休息|作息/,meal:/饭|饮食|三餐/,move:/跑步|散步|拉伸|训练|运动/}[key].test(context);
      if(item.state==='missing'&&!mentioned)questionList.push({kind:key,text:{sleep:'今天的休息状态，有什么你想记一下？',meal:'今天吃饭的节奏怎么样，有没有想补充的？',move:'今天有没有活动身体，或者安排休息？'}[key]});
    }
    const answered=new Set(state.review.answers.map(answer=>answer.question));questionList=questionList.filter(q=>!answered.has(q.text));
    if(!questionList.length){aiActive=false;aiDone=true;render();toast('已有内容已经覆盖这组示例问题，不再重复追问。');return;}
    session={id:crypto.randomUUID(),state:'active',startedAt:new Date().toISOString(),model:'本机脚本示例',snapshot:{diary:state.review.note,saved:diaryIsSaved()},queue:questionList,index:0,turns:[],analysis:null};
    state.review.sessions.push(session);state.review.activeSessionId=session.id;
  }
  questionList=session.queue;questionIndex=session.index;saveAskedQuestion(session);persist();
  aiDraft='';aiActive=true;aiDone=false;render();if(innerWidth<=900)document.querySelector('.ai-area')?.scrollIntoView({block:'center'});
}
function finishReviewSession(session){
  session.state='finished';session.endedAt=new Date().toISOString();
  if(session.turns.some(turn=>turn.state==='answered'))session.analysis={createdAt:new Date().toISOString(),source:'demo',text:'分析示例：这次补充提供了日记之外的新角度，可以在之后回看时与原文一起参考。'};
}
function nextQuestion(skipped){
  const input=document.getElementById('ai-answer'),answer=input?.value.trim()||'';
  if(!skipped&&!answer){toast('写一点回答，或者点“跳过”。');input?.focus();return;}
  captureDraft();const session=activeReviewSession();if(!session||session.state!=='active')return;
  const turn=session.turns.find(turn=>turn.index===session.index);if(!turn||turn.state!=='asked')return;
  turn.answer=skipped?'':answer;turn.state=skipped?'skipped':'answered';turn.answeredAt=new Date().toISOString();
  state.review.answers.push({sessionId:session.id,questionId:turn.id,question:turn.question,answer:turn.answer,skipped});
  session.index++;questionIndex=session.index;aiDraft='';
  if(session.index>=session.queue.length){finishReviewSession(session);aiActive=false;aiDone=true;}else saveAskedQuestion(session);
  persist();render();
}
function finishAI(){captureDraft();const session=activeReviewSession();if(session?.state==='active')finishReviewSession(session);persist();aiActive=false;aiDone=true;render();}
