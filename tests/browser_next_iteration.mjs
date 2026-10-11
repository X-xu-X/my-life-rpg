// 独立 HTTPS 合成库 + Edge CDP 验收；不得连接生产站点。
import fs from 'node:fs'
const base=process.env.QA_ORIGIN || 'https://localhost:18443'
if(!/^https:\/\/(localhost|127\.0\.0\.1):\d+$/.test(base))throw Error('仅限本机测试站')
const state=JSON.parse(fs.readFileSync(process.env.QA_STATE || '_tmp_browser_state.json','utf8'))
let targets
for(let attempt=0;attempt<40;attempt++){
 try{targets=await(await fetch('http://127.0.0.1:19223/json/list')).json();if(targets.some(t=>t.type==='page'))break}catch{}
 await new Promise(resolve=>setTimeout(resolve,100))
}
if(!targets?.some(t=>t.type==='page'))throw Error('隔离 Edge 调试端口未就绪')
const ws=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl)
await new Promise(resolve=>ws.addEventListener('open',resolve,{once:true}))
let sequence=0;const pending=new Map()
ws.addEventListener('message',e=>{const r=JSON.parse(e.data);if(r.id){const p=pending.get(r.id);pending.delete(r.id);r.error?p.reject(r.error):p.resolve(r.result)}})
function send(method,params={}){return new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))})}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value}
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms))
async function wait(expression){for(let n=0;n<60;n++){if(await evaluate(expression))return;await pause(100)}throw Error('等待失败: '+expression)}
async function fill(selector,value){await evaluate(`(()=>{const input=document.querySelector(${JSON.stringify(selector)});input.value=${JSON.stringify(value)};input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}))})()`)}
async function click(text){const ok=await evaluate(`(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)});if(!b)return false;b.click();return true})()`);if(!ok)throw Error('按钮不存在: '+text)}
await send('Page.enable');await send('Runtime.enable')
await send('Network.clearBrowserCookies')
await send('Page.addScriptToEvaluateOnNewDocument',{source:`window.qaErrors=[];window.addEventListener('error',e=>qaErrors.push(e.message));window.addEventListener('unhandledrejection',e=>qaErrors.push(String(e.reason)));window.confirm=()=>true`})
await send('Emulation.setDeviceMetricsOverride',{width:360,height:800,deviceScaleFactor:1,mobile:true})
await send('Page.navigate',{url:base+'/?invite='+encodeURIComponent(state.invite)})
await wait(`document.querySelector('input[autocomplete=username]')`)
await fill('input[autocomplete=username]',state.username || 'qa_friend')
await fill('input[type=password]','qa-friend-password')
await evaluate(`document.querySelector('form').requestSubmit()`)
await wait(`document.body.innerText.includes('我已保存恢复码')`)
await click('我已保存恢复码')
await wait(`document.querySelector('#new-record')`)
const longText='手机原文验收。'.repeat(3000).slice(0,20000)
await fill('#new-record',longText)
await evaluate(`document.querySelector('form').requestSubmit();document.querySelector('form').requestSubmit()`)
await wait(`document.body.innerText.includes('查看这条记录')`)
const facts=await evaluate(`fetch('/api/events').then(r=>r.json())`)
if(facts.length!==1||facts[0].content.length!==longText.length)throw Error('长文保存或防重复失败')
const coin=await evaluate(`fetch('/api/coins').then(r=>r.json())`)
if(coin.balance!==0)throw Error('未建档意外发币')
await evaluate(`location.hash='/me'`);await wait(`document.body.innerText.includes('用未评估基线开始')`)
await click('用未评估基线开始')
await wait(`document.body.innerText.includes('已按未评估基线开始')`)
const after=await evaluate(`fetch('/api/coins').then(r=>r.json())`)
if(after.balance!==80)throw Error('未评估基线资金错误')
const results=[]
fs.mkdirSync('_shots',{recursive:true})
for(const width of [360,390,1360]){
 await send('Emulation.setDeviceMetricsOverride',{width,height:width>500?1000:800,deviceScaleFactor:1,mobile:width<500})
 for(const path of ['/','/journal','/events/'+facts[0].id,'/review','/pending','/growth','/reports','/me','/settings','/checkin','/anchors','/onboarding','/challenges']){
  await evaluate(`location.hash=${JSON.stringify(path)}`);await pause(path==='/growth'?1300:500)
  const metric=await evaluate(`({width:innerWidth,scroll:document.documentElement.scrollWidth,nav:[...document.querySelectorAll('.mobile-nav a')].map(a=>a.textContent.trim()),errors:window.qaErrors,alerts:[...document.querySelectorAll('[role=alert]')].map(e=>e.textContent)})`)
  if(metric.scroll>metric.width+1)throw Error('横向溢出 '+width+' '+path+' '+JSON.stringify(metric))
  if(metric.errors.length)throw Error(JSON.stringify(metric.errors))
  results.push({width,path,...metric})
  if(width===390&&['/','/journal','/me'].includes(path)){
   const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false})
   fs.writeFileSync('_shots/next_'+(path==='/'?'today':path.slice(1))+'.png',Buffer.from(shot.data,'base64'))
  }
 }
}
await evaluate(`location.hash='/'`);await wait(`document.querySelector('#new-record')`)
await fill('#new-record','账号 A 未提交的草稿')
await pause(100)
await evaluate(`location.hash='/me'`);await wait(`document.body.innerText.includes('退出登录')`)
await click('退出登录');await wait(`document.querySelector('input[autocomplete=username]')`)
await fill('input[autocomplete=username]','qa_owner');await fill('input[type=password]','qa-browser-password')
await evaluate(`document.querySelector('form').requestSubmit()`)
await wait(`document.querySelector('.app-shell')`)
await evaluate(`location.hash='/'`);await wait(`document.querySelector('#new-record')`)
if(await evaluate(`document.querySelector('#new-record').value`))throw Error('跨账号草稿泄漏')
if((await evaluate(`fetch('/api/events').then(r=>r.json())`)).length)throw Error('跨账号原文泄漏')
fs.writeFileSync(process.env.QA_EVIDENCE || 'docs/review/NEXT_BROWSER_EVIDENCE.json',JSON.stringify({origin:'本机隔离 HTTPS PostgreSQL 合成库',
    tested_at:new Date().toISOString(),
    longTextLength:longText.length,oneSavedEvent:true,baselineCoins:80,accountIsolation:true,
    limitations:['浏览器模拟尺寸，未验证手机真机键盘或蜂窝网络','本机测试证书，未验证公网证书'],results},null,2))
console.log(JSON.stringify({pages:results.length,longTextLength:longText.length,accountIsolation:true}))
await send('Browser.close').catch(()=>{})
ws.close()
