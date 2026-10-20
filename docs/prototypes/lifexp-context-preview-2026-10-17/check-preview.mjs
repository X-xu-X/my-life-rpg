import fs from 'node:fs'
import path from 'node:path'
import os from 'node:os'
import http from 'node:http'
import {spawn} from 'node:child_process'
import {fileURLToPath} from 'node:url'
const folder=path.dirname(fileURLToPath(import.meta.url))
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'lifexp-routine-demo-'))
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms))
const server=http.createServer((req,res)=>{
  if(req.url==='/favicon.ico'){res.writeHead(204);res.end();return}
  if(!['/','/index.html'].includes(req.url)){res.writeHead(404);res.end();return}
  res.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});res.end(fs.readFileSync(path.join(folder,'index.html')))
})
await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve)})
const url='http://127.0.0.1:'+server.address().port
const browser=spawn('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',[
  '--headless=new','--disable-gpu','--no-first-run','--no-proxy-server',
  '--remote-debugging-address=127.0.0.1','--remote-debugging-port=0',
  '--user-data-dir='+profile,'about:blank'
],{windowsHide:true,stdio:'ignore'})
let ws,send
const checks=[],errors=[]
try{
  const active=path.join(profile,'DevToolsActivePort')
  for(let i=0;i<100&&!fs.existsSync(active);i++)await pause(150)
  if(!fs.existsSync(active))throw Error('Isolated browser unavailable')
  const port=fs.readFileSync(active,'utf8').split(/\r?\n/)[0]
  const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json()
  ws=new WebSocket(pages.find(page=>page.type==='page').webSocketDebuggerUrl)
  await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true})})
  let sequence=0;const waiting=new Map()
  ws.addEventListener('message',event=>{const message=JSON.parse(event.data);if(message.id){const task=waiting.get(message.id);waiting.delete(message.id);message.error?task.reject(Error(message.error.message)):task.resolve(message.result)}if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails.text)})
  send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;waiting.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))})
  const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);return result.result.value}
  const click=selector=>evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`)
  const fill=(selector,value)=>evaluate(`document.querySelector(${JSON.stringify(selector)}).value=${JSON.stringify(value)}`)
  const change=(selector,value)=>evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('change',{bubbles:true}))})()`)
  const writeDiary=async text=>{await click('[data-nav=review]');await fill('#review-note',text);await click('#save-review');await click('[data-nav=today]')}
  const check=async(name,expression)=>{const pass=await evaluate(expression);checks.push({name,pass:!!pass});if(!pass)throw Error(name)}
  const screenshot=async name=>{for(let i=0;i<24&&!await evaluate('document.querySelector("#toast").hidden');i++)await pause(150);const result=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.join(folder,name+'.png'),Buffer.from(result.data,'base64'))}
  const shots=[];
  const shot=async name=>{await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');await pause(120);await screenshot(name);shots.push(name+'.png')};
  const navigate=async page=>{await evaluate(`go(${JSON.stringify(page)})`)};
  const type=async(selector,value)=>{await fill(selector,value);await evaluate(`document.querySelector(${JSON.stringify(selector)}).dispatchEvent(new Event('input',{bubbles:true}))`)};
  const reload=async()=>{await send('Page.reload');for(let i=0;i<60;i++){if(await evaluate('!!document.querySelector("#app h1")'))break;await pause(100)}};
  const chooseScenario=async value=>{await change('#scenario',value);await click('#dialog-confirm')};
  const newEvent=async text=>{await navigate('today');await type('#event-text',text);await click('[data-action=save-event]')};
  await send('Page.enable');await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1080,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url});
  for(let i=0;i<60;i++){if(await evaluate('!!document.querySelector("#event-text")'))break;await pause(100)}
  // User-reported regression: two separate paid vouchers, early stop, then use the new one.
  await navigate('rewards');await click('[data-action=purchase][data-id=game]');await click('#dialog-confirm');await click('#dialog-confirm');
  const couponA=await evaluate('state.timer.voucherId');
  await click('[data-action=exception]');await type('#exception-note','第一次玩了五分钟，提前结束。');await fill('#actual-minutes','5');await click('#dialog-confirm');
  await click('[data-action=finish-timer]');await click('#dialog-confirm');
  await check('first paid voucher retains exactly 25 minutes after a five-minute session',`!state.timer&&state.vouchers[0].remaining===1500&&state.vouchers[0].originalSeconds===1800`);
  await click('[data-action=purchase][data-id=game]');await click('#dialog-confirm');
  const couponB=await evaluate('state.vouchers[1].id');
  await check('new purchase start confirmation explicitly identifies the second full voucher',`document.querySelector('#dialog').innerText.includes('第 2 张券')&&document.querySelector('#dialog').innerText.includes('30 分钟')`);
  await click('#dialog-confirm');await click('[data-action=toggle-timer]');
  await check('second voucher starts from 30 minutes with new elapsed time and does not reuse first remainder',`state.timer.voucherId===${JSON.stringify(couponB)}&&state.timer.voucherId!==${JSON.stringify(couponA)}&&state.timer.planned===1800&&elapsed()<2&&state.vouchers[0].remaining===1500`);
  await shot('desktop-second-voucher');await navigate('rewards');await click(`[data-action=use-voucher][data-id="${couponA}"]`);
  await check('choosing another voucher while a session exists asks to finish instead of silently opening old timer',`document.querySelector('#dialog').open&&document.querySelector('#dialog').innerText.includes('上一段尚未确认结束')&&state.timer.voucherId===${JSON.stringify(couponB)}`);await click('#dialog-confirm');await reload();
  await check('second voucher identity and full starting allowance survive reload',`state.timer.voucherId===${JSON.stringify(couponB)}&&state.timer.planned===1800&&state.vouchers[0].remaining===1500`);
  await click('[data-action=exception]');await type('#exception-note','第二张券这次用了两分钟。');await fill('#actual-minutes','2');await click('#dialog-confirm');await click('[data-action=finish-timer]');await click('#dialog-confirm');
  await check('settling the second voucher changes only its own remaining balance',`state.vouchers[0].remaining===1500&&state.vouchers[1].remaining===1680`);
  await click(`[data-action=use-voucher][data-id="${couponA}"]`);await click('#dialog-confirm');
  await check('explicitly selecting old voucher resumes its 25 minutes with elapsed reset',`state.timer.voucherId===${JSON.stringify(couponA)}&&state.timer.planned===1500&&elapsed()<2`);
  await evaluate("state=initial();save();go('plans')");
  await click('[data-action=new-goal]');await fill('#goal-title','英语考试');await fill('#goal-note','阅读和词汇，年底通过考试');await click('#goal-main');await click('#dialog-confirm');
  const goalId=await evaluate('state.goals.at(-1).id');
  await check('users create their own mainline instead of switching between fixed presets',`state.goals.filter(g=>g.main).length===1&&state.goals.find(g=>g.main).title==='英语考试'&&!document.querySelector('[data-action=switch-main]')`);
  await click('[data-action=new-plan]');await fill('#new-plan-name','英语阅读');await change('#new-plan-when','weekly');await click('[name=plan-weekday][value="1"]');await click('[name=plan-weekday][value="3"]');await change('#new-plan-goal',goalId);await shot('desktop-custom-schedule');await click('#dialog-confirm');
  await check('custom plan stores user goal and multiple chosen weekdays',`state.plans.at(-1).goalId===${JSON.stringify(goalId)}&&state.plans.at(-1).weekdays.join(',')==='1,3'`);
  await navigate('today');await change('#preview-day','2026-10-19');await check('chosen Monday includes custom plan',`plansToday().some(p=>p.title==='英语阅读')`);await change('#preview-day','2026-10-20');await check('Tuesday excludes custom Monday Wednesday plan',`!plansToday().some(p=>p.title==='英语阅读')`);
  await navigate('plans');await click('[data-action=new-plan]');await fill('#new-plan-name','每三天整理');await change('#new-plan-when','interval');await fill('#new-plan-interval','3');await fill('#new-plan-anchor','2026-10-22');await click('#dialog-confirm');
  await check('future interval plan does not appear before anchor and goal is optional',`!plansToday().some(p=>p.title==='每三天整理')&&!state.plans.at(-1).goalId`);
  await navigate('today');await change('#preview-day','2026-10-25');await check('interval is counted from user selected anchor',`plansToday().some(p=>p.title==='每三天整理')`);
  await navigate('plans');await click('[data-action=new-plan]');await fill('#new-plan-name','一次面试');await change('#new-plan-when','once');await fill('#new-plan-anchor','2026-10-26');await click('#dialog-confirm');await navigate('today');await change('#preview-day','2026-10-26');await check('one-off plan appears on its own date',`plansToday().some(p=>p.title==='一次面试')`);await change('#preview-day','2026-10-27');await check('one-off plan stays in all plans but does not carry over',`!plansToday().some(p=>p.title==='一次面试')&&state.plans.some(p=>p.title==='一次面试')`);
  await newEvent('认真学习英语阅读，完成两篇练习并整理了错题。');await evaluate('openRecord(state.activeRecord)');await check('event flow has no effort tier or relevance input',`!document.querySelector('#grade')&&!document.querySelector('#main-related')`);await click('[data-action=analyze-record]');
  await check('analysis proposes relationship with the user-created mainline',`state.records[0].suggestion.goalId===${JSON.stringify(goalId)}&&calculation(state.records[0]).total===25`);
  await click('[data-action=correct-record]');await fill('#analysis-detail','只是兴趣阅读，和这次考试无关。');await change('#analysis-goal','');await click('#dialog-confirm');
  await check('correcting mistaken relevance removes mainline bonus without losing original',`!state.records[0].suggestion.main&&calculation(state.records[0]).total===15&&state.records[0].text.includes('完成两篇')&&state.records[0].supplement.includes('考试无关')`);
  await newEvent('交换机');await evaluate('openRecord(state.activeRecord)');await click('[data-action=analyze-record]');
  await check('insufficient event details request relevant clarification instead of inventing rewards',`!state.records[0].suggestion&&!!state.records[0].clarify&&!document.querySelector('[data-action=confirm-reward]')`);await shot('desktop-event-clarification');
  await navigate('profile');await check('buying power preference is no longer an everyday settings input',`!document.querySelector('#buying-power')&&!!document.querySelector('[data-action=reward-preferences]')`);await click('[data-action=reward-preferences]');await type('#question-answer','认真一天，想换一份甜点和半小时游戏。');await navigate('profile');await check('questionnaire reward preference is retained and shown in settings summary',`document.querySelector('#app').innerText.includes('一份甜点和半小时游戏')`);
  await navigate('rewards');const initialProducts=await evaluate('state.products.length');await click('[data-action=add-product]');
  await check('new reward asks for the desired reward and does not ask the user to set coin price',`!document.querySelector('#product-price')&&document.querySelector('#dialog-confirm').innerText.includes('建议价格')`);await click('#dialog-confirm');
  await check('empty reward cannot request pricing or add a product',`document.querySelector('#dialog-error').innerText.includes('先写下')&&state.products.length===${initialProducts}`);
  await type('#product-name','我的掌机时间');await change('#product-type','time');await type('#product-minutes','45');await type('#product-note','想在认真学习后玩一会儿。');await shot('desktop-custom-reward');await click('#dialog-confirm');
  await check('AI price proposal has a reason and does not add a product before confirmation',`state.products.length===${initialProducts}&&document.querySelector('#dialog').innerText.includes('30 币')&&document.querySelector('#dialog').innerText.includes('试用参考')&&!document.querySelector('#product-price')`);await shot('desktop-reward-price-proposal');
  await click('[data-action=edit-product-draft]');await check('returning from a proposal retains user input',`document.querySelector('#product-name').value==='我的掌机时间'&&document.querySelector('#product-minutes').value==='45'&&document.querySelector('#product-note').value.includes('认真学习')`);await type('#product-minutes','60');await click('#dialog-confirm');
  await check('changing reward duration generates a new price proposal',`document.querySelector('#dialog').innerText.includes('40 币')&&state.products.length===${initialProducts}`);await click('[data-action=close]');await reload();await click('[data-action=add-product]');
  await check('cancelled proposal does not add reward and draft survives reload',`state.products.length===${initialProducts}&&document.querySelector('#product-minutes').value==='60'`);await type('#product-minutes','45');await click('#dialog-confirm');await click('#dialog-confirm');const productId=await evaluate('state.products.at(-1).id');await reload();
  await check('accepted AI price and its source survive reload with reward duration',`state.products.at(-1).name==='我的掌机时间'&&state.products.at(-1).minutes===45&&state.products.at(-1).price===30&&state.products.at(-1).pricing.source==='script-preview'&&!!state.products.at(-1).pricing.reason&&!state.rewardDraft`);
  await click(`[data-action=purchase][data-id="${productId}"]`);await click('#dialog-confirm');await click('#dialog-confirm');await check('AI-priced timed reward purchases and starts its own 45-minute entitlement',`state.timer.planned===2700&&state.vouchers.at(-1).paid===30&&state.vouchers.at(-1).originalSeconds===2700`);
  await evaluate("state=initial();save();go('rewards')");await click('[data-action=add-product]');await type('#product-name','我喜欢的甜点');await type('#product-real','15');await click('#dialog-confirm');
  await check('item reward gets suggested coin price from optional real price without charging or saving',`document.querySelector('#dialog').innerText.includes('30 币')&&document.querySelector('#dialog').innerText.includes('15 元')&&state.coins===80&&state.products.length===3`);await click('[data-action=close]');await evaluate("state.phase='exam';save()");await click('[data-action=add-product]');await click('#dialog-confirm');
  await click('#dialog details summary');await check('pricing preview explains stage adjustment and includes questionnaire and recent income context',`document.querySelector('#dialog').innerText.includes('36 币')&&document.querySelector('#dialog').innerText.includes('上调 20%')&&document.querySelector('#dialog').innerText.includes('问卷里的长期奖励偏好')&&state.products.length===3`);await click('[data-action=close]');
  await evaluate("state=initial();save();go('plans')");await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await click('[data-action=new-plan]');await change('#new-plan-when','weekly');await check('mobile custom schedule dialog fits viewport',`document.querySelector('#dialog').scrollWidth<=document.querySelector('#dialog').clientWidth`);await shot('mobile-custom-schedule');await click('[data-action=close]');await navigate('rewards');await click('[data-action=add-product]');await change('#product-type','time');await check('mobile desired reward form fits viewport',`document.querySelector('#dialog').scrollWidth<=document.querySelector('#dialog').clientWidth`);await shot('mobile-custom-reward');await type('#product-name','半小时游戏');await click('#dialog-confirm');await check('mobile AI pricing proposal and confirmation fit viewport',`document.querySelector('#dialog').scrollWidth<=document.querySelector('#dialog').clientWidth&&document.querySelector('#dialog-confirm').innerText.includes('接受价格')`);await shot('mobile-reward-price-proposal');await click('[data-action=close]');
  await evaluate("state=initial();save();go('today')");await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1080,deviceScaleFactor:1,mobile:false});

  await check('initial standalone preview has five user navigation entries and locked free allowance',`document.querySelectorAll('#desktop-nav a').length===5&&state.coins===80&&!eligible()&&document.querySelector('[data-action=start-free]').disabled`);
  await shot('desktop-today');
  await click('[data-action=sample-record]');await click('[data-action=save-event]');
  const firstId=await evaluate('state.activeRecord');
  await check('first original saves without a model or coin settlement and unlocks 30 free minutes',`eligible()&&state.coins===80&&remaining()===1800&&state.records[0].savedDay==='2026-10-17'`);
  await click('[data-action=claim-first]');await evaluate('document.querySelector("[data-action=claim-first]").click()');
  await check('first-record sign-in can be claimed once',`state.coins===83&&state.ledger.filter(l=>l.key==='first@2026-10-17').length===1`);
  await evaluate(`openRecord(${JSON.stringify(firstId)})`);await click('[data-action=analyze-record]');
  await check('middle mainline proposal decomposes 15 plus 10 and does not settle yet',`calculation(state.records.find(r=>r.id===state.activeRecord)).total===25&&state.coins===83`);
  await shot('desktop-reward-preview');await click('[data-action=confirm-reward]');
  await check('confirm replaces legacy flat award and records one fact award',`state.coins===108&&state.ledger.filter(l=>l.key==='fact:'+state.activeRecord).length===1`);
  await navigate('today');await click('[data-action=start-free]');await pause(1200);await click('#dialog-confirm');
  await check('free entertainment starts without purchasing a voucher or deducting coins',`state.timer.source==='free'&&state.coins===108&&state.vouchers.length===0`);
  await check('time spent reading the start confirmation is not counted as entertainment',`elapsed()<1`);
  await click('[data-action=near-end]');await click('[data-action=toggle-timer]');await shot('desktop-timer');await reload();
  await check('paused timer restores across reload',`state.timer.status==='paused'&&elapsed()>=1740&&elapsed()<1743`);
  await click('[data-action=exception]');await type('#exception-note','中间接了电话，实际娱乐只用了 12 分钟。');await fill('#actual-minutes','12');await click('[data-action=analyze-exception]');
  await check('exception analysis shows advice without modifying time or balance',`document.querySelector('#exception-advice').innerText.includes('模拟')&&elapsed()>=1740&&state.coins===108`);
  await shot('desktop-exception');await click('#dialog-confirm');
  await check('explicit correction retains explanation and audit but does not settle',`state.timer.seconds===720&&state.timer.note.includes('接了电话')&&state.audit.length===1&&state.coins===108`);
  await click('[data-action=finish-timer]');await click('#dialog-confirm');
  await check('end consumes actual free time and grants a small punctuality award once',`!state.timer&&state.timers.length===1&&remaining()===1080&&state.coins===109&&state.ledger.filter(x=>x.source==='守时').length===1`);
  await navigate('today');await click('[data-action=start-plan][data-id=math]');await click('#dialog-confirm');await click('[data-action=advance]');await click('[data-action=finish-timer]');await click('#dialog-confirm');
  await check('plan timer ending asks for actual completion instead of automatically awarding',`document.querySelector('#plan-detail')&&state.coins===109&&!state.outcomes['math@2026-10-17']`);
  await fill('#plan-detail','就是刚才记录的那次高数练习。');await change('#reuse-record',firstId);await click('#dialog-confirm');
  await check('linking a completed timer to an existing settled event does not reward twice',`state.outcomes['math@2026-10-17'].record===${JSON.stringify(firstId)}&&state.coins===109`);
  await navigate('today');await click('[data-action=plan-missed][data-id=exercise]');
  await check('missed confirmation stays in its card with no modal',`!document.querySelector('#dialog').open&&!!document.querySelector('[data-action=confirm-missed]')`);
  await click('[data-action=confirm-missed]');
  await check('confirmed missed outcome is locked and does not create an event or reward',`state.outcomes['exercise@2026-10-17'].status==='missed'&&!document.querySelector('[data-action=plan-outcome][data-id=exercise]')&&state.coins===109`);
  await change('#preview-day','2026-10-19');await check('Monday has scheduled run',`!!document.querySelector('[data-action=start-plan][data-id=run]')`);await type('#event-text','只属于周一的草稿');
  await change('#preview-day','2026-10-20');await check('Tuesday does not carry overdue Monday run',`!document.querySelector('[data-action=start-plan][data-id=run]')&&state.plans.length===3`);
  await check('new day has its own event draft',`document.querySelector('#event-text').value===''`);await change('#preview-day','2026-10-19');await check('returning to Monday restores its draft',`document.querySelector('#event-text').value==='只属于周一的草稿'`);
  await change('#preview-day','2026-10-17');await type('#event-text','这是补记前天的一段散步。');await change('#content-day','2026-10-15');await click('[data-action=save-event]');
  await check('backdated content preserves actual saved day and does not add a new saved day',`state.records[0].contentDay==='2026-10-15'&&state.records[0].savedDay==='2026-10-17'&&daysMetric('event').total===3&&daysMetric('event').current===3`);
  await navigate('diary');await type('#diary-text','今天有些沮丧，几次练习都卡住了。希望明天换一种方法。');await click('[data-action=save-diary]');const original=await evaluate('diaryRecord().text');await click('[data-action=start-review]');await type('#review-answer','朋友愿意听我讲不顺利的地方，让我觉得有人陪着。');await click('[data-action=save-review-answer]');await reload();
  await check('diary preserves original, exact AI question and corresponding answer separately',`diaryRecord().text===${JSON.stringify(original)}&&diaryRecord().reviews[0].question.includes('片段')&&diaryRecord().reviews[0].answer.includes('朋友')&&daysMetric('diary').total===3`);
  await type('#diary-text','今天日记的未保存草稿');await evaluate('openRecord("seed-d1")');await check('opening an older diary does not apply today\'s unsaved draft',`document.querySelector('#diary-text').value.includes('散步时间')`);await evaluate('openRecord(diaryRecord().id)');await check('returning to today restores that diary\'s own draft',`document.querySelector('#diary-text').value==='今天日记的未保存草稿'`);await type('#diary-text',original);await click('[data-action=save-diary]');
  await shot('desktop-diary');await navigate('growth');await click('[data-action=claim-achievement][data-kind=diary]');await click('#dialog-confirm');const milestoneBalance=await evaluate('state.coins');
  await evaluate(`document.querySelector('[data-action=claim-achievement][data-kind=diary]').click()`);
  await check('verified milestone shares one claim identity',`state.coins===${milestoneBalance}&&state.claims.filter(k=>k==='streak:diary:3').length===1`);
  await click('[data-action=seed-streak]');await check('30-day diary candidate is discovered from actual saved-day sample evidence',`daysMetric('diary').longest===30&&!!document.querySelector('[data-kind=diary][data-target="30"]')`);await shot('desktop-growth');
  await navigate('rewards');await click('[data-action=purchase][data-id=game]');await click('#dialog-confirm');
  await check('paid entertainment purchase deducts once and retains separate usage entitlement',`state.vouchers.length===1&&state.vouchers[0].paid===20&&state.coins===${milestoneBalance-20}&&document.querySelector('#dialog').open`);
  await click('[data-action=close]');await reload();await navigate('rewards');
  await check('unused paid voucher survives refresh at its original price',`state.vouchers[0].remaining===1800&&!state.vouchers[0].used`);await shot('desktop-rewards');
  await navigate('questionnaire');await type('#question-answer','最近在复习考研，每天下午有一段完整的时间。');await click('[data-action=question-next]');await click('[data-action=question-skip]');await reload();
  await check('detailed questionnaire stores answered and skipped as different states and restores progress',`groups.reduce((n,g)=>n+g[2].length,0)===36&&state.question.index===2&&state.question.answers[0].status==='answered'&&state.question.answers[1].status==='skipped'`);await shot('desktop-questionnaire');
  const builtBalance=await evaluate('state.coins');await click('[data-action=question-preview]');await click('#dialog-confirm');await check('existing baseline questionnaire does not re-award startup funds',`state.coins===${builtBalance}&&state.ledger.filter(x=>x.key==='startup').length===1`);
  await navigate('profile');await change('#phase','exam');await click('[data-action=phase-advice]');await shot('desktop-phase-advice');await click('#dialog-confirm');
  await check('stricter exam policy requires explicit confirmation',`state.profile.strict==='exam'&&state.phase==='exam'`);
  await navigate('today');await click('[data-action=start-free]');await click('#dialog-confirm');await navigate('profile');await change('#strict','gentle');await click('[data-action=save-profile]');await navigate('timer');
  await check('an already started session retains its agreed policy',`state.profile.strict==='gentle'&&state.timer.policy==='exam'`);await click('[data-action=overrun]');await click('[data-action=finish-timer]');const beforePenalty=await evaluate('state.coins');
  await check('8-minute overtime applies grace then one full 5-minute block',`timerResult().penalty===4&&state.coins===${beforePenalty}`);await shot('desktop-overtime-confirm');await click('#dialog-confirm');await check('penalty settles only on confirmation and respects no-overdraft',`state.coins===${beforePenalty-4}&&state.coins>=0`);
  await navigate('rewards');await click('[data-action=price][data-id=tea]');await check('exam price suggestion uses bounded 20-percent change',`Number(document.querySelector('#new-price').value)===36`);await click('#dialog-confirm');
  await navigate('today');await change('#preview-day','2026-10-18');await navigate('profile');await change('#phase','relax');await click('[data-action=save-profile]');await navigate('rewards');await click('[data-action=price][data-id=tea]');await check('relaxed phase can lower a raised price toward base price',`Number(document.querySelector('#new-price').value)===30`);await click('#dialog-confirm');
  await chooseScenario('new');await check('new user can enter full questionnaire without a hidden baseline',`!state.profile.built&&state.coins===0&&state.route==='questionnaire'`);
  for(let i=0;i<6;i++)await click('[data-action=question-skip-group]');await click('[data-action=question-preview]');await check('all-skipped questionnaire produces neutral preview',`Object.values(state.question.answers).every(x=>x.status==='skipped')&&document.querySelector('#dialog').innerText.includes('80 币')`);await click('#dialog-confirm');await check('all-skipped neutral start grants 80 once',`state.profile.built&&state.coins===80&&state.ledger.length===1`);
  await chooseScenario('holiday');await click('[data-action=holiday]');await click('[data-action=holiday]');await check('holiday gift claims once',`state.coins===90&&state.ledger.filter(x=>x.source==='节日').length===1`);await newEvent('节日抽出时间完成了一组练习和错题整理。');await evaluate('openRecord(state.activeRecord)');await click('[data-action=analyze-record]');await check('holiday effort bonus is independent from gift and respects amount split',`calculation(state.records[0]).holiday===5&&calculation(state.records[0]).total===30`);await shot('desktop-holiday-award');
  await chooseScenario('return');await navigate('comeback');await type('[data-return=changes]','最近工作安排变了，想先恢复规律作息。');await click('[data-action=return-save]');await click('#dialog-confirm');await check('return questionnaire updates context without filling history or changing baseline funds',`state.returnStatus==='saved'&&state.coins===80&&state.profile.initial===80&&state.records.length===4`);
  await navigate('feedback');await type('#feedback-title','希望手机计时的结束按钮更清楚');await type('#feedback-text','页面挺舒服。<img src=x onerror=alert(1)> 这段应该显示为文字。');await click('[data-action=submit-feedback]');await check('feedback content is escaped and explicitly private',`!document.querySelector('#app img')&&document.querySelector('#app').innerText.includes('仅你与授权管理员可见')`);await navigate('guide');await click('[data-action=enter-admin]');await type('[id^=reply-]','收到，我们会优先调整结束按钮与结果确认的层级。');await click('[data-action=reply-feedback]');await shot('desktop-admin-feedback');await click('[data-action=leave-admin]');await check('submitter can read admin reply and ordinary navigation is restored',`state.role==='user'&&document.querySelectorAll('#desktop-nav a').length===5&&document.querySelector('#app').innerText.includes('收到')`);
  await navigate('guide');await click('[data-action=review-choice][data-id=entertainment][data-value="认可这版"]');await type('#review-note','基础时长直观，想再看一下手机效果。');await click('[data-action=save-opinion]');await reload();await check('review feedback persists locally without dispatching anything',`state.review.entertainment==='认可这版'&&state.review.note.includes('手机效果')`);await shot('desktop-guide');
  const downloadPath=path.join(profile,'downloads');fs.mkdirSync(downloadPath);await send('Browser.setDownloadBehavior',{behavior:'allow',downloadPath});await click('[data-action=download-opinion]');for(let i=0;i<30&&!fs.existsSync(path.join(downloadPath,'LifeXP-demo-review.txt'));i++)await pause(100);if(!fs.existsSync(path.join(downloadPath,'LifeXP-demo-review.txt')))throw Error('Review download missing');checks.push({name:'review notes download as a real local text file',pass:fs.readFileSync(path.join(downloadPath,'LifeXP-demo-review.txt'),'utf8').includes('手机效果')});
  await evaluate("state.notice='';state.scenario='normal';save()");
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  for(const page of ['today','questionnaire','plans','rewards','growth','diary','profile','comeback','feedback','guide']){await navigate(page);await check('390px layout fits: '+page,'document.documentElement.scrollWidth<=innerWidth');await shot('mobile-'+page)}
  await navigate('questionnaire');await change('#question-group-select','4');await check('mobile compact group selector opens the corresponding reward questions',`state.question.index===24&&document.querySelector('.question-copy').innerText.includes('奖励自己')`);
  await navigate('today');await check('mobile free allowance appears directly after composer and before plans',`document.querySelector('.rest-card').getBoundingClientRect().top<document.querySelector('.today-plans').getBoundingClientRect().top`);
  await navigate('today');await newEvent('完成一小步，给自己留下记录。');await click('[data-action=start-free]');await click('#dialog-confirm');await check('mobile timer fits and actions remain available','document.documentElement.scrollWidth<=innerWidth&&!!document.querySelector("[data-action=finish-timer]")');await shot('mobile-timer');
  await send('Emulation.setDeviceMetricsOverride',{width:360,height:800,deviceScaleFactor:1,mobile:true});for(const page of ['today','questionnaire','rewards','profile','guide']){await navigate(page);await check('360px layout fits: '+page,'document.documentElement.scrollWidth<=innerWidth')}
  await send('Emulation.setDeviceMetricsOverride',{width:768,height:1024,deviceScaleFactor:1,mobile:true});await navigate('questionnaire');await check('tablet questionnaire fits','document.documentElement.scrollWidth<=innerWidth');await shot('tablet-questionnaire');
  await check('CSP prohibits API traffic and preview collects no passwords or keys',`document.querySelector('meta[http-equiv="Content-Security-Policy"]').content.includes("connect-src 'none'")&&!document.querySelector('input[type=password]')`);
  const direct='file:///'+path.join(folder,'index.html').replaceAll('\\','/');await send('Page.navigate',{url:direct});for(let i=0;i<50;i++){if(await evaluate('location.protocol==="file:"&&!!document.querySelector("#event-text")'))break;await pause(100)}await check('standalone HTML opens directly from disk without a server',`location.protocol==='file:'&&!!document.querySelector('#event-text')`);
  if(errors.length)throw Error('Runtime exceptions: '+errors.join(';'));
  const result={status:'PASS',validatedAt:new Date().toISOString(),scope:'Fictional standalone local preview; no real models, accounts, databases, production, or Writer dispatch. Not a backend/concurrency/real-phone acceptance test.',checks,runtimeErrors:errors,screenshots:shots};
  fs.writeFileSync(path.join(folder,'qa-summary.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({status:result.status,checks:checks.length,screenshots:shots.length,runtimeErrors:errors}));
}catch(error){fs.writeFileSync(path.join(folder,'qa-summary.json'),JSON.stringify({status:'FAIL',error:String(error.stack||error),checks,runtimeErrors:errors},null,2));throw error}
finally{if(ws)ws.close();browser.kill();await new Promise(resolve=>server.close(resolve));}
