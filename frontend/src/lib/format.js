export const dash = '–'
export const num = (v, d = 0) => (v === null || v === undefined || Number.isNaN(v) ? dash : Number(v).toLocaleString('en-IN', { minimumFractionDigits: d, maximumFractionDigits: d }))
export const cr = (v) => (v === null || v === undefined ? dash : `₹${num(v)} cr`)
export const pct = (v, d = 1, sign = true) => (v === null || v === undefined || Number.isNaN(v) ? dash : `${sign && v > 0 ? '+' : ''}${Number(v).toFixed(d)}%`)
export const tone = (v) => (v === null || v === undefined || v === 0 ? 'text-muted' : v > 0 ? 'text-up' : 'text-down')
export const price = (v) => (v === null || v === undefined ? dash : `₹${num(v, 2)}`)

export function ago(iso) {
  if (!iso) return ''
  const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z')
  const s = Math.max(0, (Date.now() - d.getTime()) / 1000)
  if (s < 90) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)}m ago`
  if (s < 86400) return `${Math.round(s / 3600)}h ago`
  if (s < 86400 * 7) return `${Math.round(s / 86400)}d ago`
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}
export const when = (iso) => iso ? new Date(iso.endsWith('Z') ? iso : iso + 'Z').toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Kolkata' }) + ' IST' : ''

export const CATEGORY_LABEL = {
  results: 'Results', 'M&A': 'M&A', fund_raise: 'Fund raise', management_change: 'Management change', litigation: 'Litigation',
  insider_trading: 'Insider trading', earnings_call: 'Earnings call', investor_meetings: 'Investor meetings', credit_rating: 'Credit rating',
  dividend: 'Dividend', bonus_split: 'Bonus / split', capex: 'Capex', press_release: 'Press release', postal_ballot: 'Postal ballot',
  agm_egm: 'AGM / EGM', pledging: 'Pledging', unclassified: 'Routine',
}
export const catLabel = (c) => CATEGORY_LABEL[c] || c
export const PRIORITIES = ['critical', 'high', 'medium', 'low']
