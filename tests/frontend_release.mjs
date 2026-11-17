import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import {webcrypto} from 'node:crypto'
const config=JSON.parse(fs.readFileSync(0,'utf8'))
class Storage {getItem(k){return this[k]??null}setItem(k,v){this[k]=String(v)}removeItem(k){delete this[k]}}
const localStorage=new Storage(),sessionStorage=new Storage()
let lost=true,readFail=false,posts=0
const ref=value=>({value}),computed=fn=>({get value(){return fn()}})
const nativeFetch=globalThis.fetch
const context=vm.createContext({ref,computed,watch:()=>{},onMounted:()=>{},onBeforeUnmount:()=>{},
  useRoute:()=>({path:'/special-vouchers',query:{},params:{},meta:{}}),
  crypto:webcrypto,localStorage,sessionStorage,AbortController,URL,URLSearchParams,Event,
  window:{dispatchEvent:()=>{}},confirm:()=>true,setTimeout:()=>0,clearTimeout:()=>{},
  toast:{success:()=>{},info:()=>{},error:()=>{}},console,
  fetch:async(url,options)=>{
    if(readFail && (url==='/api/shop/items'||url.startsWith('/api/coins')))throw Error('refresh failed')
    const response=await nativeFetch(config.url+url,{...options,headers:{...options.headers,Origin:'https://rpg.test',Cookie:config.cookie}})
    if(url.endsWith('/redeem')){posts++;if(lost){lost=false;await response.text();throw Error('response lost after commit')}}
    return response
  }})
function source(path){let s=fs.readFileSync(path,'utf8');if(s.includes('<script setup>'))s=s.match(/<script setup>([\s\S]*?)<\/script>/)[1];return s.replace(/^import .*$/gm,'').replace(/^export /gm,'')}
vm.runInContext(source('frontend/src/session.js')+'\n'+source('frontend/src/requestStatus.js')+'\n'+source('frontend/src/api.js')+'\n'+source('frontend/src/composables/useRedemption.js')+'\n'+source('frontend/src/composables/useExemptionPurchase.js')+'\nglobalThis.state={setAccount,clearAccount,useRedemption}',context)
context.state.setAccount({id:config.uid,mode:'cloud',csrf_token:config.csrf})
let controller=context.state.useRedemption()
const first=controller.send(config.item);await controller.send(config.item)
await assert.rejects(first,/response lost/)
assert.equal(posts,1)
const key=controller.pending.value.body.request_key
controller=context.state.useRedemption() // Page refresh reconstructs from durable owner-scoped state.
assert.equal(controller.pending.value.body.request_key,key)
const restored=await controller.send(config.item)
assert.equal(restored.balance,73);assert.equal(posts,1)
// Actual ChallengeView -> composable -> api -> HTTP. Success then failed GET must remain complete.
vm.runInContext(source('frontend/src/components/ChallengeView.vue')+'\nglobalThis.view={redeem,coins,redemption,error}',context)
context.view.coins.value=73;readFail=true
// 兑换现在先弹确认框（redeem 第二参数 confirmed=true 才真正提交），这里直接走确认后的分支。
await context.view.redeem(config.item,true)
assert.equal(posts,2);assert.equal(context.view.redemption.pending.value.state,'complete')
assert.notEqual(context.view.redemption.pending.value.body.request_key,key)
assert.equal(context.view.redemption.pending.value.result.balance,66)
context.state.setAccount({id:999,csrf_token:'other'})
await assert.rejects(controller.send(config.item),/账号已切换/)
assert.equal(context.state.useRedemption().pending.value,null)
console.log('PASS: actual frontend HTTP, lost committed response, duplicate click, refresh receipt, GET failure, explicit second purchase, account isolation')
