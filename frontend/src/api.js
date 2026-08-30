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
  // Onboarding
  startOnboarding: () => request('/onboarding/questions', { method: 'POST' }),
  submitAnswers: (sessionId, answers, finish) =>
    request('/onboarding/answer', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, answers, finish }),
    }),
  disputePanel: (sessionId, detail) =>
    request('/onboarding/dispute', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, detail }),
    }),

  // 事件
  createEvent: (payload) => request('/events', { method: 'POST', body: JSON.stringify(payload) }),
  listEvents: () => request('/events'),
  judgeEvent: (eventId) => request(`/events/${eventId}/judge`, { method: 'POST' }),

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
}
