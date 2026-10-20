import fs from 'node:fs'
import path from 'node:path'
import {spawn} from 'node:child_process'
import {fileURLToPath} from 'node:url'
const out=path.dirname(fileURLToPath(import.meta.url))
const base='https://127.0.0.1:19384'
const wait=ms=>new Promise(r=>setTimeout(r,ms))
const edge=spawn('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',[
  '--headless=new','--disable-gpu','--no-first-run','--no-proxy-server',
  '--ignore-certificate-errors', // Only this disposable loopback fixture/profile; never the real site.
  '--remote-debugging-address=127.0.0.1','--remote-debugging-port=19385',
  '--user-data-dir='+path.join(out,'browser-profile'),'about:blank'
],{windowsHide:true,stdio:'ignore'})
let ws
const errors=[],checks=[]
try {
  let pages
  for(let i=0;i<60;i++){
    try{pages=await (await fetch('http://127.0.0.1:19385/json/list')).json();break}catch{await wait(300)}
  }
  if(!pages)throw Error('Isolated Edge did not start')
  ws=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl)
  await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true})})
  let id=0
  const pending=new Map()
  ws.addEventListener('message',event=>{
    const r=JSON.parse(event.data)
    if(r.id){const p=pending.get(r.id);pending.delete(r.id);r.error?p.reject(r.error):p.resolve(r.result)}
    if(r.method==='Runtime.exceptionThrown')errors.push(r.params.exceptionDetails.text)
    if(r.method==='Log.entryAdded'&&r.params.entry.level==='error')errors.push(r.params.entry.text)
  })
  const send=(method,params={})=>new Promise((resolve,reject)=>{const next=++id;pending.set(next,{resolve,reject});ws.send(JSON.stringify({id:next,method,params}))})
  const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value}
  await send('Page.enable');await send('Runtime.enable')
  await send('Page.navigate',{url:base})
  for(let i=0;i<60;i++){if(await evaluate('!!document.querySelector("input[autocomplete=username]")'))break;await wait(300)}
  await evaluate(`(()=>{
    for(const [selector,value] of [['input[autocomplete=username]','browser_reviewer'],['input[type=password]','friend-test-password']]){
      const element=document.querySelector(selector);element.value=value;element.dispatchEvent(new Event('input',{bubbles:true}))
    }
    document.querySelector('form').requestSubmit()
  })()`)
  for(let i=0;i<60;i++){if(await evaluate('document.body.innerText.includes("今日片段")'))break;await wait(300)}
  if(!await evaluate('document.body.innerText.includes("今日片段")'))throw Error('Synthetic browser login did not complete')
  const routes=[['today','/'],['journal','/journal'],['detail','/events/2'],['pending','/pending'],
    ['growth','/growth'],['me','/me'],['settings','/settings'],['checkin','/checkin'],
    ['judgments','/judgments'],['shop','/challenges'],['review','/review'],['reports','/reports'],
    ['anchors','/anchors'],['onboarding','/onboarding']]
  for(const [name,width,height,mobile] of [['desktop',1440,1000,false],['mobile',390,844,true]]){
    await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile})
    for(const [page,route] of routes){
      await evaluate(`location.hash=${JSON.stringify('#'+route)}`)
      await wait(650)
      const state=await evaluate(`(()=>({title:document.querySelector('h1')?.innerText||'',textLength:document.body.innerText.length,
        bodyWidth:document.documentElement.scrollWidth,viewportWidth:innerWidth,
        keyInputsEmpty:[...document.querySelectorAll('input[type=password]')].every(e=>!e.value),
        errors:[...document.querySelectorAll('[role=alert],.error,.read-error')].map(e=>e.innerText).filter(Boolean)}))()`)
      if(state.textLength<60)throw Error('Empty page '+page)
      const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false})
      fs.writeFileSync(path.join(out,`${name}-${page}.png`),Buffer.from(shot.data,'base64'))
      checks.push({viewport:name,page,route,...state})
    }
  }
  fs.writeFileSync(path.join(out,'browser-summary.json'),JSON.stringify({scope:'real compiled Vue + loopback HTTPS + disposable SQLite synthetic account; no provider calls; not remote production acceptance',checks,runtimeErrors:errors},null,2))
  console.log(JSON.stringify({pages:checks.length,runtimeErrors:errors,readErrors:checks.filter(c=>c.errors.length),horizontalOverflow:checks.filter(c=>c.bodyWidth>c.viewportWidth+1).map(c=>({viewport:c.viewport,page:c.page,width:c.bodyWidth,viewportWidth:c.viewportWidth}))},null,2))
  await send('Browser.close').catch(()=>{})
}finally{
  ws?.close()
  edge.kill()
}
