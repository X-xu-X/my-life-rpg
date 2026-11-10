import { ref } from 'vue'
import { api } from '../api'

/**
 * 行级提示偏好（v1 UI-IA F7）——模块级单例，全站只发一次 GET。
 *
 * 权威状态在服务端（experience_preferences.suppressed_lines），不接受 localStorage 当权威。
 * 失败时宁可继续显示提示，也不让内容凭空消失。
 */
const prefs = ref(null)
const loading = ref(false)
const error = ref('')
let inflight = null

async function ensure() {
  if (prefs.value) return prefs.value
  if (inflight) return inflight
  loading.value = true
  inflight = api
    .flow('/experience-preferences')
    .then((v) => {
      prefs.value = { ...v, suppressed_lines: v.suppressed_lines || [] }
      return prefs.value
    })
    .catch((e) => {
      error.value = e.message
      prefs.value = { version: 0, suppressed: [], suppressed_lines: [], return_disabled: false }
      return prefs.value
    })
    .finally(() => {
      loading.value = false
      inflight = null
    })
  return inflight
}

function hidden(id) {
  return (prefs.value?.suppressed_lines || []).includes(id)
}

async function hide(id) {
  const p = await ensure()
  const next = [...new Set([...(p.suppressed_lines || []), id])]
  try {
    const saved = await api.flow(
      '/experience-preferences',
      {
        // WriteIn 要求 request_key（幂等键）；缺了会 422
        request_key: crypto.randomUUID(),
        expected_version: p.version,
        suppressed: p.suppressed || [],
        suppressed_lines: next,
        return_disabled: !!p.return_disabled,
      },
      'PUT'
    )
    prefs.value = { ...saved, suppressed_lines: saved.suppressed_lines || [] }
    return true
  } catch (e) {
    error.value = e.message
    return false
  }
}

/** 强制重新拉取（偏好页保存/恢复后调用，让其他页面本次会话立即生效）。 */
async function refresh() {
  prefs.value = null
  inflight = null
  return ensure()
}

export function useTipPrefs() {
  return { prefs, loading, error, ensure, hidden, hide, refresh }
}
