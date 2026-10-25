// Compiled Vue + actual FastAPI routes/services; only DB, supplier and clock synthetic.
import fs from 'node:fs'
import path from 'node:path'
import {spawn} from 'node:child_process'
import crypto from 'node:crypto'
const root='docs/review/cloud_update_2026-10-25/browser'
process.env.DAILY_USE_EVIDENCE_DIR=root
process.env.DAILY_USE_REVIEW_CASES='1'
fs.mkdirSync(root,{recursive:true})
const pause=ms=>new Promise(r=>setTimeout(r,ms))
const runtimePath=root+'/runtime.json'
if(fs.existsSync(runtimePath))fs.unlinkSync(runtimePath)
const fixture=spawn(process.env.LIFEXP_TEST_PYTHON||'.venv/Scripts/python.exe',['tests/daily_use_runtime.py'],{windowsHide:true,stdio:['ignore','pipe','pipe']})
let fixtureLog='';fixture.stdout.on('data',b=>fixtureLog+=b);fixture.stderr.on('data',b=>fixtureLog+=b)
const profile=fs.mkdtempSync(path.resolve('_tmp_daily_edge_'))
let edge,ws,seq=0,runtime
const pending=new Map(),checks=[],errors=[],exceptions=[],consoleMessages=[],networkFailures=[]
function check(name,ok,detail){checks.push({name,status:ok?'PASS':'FAIL',...(detail?{detail}: {})});if(!ok)throw Error(name+(detail?' '+JSON.stringify(detail):''))}
function send(method,params={}){return new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))})}
async function ev(expression){const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value}
async function wait(expression){for(let i=0;i<150;i++){if(await ev(expression))return;await pause(100)}throw Error('wait '+expression)}
async function go(route){await ev(`location.hash=${JSON.stringify(route)}`);await pause(500);await wait(`!!document.querySelector('.app-shell')&&!document.querySelector('.hub-loading')`)}
async function click(text,selector='button'){const query=`[...document.querySelectorAll(${JSON.stringify(selector)})].find(e=>e.textContent.trim()===${JSON.stringify(text)}&&!e.disabled&&e.checkVisibility())`;await wait(`!!(${query})`);await ev(`(${query}).scrollIntoView({block:'center'})`);await pause(40);const point=await ev(`(()=>{const e=(${query}),r=e.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2;return {x,y,reachable:e.contains(document.elementFromPoint(x,y))}})()`);if(!point.reachable)throw Error('button obstructed '+text);await send('Input.dispatchMouseEvent',{type:'mousePressed',x:point.x,y:point.y,button:'left',clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:point.x,y:point.y,button:'left',clickCount:1});await pause(200)}
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
 let port;for(let i=0;i<150;i++){try{port=fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];break}catch{}await pause(100)}
 const targets=await fetch('http://127.0.0.1:'+port+'/json').then(r=>r.json());ws=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl)
 await new Promise(r=>ws.addEventListener('open',r,{once:true}))
 ws.addEventListener('message',e=>{const r=JSON.parse(e.data);if(r.id){const p=pending.get(r.id);pending.delete(r.id);r.error?p.reject(Error(JSON.stringify(r.error))):p.resolve(r.result)}else if(r.method==='Runtime.exceptionThrown')exceptions.push(r.params.exceptionDetails);else if(r.method==='Runtime.consoleAPICalled')consoleMessages.push(r.params.args.map(a=>a.value||a.description||'').join(' '));else if(r.method==='Network.loadingFailed')networkFailures.push(r.params)})
 await send('Runtime.enable');await send('Page.enable');await send('Network.enable');await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});await send('Page.navigate',{url:runtime.origin});await wait(`!!document.querySelector('.auth-paper')`)
 check('production title and ICP footer',await ev(`document.title.includes('人生手账')&&document.querySelector('.site-footer').textContent.includes('浙ICP备2026087237号-1')`))
 await login('日常测试','daily-test-password');await wait(`!!document.querySelector('[data-hub=today]')`)
 check('home compact actions not inline editor',await ev(`!!document.querySelector('a[href="#/capture"]')&&!document.querySelector('#new-record')`))
 check('home retains first record and rest access',await ev(`document.body.innerText.includes('首记与休息')`))
 await go('/growth');check('ability closed by default',await ev(`!document.querySelector('.hub-ability').open`));await ev(`document.querySelector('.hub-ability').open=true`)
 await ev(`document.querySelector('a[href="#/growth/attributes"]').click()`);await wait(`!!document.querySelector('.growth-page')`);await ev(`document.querySelector('.page-back').click()`);await wait(`!!document.querySelector('.hub-ability')`);check('ability state retained on return',await ev(`document.querySelector('.hub-ability').open`))
 const today=(await api('/trial')).data.today
 const make=async(name,category,minutes)=>api('/projects',{request_key:crypto.randomUUID(),expected_version:0,name,category,frequency:'daily',start:today,planned_minutes:minutes})
 check('real project timed created',(await make('阅读半小时','plan',30)).status===200)
 check('real project untimed created',(await make('不定时行动','plan',null)).status===200)
 check('real care created',(await make('记得喝水','care',null)).status===200)
 await go('/plans');await wait(`document.body.innerText.includes('阅读半小时')`);check('plans root no expanded forms',await ev(`!document.querySelector('.project-manager')`))
 await ev(`document.querySelector('a[href^="#/plans/item"]').click()`);await wait(`document.querySelectorAll('.project-row').length===1`);check('selected project only',true)
 await go('/plans/timer');await wait(`document.body.innerText.includes('阅读半小时')`);check('plan timer excludes untimed and care',await ev(`!document.body.innerText.includes('不定时行动')&&!document.body.innerText.includes('记得喝水')`))
 await go('/timers');check('entertainment separated from plan timing',await ev(`!document.body.innerText.includes('阅读半小时')`))
 await go('/capture');await fill('#new-record','联合验收：阅读二十分钟，整理三条笔记。');await fill('.composer-analysis select','now');await click('保存记录');await wait(`!!document.querySelector('a[href^="#/events/"]')`)
 const href=await ev(`document.querySelector('a[href^="#/events/"]').getAttribute('href')`);const eventId=Number(href.split('/').at(-1));await ev(`document.querySelector('a[href^="#/events/"]').click()`)
 await wait(`document.querySelector('.entry-state')?.textContent==='建议已就绪'`);check('record detail compact original and reward cards',await ev(`!!document.querySelector('.entry-original-card')&&!!document.querySelector('.entry-result-card')`))
 check('proposed attributes visible',await ev(`document.querySelector('.entry-attributes').innerText.includes('体能')`));await click('查看入账预览');await wait(`document.querySelector('.entry-coin').innerText.includes('+6')`);check('normal event earns preview six coins',true)
 await click('确认入账');await wait(`document.querySelector('.entry-state')?.textContent==='已入账'`);check('actual attribute and coins visible after confirmation',await ev(`document.querySelector('.entry-coin').innerText.includes('+6')&&document.querySelector('.entry-attributes').innerText.includes('+0.9')`))
 const pendingAfter=await api('/pending');check('event no longer pending',pendingAfter.status===200&&Array.isArray(pendingAfter.data.items)&&!pendingAfter.data.items.some(r=>r.event_id===eventId))
 await go('/');await wait(`!!document.querySelector('[data-hub=today]')`);check('home retained claim action',await ev(`document.body.innerText.includes('领取首记 3 币')`));await click('领取首记 3 币');await wait(`document.body.innerText.includes('首记签到 +3 币')`)
 await go('/journal');await fill('input[type=search]','联合验收');await click('搜索');await wait(`document.querySelectorAll('.record-preview').length===1`);await ev(`document.querySelector('.record-preview').click()`);await wait(`!!document.querySelector('.entry-page')`);await ev(`document.querySelector('.page-back').click()`);await wait(`!!document.querySelector('input[type=search]')`);check('journal search preserved',await ev(`document.querySelector('input[type=search]').value==='联合验收'`))
 await go('/growth/calendar');await wait(`!!document.querySelector('.is-today')`);await ev(`document.querySelector('.is-today').click()`);await wait(`!!document.querySelector('input[aria-label="内容日期"]')`);check('calendar opens date-filtered journal',await ev(`document.querySelector('input[aria-label="内容日期"]').value===${JSON.stringify(today)}`))
 const paths=['/','/journal','/plans','/growth','/rewards','/me','/capture','/plans/all','/plans/care','/plans/goals','/plans/mainline','/plans/context','/plans/legacy','/growth/attributes','/growth/history','/growth/calendar','/reports','/diary','/pending','/achievements','/rewards/shop','/rewards/manage','/rewards/vouchers','/rewards/history','/rewards/ledger','/rewards/rules','/rewards/agreements','/me/personal','/personal-information','/important-days','/preferences','/settings','/security','/feedback','/announcements','/challenges','/special-vouchers']
 for(const width of [1440,390]){await send('Emulation.setDeviceMetricsOverride',{width,height:width<500?844:1000,deviceScaleFactor:1,mobile:false});for(const p of paths){await go(p);check('reachable no overflow '+width+' '+p,await ev(`document.documentElement.scrollWidth<=innerWidth+1&&!document.body.innerText.includes('本地体验账号')`));if(['/','/plans','/growth','/rewards','/me'].includes(p))await shot(p.replace('/','')||'today',false)}}
 await go('/events/'+eventId);check('record mobile no horizontal overflow',await ev(`document.documentElement.scrollWidth<=innerWidth+1`));await shot('event-mobile')
 await go('/me');await click('退出登录');await wait(`!!document.querySelector('.auth-paper')`);check('logout retained',true)
 await login('owner_fixture','owner-test-password');await wait(`location.hash.startsWith('#/admin')`);check('admin separate from personal pages',await ev(`!document.querySelector('nav[aria-label="主要导航"]').textContent.includes('手账')`))
 await go('/security');await wait(`location.hash.startsWith('#/admin')`);check('admin guard retained',true)
 check('no browser exceptions',exceptions.length===0)
 console.log(JSON.stringify({status:'PASS',checks:checks.length}))
}catch(e){process.exitCode=1;console.error(e);try{await shot('failure');fs.writeFileSync(root+'/failure.txt',await ev('document.body.innerText'))}catch{}}
finally{
 try{if(runtime)await fetch(runtime.origin+'/__qa__/shutdown',{method:'POST',headers:{'X-QA-Guard':runtime.guard}})}catch{}
 fs.writeFileSync(root+'/browser-results.json',JSON.stringify({status:process.exitCode?'FAIL':'PASS',checks,exceptions,consoleMessages,limits:['compiled production frontend and actual API with synthetic SQLite and scripted models','Edge viewport emulation; no physical phone or supplier validation']},null,2))
 try{if(ws?.readyState===1){await send('Browser.close');ws.close()}}catch{}edge?.kill();fixture.kill()
 fs.writeFileSync(root+'/fixture.log',fixtureLog)
}
