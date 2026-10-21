// Queue requests only: GET polling never starts another sweep. Each accepted
// batch may advance to the next, at most four batches / ten distinct items.
// Separate slots keep simultaneous tabs from overwriting an unknown request.
export async function queuePriceSweep({storage,key,request,current=()=>true,uuid=()=>crypto.randomUUID()}){
 const prefix=key+':pending:'
 let total=0,last=null
 for(let batch=0;batch<4&&current();batch++){
  let slots=Object.keys(storage).filter(k=>k.startsWith(prefix)).sort()
  const legacy=storage.getItem(key)
  if(!slots.length&&legacy){storage.setItem(prefix+legacy,legacy);slots=[prefix+legacy]}
  const id=slots.length?storage.getItem(slots[0]):uuid(),slot=prefix+id
  storage.setItem(slot,id) // Durable before POST; a lost response retains this UUID.
  const result=await request({request_key:id,expected_version:0})
  storage.removeItem(slot)
  if(legacy===id)storage.removeItem(key)
  if(!current())return {queued:total,reason:'account_changed'}
  total+=result.queued||0;last=result
  // An old receipt has no has_more: advance once more to obtain current state.
  if(result.has_more===false||['model_not_ready','daily_limit'].includes(result.reason))break
 }
 return {...last,queued:total}
}
