import { ref } from 'vue'
import { accountEpoch } from './session'
export const modelRequests=ref([])
let seq=0
export function beginRequest(path,method,body){
 if(!method||method==='GET')return ()=>{}
 let label=''
 if(/\/analysis-jobs(?:\/[^/]+\/retry)?$/.test(path))label='正在提交分析任务'
 else if(path==='/reward-quotes')label='正在为你的奖励定价'
 else if(/questionnaire\/(analyze|preview)$/.test(path))label=body?.use_ai?'正在整体分析问卷':'正在准备未评估起点'
 else if(path.includes('/llm-config/test'))label='正在测试已保存的模型'
 else if(/\/reports?$/.test(path)||/\/report\?/.test(path))label='正在整理成长报告'
 else if(/(analyze|analyze-explanation|suggestions|propose|generate|variant|judge|supplement|dispute)$/.test(path))label='正在分析这次内容'
 if(!label)return ()=>{}
 const id=++seq,epoch=accountEpoch;modelRequests.value=[...modelRequests.value,{id,epoch,label,started:Date.now()}]
 return ()=>{modelRequests.value=modelRequests.value.filter(r=>r.id!==id)}
}
