import { ref } from 'vue'

export const account = ref(null)
export let accountEpoch = 0
export const activeRequests = new Set()
let csrfToken = ''
export const csrf = () => csrfToken
export const storageKey = (name) => `gol:${account.value?.id || 'local'}:${name}`

export function setAccount(user) {
  if (account.value?.id !== user?.id) clearAccount()
  account.value = user
  csrfToken = user?.csrf_token || ''
}

export function clearAccount() {
  const prefix = `gol:${account.value?.id || 'local'}:`
  accountEpoch++
  for (const controller of activeRequests) controller.abort()
  activeRequests.clear()
  for (const storage of [localStorage, sessionStorage]) {
    try {
      for (const key of Object.keys(storage)) if (key.startsWith(prefix)) storage.removeItem(key)
    } catch { /* 存储不可用不影响退出 */ }
  }
  account.value = null
  csrfToken = ''
}

export function localDate(value = new Date()) {
  if (typeof value === 'string') value = new Date(!/(Z|[+-]\d{2}:\d{2})$/.test(value) ? value + '+08:00' : value)
  return new Intl.DateTimeFormat('sv-SE', { timeZone: account.value?.timezone || 'Asia/Shanghai',
    year: 'numeric', month: '2-digit', day: '2-digit' }).format(value)
}

export function displayTime(value, dateOnly = false) {
  if (!value) return ''
  // 旧本地档案的无偏移时间明确按上海解释。
  const raw = typeof value === 'string' && !/(Z|[+-]\d{2}:\d{2})$/.test(value) ? value + '+08:00' : value
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return ''
  const options = { timeZone: account.value?.timezone || 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }
  if (!dateOnly) Object.assign(options, { hour: '2-digit', minute: '2-digit' })
  return new Intl.DateTimeFormat('zh-CN', options).format(date)
}

export function displayEventTime(event){
  return event.time_precision==='date'&&event.occurred_on ? event.occurred_on+' · 仅日期' : displayTime(event.occurred_at)
}
