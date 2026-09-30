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
  resetOnboarding: () => request('/onboarding/reset', { method: 'POST' }),
  resetAllData: () => request('/onboarding/reset-all', { method: 'POST' }),

  // 事件
  createEvent: (payload) => request('/events', { method: 'POST', body: JSON.stringify(payload) }),
  listEvents: (pure) => request(pure !== undefined ? `/events?pure=${pure}` : '/events'),
  getEvent: (id) => request(`/events/${id}`),
  updateEvent: (id, payload) => request(`/events/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  judgeEvent: (eventId, clarification) =>
    request(`/events/${eventId}/judge`, {
      method: 'POST',
      body: JSON.stringify({ clarification: clarification || '' }),
    }),
  deleteEvent: (eventId) => request(`/events/${eventId}`, { method: 'DELETE' }),
  getHeatmap: () => request('/events/heatmap'),

  // 打卡项目（v1.7）
  listItems: (params = {}) => {
    const qs = new URLSearchParams()
    if (params.enabled !== undefined) qs.set('enabled', params.enabled)
    if (params.nature) qs.set('nature', params.nature)
    const q = qs.toString()
    return request(q ? `/items?${q}` : '/items')
  },
  getItemsStats: () => request('/items/stats'),
  createItem: (payload) => request('/items', { method: 'POST', body: JSON.stringify(payload) }),
  updateItem: (id, payload) => request(`/items/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  toggleItem: (id) => request(`/items/${id}/toggle`, { method: 'POST' }),
  disableItem: (id) => request(`/items/${id}`, { method: 'DELETE' }),

  // 判定
  listJudgments: () => request('/judgments'),
  getJudgment: (id) => request(`/judgments/${id}`),
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

  // AI 模型配置（BYOK，v1.4）
  getLLMConfig: () => request('/llm-config'),
  putLLMConfig: (payload) =>
    request('/llm-config', { method: 'PUT', body: JSON.stringify(payload) }),

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

  // 备份
  backup: () => request('/backup', { method: 'POST' }),
  listBackups: () => request('/backup/list'),

  // 成长报告
  getReport: (period) => request(`/report?period=${period}`),

  // ===== 金币（v1.8） =====
  getCoins: (limit = 50) => request(`/coins?limit=${limit}`),

  // ===== 挑战（v1.8） =====
  getCurrentChallenges: () => request('/challenges/current'),
  listChallenges: (scope) => request(scope ? `/challenges?scope=${scope}` : '/challenges'),
  generateChallenges: (scope, force = false) =>
    request('/challenges/generate', {
      method: 'POST',
      body: JSON.stringify({ scope, force }),
    }),
  acceptChallenge: (id) => request(`/challenges/${id}/accept`, { method: 'POST' }),
  // v1.9 F3：候选期切换难度档位（接受后档位锁定，会返回 400）
  switchChallengeVariant: (id, variantIndex) =>
    request(`/challenges/${id}/variant`, {
      method: 'PUT',
      body: JSON.stringify({ variant_index: variantIndex }),
    }),
  completeChallenge: (id, note) =>
    request(`/challenges/${id}/complete`, { method: 'POST', body: JSON.stringify({ note }) }),
  settleChallenge: (id) => request(`/challenges/${id}/settle`, { method: 'POST' }),
  abandonChallenge: (id, note = '') =>
    request(`/challenges/${id}/abandon`, { method: 'POST', body: JSON.stringify({ note }) }),

  // ===== 商店与奖励券（v1.8） =====
  listShopItems: () => request('/shop/items'),
  createShopItem: (payload) =>
    request('/shop/items', { method: 'POST', body: JSON.stringify(payload) }),
  updateShopItem: (id, payload) =>
    request(`/shop/items/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  repriceShopItem: (id) => request(`/shop/items/${id}/reprice`, { method: 'POST' }),
  disableShopItem: (id) => request(`/shop/items/${id}`, { method: 'DELETE' }),
  redeemShopItem: (id, note = '') =>
    request(`/shop/items/${id}/redeem`, { method: 'POST', body: JSON.stringify({ note }) }),
  listRedemptions: () => request('/redemptions'),
  fulfillRedemption: (id, note = '') =>
    request(`/redemptions/${id}/fulfill`, { method: 'POST', body: JSON.stringify({ note }) }),

  // ===== 停滞问询（v1.8） =====
  getStagnation: () => request('/stagnation'),
  answerStagnation: (name, stopped, note = '') =>
    request(`/stagnation/${encodeURIComponent(name)}/answer`, {
      method: 'POST',
      body: JSON.stringify({ stopped, note }),
    }),

  // ===== 成就（v1.10 M1） =====
  getAchievements: () => request('/achievements'),
  // 处理 AI 发现型里程碑建议：action = 'grant'（追授）/ 'dismiss'（忽略）
  handleAchievement: (judgmentId, action) =>
    request(`/judgments/${judgmentId}/achievement`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    }),

  // ===== 豁免券（v1.10 M2） =====
  listExemptions: () => request('/exemptions'),
  // body: { target_date, period, start_time?, end_time?, reason? }
  buyExemption: (payload) =>
    request('/exemptions', { method: 'POST', body: JSON.stringify(payload) }),
}
