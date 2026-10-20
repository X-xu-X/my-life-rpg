// Real compiled Vue, isolated headless Edge, synthetic API only. No DB or supplier.
import fs from 'node:fs'
import path from 'node:path'
import http from 'node:http'
import {spawn} from 'node:child_process'
import crypto from 'node:crypto'
const root='docs/review/full_system_2026-10-19/browser';fs.mkdirSync(root,{recursive:true})
const profile=fs.mkdtempSync(path.resolve('_tmp_full_edge_'))
const pause=ms=>new Promise(r=>setTimeout(r,ms))
const server=http.createServer((req,res)=>{const name=decodeURIComponent(req.url.split('?')[0]);const file=path.resolve('docs/review/full_system_2026-10-19/frontend-dist','.'+(name==='/'?'/index.html':name));if(!file.startsWith(path.resolve('docs/review/full_system_2026-10-19/frontend-dist')+path.sep)||!fs.existsSync(file)){res.writeHead(404);res.end();return}res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');fs.createReadStream(file).pipe(res)})
await new Promise(r=>server.listen(0,'127.0.0.1',r))
const origin=`http://127.0.0.1:${server.address().port}`
const binary=['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','C:/Program Files/Microsoft/Edge/Application/msedge.exe'].find(fs.existsSync)
const edge=spawn(binary,['--headless=new','--disable-gpu','--no-first-run','--disable-background-networking','--disable-sync','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:'ignore'})
let ws,seq=0;const pending=new Map(),checks=[],errors=[],unknown=[]
let testCalls=0,saveCalls=0,redeemCalls=0,jobReads=0,jobMode=false,testDelay=0
const account={role:'user',id:99016,username:'trial_fixture',timezone:'Asia/Shanghai',mode:'cloud',onboarding_completed:true,baseline_kind:'neutral'}
const record={record_kind:'event',ai_permission:'allowed',ai_permission_version:1,saved_on:'2026-10-18',saved_timezone:'Asia/Shanghai',id:301,title:'部署项目的单件事件',content:'整理了部署流程并完成一次隔离验证。',source:'form',occurred_at:'2026-10-15T16:00:00Z',occurred_on:'2026-10-16',time_precision:'date',created_at:'2026-10-16T06:00:00Z',content_version:1,analysis_intent:'never',is_pure:false}
const group=()=>({provider_id:'deepseek',enabled:true,configured:true,model:'fixture-chat',base_url:'https://api.deepseek.com',config_version:4,validation:{status:'untested'}})
const models={primary:group(),aux:{...group(),enabled:false},providers:{deepseek:'https://api.deepseek.com',openai:'https://api.openai.com/v1',siliconflow:'https://api.siliconflow.cn/v1'},env_fallback:{ready:false}}
const names=['体能','力量','敏捷','智力','专注','意志','情绪','表达','社交','创造','审美','生活','财富']
function send(method,params={}){return new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))})}
async function evaluate(expression){const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value}
function check(name,ok){checks.push({name,status:ok?'PASS':'FAIL'});if(!ok)throw Error(name)}
async function wait(expression){for(let n=0;n<100;n++){if(await evaluate(expression))return;await pause(100)}throw Error('Wait '+expression)}
async function go(route){await evaluate(`location.hash=${JSON.stringify(route)}`);await pause(450)}
async function click(text,selector='button'){await evaluate(`(()=>{const e=[...document.querySelectorAll(${JSON.stringify(selector)})].find(e=>e.textContent.trim()===${JSON.stringify(text)});if(!e)throw Error('No button');e.click()})()`);await pause(150)}
async function fill(selector,value){await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('input',{bubbles:true}))})()`)}
async function shot(name){const result=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(`${root}/${name}.png`,Buffer.from(result.data,'base64'))}

let planMode=false,planLag=false;const occurrences={}
const planFixture={id:901,name:'合成周期阅读',version:1,enabled:true,goal_id:null,rule:{frequency:'daily',start:'2026-10-01',timezone:'Asia/Shanghai'},history:[]}
let savedEvents=[record,{...record,id:303,ai_permission:'private',analysis_intent:'never',content:'已关闭AI的历史原文'}],diary=null,notes=[],careItems=[],feedback=[],pricing=[],qDraft=null
const careConfig={id:1,version:1,enabled:true,ai_allowed:false,suggestions:[]}
const groups=[{id:'life',title:'生活偏好'}],questions=Array.from({length:6},(_,n)=>({id:'life_'+(n+1),group:'life',text:'合成偏好问题 '+(n+1)}))
const trial={config:{id:1,version:1,enabled:true,base_minutes:30,timezone:'Asia/Shanghai'},today:'2026-10-18',daily:{id:1,version:1,base_seconds:1800,used_seconds:0,claimed:true},action_used:0}
let timers={items:[],active:null,server_now:new Date().toISOString(),vouchers:[1,2].map(id=>({redemption:{id,duration_seconds:1800,status:'pending'},allowance:null}))}
async function respond(p){
 const url=new URL(p.request.url)
 if(url.origin!==origin){await send('Fetch.failRequest',{requestId:p.requestId,errorReason:'BlockedByClient'});return}
 if(!url.pathname.startsWith('/api/')){await send('Fetch.continueRequest',{requestId:p.requestId});return}
 const route=url.pathname.slice(4),method=p.request.method,input=p.request.postData?JSON.parse(p.request.postData):{};let status=200,body
 if(route==='/auth/me')body=account
 else if(route==='/admin/overview')body={users:2,active:2,timezone:'Asia/Shanghai',groups:{ordinary:{total:1,active:1,disabled:0,created_today:1,logged_in_7_days:1},administrators:{total:1,active:1,disabled:0,created_today:1,logged_in_7_days:1}},published_announcements:0,site:{site_name:'合成站点',registration:'open'}}
 else if(route==='/admin/site')body={version:1,site_name:'合成站点',description:'管理元数据，不含日记',registration:'open',email_required:false,password_sessions:'all'}
 else if(route==='/admin/hosted-ai')body={enabled:false,version:0,payload:null}
 else if(route==='/admin/hosted-monitor')body={date_basis:'UTC',calls:0,tokens:0,cost:0,unknown:0,failures:0}
 else if(route.startsWith('/admin/'))body={items:[]}
 else if(route==='/export'){const format=url.searchParams.get('format'),ext={markdown:'md',html:'html',csv:'csv',json:'json'}[format];const bytes=fs.readFileSync(root+'/export-fixtures/lifexp-records.'+ext);await send('Fetch.fulfillRequest',{requestId:p.requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:{json:'application/json',markdown:'text/markdown',html:'text/html',csv:'text/csv'}[format]}],body:bytes.toString('base64')});return}
 else if(route==='/ai/preferences')body={mode:'personal',version:0,hosted:{available:false,version:0}}
 else if(route==='/trial')body=trial
 else if(route==='/phase')body={phase:null,return_prompt:false,holidays:[],holiday_claimed:false}
 else if(route==='/care'&&method==='GET')body={config:careConfig,day:'2026-10-18',items:careItems,today:careItems.map(item=>({item,entry:null})),legacy_history:[]}
 else if(route==='/care/items'&&method==='POST'){body={...input,id:careItems.length+1,version:1,rule:{frequency:input.frequency,weekdays:input.weekdays}};careItems.push(body)}
 else if(route==='/care/config'){Object.assign(careConfig,input,{version:careConfig.version+1});body=careConfig}
 else if(route.startsWith('/care/items/')&&method==='PUT'){const id=+route.split('/')[3];careItems=careItems.filter(i=>i.id!==id);body={...input,id,version:2}}
 else if(route==='/feedback'&&method==='GET')body={items:feedback}
 else if(route==='/feedback'&&method==='POST'){body={...input,id:1,version:1,state:'open',created_at:new Date().toISOString(),replies:[],user_id:account.id};feedback.push(body)}
 else if(route==='/questionnaire'&&method==='GET')body={groups,questions,draft:qDraft,onboarding_completed:true,baseline_kind:'neutral'}
 else if(route==='/questionnaire'&&method==='PUT'){qDraft={...input,version:(qDraft?.version||0)+1,preview:null};body=qDraft}
 else if(route==='/questionnaire/preview'){qDraft.preview={summary:'只更新未来背景',attributes:[],initial_coins:80};qDraft.version++;body=qDraft}
 else if(route==='/timers'&&method==='GET')body=timers
 else if(route==='/timers'&&method==='POST'){const voucher=timers.vouchers.find(r=>r.redemption.id===input.source_id);timers.active={id:101+timers.items.length,version:1,kind:input.kind,source_id:input.source_id,state:'running',intervals:[{start:new Date().toISOString(),end:null}],limit_seconds:1800-(voucher?.allowance?.used_seconds||0),last_sync_at:new Date().toISOString()};body=timers.active}
 else if(/^\/timers\/\d+\/end-preview$/.test(route)){timers.active={...timers.active,state:'review',version:timers.active.version+1,preview:{actual_seconds:input.actual_seconds||300,penalty_charged:0,ontime_awarded:1,coin_delta:1,offline_interval:true}};body=timers.active}
 else if(/^\/timers\/\d+\/confirm$/.test(route)){const active=timers.active,voucher=timers.vouchers.find(v=>v.redemption.id===active.source_id);if(voucher)voucher.allowance={total_seconds:1800,used_seconds:(voucher.allowance?.used_seconds||0)+active.preview.actual_seconds};timers.items.push({...active,state:'ended',settlement:active.preview,local_date:'2026-10-18'});timers.active=null;body={status:'confirmed'}}
 else if(/^\/timers\/\d+\/(pause|resume|sync)$/.test(route)){timers.active.version++;timers.active.state=route.endsWith('/pause')?'paused':'running';body=timers.active}
 else if(route==='/events'&&method==='POST'){saveCalls++;check('private raw save requires explicit permission',input.ai_permission==='private'&&input.intent==='never');body={...record,...input,id:302,ai_permission_version:1};savedEvents.push(body)}
 else if(route==='/events')body=savedEvents
 else if(/^\/events\/\d+$/.test(route))body=savedEvents.find(e=>e.id===+route.split('/')[2])||record
 else if(route==='/events/303/fact-bundles')body={items:[{id:91,event_version:1,version:2,state:'confirmed',payload:{items:[{fragment_id:11,fact_id:12,excerpt:'旧事实原句',summary:'HISTORICAL_FACT_OWNER_ONLY',grade:'small',changes:[],decision:'keep'}]},provenance:{provider:'fixture',model:'historical-fixture',config_version:1}}]}
 else if(route.endsWith('/fact-bundles'))body={items:[]}
 else if(route.endsWith('/fact-notes')&&method==='GET')body={items:notes.filter(n=>n.event_id===+route.split('/')[2])}
 else if(route.endsWith('/fact-notes')&&method==='POST'){body={...input,id:1,version:1,event_id:+route.split('/')[2]};notes.push(body)}
 else if(route.endsWith('/analysis-jobs')&&method==='GET')body={items:[]}
 else if(route.endsWith('/analysis-jobs')&&method==='POST'){testCalls++;body={id:601,state:'queued'}}
 else if(route.startsWith('/diaries/')&&method==='PUT'){check('diary defaults to private',input.ai_permission==='private');diary={...record,...input,record_kind:'diary',id:401,content_version:1};body={diary}}
 else if(route==='/diaries/2026-10-17'&&method==='GET')body={diary:{...record,id:402,record_kind:'diary',ai_permission:'private',content:'历史日记原文'},revisions:[],sessions:[{id:702,source_version:1,state:'needs_input'}]}
 else if(route==='/review-sessions/702')body={id:702,source_version:1,source_changed:false,version:1,jobs:[],turns:[{id:1,ordinal:1,question:'HISTORICAL_QUESTION_OWNER_ONLY',answer:'HISTORICAL_ANSWER_OWNER_ONLY',state:'answered'}],analyses:[]}
 else if(route.startsWith('/diaries/')&&method==='GET')body={diary,revisions:[],sessions:[],has_bookings:false}
 else if(route==='/reward-quotes'&&method==='GET')body={items:pricing}
 else if(route==='/reward-quotes'&&method==='POST'){status=503;body={detail:'MODEL_NOT_CONFIGURED'}}
 else if(route==='/plan-schedules')body=planMode?[planFixture]:[]
 else if(route==='/plan-occurrences'){const day=url.searchParams.get('day')||'2026-10-18';if(planLag&&day==='2026-10-16')await pause(500);body=(url.searchParams.has('day')||url.searchParams.has('today'))?{items:planMode?[{schedule:planFixture,local_date:day,occurrence:occurrences[day]||null}]:[]}:{history:Object.values(occurrences)}}
 else if(/^\/plan-schedules\/901\/occurrences\//.test(route)){const day=route.split('/').at(-1);body={...input,id:1,version:1,schedule_id:901,local_date:day,schedule_snapshot:planFixture,facts:{actual:input.actual,unit:input.unit},event_id:null,history:[]};occurrences[day]=body}
 else if(route==='/fact-relations')body=[]
 else if(route==='/event-options')body={items:[],next_cursor:null}
 else if(route==='/mainlines')body={items:[],previews:[],rule:null}
 else if(route==='/discoveries/refresh')body={status:'refreshed'}
 else if(route==='/dynamic-candidates')body={items:[],rule:null}
 else if(route==='/record-metrics')body={policy_version:'candidate-date-v1',legacy_unclassified:0,metrics:{}}
 else if(route==='/llm-config')body=models
 else if(route==='/settings')body={hidden_attributes:[],disabled_attributes:[],gamification_modules:{}}
 else if(route==='/attributes')body={attributes:names.map((name,i)=>({name,id:i+1,value:50,max_value:100,tier:'熟练',visibility:'show',description:'合成说明'})),onboarding_completed:true,baseline_kind:'neutral',level:1,exp:0}
 else if(['/attributes/history','/events/heatmap','/items','/items/stats','/goals','/anchors','/judgments'].includes(route))body=[]
 else if(route==='/pending')body={items:[]}
 else if(route==='/subdimensions')body={hierarchy:{},candidates:[]}
 else if(['/reports','/reports/previews','/daily-reviews','/announcements'].includes(route))body={items:[]}
 else if(route==='/onboarding/status')body={onboarding_completed:true,in_progress:false}
 else if(route==='/coins')body={balance:1234567890123,ledger:[]}
 else if(route==='/challenges/current')body={daily:[],weekly:[]}
 else if(route==='/shop/items')body={items:[{id:701,name:'合成娱乐券',reward_kind:'entertainment',duration_seconds:1800,enabled:true,coin_price:12,updated_at:'2026-10-18T06:00:00Z'}],balance:1234567890123}
 else if(route==='/redemptions')body={redemptions:[]}
 else if(route.startsWith('/shop/items/701/redemption-submissions/')){status=404;body={detail:'未找到'}}
 else if(route==='/shop/items/701/redeem'){redeemCalls++;body={id:801,item_name:'合成娱乐券',coin_spent:12}}
 else if(route==='/achievements/check')body={granted:[]}
 else if(route==='/achievements')body={achievements:[]}
 else if(route==='/auth/sessions')body={items:[]}
 else if(route==='/auth/security')body={has_password:true,email:null,email_verified:false,credentials_version:1,mail_ready:false}
 else if(['/exemptions','/stagnation'].includes(route))body={items:[],presets:[],balance:1234567890123}
 else{unknown.push(method+' '+route);status=404;body={detail:'Unmocked route'}}
 await send('Fetch.fulfillRequest',{requestId:p.requestId,responseCode:status,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from(JSON.stringify(body)).toString('base64')})
}
try{
 let port
 for(let i=0;i<100;i++){try{port=fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];break}catch{}await pause(100)}
 if(!port)throw Error('Edge startup failed')
 const targets=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();ws=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl)
 await new Promise(r=>ws.addEventListener('open',r,{once:true}))
 ws.addEventListener('message',e=>{const value=JSON.parse(e.data);if(value.id){const task=pending.get(value.id);pending.delete(value.id);value.error?task.reject(value.error):task.resolve(value.result)}else if(value.method==='Fetch.requestPaused')respond(value.params).catch(e=>errors.push(String(e)));else if(value.method==='Runtime.exceptionThrown')errors.push(value.params.exceptionDetails.text)})
 await send('Runtime.enable');await send('Page.enable');await send('Fetch.enable',{patterns:[{urlPattern:'*'}]});await send('Page.navigate',{url:origin});await wait(`!!document.querySelector('#new-record')`)

 check('five navigation sections',await evaluate(`document.querySelectorAll('.mobile-nav a').length===5`))
 for(const width of [390,1440]){
  await send('Emulation.setDeviceMetricsOverride',{width,height:width<500?844:1000,deviceScaleFactor:1,mobile:false})
  for(const route of ['/','/plans','/diary','/care','/onboarding','/timers','/phase','/growth','/settings','/feedback','/security','/challenges','/journal','/checkin','/reports']){
   await go(route);check(`layout ${width} ${route}`,await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`));await shot((route==='/'?'today':route.slice(1))+'-'+width)
  }
 }
 await go('/');await fill('#new-record','私密合成事件');await click('保存记录');check('private save succeeds without model',saveCalls===1&&testCalls===0)
 await go('/diary');await fill('[aria-label="日记原文"]','负面情绪也可以只保存。');await click('保存原文');await wait(`document.body.innerText.includes('原文已保存')`);check('private diary creates no question or fact job',!!diary&&testCalls===0)
 planMode=true;await go('/plans');await fill('.plan-agenda > label input[type=date]','2026-10-15');await wait(`!!document.querySelector('.plan-card textarea')`);await fill('.plan-card textarea','周一草稿A')
 await fill('.plan-agenda > label input[type=date]','2026-10-16');await wait(`!!document.querySelector('.plan-card textarea')`);check('next day starts with its own empty plan draft',await evaluate(`document.querySelector('.plan-card textarea').value===''`));await fill('.plan-card textarea','周二草稿B')
 await fill('.plan-agenda > label input[type=date]','2026-10-15');await wait(`!!document.querySelector('.plan-card textarea')`);check('plan A to B to A restores A',await evaluate(`document.querySelector('.plan-card textarea').value==='周一草稿A'`))
 planLag=true;await fill('.plan-agenda > label input[type=date]','2026-10-16');await pause(80);await fill('.plan-agenda > label input[type=date]','2026-10-17');await wait(`!!document.querySelector('.plan-card textarea')`);await pause(600);check('late plan response cannot overwrite a newer date',await evaluate(`document.querySelector('.plan-card').innerText.includes('2026-10-17')&&document.querySelector('.plan-card textarea').value===''`));planLag=false
 await fill('.plan-agenda > label input[type=date]','2026-10-16');await wait(`!!document.querySelector('.plan-card textarea')`);check('plan B draft remains isolated after race',await evaluate(`document.querySelector('.plan-card textarea').value==='周二草稿B'`))
 await evaluate(`(()=>{const e=document.querySelector('.plan-card select');e.value='missed';e.dispatchEvent(new Event('change',{bubbles:true}))})()`);await click('确认未完成并锁定');await wait(`document.querySelector('.plan-card').innerText.includes('已锁定')`);check('missed plan locks without inventing facts',!occurrences['2026-10-16'].event_id&&await evaluate(`!document.querySelector('.plan-card textarea')`));await shot('plan-missed-lock')
 await go('/me');await go('/plans');await fill('.plan-agenda > label input[type=date]','2026-10-15');await wait(`!!document.querySelector('.plan-card textarea')`);check('plan draft restores after leaving the page',await evaluate(`document.querySelector('.plan-card textarea').value==='周一草稿A'`));planMode=false
 await go('/care')
 for(let i=1;i<=8;i++){await fill('form input','自定项目 '+i);await click('保存项目');await wait(`document.body.innerText.includes('自定项目 ${i} ·')`)}
 check('eight care projects persist',careItems.length===8);await shot('care-eight')
 await go('/me');await go('/care');check('care projects survive remount',await evaluate(`[...document.querySelectorAll('h3')].filter(e=>e.textContent.includes('自定项目')).length===8`))
 await go('/onboarding');await evaluate(`document.querySelector('details summary').click()`);await click('跳过整组');await pause(1200);check('questionnaire autosaves skipped answers without AI',Object.values(qDraft.answers).every(a=>a.state==='skipped')&&testCalls===0)
 await go('/me');await go('/onboarding');check('skipped questionnaire restores',await evaluate(`document.body.innerText.includes('6/6')`))
 await go('/timers');await click('使用这张券（本次重新计时）');await fill('input[type=number]','300');await click('结束并查看核对预览');await click('确认实际用量与结算');check('first voucher has 25 minutes',timers.vouchers[0].allowance.used_seconds===300)
 await evaluate(`document.querySelectorAll('article button')[1].click()`);await pause(250);check('new voucher starts with all 30 minutes',timers.active.source_id===2&&timers.active.limit_seconds===1800);check('new session clears previous actual-time draft',await evaluate(`document.querySelector('input[type=number]').value===''`));await shot('timer-second-voucher')
 await click('暂停');check('timer pauses durably',timers.active.state==='paused');await go('/me');await go('/timers');check('paused timer restores',await evaluate(`document.body.innerText.includes('已暂停')`))
 await go('/events/301');await fill('textarea','仅关于本事件的补充');await click('保存相关补充');check('related supplement saved separately',notes.length===1&&savedEvents[0].content===record.content);await shot('event-supplement')
 await go('/events/303');check('closed permission retains read-only fact history',await evaluate(`document.body.innerText.includes('HISTORICAL_FACT_OWNER_ONLY')&&![...document.querySelectorAll('button')].some(b=>b.textContent.includes('分析这篇记录')||b.textContent.includes('确认本组'))`));await shot('private-fact-history');await go('/diary?date=2026-10-17');check('closed permission retains read-only paired answers',await evaluate(`document.body.innerText.includes('HISTORICAL_ANSWER_OWNER_ONLY')&&![...document.querySelectorAll('button')].some(b=>b.textContent==='保存回答')`));await shot('private-diary-history')
 await go('/challenges');await click('商店');await fill('form input','想要的体验');await click('请求 AI 价格建议');await wait(`document.body.innerText.includes('MODEL_NOT_CONFIGURED')`);check('failed price keeps content draft',await evaluate(`document.querySelector('form input').value==='想要的体验'`));check('failed price creates no product',pricing.length===0);await click('保留草稿，结束本次价格请求')
 await click('兑换');await wait(`!!document.querySelector('dialog[open]')`);check('open dialog has a unique accessible title',await evaluate(`(()=>{const e=document.querySelector('dialog[open]'),id=e.getAttribute('aria-labelledby');return document.querySelectorAll('#'+id).length===1&&document.getElementById(id).textContent.includes('确认兑换')})()`));check('financial modal receives focus',await evaluate(`document.querySelector('dialog').contains(document.activeElement)`));await shot('reward-confirm');await click('取消');check('cancel changes no balance',redeemCalls===0)
 await click('兑换');await evaluate(`document.querySelector('dialog button.primary').click()`);await wait(`!document.querySelector('dialog[open]')`);check('confirmed redemption sends one request',redeemCalls===1)
 await go('/feedback');await fill('form input','私密反馈标题');await fill('form textarea','长内容'.repeat(400));await click('提交私密反馈');check('feedback retains plain text',feedback.length===1);await shot('feedback-long')
 await send('Emulation.setDeviceMetricsOverride',{width:360,height:520,deviceScaleFactor:1,mobile:false});await go('/diary');await evaluate(`document.querySelector('textarea').focus();document.querySelector('textarea').scrollIntoView({block:'center'})`);check('reduced viewport input remains reachable',await evaluate(`document.querySelector('textarea').getBoundingClientRect().bottom>0&&document.documentElement.scrollWidth<=innerWidth+1`));await shot('diary-keyboard-sized')
 await go('/settings');fs.mkdirSync(root+'/downloads',{recursive:true});await send('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:path.resolve(root,'downloads')});for(const format of ['json','markdown','html','csv']){const ext={json:'json',markdown:'md',html:'html',csv:'csv'}[format],file=root+'/downloads/lifexp-records.'+ext;if(fs.existsSync(file))fs.unlinkSync(file);await evaluate(`(()=>{const e=document.querySelector('#settings-data select');e.value=${JSON.stringify(format)};e.dispatchEvent(new Event('change',{bubbles:true}))})()`);await click('生成并下载');for(let n=0;n<50&&!fs.existsSync(file);n++)await pause(100);check('real browser download '+format,fs.existsSync(file)&&fs.readFileSync(file).equals(fs.readFileSync(root+'/export-fixtures/lifexp-records.'+ext)))}await evaluate(`(()=>{const sizes=[...document.querySelectorAll('body *')].map(e=>[e,parseFloat(getComputedStyle(e).fontSize)]);for(const [e,size] of sizes)e.style.fontSize=(size*2)+'px'})()`);check('settings at 200 percent text width',await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`));await shot('settings-large-text')
 account.role='owner';await send('Page.reload');await pause(900);await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});for(const route of ['/admin','/admin/users','/admin/announcements','/admin/site','/admin/audit','/admin/feedback','/admin/security']){await go(route);check('admin layout '+route,await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`));await shot(route.replaceAll('/','_')+'-390')}check('admin workspace has no ordinary diary navigation',await evaluate(`![...document.querySelectorAll('.mobile-nav a')].some(a=>a.hash==='#/diary'||a.hash==='#/journal')`))
 check('no unexpected API',unknown.length===0);check('no Vue runtime errors',errors.length===0)
 console.log(JSON.stringify({status:'PASS',checks:checks.length,source:'compiled Vue, synthetic API',limitations:['No real phone/model/PG/mail/deployment']}))
}catch(error){try{await shot('failure');const overflow=await evaluate(`([...document.querySelectorAll('body *')].map(e=>({tag:e.tagName,cls:e.className,text:e.innerText?.slice(0,80),right:e.getBoundingClientRect().right,width:e.getBoundingClientRect().width})).filter(e=>e.right>innerWidth+1))`);fs.writeFileSync(root+'/overflow-debug.json',JSON.stringify(overflow,null,2))}catch{}errors.push(String(error));console.error(error);process.exitCode=1}
finally{
 const buildHashes=Object.fromEntries(fs.readdirSync('docs/review/full_system_2026-10-19/frontend-dist',{recursive:true}).map(name=>path.join('docs/review/full_system_2026-10-19/frontend-dist',name)).filter(name=>fs.statSync(name).isFile()).map(name=>[name,crypto.createHash('sha256').update(fs.readFileSync(name)).digest('hex')]))
 fs.writeFileSync(`${root}/browser-results.json`,JSON.stringify({status:process.exitCode?'FAIL':'PASS',checks,errors,unknown,buildHashes,exportHashes:Object.fromEntries(['json','md','html','csv'].map(ext=>{const name='lifexp-records.'+ext;return [name,{response:crypto.createHash('sha256').update(fs.readFileSync(root+'/export-fixtures/'+name)).digest('hex'),download:crypto.createHash('sha256').update(fs.readFileSync(root+'/downloads/'+name)).digest('hex')}]})),limitations:['Desktop Edge emulated widths; synthetic APIs only']},null,2))
 try{if(ws?.readyState===1){await send('Browser.close');ws.close()}}catch{}edge.kill();server.close()
}
