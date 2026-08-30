// API 封装：统一请求后端 FastAPI 接口
const BASE = '/api'

async function request(path, options = {}) {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  const data = await resp.json().catch(() => ({}))
  if (!resp.ok) {
    // 后端返回的 detail 可能是字符串或对象，统一转字符串
    const msg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    throw new Error(msg || `请求失败（${resp.status}）`)
  }
  return data
}

export const api = {
  // 健康检查（前端启动时探测后端连接状态）
  health: () => request('/health'),

  // Onboarding
  getOnboardingStatus: () => request('/onboarding/status'),
  startOnboarding: () => request('/onboarding/questions', { method: 'POST' }),
  submitAnswers: (answers) =>
    request('/onboarding/answer', {
      method: 'POST',
      body: JSON.stringify({ answers }),
    }),
  supplementProfile: (detail) =>
    request('/onboarding/supplement', {
      method: 'POST',
      body: JSON.stringify({ detail }),
    }),
  confirmSupplement: () => request('/onboarding/supplement/confirm', { method: 'POST' }),

  // 事件
  createEvent: (payload) => request('/events', { method: 'POST', body: JSON.stringify(payload) }),
  listEvents: (pure) => request(pure !== undefined ? `/events?pure=${pure}` : '/events'),
  judgeEvent: (eventId) => request(`/events/${eventId}/judge`, { method: 'POST' }),
  deleteEvent: (eventId) => request(`/events/${eventId}`, { method: 'DELETE' }),
  getHeatmap: () => request('/events/heatmap'),

  // 判定
  listJudgments: () => request('/judgments'),
  confirmJudgment: (id) => request(`/judgments/${id}/confirm`, { method: 'POST' }),
  supplementJudgment: (id, detail) =>
    request(`/judgments/${id}/supplement`, { method: 'POST', body: JSON.stringify({ detail }) }),
  disputeJudgment: (id, detail) =>
    request(`/judgments/${id}/dispute`, { method: 'POST', body: JSON.stringify({ detail }) }),
  getJudgmentLogs: (id) => request(`/judgments/${id}/logs`),

  // 属性
  getAttributes: () => request('/attributes'),
  getAttributeHistory: () => request('/attributes/history'),

  // 锚点
  getAnchors: () => request('/anchors'),
  calibrateAnchor: (id, calibratedValue) =>
    request(`/anchors/${id}/calibrate`, {
      method: 'POST',
      body: JSON.stringify({ calibrated_value: calibratedValue }),
    }),

  // 目标
  listGoals: () => request('/goals'),
  createGoal: (payload) => request('/goals', { method: 'POST', body: JSON.stringify(payload) }),
  achieveGoal: (id) => request(`/goals/${id}/achieve`, { method: 'POST' }),
  failGoal: (id) => request(`/goals/${id}/fail`, { method: 'POST' }),
  cancelGoal: (id) => request(`/goals/${id}/cancel`, { method: 'POST' }),

  // 设置
  getSettings: () => request('/settings'),
  updateSetting: (key, value) =>
    request('/settings', { method: 'POST', body: JSON.stringify({ key, value }) }),

  // 数据导出（文件下载）
  exportData: async (format) => {
    const resp = await fetch(`${BASE}/export?format=${format}`)
    if (!resp.ok) throw new Error(`导出失败（${resp.status}）`)
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = format === 'csv' ? 'game_of_life_events.csv' : 'game_of_life_data.json'
    a.click()
    URL.revokeObjectURL(url)
  },
}
