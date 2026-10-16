// Real compiled Vue, isolated headless Edge, synthetic API only. No DB or supplier.
import fs from 'node:fs'
import path from 'node:path'
import http from 'node:http'
import {spawn} from 'node:child_process'
import crypto from 'node:crypto'
const root='docs/review/continuation_2026-10-16';fs.mkdirSync(root,{recursive:true})
const profile=fs.mkdtempSync(path.resolve('_tmp_trial_edge_'))
const pause=ms=>new Promise(r=>setTimeout(r,ms))
const server=http.createServer((req,res)=>{const name=decodeURIComponent(req.url.split('?')[0]);const file=path.resolve('frontend/dist','.'+(name==='/'?'/index.html':name));if(!file.startsWith(path.resolve('frontend/dist')+path.sep)||!fs.existsSync(file)){res.writeHead(404);res.end();return}res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');fs.createReadStream(file).pipe(res)})
await new Promise(r=>server.listen(0,'127.0.0.1',r))
const origin=`http://127.0.0.1:${server.address().port}`
const binary=['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','C:/Program Files/Microsoft/Edge/Application/msedge.exe'].find(fs.existsSync)
const edge=spawn(binary,['--headless=new','--disable-gpu','--no-first-run','--disable-background-networking','--disable-sync','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:'ignore'})
let ws,seq=0;const pending=new Map(),checks=[],errors=[],unknown=[]
let testCalls=0,saveCalls=0,redeemCalls=0,jobReads=0,jobMode=false,testDelay=0
const account={id:99016,username:'trial_fixture',timezone:'Asia/Shanghai',mode:'cloud',onboarding_completed:true,baseline_kind:'neutral'}
const record={id:301,title:'部署项目的单件事件',content:'整理了部署流程并完成一次隔离验证。',source:'form',occurred_at:'2026-10-15T16:00:00Z',occurred_on:'2026-10-16',time_precision:'date',created_at:'2026-10-16T06:00:00Z',content_version:1,analysis_intent:'never',is_pure:false}
const group=()=>({provider_id:'deepseek',enabled:true,configured:true,model:'fixture-chat',base_url:'https://api.deepseek.com',config_version:4,validation:{status:'untested'}})
const models={primary:group(),aux:{...group(),enabled:false},providers:{deepseek:'https://api.deepseek.com',openai:'https://api.openai.com/v1',siliconflow:'https://api.siliconflow.cn/v1'},env_fallback:{ready:false}}
let diary=null,review=null,schedule=null,occurrence=null,exportCalls=0;
const names=['体能','力量','敏捷','智力','专注','意志','情绪','表达','社交','创造','审美','生活','财富']
function send(method,params={}){return new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))})}
async function evaluate(expression){const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value}
function check(name,ok){checks.push({name,status:ok?'PASS':'FAIL'});if(!ok)throw Error(name)}
async function wait(expression){for(let n=0;n<100;n++){if(await evaluate(expression))return;await pause(100)}throw Error('Wait '+expression)}
async function go(route){await evaluate(`location.hash=${JSON.stringify(route)}`);await pause(450)}
async function click(text,selector='button'){await evaluate(`(()=>{const e=[...document.querySelectorAll(${JSON.stringify(selector)})].find(e=>e.textContent.trim()===${JSON.stringify(text)});if(!e)throw Error('No button');e.click()})()`);await pause(150)}
async function fill(selector,value){await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('input',{bubbles:true}))})()`)}
async function shot(name){const result=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(`${root}/${name}.png`,Buffer.from(result.data,'base64'))}
async function respond(p){
 const url=new URL(p.request.url)
 if(url.origin!==origin){await send('Fetch.failRequest',{requestId:p.requestId,errorReason:'BlockedByClient'});return}
 if(!url.pathname.startsWith('/api/')){await send('Fetch.continueRequest',{requestId:p.requestId});return}
 const route=url.pathname.slice(4),method=p.request.method;let status=200,body
 if(route==='/record-metrics')body={policy_version:'candidate-date-v1',legacy_unclassified:0,metrics:{}}
 else if(route==='/export'){exportCalls++;body={synthetic:true};check('export selection sent',url.searchParams.get('format')==='html')}
 else if(route==='/plan-schedules'&&method==='POST'){const input=JSON.parse(p.request.postData);schedule={id:905,name:input.name,version:1,enabled:true,rule:{frequency:input.frequency,start:input.start},history:[]};body=schedule}
 else if(route==='/plan-schedules')body=schedule?[schedule]:[]
 else if(route==='/plan-occurrences')body=url.searchParams.has('day')?{items:schedule?[{schedule,occurrence}]:[]}:{history:occurrence?[occurrence]:[]}
 else if(route.startsWith('/plan-schedules/905/occurrences/')){const input=JSON.parse(p.request.postData);occurrence={id:906,version:1,local_date:'2026-10-16',outcome:input.outcome,facts:{content:input.content,actual:input.actual,unit:input.unit},schedule_snapshot:{name:schedule.name},history:[]};body=occurrence}
 else if(route==='/fact-relations')body=[]
 else if(route.startsWith('/life-checklists/'))body={version:0,payload:{enabled:false,entries:{},event_ids:[]}}
 else if(route==='/diaries/2026-10-16'&&method==='PUT'){const input=JSON.parse(p.request.postData);diary={id:901,content:input.content,content_version:(diary?.content_version||0)+1,occurred_on:'2026-10-16',record_kind:'diary'};body={diary}}
 else if(route==='/diaries/2026-10-16')body={diary,revisions:diary?[{id:1,version:diary.content_version,content:diary.content}]:[],sessions:review?[review]:[]}
 else if(route==='/diaries/2026-10-16/review-sessions'){review={id:902,source_version:diary.content_version,version:1,state:'draft',turns:[],analyses:[],jobs:[],source_changed:false};body=review}
 else if(route==='/review-sessions/902/analyze'){review.version++;review.turns=[{id:903,ordinal:1,version:1,question:'部署中最大的困难是什么？',answer:'',state:'unanswered'}];review.jobs=[{id:904,state:'ready'}];body={id:904,state:'queued'}}
 else if(route==='/review-sessions/902/turns/903'){const input=JSON.parse(p.request.postData);review.turns[0].answer=input.answer;review.turns[0].state=input.skip?'skipped':'answered';review.version++;body={version:review.version,turn:review.turns[0]}}
 else if(route==='/review-sessions/902')body=review
 else if(route==='/auth/me')body=account
 else if(route==='/events'&&method==='POST'){saveCalls++;const input=JSON.parse(p.request.postData);body={...record,...input,id:302};check('date-only payload without invented timestamp',input.time_precision==='date'&&!input.occurred_at&&input.source==='form')}
 else if(route==='/events')body=[record]
 else if(route==='/events/301')body=record
 else if(route==='/judgments')body=jobMode&&jobReads>=2?[{id:501,event_id:301,status:'pending',confidence:.95,summary:'隔离建议',analysis:[],suggested_changes:[],updated_at:'2026-10-16T06:00:00Z',model_provenance:{provider:'deepseek',model:'fixture-chat',config_version:4}}]:[]
 else if(route==='/pending')body={items:jobMode?[{event_id:301,job:{id:601,state:'running'}}]:[]}
 else if(route==='/analysis-jobs/601'){jobReads++;body={id:601,event_id:301,state:jobReads>=2?'ready':'running',result:{}}}
 else if(route==='/llm-config'&&method==='PUT'){const input=JSON.parse(p.request.postData);models[input.group]={...models[input.group],...input,config_version:models[input.group].config_version+1,validation:{status:'untested'}};body={ok:true}}
 else if(route==='/llm-config/test'){testCalls++;const input=JSON.parse(p.request.postData);check('tests saved version only',Object.keys(input).sort().join(',')==='expected_config_version,group'&&input.expected_config_version===models[input.group].config_version);await pause(testDelay);body={status:'failed',message:'模型不存在或无权限，请核对模型 ID。',error_code:'MODEL_NOT_FOUND',config_version:input.expected_config_version,tested_at:'2026-10-16T06:00:00Z'};models[input.group].validation=body}
 else if(route==='/llm-config')body=models
 else if(route==='/settings')body={hidden_attributes:[],disabled_attributes:[],gamification_modules:{}}
 else if(route==='/attributes')body={attributes:names.map((name,i)=>({name,id:i+1,value:50,max_value:100,tier:'熟练',visibility:'show',description:'合成说明'})),onboarding_completed:true,baseline_kind:'neutral',level:1,exp:0}
 else if(['/attributes/history','/events/heatmap','/items','/items/stats','/goals','/anchors'].includes(route))body=[]
 else if(route==='/subdimensions')body={hierarchy:{},candidates:[]}
 else if(route==='/reports'||route==='/daily-reviews')body={items:[]}
 else if(route==='/onboarding/status')body={onboarding_completed:true,in_progress:false}
 else if(route==='/coins')body={balance:1234567890123,ledger:[]}
 else if(route==='/challenges/current')body={daily:[],weekly:[]}
 else if(route==='/shop/items')body={items:[{id:701,name:'阅读一小时的奖励',enabled:true,coin_price:12,updated_at:'2026-10-16T06:00:00Z'}],balance:1234567890123}
 else if(route==='/redemptions')body={redemptions:[]}
 else if(route.startsWith('/shop/items/701/redemption-submissions/')){status=404;body={detail:'未找到'}}
 else if(route==='/shop/items/701/redeem'){redeemCalls++;body={id:801,item_name:'阅读一小时的奖励',coin_spent:12}}
 else if(route==='/achievements/check')body={granted:[]}
 else if(route==='/achievements')body={achievements:[]}
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

 await go('/diary?date=2026-10-16');await wait(`!!document.querySelector('textarea[aria-label="日记原文"]')`)
 await fill('textarea[aria-label="日记原文"]','今天完成了项目部署，保留自己的原文。');await click('保存原文');await wait(`document.body.innerText.includes('原文已保存，问答不会改写原文。')`)
 check('diary original persisted',diary.content.includes('自己的原文'))
 await click('开始 / 恢复此版本回顾');await click('生成辅助问题与回顾');await wait(`document.body.innerText.includes('部署中最大的困难是什么？')`)
 await fill('.review-turn textarea','迁移时遇到版本冲突，已解决。');await click('保存回答');await wait(`document.querySelector('.review-turn').innerText.includes('已解决')`)
 check('answer separate from original',!diary.content.includes('版本冲突')&&review.turns[0].answer.includes('版本冲突'))
 await go('/journal');await go('/diary?date=2026-10-16');await wait(`document.body.innerText.includes('已解决')`)
 check('review restored after navigation',await evaluate(`document.querySelector('textarea[aria-label="日记原文"]').value.includes('自己的原文')&&document.body.innerText.includes('部署中最大的困难是什么？')`))
 for(const width of [390,1440]){await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});check('diary layout '+width,await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`));await shot('diary-'+width)}

 await go('/plans');await evaluate(`document.querySelector('.plan-agenda details').open=true`);await fill('.plan-agenda form input[required]','每天阅读');await click('保存日程');await wait(`!!document.querySelector('.plan-card')`)
 check('schedule created in real Vue',schedule.name==='每天阅读')
 await evaluate(`(()=>{const e=document.querySelector('.plan-card select');e.value='missed';e.dispatchEvent(new Event('change',{bubbles:true}))})()`);await click('确认未完成并锁定');await wait(`document.querySelector('.plan-card').innerText.includes('已锁定')`)
 check('missed locks inline with no event',occurrence.outcome==='missed'&&!occurrence.event_id)
 check('missed has no success notice',await evaluate(`![...document.querySelectorAll('.plan-agenda [role=status]')].some(e=>e.textContent.includes('已保存'))`))
 for(const width of [390,1440]){await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});check('plans layout '+width,await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`));await shot('plans-'+width)}
 await go('/settings');await evaluate(`(()=>{const e=document.querySelector('#settings-data select');e.value='html';e.dispatchEvent(new Event('change',{bubbles:true}))})()`);await click('生成并下载');await wait(`document.body.innerText.includes('文件已生成并开始下载')`);check('real Vue export download',exportCalls===1)
 check('no unexpected API' ,unknown.length===0);check('no runtime errors',errors.length===0)
 console.log(JSON.stringify({status:'PASS',checks:checks.length}))
}catch(error){errors.push(String(error));console.error(error);process.exitCode=1}
finally{
 fs.writeFileSync(`${root}/browser-results.json`,JSON.stringify({status:process.exitCode?'FAIL':'PASS',checks,errors,unknown,limitations:['Compiled Vue; synthetic APIs; no real PG/model/mail/phone']},null,2))
 try{if(ws?.readyState===1){await send('Browser.close');ws.close()}}catch{}edge.kill();server.close()
}
