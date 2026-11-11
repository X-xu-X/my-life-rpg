import { computed, ref } from 'vue'
import { api } from '../api'

/**
 * 行级提示偏好（v1 UI-IA F7）——模块级单例，全站只发一次 GET。
 *
 * 权威状态在服务端（experience_preferences.suppressed_lines），不接受 localStorage 当权威。
 * 失败时宁可继续显示提示，也不让内容凭空消失。
 */
const prefs = ref(null)
// 就绪门：异步拉取完成前不渲染提示行，避免"已关闭的提示先闪一下再消失"
const ready = computed(() => prefs.value !== null)
const loading = ref(false)
const error = ref('')
let inflight = null

/**
 * 生成 UUID v4。crypto.randomUUID 只在安全上下文（HTTPS / localhost）存在，
 * 手机通过局域网 http://10.x.x.x 访问时为 undefined，直接调用会抛错。
 * 后端 WriteIn.request_key 的类型是 UUID，降级结果必须是合法 UUID 格式。
 */
function uuid4() {
  if (globalThis.crypto?.randomUUID) return crypto.randomUUID()
  const b = new Uint8Array(16)
  if (globalThis.crypto?.getRandomValues) globalThis.crypto.getRandomValues(b)
  else for (let i = 0; i < 16; i += 1) b[i] = Math.floor(Math.random() * 256)
  b[6] = (b[6] & 0x0f) | 0x40
  b[8] = (b[8] & 0x3f) | 0x80
  const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('')
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`
}

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

async function doHide(id) {
  const p = await ensure()
  const next = [...new Set([...(p.suppressed_lines || []), id])]
  try {
    const saved = await api.flow(
      '/experience-preferences',
      {
        // WriteIn 要求 request_key（幂等键）；缺了会 422
        request_key: uuid4(),
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

// 串行队列：偏好接口是 PUT 全量替换 + 乐观锁，两次并发会读到同一个 expected_version，
// 后到的那次必然 409。串行化后第二次能读到第一次返回的新 version。
let chain = Promise.resolve()
function hide(id) {
  const run = chain.then(() => doHide(id))
  chain = run.then(() => {}, () => {})
  return run
}

/** 强制重新拉取（偏好页保存/恢复后调用，让其他页面本次会话立即生效）。 */
async function refresh() {
  prefs.value = null
  inflight = null
  return ensure()
}

export function useTipPrefs() {
  return { prefs, loading, error, ready, ensure, hidden, hide, refresh }
}
