// Thin fetch wrapper. Every failure becomes an Error with a human-readable message (the backend sends {detail}).
async function request(path, { method = 'GET', body, form } = {}) {
  const opts = { method, headers: {} }
  if (form) opts.body = form
  else if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body) }
  let res
  try { res = await fetch('/api' + path, opts) } catch { throw new Error('Cannot reach the FINN backend. Is it running on port 8000?') }
  if (!res.ok) {
    let msg = `Request failed (${res.status})`
    try { const j = await res.json(); if (j.detail) msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail) } catch { /* not json */ }
    throw new Error(msg)
  }
  return res.json()
}
const qs = (o) => { const p = new URLSearchParams(); Object.entries(o || {}).forEach(([k, v]) => v !== undefined && v !== null && v !== '' && p.set(k, v)); const s = p.toString(); return s ? '?' + s : '' }

export const api = {
  status: () => request('/system/status'),
  setMode: (mode) => request('/system/mode', { method: 'POST', body: { mode } }),
  loadDemo: () => request('/system/demo/load', { method: 'POST' }),
  refreshLive: () => request('/system/refresh', { method: 'POST' }),
  digest: (p) => request('/digest' + qs(p)),
  announcements: (p) => request('/announcements' + qs(p)),
  announcement: (id) => request(`/announcements/${id}`),
  markSeen: () => request('/digest/seen', { method: 'POST' }),
  portfolio: () => request('/portfolio'),
  exposure: () => request('/portfolio/exposure'),
  addHolding: (ticker, kind = 'portfolio') => request('/portfolio', { method: 'POST', body: { ticker, kind } }),
  removeHolding: (t) => request(`/portfolio/${encodeURIComponent(t)}`, { method: 'DELETE' }),
  search: (q) => request('/companies/search' + qs({ q })),
  history: (t, days = 120) => request(`/market/${encodeURIComponent(t)}/history` + qs({ days })),
  alerts: () => request('/alerts'),
  alertSettings: () => request('/alerts/settings'),
  saveAlertSettings: (s) => request('/alerts/settings', { method: 'PUT', body: s }),
  evaluateAlerts: () => request('/alerts/evaluate', { method: 'POST' }),
  readAlert: (id) => request(`/alerts/${id}/read`, { method: 'POST' }),
  readAllAlerts: () => request('/alerts/read-all', { method: 'POST' }),
  runResearch: (t, refresh = false) => request(`/research/${encodeURIComponent(t)}/run` + qs({ refresh: refresh || undefined }), { method: 'POST' }),
  researchStatus: (t) => request(`/research/${encodeURIComponent(t)}/status`),
  report: (t) => request(`/research/${encodeURIComponent(t)}`),
  documents: (t) => request(`/research/${encodeURIComponent(t)}/documents`),
  upload: (t, file, doc_type, period, title) => {
    const f = new FormData(); f.append('file', file); f.append('doc_type', doc_type)
    if (period) f.append('period', period); if (title) f.append('title', title)
    return request(`/research/${encodeURIComponent(t)}/upload`, { method: 'POST', form: f })
  },
  suggestions: () => request('/copilot/suggestions'),
  chat: (ticker, message, conversation_id) => request('/copilot/chat', { method: 'POST', body: { ticker, message, conversation_id } }),
  conversations: (ticker) => request('/copilot/conversations' + qs({ ticker })),
  conversation: (id) => request(`/copilot/conversations/${id}`),
  deleteConversation: (id) => request(`/copilot/conversations/${id}`, { method: 'DELETE' }),
}
