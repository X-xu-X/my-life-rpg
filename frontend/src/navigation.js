import { account, storageKey } from './session'
const roots={today:'/',journal:'/journal',plans:'/plans',growth:'/growth',me:'/me',admin:'/admin'}
let returning=null
export function beginReturn(path){returning={path,owner:account.value?.id}}
export function sectionRoot(route){return route.meta.workspace==='admin'?'/admin':roots[route.meta.section] || '/'}
function valid(router,path,workspace){
  if(typeof path!=='string'||!path.startsWith('/')||path.startsWith('//')||/[\\\r\n]/.test(path))return false
  const target=router.resolve(path)
  return !!target.meta.section && (target.meta.workspace || 'personal')===workspace
}
export function rememberReturn(router,to,from){
  const previous=returning;returning=null
  if(previous?.owner===account.value?.id&&previous.path===to.fullPath)return
  const workspace=to.meta.workspace || 'personal'
  if(!account.value || to.fullPath===from.fullPath || !valid(router,from.fullPath,workspace))return
  try{sessionStorage.setItem(storageKey('return:'+to.fullPath),from.fullPath)}catch{}
}
export function returnTarget(router,route){
  let stored
  try{stored=sessionStorage.getItem(storageKey('return:'+route.fullPath))}catch{}
  return valid(router,stored,route.meta.workspace || 'personal') && stored!==route.fullPath ? stored : sectionRoot(route)
}
