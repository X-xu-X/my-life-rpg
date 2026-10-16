// Real compiled Vue, isolated headless Edge, synthetic API only. No DB or supplier.
import fs from 'node:fs'
import path from 'node:path'
import http from 'node:http'
import {spawn} from 'node:child_process'
import crypto from 'node:crypto'
const root='docs/review/trial_p1_2026-10-16';fs.mkdirSync(root,{recursive:true})
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
 if(route==='/auth/me')body=account
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
 check('five navigation sections',await evaluate(`document.querySelectorAll('.mobile-nav a').length===5`))
 for(const width of [360,390,768,1440]){
  await send('Emulation.setDeviceMetricsOverride',{width,height:width<500?844:1000,deviceScaleFactor:1,mobile:false})
  for(const route of ['/','/plans','/settings','/growth','/challenges']){await go(route);check(`layout ${width} ${route}`,await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`));if(width===390||width===1440)await shot((route==='/'?'today':route.slice(1))+'-'+width)}
 }
 await go('/growth');check('neutral values never labelled proficient',await evaluate(`!document.querySelector('.growth-layout').innerText.includes('熟练')&&document.body.innerText.includes('未评估基线')`))
 await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});await evaluate(`(()=>{const e=document.querySelector('.radar-details');if(!e.open)e.querySelector('summary').click();e.scrollIntoView({block:'start'})})()`);await pause(400);await shot('radar-390')
 await go('/me');await go('/settings');await evaluate(`document.querySelector('.page-back').click()`);await pause(200);check('back preserves account and valid source',await evaluate(`location.hash==='#/me'&&!!document.querySelector('.app-shell')`))
 await go('/settings');await fill('#primary-model','wrong-fixture-model');check('unsaved test disabled',await evaluate(`document.querySelectorAll('.model-group')[0].querySelectorAll('button')[1].disabled`))
 await click('保存判定模型');check('save has no supplier request',testCalls===0);await click('测试已保存配置（可能计费）');await wait(`document.querySelector('[data-model-state=primary]').innerText.includes('测试失败')`);check('failure shown nearby',await evaluate(`document.querySelector('.model-group').innerText.includes('MODEL_NOT_FOUND')`));await shot('model-failure')
 await fill('#primary-model','edited-after-failure');check('edited config not marked verified',await evaluate(`document.querySelector('[data-model-state=primary]').innerText.includes('未保存')`))
 await click('保存判定模型');testDelay=450;await click('测试已保存配置（可能计费）');await fill('#primary-model','edit-during-test');await pause(600);check('late test result invalid for edited input',await evaluate(`document.querySelector('[data-model-state=primary]').innerText.includes('未保存')`))
 models.primary.configured=false;models.primary.enabled=false;models.aux.configured=false
 await go('/');await fill('#new-record','只保存合成事件');await click('保存记录');check('no-key recording stays independent',saveCalls===1)
 jobMode=true;jobReads=0;await go('/events/301');await wait(`document.body.innerText.includes('建议已就绪')`);const terminalReads=jobReads;await pause(3000);check('terminal job stops polling',jobReads===terminalReads);check('later analysis overrides original never label',await evaluate(`!document.body.innerText.includes('选择了不分析')&&document.body.innerText.includes('fixture-chat')`));await shot('event-ready')
 jobReads=0;await go('/me');await go('/events/301');await go('/journal');const leavingReads=jobReads;await pause(2800);check('leaving stops old job polling',jobReads===leavingReads)
 await go('/challenges');await click('商店');await click('兑换');await wait(`!!document.querySelector('dialog[open]')`);check('native modal receives focus',await evaluate(`document.querySelector('dialog').contains(document.activeElement)`));await shot('redeem-modal')
 await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});await shot('redeem-modal-390')
 for(let i=0;i<5;i++){await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9})}
 check('keyboard tab stays within modal',await evaluate(`document.querySelector('dialog').contains(document.activeElement)`))
 await click('取消');check('cancel has no financial effect',redeemCalls===0);check('focus returns to trigger',await evaluate(`document.activeElement.textContent.trim()==='兑换'`))
 await click('兑换');await evaluate(`(()=>{const b=document.querySelector('dialog button.primary');b.click();b.click()})()`);await wait(`!document.querySelector('dialog[open]')`);check('double click produces one confirmed financial request',redeemCalls===1)
 await go('/settings');await evaluate(`(()=>{const sizes=[...document.querySelectorAll('body *')].map(e=>[e,parseFloat(getComputedStyle(e).fontSize)]);for(const [e,size] of sizes)e.style.fontSize=(size*2)+'px'})()`);check('200 percent text remains within viewport',await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`));await shot('settings-200-percent')
 check('no unexpected API',unknown.length===0);check('no Vue runtime errors',errors.length===0)
 console.log(JSON.stringify({status:'PASS',checks:checks.length,source:'compiled Vue, API mocks',limitations:['No real phone/model/PG/concurrency/deployment']}))
}catch(error){errors.push(String(error));console.error(error);process.exitCode=1}
finally{
 const buildHashes=Object.fromEntries(fs.readdirSync('frontend/dist',{recursive:true}).map(name=>path.join('frontend/dist',name)).filter(name=>fs.statSync(name).isFile()).map(name=>[name,crypto.createHash('sha256').update(fs.readFileSync(name)).digest('hex')]))
 fs.writeFileSync(`${root}/browser-results.json`,JSON.stringify({status:process.exitCode?'FAIL':'PASS',checks,errors,unknown,buildHashes,limitations:['Desktop Edge emulated widths; synthetic APIs only']},null,2))
 try{if(ws?.readyState===1){await send('Browser.close');ws.close()}}catch{}edge.kill();server.close()
}
