// Compiled Vue + actual FastAPI routes/services; only DB, supplier and clock synthetic.
import fs from 'node:fs'
import path from 'node:path'
import {spawn} from 'node:child_process'
import crypto from 'node:crypto'
const root='docs/review/daily_use_fixes_2026-10-21/review-browser'
process.env.DAILY_USE_EVIDENCE_DIR=root
process.env.DAILY_USE_REVIEW_CASES='1'
fs.mkdirSync(root,{recursive:true})
const pause=ms=>new Promise(r=>setTimeout(r,ms))
const runtimePath=root+'/runtime.json'
if(fs.existsSync(runtimePath))fs.unlinkSync(runtimePath)
const fixture=spawn('.venv/Scripts/python.exe',['tests/daily_use_runtime.py'],{windowsHide:true,stdio:['ignore','pipe','pipe']})
let fixtureLog='';fixture.stdout.on('data',b=>fixtureLog+=b);fixture.stderr.on('data',b=>fixtureLog+=b)
const profile=fs.mkdtempSync(path.resolve('_tmp_daily_edge_'))
let edge,ws,seq=0,runtime
const pending=new Map(),checks=[],errors=[],exceptions=[],consoleMessages=[],networkFailures=[]
function check(name,ok,detail){checks.push({name,status:ok?'PASS':'FAIL',...(detail?{detail}: {})});if(!ok)throw Error(name+(detail?' '+JSON.stringify(detail):''))}
function send(method,params={}){return new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))})}
async function ev(expression){const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value}
async function wait(expression){for(let i=0;i<150;i++){if(await ev(expression))return;await pause(100)}throw Error('wait '+expression)}
async function go(route){await ev(`location.hash=${JSON.stringify(route)}`);await pause(650);const selector={'/':'#new-record','/plans':'.project-manager','/rewards':'form input[maxlength=\"120\"]'}[route];if(selector)await wait(`!!document.querySelector(${JSON.stringify(selector)})`)}
async function click(text,selector='button'){const query=`[...document.querySelectorAll(${JSON.stringify(selector)})].find(e=>e.textContent.trim()===${JSON.stringify(text)}&&!e.disabled&&e.getClientRects().length)`;await wait(`!!(${query})`);await ev(`(${query}).scrollIntoView({block:'center'})`);await pause(40);const point=await ev(`(()=>{const e=(${query}),r=e.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2;return {x,y,reachable:e.contains(document.elementFromPoint(x,y))}})()`);if(!point.reachable)throw Error('button obstructed '+text);await send('Input.dispatchMouseEvent',{type:'mousePressed',x:point.x,y:point.y,button:'left',clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:point.x,y:point.y,button:'left',clickCount:1});await pause(200)}
async function fill(selector,value){await ev(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!e)throw Error('input missing: '+${JSON.stringify(selector)});e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}))})()`)}
async function shot(name,full=false){let clip;if(full){const metrics=await send('Page.getLayoutMetrics');clip={x:0,y:0,width:metrics.cssContentSize.width,height:metrics.cssContentSize.height,scale:1}}const r=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:full,...(clip?{clip}: {})});fs.writeFileSync(root+'/'+name+'.png',Buffer.from(r.data,'base64'))}
async function api(route,body,method='POST'){return ev(`(async()=>{const me=await fetch('/api/auth/me').then(r=>r.json());const r=await fetch('/api'+${JSON.stringify(route)},{method:${JSON.stringify(body===undefined?'GET':method)},headers:{'Content-Type':'application/json','X-CSRF-Token':me.csrf_token||''},${body===undefined?'':'body:JSON.stringify('+JSON.stringify(body)+'),'}});return {status:r.status,data:await r.json()}})()`)}
async function login(user,password){await wait(`!!document.querySelector('input[autocomplete=username]')`);await fill('input[autocomplete=username]',user);await fill('input[type=password]',password);await click('登录');await wait(`!document.querySelector('.auth-paper')`);await pause(500)}
async function logout(){await api('/auth/logout',{});await send('Page.reload');await wait(`!!document.querySelector('.auth-paper')`)}
async function layout(route,width){await send('Emulation.setDeviceMetricsOverride',{width,height:width<500?844:1000,deviceScaleFactor:1,mobile:false});await go(route);check('layout '+route+' '+width,await ev(`document.documentElement.scrollWidth<=innerWidth+1`));await shot(route.replaceAll('/','_')+'-'+width)}
try{
 for(let i=0;i<150&&!fs.existsSync(runtimePath);i++){if(fixture.exitCode!==null)throw Error(fixtureLog);await pause(100)}
 runtime=JSON.parse(fs.readFileSync(runtimePath,'utf8'))
 const binary=['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','C:/Program Files/Microsoft/Edge/Application/msedge.exe'].find(fs.existsSync)
 edge=spawn(binary,['--headless=new','--disable-gpu','--no-first-run','--disable-background-networking','--disable-sync','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:'ignore'})
 let port
 for(let i=0;i<150;i++){try{port=fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];break}catch{}await pause(100)}
 const targets=await fetch('http://127.0.0.1:'+port+'/json').then(r=>r.json());ws=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl)
 await new Promise(r=>ws.addEventListener('open',r,{once:true}))
 ws.addEventListener('message',e=>{const r=JSON.parse(e.data);if(r.id){const p=pending.get(r.id);pending.delete(r.id);r.error?p.reject(Error(JSON.stringify(r.error))):p.resolve(r.result)}else if(r.method==='Runtime.exceptionThrown')exceptions.push(r.params.exceptionDetails);else if(r.method==='Runtime.consoleAPICalled')consoleMessages.push(r.params.args.map(a=>a.value||a.description||'').join(' '));else if(r.method==='Network.loadingFailed')networkFailures.push(r.params)})
 await send('Runtime.enable');await send('Page.enable');await send('Network.enable');await send('Page.navigate',{url:runtime.origin});await wait(`!!document.querySelector('.auth-paper')`)
 check('public title and ICP',await ev(`document.title.includes('人生手账')&&document.querySelectorAll('.site-footer').length===1`))
 await login('日常测试','daily-test-password');await wait(`!!document.querySelector('#new-record')`);check('existing evaluated user no onboarding',await ev(`location.hash!=='#/onboarding'`))
 const today=(await api('/trial')).data.today
 const shift=n=>{const d=new Date(today+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10)}
 async function project(name){const r=await api('/projects?include_removed=true');return r.data.items.find(p=>p.name===name)}
 const row=p=>`[data-project-key="${p.key}"]`
 async function toggle(text,value){await ev(`(()=>{const label=[...document.querySelectorAll('label')].find(e=>e.textContent.trim()===${JSON.stringify(text)});const e=label.querySelector('input[type=checkbox]');e.checked=${value};e.dispatchEvent(new Event('change',{bubbles:true}))})()`)}
 async function create(name,category,frequency,start,position=0){
  await go('/plans');await click('添加项目');await fill('dialog[open] input[maxlength="80"]',name);await fill('dialog[open] select[aria-label="项目类型"]',category);await fill('dialog[open] select:not([aria-label])',frequency);await fill('dialog[open] input[aria-label="排期起算日"]',start);await fill('dialog[open] input[aria-label="显示排序"]',position)
  if(frequency==='interval')await fill('dialog[open] input[max="366"]',3)
  await click('保存项目');await wait(`!document.querySelector('dialog[open]')`);const p=await project(name);check('UI create '+category+' '+frequency,!!p);return p
 }
 await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false})
 await go('/');check('R4 zero care hides entire home card',await ev(`!document.querySelector('[data-project-category=care]')`))
 for(const category of ['plan','care']){
  let p=await create('未来一次 '+category,category,'once',shift(7),17)
  if(category==='care')await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false})
  await click('编辑项目',row(p)+' button');check('R2 future once prefill '+category,await ev(`document.querySelector('dialog[open] input[aria-label="排期起算日"]').value===${JSON.stringify(shift(7))}`));check('R1 editor opens at name field '+category,await ev(`document.activeElement===document.querySelector('dialog[open] input[maxlength=\"80\"]')`));await shot('future-once-'+category+'-edit');if(category==='care')check('R1 R2 narrow editor dates fit',await ev(`document.documentElement.scrollWidth<=innerWidth+1&&document.querySelector('dialog[open]').scrollWidth<=document.querySelector('dialog[open]').clientWidth+1`))
  await fill('dialog[open] input[maxlength="80"]','未来改名 '+category);await fill('dialog[open] select[aria-label="项目类型"]',category==='plan'?'care':'plan');await toggle('启用项目',false);await click('保存项目');await wait(`!document.querySelector('dialog[open]')`);await send('Page.reload');await wait(`!!document.querySelector('.project-manager')`)
  p=await project('未来改名 '+category);check('R1 R2 UI renamed reclassified disabled persists '+category,p.category!==category&&!p.enabled&&p.rule.start===shift(7)&&p.position===17)
  await click('编辑项目',row(p)+' button');check('R4 editing retains sort '+category,await ev(`document.querySelector('dialog[open] input[aria-label="显示排序"]').value==='17'`));await click('取消');await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false})
 }
 let interval=await create('历史间隔','plan','interval',shift(-7),8)
 await fill('.project-manager input[type=date]',shift(-1));await pause(450);await fill(row(interval)+' select','partial');await fill(row(interval)+' textarea','实际阅读十分钟，保留原事实');await click('保存实际记录',row(interval)+' button');await pause(350)
 const oldInterval=(await api('/projects?day='+shift(-1))).data.items.find(p=>p.key===interval.key).entry;check('R2 historical interval result saved by UI',oldInterval?.outcome==='partial')
 await click('编辑项目',row(interval)+' button');check('R2 interval edit keeps original anchor',await ev(`document.querySelector('dialog[open] input[aria-label="排期起算日"]').value===${JSON.stringify(shift(-7))}&&document.querySelector('dialog[open] input[aria-label="修改生效日"]').value===${JSON.stringify(today)}`));await fill('dialog[open] input[maxlength="80"]','历史间隔改名');await click('保存项目');await wait(`!document.querySelector('dialog[open]')`)
 interval=await project('历史间隔改名');const intervalToday=(await api('/projects')).data.items.find(p=>p.key===interval.key);const intervalNext=(await api('/projects?day='+shift(2))).data.items.find(p=>p.key===interval.key)
 check('R2 interval schedule unchanged',interval.rule.start===shift(-7)&&!intervalToday.scheduled_due&&intervalNext.scheduled_due)
 check('R2 interval old result identity retained',JSON.stringify((await api('/projects?day='+shift(-1))).data.items.find(p=>p.key===interval.key).entry)===JSON.stringify(oldInterval))
 await click('明确更正这次结果',row(interval)+' button');check('R4 explicit correction starts from original partial result',await ev(`document.querySelector(${JSON.stringify(row(interval)+' select')}).value==='partial'`))
 let daily=await create('历史每日','plan','daily',shift(-10),5)
 await fill('.project-manager input[type=date]',today);await pause(400);await fill(row(daily)+' select','missed');await click('确认并保存结果',row(daily)+' button');await pause(350)
 const oldDaily=(await api('/projects')).data.items.find(p=>p.key===daily.key).entry
 await click('编辑项目',row(daily)+' button');await fill('dialog[open] input[maxlength="80"]','明天的新名称');await fill('dialog[open] input[aria-label="修改生效日"]',shift(1));await click('保存项目');await wait(`!document.querySelector('dialog[open]')`)
 daily=await project('明天的新名称');const todayDaily=(await api('/projects')).data.items.find(p=>p.key===daily.key)
 check('R2 daily edit keeps anchor and current result',daily.rule.start===shift(-10)&&todayDaily.effective.name==='历史每日'&&JSON.stringify(todayDaily.entry)===JSON.stringify(oldDaily))
 await shot('separate-start-and-effective',true)
 let later=await create('排序四十的照顾项目','care','daily',today,40),earlier=await create('排序二的照顾项目','care','daily',today,2)
 await click('编辑项目',row(later)+' button');await fill('dialog[open] input[maxlength="80"]','排序四十只改名');await click('保存项目');await wait(`!document.querySelector('dialog[open]')`);later=await project('排序四十只改名');check('R4 rename does not reset position',later.position===40)
 await toggle('在今天显示照顾清单',false);await click('保存清单显示');await go('/');check('R4 old disabled preference hides home card',await ev(`!document.querySelector('[data-project-category=care]')`));check('R4 disabled preference persists in backend',(await api('/projects')).data.care_config.enabled===false)
 await go('/plans');await toggle('在今天显示照顾清单',true);await click('保存清单显示');await go('/')
 check('R4 care sorted by custom position',await ev(`JSON.stringify([...document.querySelectorAll('[data-project-category=care] article h3')].map(e=>e.textContent))===${JSON.stringify(JSON.stringify([earlier.name,later.name]))}`));await shot('care-custom-order',true)
 await go('/plans');await fill(row(later)+' textarea','实际照顾植物，保留自己的原文');await click('保存实际记录',row(later)+' button');await pause(350);const savedCare=(await api('/projects')).data.items.find(p=>p.key===later.key).entry;check('R4 care actual record saved',!!savedCare?.event_id)
 const coins=(await api('/coins')).data.balance
 for(const p of [later,earlier]){await click('移除项目',row(p)+' button');await click('确认移除项目');await wait(`!document.querySelector('dialog[open]')`)}
 await go('/');check('R4 removed zero items hides home card',await ev(`!document.querySelector('[data-project-category=care]')`));await go('/plans');await toggle('查看已移除项目与历史',true)
 check('R4 removed record still visible from unified manager',await ev(`!!document.querySelector(${JSON.stringify(row(later)+' a[href="#/events/'+savedCare.event_id+'"]')})`))
 const archive=(await api('/projects?include_removed=true')).data.items.find(p=>p.key===later.key)
 check('R4 removal retains original event and result',archive.removed&&JSON.stringify(archive.entry)===JSON.stringify(savedCare)&&(await api('/coins')).data.balance===coins);await shot('removed-history-preserved',true)
 await go('/rewards');check('R3 empty first entry has no jobs',(await api('/pricing-checks')).data.items.length===0);await go('/plans')
 const qa=(name,body={})=>fetch(runtime.origin+'/__qa__/'+name,{method:'POST',headers:{'X-QA-Guard':runtime.guard},body:JSON.stringify(body)}).then(r=>r.json())
 await qa('seed-pricing',{count:6,fail_index:5});await go('/rewards')
 for(let i=0;i<120;i++){const c=(await api('/pricing-checks')).data.items;if(c.length===6&&c.every(r=>['completed','failed'].includes(r.state)))break;await pause(100)}
 let jobs=(await api('/pricing-checks')).data.items;check('R3 actual page queues all six in bounded batches',jobs.length===6&&jobs.every(r=>['completed','failed'].includes(r.state)))
 check('R3 failed item does not auto retry',jobs.filter(r=>r.state==='failed').length===1);const calls=(await qa('advance',{seconds:0})).model_calls
 await send('Page.reload');await wait(`!!document.querySelector('.reward-row')`);await pause(700);check('R3 refresh does not re-call failed or completed models',(await qa('advance',{seconds:0})).model_calls===calls)
 await shot('six-price-checks-with-one-failure',true);await go('/plans');await qa('seed-pricing',{count:7})
 const main=ws
 const secondTarget=await send('Target.createTarget',{url:'about:blank'})
 const secondInfo=(await fetch('http://127.0.0.1:'+port+'/json').then(r=>r.json())).find(t=>t.id===secondTarget.targetId)
 const second=new WebSocket(secondInfo.webSocketDebuggerUrl);await new Promise(r=>second.addEventListener('open',r,{once:true}))
 second.addEventListener('message',e=>{const r=JSON.parse(e.data);if(r.id){const p=pending.get(r.id);pending.delete(r.id);r.error?p.reject(Error(JSON.stringify(r.error))):p.resolve(r.result)}else if(r.method==='Runtime.exceptionThrown')exceptions.push(r.params.exceptionDetails);else if(r.method==='Runtime.consoleAPICalled')consoleMessages.push(r.params.args.map(a=>a.value||a.description||'').join(' '));else if(r.method==='Network.loadingFailed')networkFailures.push(r.params)})
 ws=second;await send('Runtime.enable');await send('Page.enable');await send('Page.navigate',{url:runtime.origin+'/#/rewards'});ws=main;await go('/rewards');await pause(1800)
 for(let i=0;i<100;i++){const c=(await api('/pricing-checks')).data.items;if(c.length===10&&c.every(r=>['completed','failed'].includes(r.state)))break;await pause(100)}
 jobs=(await api('/pricing-checks')).data.items;check('R3 two tabs stop at ten unique items',jobs.length===10&&new Set(jobs.map(r=>r.item_id)).size===10)
 const remaining=(await api('/shop/items')).data.items.filter(i=>!jobs.some(j=>j.item_id===i.id));check('R3 over-budget items retained for another day',remaining.length===3);check('R3 ten items cause at most ten supplier calls',(await qa('advance',{seconds:0})).model_calls===10)
 await send('Target.closeTarget',{targetId:secondTarget.targetId});second.close()
 check('R1 actual page requests never return timezone',JSON.parse(fs.readFileSync(root+'/api-requests.json','utf8')).filter(r=>r.body_fields).every(r=>r.status===200&&!r.body_fields.includes('timezone')))
 check('no Vue runtime exceptions',exceptions.length===0,exceptions)
 const state=await qa('advance',{seconds:0});check('no backend or worker exceptions',state.errors.length===0,state.errors)
 console.log(JSON.stringify({status:'PASS',checks:checks.length,source:'compiled Vue + real ASGI review regression, synthetic data/supplier'}))
}catch(e){errors.push(String(e));console.error(e);process.exitCode=1;try{await shot('failure');fs.writeFileSync(root+'/failure-dom.txt',await ev(`document.body.innerText`));fs.writeFileSync(root+'/overflow-debug.json',JSON.stringify(await ev(`([...document.querySelectorAll('body *')].map(e=>({tag:e.tagName,cls:e.className,text:e.innerText?.slice(0,60),right:e.getBoundingClientRect().right})).filter(e=>e.right>innerWidth+1))`),null,2))}catch{}}
finally{
 const hash=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')
 const buildHashes=Object.fromEntries(fs.readdirSync('frontend/dist',{recursive:true}).map(n=>path.join('frontend/dist',n)).filter(n=>fs.statSync(n).isFile()).map(n=>[n,hash(n)]))
 fs.writeFileSync(root+'/browser-results.json',JSON.stringify({status:process.exitCode?'FAIL':'PASS',checks,errors,exceptions,consoleMessages,networkFailures,buildHashes,limitations:['Temporary synthetic SQLite, fake model callable','HTTP bridge to HTTPS TestClient: production TLS/browser cookie NOT_RUN','Desktop Edge emulation, not physical phone','No real supplier/mail/PG/deployment']},null,2));fs.writeFileSync(root+'/fixture.log',fixtureLog)
 try{if(ws?.readyState===1){await send('Browser.close');ws.close()}}catch{}edge?.kill()
 try{if(runtime)await fetch(runtime.origin+'/__qa__/shutdown',{method:'POST',headers:{'X-QA-Guard':runtime.guard}});await pause(1000)}catch{}if(fixture.exitCode===null)fixture.kill()
}
