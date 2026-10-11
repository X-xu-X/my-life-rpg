import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import { webcrypto } from 'node:crypto'
class Storage {getItem(key){return this[key]??null}setItem(key,value){this[key]=String(value)}removeItem(key){delete this[key]}}
const localStorage=new Storage(),sessionStorage=new Storage(),requests=[]
const context=vm.createContext({ref:value=>({value}),watch:()=>{},useRouter:()=>({}),
    defineEmits:()=>()=>{},crypto:webcrypto,localStorage,sessionStorage,AbortController,
    Event,window:{dispatchEvent:()=>{}},URL,URLSearchParams,console,
    fetch:(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}))})
function read(file){const source=fs.readFileSync(file,'utf8');return (source.includes('<script setup>')?source.match(/<script setup>([\s\S]*?)<\/script>/)[1]:source).replace(/^import .*$/gm,'').replace(/^export /gm,'')}
vm.runInContext(read('frontend/src/session.js')+'\n'+read('frontend/src/api.js')+'\nglobalThis.exposed={account,setAccount,clearAccount,api,request,csrf}',context)
const s=context.exposed
s.setAccount({id:1,csrf_token:'a-token'})
localStorage.setItem('gol:1:record-draft','A 的草稿')
const late=s.api.records()
s.setAccount({id:2,csrf_token:'b-token'})
requests.shift().resolve({ok:true,json:async()=>[{content:'A 的原文'}]})
await assert.rejects(late,/账号已切换/)
assert.equal(localStorage.getItem('gol:1:record-draft'),null)
assert.equal(s.csrf(),'b-token')
vm.runInContext(read('frontend/src/components/RecordComposer.vue')+'\nglobalThis.composer={content,save,uncertain,savedId}',context)
const c=context.composer
c.content.value='先保存这段正文'
const first=c.save();await c.save()
assert.equal(requests.length,1)
const initial=requests.shift(),body=JSON.parse(initial.options.body)
assert.ok(body.client_request_id)
initial.reject(Error('响应丢失'))
await first
assert.equal(c.uncertain.value,true)
const retry=c.save()
assert.equal(requests[0].url,'/api/event-submissions/'+body.client_request_id)
requests.shift().resolve({ok:true,json:async()=>({id:42,content_version:1})})
await retry
assert.equal(c.savedId.value,42)
assert.equal(requests.length,0)
assert.equal(c.uncertain.value,false)
console.log('PASS: account switch abort/late-response guard, namespaced draft removal, save double-click, lost response receipt recovery')

s.setAccount({id:2,mode:'cloud',csrf_token:'b-token'})
const supplement=s.api.supplementJudgment(9,'保留原回答','2026-10-10T00:00:00Z')
let call=requests.shift();assert.equal(call.url,'/api/judgments/9')
call.resolve({ok:true,json:async()=>({event_id:7,updated_at:'2026-10-10T00:01:00Z'})})
await new Promise(resolve=>setImmediate(resolve))
call=requests.shift();assert.equal(call.url,'/api/events/7')
call.resolve({ok:true,json:async()=>({id:7,content_version:3})})
await new Promise(resolve=>setImmediate(resolve))
call=requests.shift();assert.equal(call.url,'/api/events/7/analysis-jobs')
const revision=JSON.parse(call.options.body)
assert.equal(revision.judgment_version,'2026-10-10T00:00:00Z')
assert.equal(revision.operation,'supplement');assert.equal(revision.event_version,3)
assert.ok(revision.request_key)
call.resolve({ok:true,json:async()=>({state:'queued'})});await supplement
assert.equal(requests.length,0)
console.log('PASS: cloud supplement uses task queue and preserves caller judgment version for stale-input conflict')
