// Real Edge DOM/layout checks; every API request is fulfilled locally by CDP.
import fs from 'node:fs'
import crypto from 'node:crypto'
const root='docs/review/ui_polish_2026-10-10'
const phase=process.env.UI_PHASE || 'after'
fs.mkdirSync(`${root}/${phase}`,{recursive:true})
const names=['体能','力量','敏捷','智力','专注','意志','情绪','表达','社交','创造','审美','生活','财富']
const content=('今天在河边走了一会儿，整理了一个一直没学懂的问题，也给自己留了一点休息的时间。\n').repeat(500).slice(0,20000)
const records=[{id:101,title:'今天在河边走了三公里，最后一段放慢脚步，重新理解一个一直没有想明白的问题。'.repeat(4),content,occurred_at:'2026-10-10T10:30:00Z',created_at:'2026-10-10T10:31:00Z',content_version:1,analysis_intent:'later',is_pure:false,origin:'journal'}, {id:102,title:'一段没有空格的链接',content:'https://example.invalid/'+('abcdefghijklmnop'.repeat(100)),occurred_at:'2026-10-10T09:00:00Z',created_at:'2026-10-10T09:01:00Z',content_version:1,analysis_intent:'never',is_pure:false,origin:'journal'}]
const attributes=names.map((name,i)=>({id:i+1,name,value:50+i/10,max_value:100,visibility:i===2?'disabled':'show',tier:'起步',description:'游戏分数用于记录积累，不是精确的能力测量。'+name+'的真实说明仍可查看。'}))
const fixture={clock:'2026-10-10T12:00:00+08:00',records,attributes,history:names.flatMap((name,i)=>[0,1,2].map(n=>({name,value_after:48+i/10+n,created_at:`2026-10-0${7+n}T10:00:00Z` }))),heatmap:[{date:'2026-10-09',count:1},{date:'2026-10-10',count:6}]}
fs.writeFileSync(`${root}/fixtures.json`,JSON.stringify(fixture,null,2))
const sourceFiles=['frontend/index.html','frontend/src/App.vue','frontend/src/styles.css','frontend/src/ui-layout.css','frontend/src/design-tokens.css',...fs.readdirSync('frontend/src/components',{recursive:true}).filter(f=>f.endsWith('.vue')).map(f=>'frontend/src/components/'+f)].filter(f=>fs.existsSync(f))
const sourceHashes=Object.fromEntries(sourceFiles.map(f=>[f,crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex')]))
const targets=await(await fetch('http://127.0.0.1:19224/json/list')).json()
const ws=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl)
await new Promise(resolve=>ws.addEventListener('open',resolve,{once:true}))
let sequence=0;const pending=new Map(),requests=[],unknown=[],runtime=[]
let readMode='normal',auth=true,authDelay=0,saveMode='normal',saved=null,reviewVersion=1,judgmentMode='none',jobState=''
const saves=[]
function send(method,params={}){return new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))})}
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms))
async function respond(p){
 const u=new URL(p.request.url),path=u.pathname.replace(/^\/api/,''),method=p.request.method
 requests.push({path:u.pathname+u.search,method}) // Never capture bodies or input credentials.
 let code=200,body,delay=0
 if(method==='GET'&&['/events','/pending','/attributes','/attributes/history','/events/heatmap'].includes(path)){
  if(readMode==='slow')delay=1000
  if(readMode==='fail'){code=500;body={detail:'虚构读取失败，请重试'}}
 }
 if(body===undefined){
 const account={id:99001,username:'ui_fixture',timezone:'Asia/Shanghai',mode:'cloud',onboarding_completed:true,baseline_kind:'neutral'}
 if(path==='/auth/me'){body=auth?account:{detail:'请登录'};if(!auth)code=401}
 else if(path.startsWith('/auth/')){delay=authDelay;body=path==='/auth/login'?account:{recovery_code:'UI-FIXTURE-RECOVERY-ONLY'};auth=true}
 else if(path==='/events'&&method==='GET')body=u.searchParams.has('cursor')?[]:readMode==='empty'?[]:records
 else if(path==='/events'&&method==='POST'){
  saved={...records[0],...JSON.parse(p.request.postData),id:103};body=saved
  saves.push({key:saved.client_request_id,contentLength:saved.content.length,payloadHash:crypto.createHash('sha256').update(p.request.postData).digest('hex'),intent:saved.intent})
  if(saveMode==='lost'){await send('Fetch.failRequest',{requestId:p.requestId,errorReason:'ConnectionReset'});return}
 }
 else if(path.startsWith('/event-submissions/')){body=saved || {detail:'未找到'};if(!saved)code=404}
 else if(/^\/events\/\d+\/analysis-jobs$/.test(path)){code=500;body={detail:'虚构分析不可用，原文已经保存'}}
 else if(/^\/events\/\d+$/.test(path))body={...records[0],id:Number(path.split('/').at(-1)),origin:judgmentMode==='challenge'?'challenge':'journal',analysis_intent:judgmentMode==='never'?'never':'later'}
 else if(path==='/pending')body={items:readMode==='empty'?[]:[{event_id:101,title:records[0].title,content,state:jobState || 'saved',...(jobState?{job:{id:601,state:jobState,result:{questions:['请补充虚构细节']},safe_error_code:jobState==='failed'?'UI_FICTION_FAILURE':null}}:{})}]}
 else if(path==='/attributes')body={attributes:readMode==='empty'?[]:attributes,level:2,exp:64,onboarding_completed:true,baseline_kind:'neutral'}
 else if(path==='/attributes/history')body=readMode==='empty'?[]:fixture.history
 else if(path==='/events/heatmap')body=readMode==='empty'?[]:fixture.heatmap
 else if(path==='/subdimensions')body={threshold:95,candidates:[],hierarchy:{}}
 else if(path==='/judgments')body=['confirmed','low','ready'].includes(judgmentMode)?[{id:501,event_id:101,status:judgmentMode==='confirmed'?'confirmed':'pending',confidence:judgmentMode==='low'?0.6:0.9,summary:'虚构分析建议',analysis:['虚构依据'],suggested_changes:[{name:'体能',delta:0.2,reason:'散步'}],final_changes:[],updated_at:'2026-10-10T11:00:00Z'}]:[]
 else if(path==='/daily-reviews')body={items:[]}
 else if(path.startsWith('/daily-reviews/')){if(method==='PUT'){code=409;reviewVersion=2;body={detail:'回顾版本冲突'}}else body={version:reviewVersion,date:'2026-10-10',timezone:'Asia/Shanghai',note:reviewVersion===1?'':'服务器的长回顾。'.repeat(400),events:records,judgments:[]}}
 else if(path==='/settings')body={hidden_attributes:[],disabled_attributes:[],gamification_modules:{}}
 else if(path==='/llm-config')body={primary:{enabled:false,configured:false,model:'',provider_id:'deepseek'},aux:{enabled:false,configured:false,model:'',provider_id:'deepseek'},env_fallback:{ready:false},providers:{deepseek:'https://api.deepseek.com',openai:'https://api.openai.com',siliconflow:'https://api.siliconflow.cn'}}
 else if(path==='/onboarding/status')body={onboarding_completed:true,in_progress:false}
 else if(path==='/reports')body={items:[]}
 else if(['/items','/items/stats','/goals','/anchors','/redemptions'].includes(path))body=[]
 else if(path==='/coins')body={balance:80,ledger:[]}
 else if(path==='/challenges/current')body={daily:[],weekly:[]}
 else if(path==='/shop/items'||path==='/exemptions'||path==='/stagnation')body={items:[],balance:80,presets:[]}
 else if(path==='/achievements/check')body={granted:[]}
 else if(path==='/achievements')body={items:[],achievements:[]}
 else {unknown.push({path,method});code=599;body={detail:'Unknown mock API'}}
 }
 if(delay)await pause(delay)
 await send('Fetch.fulfillRequest',{requestId:p.requestId,responseCode:code,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from(JSON.stringify(body)).toString('base64')})
}
ws.addEventListener('message',e=>{const r=JSON.parse(e.data);if(r.id){const p=pending.get(r.id);pending.delete(r.id);r.error?p.reject(r.error):p.resolve(r.result)}else if(r.method==='Fetch.requestPaused')respond(r.params).catch(e=>runtime.push(String(e)));else if(r.method==='Runtime.exceptionThrown')runtime.push(r.params.exceptionDetails.text)})
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value}
async function wait(expression){for(let n=0;n<80;n++){if(await evaluate(expression))return;await pause(100)}throw Error('Wait: '+expression)}
async function size(width,height=width===390?844:width===360?800:1000){await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await pause(180)}
async function go(path){await evaluate(`location.hash=${JSON.stringify(path)}`);await pause(path==='/growth'?700:250)}
async function click(text){const result=await evaluate(`(()=>{const b=[...document.querySelectorAll('button,summary')].find(b=>b.textContent.trim()===${JSON.stringify(text)});if(!b)return false;b.click();return true})()`);if(!result)throw Error('Button: '+text);await pause(100)}
async function fill(selector,value){await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!e)throw Error('Missing field');e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}))})()`)}
async function shot(name){const s=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(`${root}/${phase}/${name}.png`,Buffer.from(s.data,'base64'))}
const checks=[],measurements=[],contrast=[]
function check(name,ok,details){checks.push({name,status:ok?'PASS':'FAIL',details});if(!ok)console.error('FAIL '+name,details)}
await send('Page.enable');await send('Runtime.enable');await send('Fetch.enable',{patterns:[{urlPattern:'*/api/*'}]})
await send('Page.addScriptToEvaluateOnNewDocument',{source:`const NativeDate=Date;window.Date=class extends NativeDate{constructor(...a){super(...(a.length?a:['2026-10-10T12:00:00+08:00']))}static now(){return new NativeDate('2026-10-10T12:00:00+08:00').valueOf()}};window.confirm=()=>true;localStorage.clear()`})
await size(390)
await send('Page.navigate',{url:'http://127.0.0.1:15173'})
await wait(`document.querySelector('#new-record')`)
const routes=['/','/journal','/events/101','/growth','/reports','/me','/checkin','/pending','/judgments','/review','/challenges','/onboarding','/anchors','/settings']
for(const width of phase==='before'?[390,1440]:[360,390,768,1024,1440]){
 await size(width)
 for(const path of phase==='before'?['/','/journal','/growth','/settings']:routes){
  await go(path)
  const m=await evaluate(`(()=>{const rect=s=>{const e=document.querySelector(s);if(!e)return null;const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom}};return {width:innerWidth,scrollWidth:document.documentElement.scrollWidth,firstRecord:rect('.event-row'),save:rect('.record-composer .primary'),links:rect('.today-links'),nav:rect('.mobile-nav'),radar:rect('[data-chart=radar]'),growth:rect('[data-chart=growth]'),heatmap:rect('[data-chart=heatmap]')}})()`)
  measurements.push({path,...m});check(`layout ${width} ${path}`,m.scrollWidth<=width+1,m)
  if(phase==='after'&&width===390&&path==='/journal')check('U01 first preview height',m.firstRecord.height<=220,m.firstRecord)
  if(phase==='after'&&width===390&&path==='/')check('U05 default save and both links above nav',m.save.bottom<m.nav.y&&m.links.bottom<m.nav.y,{save:m.save,links:m.links,nav:m.nav})
  if(width===390||width===1440)await shot(`${path==='/'?'today':path.replaceAll('/','_').slice(1)}-${width}`)
 }
}
if(phase==='after'){
 const key=async(value,shift=false)=>{await send('Input.dispatchKeyEvent',{type:'keyDown',key:value,code:value,modifiers:shift?8:0});await send('Input.dispatchKeyEvent',{type:'keyUp',key:value,code:value,modifiers:shift?8:0});await pause(100)}
 // V01: DOM node identity, draft values and provider survive directory, folding and resize.
 await size(390);await go('/settings')
 await fill('#primary-model','ui-fiction-model');await fill('#settings-models select','openai');await fill('#primary-key','UI-PLACEHOLDER-NOT-A-KEY')
 await evaluate(`window.uiModelNode=document.querySelector('#primary-model')`)
 const startWrites=requests.filter(r=>r.method!=='GET').length
 for(const label of ['数据导出','打卡项目','属性维度','旧扩展开关','成长报告','AI 模型'])await click(label)
 await click('判定模型组 · 未绑定 · 已停用');await click('判定模型组 · 未绑定 · 已停用')
 for(const w of [1024,390])await size(w)
 const kept=await evaluate(`({same:window.uiModelNode===document.querySelector('#primary-model'),model:document.querySelector('#primary-model').value,provider:document.querySelector('#settings-models select').value,key:document.querySelector('#primary-key').value==='UI-PLACEHOLDER-NOT-A-KEY',stored:Object.values(localStorage).some(v=>v.includes('UI-PLACEHOLDER-NOT-A-KEY')),hash:location.hash,focus:document.activeElement.tagName})`)
 check('V01 settings identity and private draft',kept.same&&kept.model==='ui-fiction-model'&&kept.provider==='openai'&&kept.key&&!kept.stored&&kept.hash==='#/settings'&&startWrites===requests.filter(r=>r.method!=='GET').length,kept)
 await fill('#primary-key','');await shot('settings-model-390')
 // V02/V03 first reads, refresh failures, successful retry and true empty state.
 for(const path of ['/','/journal','/pending','/growth']){
  await go('/me');readMode='slow';await go(path)
  const slow=await evaluate(`({text:document.body.innerText,composer:!!document.querySelector('#new-record')})`)
  check('V02 slow '+path,slow.text.includes('正在读取')&&!/这里还没有记录|暂时没有待处理|尚未评估|暂无属性|今天还没有记录/.test(slow.text))
  await pause(1100);readMode='normal'
  readMode='fail'
  if(path==='/pending')await pause(5200)
  else if(path==='/journal')await evaluate(`document.querySelector('.record-search').requestSubmit()`)
  else await click('重新读取')
  await pause(150)
  check('V03 stale data '+path,await evaluate(`document.body.innerText.includes('本次未刷新成功') && !document.querySelector('.empty-note')`))
  readMode='normal';await click('重新读取');await pause(200)
  check('V03 retry '+path,await evaluate(`!document.querySelector('.read-error')`))
  await go('/me');readMode='fail';await go(path)
  check('V03 initial failure '+path,await evaluate(`!!document.querySelector('.read-error') && !document.querySelector('.empty-note') && !document.body.innerText.includes('尚未评估')`))
  readMode='empty';await click('重新读取');await pause(180)
  check('V03 true empty '+path,await evaluate(`!document.querySelector('.read-error') && !!document.querySelector(${JSON.stringify(path==='/growth'?'.attr-bar':'.empty-note')})===${path==='/growth'?'false':'true'}`))
  readMode='normal'
 }
 // V04 real Tab/Shift+Tab, Enter and existing pure filter query contract.
 for(const width of [360,390,1440]){
  await size(width);await go('/journal');await evaluate(`document.querySelector('.record-search input').focus()`)
  await key('Tab');const next=await evaluate(`document.activeElement.textContent.trim()`)
  await key('Tab');const filterFocused=await evaluate(`document.activeElement.tagName==='SELECT'`)
  await key('Tab',true);const back=await evaluate(`document.activeElement.textContent.trim()`)
  await fill('.record-search input','河边');await evaluate(`document.querySelector('.record-search input').focus()`);await key('Enter')
  await fill('.record-search select','pure')
  check('V04 search keyboard '+width,next==='搜索'&&back==='搜索'&&filterFocused&&!await evaluate(`!!document.querySelector('[tabindex="1"]')`))
  check('V04 pure query '+width,requests.some(r=>r.path.includes('q=%E6%B2%B3%E8%BE%B9')&&r.path.includes('pure=true')))
 }
 await click('继续回看');await pause(150);check('pagination empty batch',await evaluate(`document.body.innerText.includes('已经回看到这里')`));await fill('.record-search input','新查询');await evaluate(`document.querySelector('.record-search input').focus()`);await key('Enter');check('pagination reset',await evaluate(`[...document.querySelectorAll('button')].some(b=>b.textContent.trim()==='继续回看')`))
 // V05 container dimensions and one retained selection/manual radar choice across boundaries.
 await size(390);await go('/growth')
 check('V05 collapsed radar has no instance',await evaluate(`!document.querySelector('[data-chart=radar]').getAttribute('_echarts_instance_')`))
 await fill('.trend-mobile select',names[4]);await click('能力雷达图');await pause(300)
 for(const width of [759,760,1023,1024,1200,1440,390]){
  await size(width);await pause(150)
  const m=await evaluate(`(()=>{const l=document.querySelector('.growth-layout'),r=document.querySelector('[data-chart=radar]');return {width:innerWidth,available:l.clientWidth,columns:getComputedStyle(l).gridTemplateColumns,wide:l.classList.contains('growth-wide'),open:document.querySelector('.radar-details').open,radarWidth:r.clientWidth,canvases:r.querySelectorAll('canvas').length,dimension:document.querySelector('.trend-mobile select').value,overflow:document.documentElement.scrollWidth>innerWidth}})()`)
  check('V05 chart boundary '+width,m.open&&m.radarWidth>0&&m.canvases===1&&m.dimension===names[4]&&!m.overflow&&m.wide===(m.available>=860),m)
  if(width===390){await evaluate(`document.querySelector('.radar-details').scrollIntoView()`);await shot('growth-radar-open-390')}
 }
 await click('能力雷达图');await size(1440);check('V05 manual close retained',await evaluate(`!document.querySelector('.radar-details').open`))
 // V06 response lost: double submit protects original input; receipt recovers same operation.
 await size(390);await go('/');await fill('#new-record','UI 结果不明保护原文');saveMode='lost'
 await evaluate(`document.querySelector('.record-composer').requestSubmit();document.querySelector('.record-composer').requestSubmit()`);await pause(300)
 check('V06 unknown preserves input',await evaluate(`document.querySelector('#new-record').disabled && document.querySelector('#new-record').value==='UI 结果不明保护原文' && document.body.innerText.includes('查询并重试本次保存')`))
 await shot('today-uncertain-390');const posts=saves.length;saveMode='normal';await click('查询并重试本次保存');await pause(250)
 check('V06 receipt no duplicate',saves.length===posts&&posts===1&&await evaluate(`!document.querySelector('#new-record').value && document.body.innerText.includes('查看这条记录')`),{posts,uniqueKeys:new Set(saves.map(r=>r.key)).size})
 await fill('#new-record','UI now 分析失败');await fill('.composer-analysis select','now');await click('保存记录');await pause(300)
 check('V06 saved original versus analysis failure',await evaluate(`document.body.innerText.includes('记录已保存，分析未完成') && !!document.querySelector('a[href="#/events/103"]')`))
 // Time and intent stay in the existing account draft on route changes.
 await fill('#new-record','UI 补记草稿');await click('修改时间');await fill('input[type=datetime-local]','2026-10-09T18:30');await fill('.composer-analysis select','never');await go('/me');await go('/')
 check('V06 time draft restored',await evaluate(`document.querySelector('input[type=datetime-local]').value==='2026-10-09T18:30' && document.querySelector('.composer-analysis select').value==='never'`))
 await click('使用现在');check('V06 use now clears time',await evaluate(`!document.querySelector('input[type=datetime-local]') && document.body.innerText.includes('发生时间：现在')`))
 // V07 conflict shows full server note and keeps long local input, blocking completion.
 await go('/review');const myNote='我的长回顾。'.repeat(500);await fill('textarea',myNote);await click('结束回顾');await pause(250)
 const conflict=await evaluate(`({note:document.querySelector('textarea').value.length,server:document.querySelector('.review-conflict .original-text')?.textContent.length,disabled:[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='结束回顾').disabled})`)
 check('V07 full conflict comparison',conflict.note===myNote.length&&conflict.server==='服务器的长回顾。'.repeat(400).length&&conflict.disabled,conflict);await shot('review-conflict-390')
 await click('比较后提交我的输入');check('V07 explicit conflict choice',await evaluate(`!document.querySelector('.review-conflict') && document.querySelector('textarea').value.length===${myNote.length}`))
 // V09 rendering only: keep original restrictions and fees, without performing writes.
 for(const state of ['confirmed','low','challenge','never','ready','none']){
  judgmentMode=state;await go('/me');await go('/events/101')
  const m=await evaluate(`({full:document.querySelector('.original-text')?.textContent.length,edit:[...document.querySelectorAll('button')].some(b=>b.textContent.trim()==='编辑原文'),confirm:[...document.querySelectorAll('button')].filter(b=>/确认入账|需补充信息后确认/.test(b.textContent)).map(b=>({disabled:b.disabled,label:b.textContent.trim()})),text:document.body.innerText})`)
  check('V09 restriction '+state,m.full===content.length&&(state==='confirmed'?!m.edit&&m.confirm.length===0:state==='low'?m.confirm[0]?.disabled:state==='challenge'?!m.edit&&m.text.includes('挑战记录请前往挑战页处理'):state==='never'?m.text.includes('这条记录选择了不分析'):state==='none'?m.text.includes('费用由你的供应商账户承担'):!!m.confirm.length))
  if(['confirmed','ready'].includes(state))await shot('detail-'+state+'-390')
 }
 judgmentMode='none'
 for(const state of ['queued','running','needs_input','failed','cancelled','superseded','ready']){
  jobState=state;await go('/me');const writes=requests.filter(r=>r.method!=='GET').length;await go('/events/101')
  const m=await evaluate(`({text:document.body.innerText,buttons:[...document.querySelectorAll('.analysis-detail button')].map(b=>({label:b.textContent.trim(),disabled:b.disabled,primary:b.classList.contains('primary')}))})`)
  check('V09 task state '+state,!m.text.includes('undefined')&&writes===requests.filter(r=>r.method!=='GET').length&&(['queued','running'].includes(state)?m.buttons.some(b=>b.label==='现在分析'&&b.disabled)&&m.buttons.some(b=>b.label==='取消分析'):state==='needs_input'?m.buttons.some(b=>b.label==='提交补充'&&b.primary):m.text.includes('分析状态')),m.buttons)
 }
 jobState=''
 // V10 text-only 200% scaling; naturally tall content remains scrollable.
 await go('/journal');await evaluate(`window.uiTextSizes=[...document.querySelectorAll('body *:not(svg):not(path):not(canvas)')].map(e=>[e,e.style.fontSize,parseFloat(getComputedStyle(e).fontSize)*2]);uiTextSizes.forEach(([e,old,size])=>e.style.fontSize=size+'px')`)
 const zoom=await evaluate(`({overflow:document.documentElement.scrollWidth>innerWidth,link:!!document.querySelector('a[href="#/events/101"]')})`);check('V10 text 200 percent',!zoom.overflow&&zoom.link,zoom);await shot('journal-text-200');await evaluate(`uiTextSizes.forEach(([e,old])=>e.style.fontSize=old)`)
 // V11 real route selected state, original Chinese brand and new English title.
 await go('/growth');check('V11 brand and nav',await evaluate(`document.title==='游戏人生 · LifeXP' && [...document.querySelectorAll('nav[aria-label="主要导航"]')].every(n=>n.querySelector('a.selected[aria-current="page"]')?.textContent.trim()==='成长') && document.querySelector('.mobile-heading').textContent.includes('游戏人生')`))
 // U04 sample actual rendered text/background pairs, including hover/selection/focus.
 const contrastSample=async(label,selector)=>{
  const c=await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});const s=getComputedStyle(e);let bg=e;while(bg&&getComputedStyle(bg).backgroundColor==='rgba(0, 0, 0, 0)')bg=bg.parentElement;return {color:s.color,background:getComputedStyle(bg||document.body).backgroundColor,outline:s.outlineColor,outlineWidth:s.outlineWidth}})()`)
  const rgb=s=>s.match(/[\d.]+/g).slice(0,3).map(Number)
  const lum=a=>a.map(v=>v/255).map(v=>v<=0.04045?v/12.92:((v+0.055)/1.055)**2.4).reduce((s,v,i)=>s+v*[0.2126,0.7152,0.0722][i],0)
  const a=lum(rgb(c.color)),b=lum(rgb(c.background)),ratio=(Math.max(a,b)+0.05)/(Math.min(a,b)+0.05)
  contrast.push({label,selector,...c,ratio});check('U04 contrast '+label,ratio>=4.5,{ratio,...c})
 }
 await go('/journal');await contrastSample('body secondary','.page-intro .muted');await contrastSample('selected nav','.mobile-nav a.selected');await contrastSample('preview link','.preview-link');await contrastSample('normal search','.record-search button')
 await evaluate(`document.querySelector('.record-search input').focus()`);const f=await evaluate(`getComputedStyle(document.activeElement).outlineWidth`);check('U04 input focus visible',f==='3px');await shot('focus-form-390')
 await go('/');await fill('#new-record','虚构焦点样本');await contrastSample('primary save','.record-composer .primary')
 const position=await evaluate(`(()=>{const r=document.querySelector('.record-composer .primary').getBoundingClientRect();return {x:r.x+5,y:r.y+5}})()`);await send('Input.dispatchMouseEvent',{type:'mouseMoved',...position});await pause(200);await contrastSample('primary hover','.record-composer .primary')
 await go('/settings');await contrastSample('warning','.settings-section > p[style]')
 await go('/journal');await evaluate(`scrollTo(0,document.documentElement.scrollHeight)`)
 check('U07 last control above nav',await evaluate(`[...document.querySelectorAll('main button')].at(-1).getBoundingClientRect().bottom<=document.querySelector('.mobile-nav').getBoundingClientRect().top`))
 // V08 isolated auth branches, pending mode controls and explicit recovery acknowledgement.
 auth=false;await send('Page.reload');await wait(`document.querySelector('input[autocomplete=username]')`)
 for(const mode of ['login','register','recover']){
  if(mode==='register')await click('使用邀请加入');if(mode==='recover')await click('忘记密码')
  check('V08 one primary '+mode,await evaluate(`document.querySelectorAll('form > button.primary').length===1 && document.querySelectorAll('.auth-switch button').length===2`))
  if(mode!=='recover')await fill('input[autocomplete=username]','ui_fixture_user')
  if(mode==='register')await fill('input[autocomplete=off]','UI-FICTION-INVITE')
  if(mode==='recover')await fill('input[autocomplete=off]','UI-FICTION-RECOVERY')
  await fill('input[type=password]','fictional-password-only');authDelay=650
  await evaluate(`document.querySelector('form').requestSubmit()`);await pause(150)
  check('V08 busy prevents switching '+mode,await evaluate(`[...document.querySelectorAll('.auth-switch button')].every(b=>b.disabled)`))
  await pause(700)
  if(mode==='login'){auth=false;await send('Page.reload');await wait(`document.querySelector('input[autocomplete=username]')`)}
  else{check('V08 recovery explicit '+mode,await evaluate(`document.body.innerText.includes('我已保存恢复码') && !document.querySelector('.app-shell')`));await shot('auth-'+mode+'-recovery');await click('我已保存恢复码');auth=false;await send('Page.reload');await wait(`document.querySelector('input[autocomplete=username]')`)}
 }
 await shot('auth-login-390')
}
fs.writeFileSync(`${root}/${phase}/measurements.json`,JSON.stringify(measurements,null,2))
fs.writeFileSync(`${root}/${phase}/contrast-checks.json`,JSON.stringify(contrast,null,2))
fs.writeFileSync(`${root}/${phase}/checks.json`,JSON.stringify({phase,tested_at:new Date().toISOString(),browser:await send('Browser.getVersion'),sourceHashes,checks,requests,unknown,runtime,saves,limitations:['Desktop Edge simulated viewports; no physical phone or screen reader','All APIs mocked; no database, model, financial or deployment proof']},null,2))
console.log(JSON.stringify({phase,layouts:measurements.length,failed:checks.filter(c=>c.status==='FAIL').length,unknown,runtime}))
await send('Browser.close');ws.close()
if(unknown.length||runtime.length||checks.some(c=>c.status==='FAIL'))process.exitCode=1
