import {test} from 'node:test'
import assert from 'node:assert/strict'
import {queuePriceSweep} from '../frontend/src/pricingSweep.js'
const storage=()=>Object.create({getItem(key){return Object.hasOwn(this,key)?this[key]:null},setItem(key,value){this[key]=String(value)},removeItem(key){delete this[key]}})
test('six items continue only after a known accepted first batch',async()=>{
 const store=storage(),calls=[];let n=0
 const result=await queuePriceSweep({storage:store,key:'day',uuid:()=>String(++n),request:async body=>{calls.push(body.request_key);return {queued:3,has_more:calls.length===1}}})
 assert.equal(result.queued,6);assert.deepEqual(calls,['1','2']);assert.deepEqual(Object.keys(store),[])
})
test('unknown response survives reload and uses the exact original UUID',async()=>{
 const store=storage(),calls=[];let n=0
 await assert.rejects(queuePriceSweep({storage:store,key:'day',uuid:()=>String(++n),request:async body=>{calls.push(body.request_key);throw Error('response lost after acceptance')}}))
 assert.equal(store.getItem('day:pending:1'),'1')
 await queuePriceSweep({storage:store,key:'day',uuid:()=>String(++n),request:async body=>{calls.push(body.request_key);return {queued:3,has_more:false}}})
 assert.deepEqual(calls,['1','1']);assert.equal(n,1);assert.deepEqual(Object.keys(store),[])
})
test('separate unknown tab requests never overwrite each other',async()=>{
 const store=storage();store.setItem('day:pending:a','a');store.setItem('day:pending:b','b');const calls=[]
 await queuePriceSweep({storage:store,key:'day',request:async body=>{calls.push(body.request_key);return {queued:0,has_more:false}}})
 assert.deepEqual(calls,['a']);assert.equal(store.getItem('day:pending:b'),'b')
 await queuePriceSweep({storage:store,key:'day',request:async body=>{calls.push(body.request_key);return {queued:0,has_more:false}}})
 assert.deepEqual(calls,['a','b'])
})
test('completed empty first visit does not freeze later added rewards',async()=>{
 const store=storage(),calls=[];let n=0
 for(const queued of [0,1])await queuePriceSweep({storage:store,key:'day',uuid:()=>String(++n),request:async body=>{calls.push(body.request_key);return {queued,has_more:false}}})
 assert.deepEqual(calls,['1','2'])
})
test('legacy day receipt is recovered then advanced to current queue metadata',async()=>{
 const store=storage(),calls=[];store.setItem('day','legacy-uuid')
 await queuePriceSweep({storage:store,key:'day',uuid:()=> 'new-uuid',request:async body=>{calls.push(body.request_key);return calls.length===1?{queued:0,ids:[]}:{queued:3,has_more:false}}})
 assert.deepEqual(calls,['legacy-uuid','new-uuid']);assert.deepEqual(Object.keys(store),[])
})
test('daily budget and hard four-request bound prevent polling loops',async()=>{
 let calls=0,n=0
 await queuePriceSweep({storage:storage(),key:'day',uuid:()=>String(++n),request:async()=>{calls++;return {queued:3,has_more:true}}})
 assert.equal(calls,4)
 calls=0
 await queuePriceSweep({storage:storage(),key:'day',request:async()=>{calls++;return {queued:1,has_more:false,reason:'daily_limit'}}})
 assert.equal(calls,1)
})
