// API 封装：统一请求后端 FastAPI 接口
const BASE = '/api'

import { account, accountEpoch, activeRequests, csrf } from './session'

async function request(path, options = {}) {
  const epoch = accountEpoch
  const controller = new AbortController()
  activeRequests.add(controller)
  try {
    const resp = await fetch(`${BASE}${path}`, {
      ...options, credentials: 'same-origin', signal: controller.signal,
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf(), ...(options.headers || {}) },
    })
    const data = await resp.json().catch(() => ({}))
    if (epoch !== accountEpoch) throw new Error('账号已切换，请重新打开此页面。')
    if (!resp.ok) {
      if (resp.status === 401 && !['/auth/login', '/auth/register', '/auth/recover'].includes(path)) window.dispatchEvent(new Event('gol-auth-lost'))
      const msg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
      const error = new Error(msg || `请求失败（${resp.status}）`)
      error.status = resp.status
      throw error
    }
    return data
  } finally { activeRequests.delete(controller) }
}

async function queueJudgmentRevision(id, operation, detail, version) {
  const judgment = await request(`/judgments/${id}`)
  const event = await request(`/events/${judgment.event_id}`)
  return request(`/events/${event.id}/analysis-jobs`, { method: 'POST', body: JSON.stringify({
    request_key: crypto.randomUUID(), event_version: event.content_version,
    operation, detail, judgment_version: version,
  }) })
}

export const api = {
  me: () => request('/auth/me'),
  login: (body) => request('/auth/login', { method: 'POST', body: JSON.stringify(body) }),
  register: (body) => request('/auth/register', { method: 'POST', body: JSON.stringify(body) }),
  recover: (body) => request('/auth/recover', { method: 'POST', body: JSON.stringify(body) }),
  logout: () => request('/auth/logout', { method: 'POST' }),
  neutralBaseline: () => request('/onboarding/neutral', { method: 'POST', body: JSON.stringify({ acknowledge: true }) }),
  checkStreak: () => request('/coins/check-streak', {method:'POST'}),
  submission: (key) => request(`/event-submissions/${key}`),
  pending: () => request('/pending'),
  submitJob: (id, body) => request(`/events/${id}/analysis-jobs`, { method: 'POST', body: JSON.stringify(body) }),
  getJob: (id) => request(`/analysis-jobs/${id}`),
  cancelJob: (id) => request(`/analysis-jobs/${id}/cancel`, { method: 'POST' }),
  getReview: (day, timezone) => request(`/daily-reviews/${day}`+(timezone?'?'+new URLSearchParams({timezone}):'')),
  listReviews: () => request('/daily-reviews'),
  putReview: (day, body) => request(`/daily-reviews/${day}`, { method: 'PUT', body: JSON.stringify(body) }),

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
  createEvent: (payload) => request('/events', { method: 'POST', body: JSON.stringify({ client_request_id: crypto.randomUUID(), timezone:account.value?.timezone || 'Asia/Shanghai', ...payload }) }),
  listEvents: (pure) => request(pure !== undefined ? `/events?pure=${pure}` : '/events'),
  records: (params = {}) => request('/events?' + new URLSearchParams(Object.entries(params).filter(([, value]) => value !== undefined && value !== ''))),
  getEvent: (id) => request(`/events/${id}`),
  updateEvent: (id, payload) => request(`/events/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  judgeEvent: async (eventId, clarification) => {
    if (account.value?.mode === 'cloud') {
      const event = await request(`/events/${eventId}`)
      const job = await request(`/events/${eventId}/analysis-jobs`, {method:'POST',body:JSON.stringify({
        request_key:crypto.randomUUID(),event_version:event.content_version,operation:'judge',detail:clarification||''})})
      return {status:'queued',event_id:eventId,job_id:job.id,summary:'原文已保存，分析已排队。可在待处理或原记录中查看。'}
    }
    return request(`/events/${eventId}/judge`, {
      method: 'POST',
      body: JSON.stringify({ clarification: clarification || '' }),
    })
  },
  deleteEvent: async (eventId, version) => { const event = version === undefined ? await request(`/events/${eventId}`) : {content_version:version}; return request(`/events/${eventId}`, { method: 'DELETE', body: JSON.stringify({expected_version:event.content_version,request_key:crypto.randomUUID()}) }) },
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
  confirmJudgment: async (id, version) => { const judgment = version === undefined ? await request(`/judgments/${id}`) : {updated_at:version}; return request(`/judgments/${id}/confirm`, { method: 'POST', body: JSON.stringify({expected_version:judgment.updated_at,request_key:crypto.randomUUID()}) }) },
  supplementJudgment: (id, detail, version) => account.value?.mode === 'cloud'
    ? queueJudgmentRevision(id, 'supplement', detail, version)
    : request(`/judgments/${id}/supplement`, { method: 'POST', body: JSON.stringify({ detail }) }),
  disputeJudgment: (id, detail, version) => account.value?.mode === 'cloud'
    ? queueJudgmentRevision(id, 'dispute', detail, version)
    : request(`/judgments/${id}/dispute`, { method: 'POST', body: JSON.stringify({ detail }) }),
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
  achieveGoal: (id, version) => request(`/goals/${id}/achieve`, { method: 'POST',body:JSON.stringify({request_key:crypto.randomUUID(),expected_version:version}) }),
  failGoal: (id, version) => request(`/goals/${id}/fail`, { method: 'POST',body:JSON.stringify({request_key:crypto.randomUUID(),expected_version:version}) }),
  cancelGoal: (id, version) => request(`/goals/${id}/cancel`, { method: 'POST',body:JSON.stringify({request_key:crypto.randomUUID(),expected_version:version}) }),

  // 设置
  getSettings: () => request('/settings'),
  updateSetting: (key, value) =>
    request('/settings', { method: 'POST', body: JSON.stringify({ key, value }) }),

  // AI 模型配置（BYOK，v1.4）
  getLLMConfig: () => request('/llm-config'),
  putLLMConfig: (payload) =>
    request('/llm-config', { method: 'PUT', body: JSON.stringify(payload) }),
  testLLMConfig: (group) => request('/llm-config/test', {method:'POST',body:JSON.stringify({group})}),

  // 数据导出（文件下载）
  exportData: async (format) => {
    const epoch = accountEpoch
    const controller = new AbortController()
    activeRequests.add(controller)
    let blob
    try {
      const resp = await fetch(`${BASE}/export?format=${format}`, {credentials:'same-origin',signal:controller.signal})
      if (!resp.ok) throw new Error(`导出失败（${resp.status}）`)
      blob = await resp.blob()
      if(epoch !== accountEpoch) throw new Error('账号已切换，导出已取消。')
    } finally { activeRequests.delete(controller) }
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
  getReport: (period) => request(`/report?period=${period}`, { method: 'POST' }),
  listReports: () => request('/reports'),
  getSavedReport: (id) => request(`/reports/${id}`),

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
  acceptChallenge: (id, version) => request(`/challenges/${id}/accept`, { method: 'POST', body:JSON.stringify({request_key:crypto.randomUUID(),expected_version:version}) }),
  // v1.9 F3：候选期切换难度档位（接受后档位锁定，会返回 400）
  switchChallengeVariant: (id, variantIndex) =>
    request(`/challenges/${id}/variant`, {
      method: 'PUT',
      body: JSON.stringify({ variant_index: variantIndex }),
    }),
  completeChallenge: (id, note) =>
    request(`/challenges/${id}/complete`, { method: 'POST', body: JSON.stringify({ note }) }),
  settleChallenge: (id, version) => request(`/challenges/${id}/settle`, { method: 'POST', body:JSON.stringify({request_key:crypto.randomUUID(),expected_version:version}) }),
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
  redeemShopItem: (id, body) => request(`/shop/items/${id}/redeem`, {method:'POST',body:JSON.stringify(body)}),
  redemptionSubmission: (id, key) => request(`/shop/items/${id}/redemption-submissions/${key}`),
  listRedemptions: () => request('/redemptions'),
  fulfillRedemption: (id, note = '') =>
    request(`/redemptions/${id}/fulfill`, { method: 'POST', body: JSON.stringify({ note }) }),

  // ===== 停滞问询（v1.8） =====
  getStagnation: () => request('/stagnation'),
  answerStagnation: (name, stopped, note = '', version) =>
    request(`/stagnation/${encodeURIComponent(name)}/answer`, {
      method: 'POST',
      body: JSON.stringify({ stopped, note, request_key:crypto.randomUUID(), expected_version:version }),
    }),

  // ===== 成就（v1.10 M1） =====
  getAchievements: async () => { await request('/achievements/check', { method: 'POST' }); return request('/achievements') },
  // 处理 AI 发现型里程碑建议：action = 'grant'（追授）/ 'dismiss'（忽略）
  handleAchievement: async (judgmentId, action) =>
    request(`/judgments/${judgmentId}/achievement`, {
      method: 'POST',
      body: JSON.stringify({ action, request_key:crypto.randomUUID(),expected_version:(await request(`/judgments/${judgmentId}`)).updated_at }),
    }),

  // ===== 豁免券（v1.10 M2） =====
  listExemptions: () => request('/exemptions'),
  exemptionSubmission: (key) => request(`/exemption-submissions/${key}`),
  // body: { target_date, period, start_time?, end_time?, reason? }
  buyExemption: (payload) =>
    request('/exemptions', { method: 'POST', body: JSON.stringify(payload) }),

  // ===== 子维度（v1.10 M3） =====
  listSubdimensions: () => request('/subdimensions'),
  // AI 提议细分方向（真实 LLM 调用，调用方需 loading + 防重复）
  proposeSubdimension: (attrId) =>
    request(`/subdimensions/${attrId}/propose`, { method: 'POST' }),
  // 用户勾选确认后才真正创建（多选后确认）
  acceptSubdimension: (attrId, names) =>
    request(`/subdimensions/${attrId}/accept`, {
      method: 'POST',
      body: JSON.stringify({ names }),
    }),
  dismissSubdimension: (attrId) =>
    request(`/subdimensions/${attrId}/dismiss`, { method: 'POST' }),
}
