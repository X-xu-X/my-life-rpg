import { ref } from 'vue'
import { account, accountEpoch } from '../session'
import { api } from '../api'

export function useExemptionPurchase(){
  const owner=account.value?.id || 'local',epoch=accountEpoch,key=`gol-receipts:${owner}:exemption`
  const pending=ref(null),busy=ref(false),warning=ref('')
  try{pending.value=JSON.parse(localStorage.getItem(key)||'null');if(pending.value && (pending.value.owner!==owner || !pending.value.body?.request_key))throw Error('invalid')}
  catch{warning.value='豁免购买恢复记录不可读，请先核对券和金币流水。'}
  function persist(value){localStorage.setItem(key,JSON.stringify(value));if(localStorage.getItem(key)!==JSON.stringify(value))throw Error('无法保存购买标识，请开启浏览器存储后重试。');pending.value=value}
  function current(){if(epoch!==accountEpoch || owner!==(account.value?.id || 'local'))throw Error('账号已切换，请重新打开商店。')}
  async function send(payload){
    if(busy.value)return
    current();if(warning.value)throw Error(warning.value)
    busy.value=true
    try{
      let operation=pending.value
      if(!operation || operation.state!=='unknown'){
        operation={owner,state:'unknown',body:{...payload,request_key:crypto.randomUUID()}};persist(operation)
      }
      let result
      try{result=await api.exemptionSubmission(operation.body.request_key)}catch(e){if(e.status!==404)throw e}
      if(!result){
        try{result=await api.buyExemption(operation.body)}
        catch(e){if([400,409,422].includes(e.status)){current();persist({...operation,state:'rejected'})}throw e}
      }
      current();pending.value={...operation,state:'complete',result}
      try{persist(pending.value)}catch{warning.value='购买已成功，但结果恢复记录未能保存，请先核对券和金币流水。'}
      return result
    }finally{busy.value=false}
  }
  return {pending,busy,warning,send}
}
