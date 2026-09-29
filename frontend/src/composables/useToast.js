// v1.9 F2：全局轻提示（toast）
// 单例：任意组件 import { toast } 直接调用，由 App.vue 里挂载的 <ToastHost /> 统一渲染。
// 设计：约 3 秒自动消失、不阻塞操作（容器 pointer-events:none，单条 auto）。
import { reactive } from 'vue'

let seq = 0
const state = reactive({ items: [] })

const DEFAULT_DURATION = 3000

function push(type, message, duration = DEFAULT_DURATION) {
  const text = (message === null || message === undefined) ? '' : String(message)
  if (!text.trim()) return null
  // 去重：同类型 + 同文案已在显示中 → 不再堆叠。
  // 场景：页面挂载时多个请求同时失败（如后端整体不可达），只浮一次提示，
  // 对应 F2-2「保留顶部横幅 + 浮出一次 toast」的“一次”。
  const dup = state.items.find((x) => x.type === type && x.message === text)
  if (dup) return dup.id
  const id = ++seq
  state.items.push({ id, type, message: text })
  if (duration > 0) {
    setTimeout(() => dismiss(id), duration)
  }
  return id
}

export function dismiss(id) {
  const i = state.items.findIndex((x) => x.id === id)
  if (i >= 0) state.items.splice(i, 1)
}

export function dismissAll() {
  state.items.splice(0, state.items.length)
}

export const toast = {
  state,
  success: (msg, duration) => push('success', msg, duration),
  error: (msg, duration) => push('error', msg, duration),
  info: (msg, duration) => push('info', msg, duration),
  dismiss,
  dismissAll,
}

export function useToast() {
  return toast
}
