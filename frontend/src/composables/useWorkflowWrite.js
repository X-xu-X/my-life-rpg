import { ref } from 'vue'
import { api } from '../api'
import { storageKey, accountEpoch } from '../session'
// Unknown results keep the exact original request across refresh; never invent a new UUID.
export function useWorkflowWrite(scope){
 const busy=ref(false),pending=ref(null),key=storageKey('flow:'+scope),epoch=accountEpoch
 try{pending.value=JSON.parse(localStorage.getItem(key)||'null')}catch{}
 async function send(path,body,method='POST'){
  if(busy.value)throw Error('操作正在进行，请等待。')
  const request=pending.value || {path,body:{...JSON.parse(JSON.stringify(body)),request_key:crypto.randomUUID()},method}
  pending.value=request;try{localStorage.setItem(key,JSON.stringify(request))}catch{};busy.value=true
  try{const result=await api.flow(request.path,request.body,request.method);if(epoch!==accountEpoch)throw Error('账号已切换。');pending.value=null;try{localStorage.removeItem(key)}catch{};return result}
  catch(e){if(epoch===accountEpoch&&e.status>=400&&e.status<500){pending.value=null;try{localStorage.removeItem(key)}catch{}}throw e}
  finally{busy.value=false}
 }
 function discardSuggestion(){
  if(busy.value||pending.value?.path!=='/reward-quotes')return
  pending.value=null;try{localStorage.removeItem(key)}catch{}
 }
 return {busy,pending,send,discardSuggestion}
}
