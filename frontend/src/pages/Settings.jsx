import { useEffect, useState } from 'react'
import { Cpu, Database, Download, FlaskConical, Loader2, Moon, RefreshCw, Save, Sun, Wifi } from 'lucide-react'
import { api } from '../lib/api'
import { useApp, useLoad } from '../lib/AppContext'
import { ErrorBox, Segmented, Skeleton, Toggle, cx } from '../components/ui'
import { CATEGORY_LABEL } from '../lib/format'

function Block({ icon: Icon, title, children }) {
  return <section className="card p-4 md:p-5"><h2 className="mb-4 flex items-center gap-2 text-base font-extrabold"><Icon size={17} className="text-accent" /> {title}</h2><div className="space-y-4">{children}</div></section>
}
const Row = ({ label, hint, children }) => <div className="flex items-center justify-between gap-4"><div className="min-w-0"><p className="text-sm font-semibold">{label}</p>{hint && <p className="text-xs text-muted">{hint}</p>}</div>{children}</div>

function DataSection() {
  const { status, demo, refreshAll } = useApp()
  const [busy, setBusy] = useState(''); const [msg, setMsg] = useState(null); const [err, setErr] = useState(null)
  const run = async (key, fn, ok) => {
    setBusy(key); setErr(null); setMsg(null)
    try { const r = await fn(); setMsg(ok(r)); await refreshAll() } catch (e) { setErr(e) } finally { setBusy('') }
  }
  return (
    <Block icon={Database} title="Data source">
      <Row label="Mode" hint={demo ? 'Synthetic sample data (labelled everywhere).' : 'Public exchange data via yfinance / NSE / BSE.'}>
        <Segmented value={status?.mode || 'demo'} onChange={(m) => run('mode', () => api.setMode(m), () => `Switched to ${m} mode.`)} options={[{ value: 'demo', label: 'Demo' }, { value: 'live', label: 'Live' }]} />
      </Row>
      {status && <p className="rounded-xl bg-raised p-3 text-xs text-muted"><span className="num font-semibold text-ink">{status.counts.holdings}</span> companies · <span className="num font-semibold text-ink">{status.counts.announcements}</span> filings · <span className="num font-semibold text-ink">{status.counts.documents}</span> documents · <span className="num font-semibold text-ink">{status.counts.price_bars}</span> price bars{status.latest_price_date && <> · prices to <span className="num font-semibold text-ink">{status.latest_price_date}</span></>} <span className="ml-1">({status.mode})</span></p>}
      <div className="flex flex-wrap gap-2">
        <button className="btn-ghost" disabled={!!busy} onClick={() => run('demo', api.loadDemo, () => 'Sample dataset reloaded.')}>{busy === 'demo' ? <Loader2 size={16} className="animate-spin" /> : <FlaskConical size={16} />} Load / reset demo data</button>
        <button className="btn-primary" disabled={!!busy || demo} onClick={() => run('live', api.refreshLive, (r) => {
            const n = Object.values(r.announcements || {}).reduce((x, y) => x + y, 0)
            const errs = [...(r.announcement_errors || []), ...Object.entries(r.price_errors || {}).map(([t, m]) => `${t}: ${m}`)]
            return `Prices updated for ${r.prices_ok}/${r.prices_total} companies; ${n} filings ingested.${errs.length ? ` ${errs.length} source issue(s): ${errs.slice(0, 2).join('; ')}` : ''}`
          })}>{busy === 'live' ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />} Refresh live data</button>
      </div>
      {demo && <p className="text-xs text-muted">Refreshing live data is available in Live mode. It needs internet access to Yahoo Finance and the exchanges; some may rate-limit or block automated requests.</p>}
      {msg && <p className="rounded-xl bg-up/10 p-3 text-sm text-up" role="status">{msg}</p>}
      <ErrorBox error={err} />
    </Block>
  )
}

function AlertSettings() {
  const { data, error, loading } = useLoad(() => api.alertSettings(), [])
  const hold = useLoad(() => api.portfolio(), [])
  const { refreshAll } = useApp()
  const [s, setS] = useState(null); const [saved, setSaved] = useState(false); const [err, setErr] = useState(null); const [busy, setBusy] = useState(false)
  useEffect(() => { if (data) setS(data.settings) }, [data])
  if (loading || !s) return <Block icon={Wifi} title="Alerts">{error ? <ErrorBox error={error} /> : <Skeleton className="h-48" />}</Block>
  const set = (k, v) => { setSaved(false); setS((x) => ({ ...x, [k]: v })) }
  const toggle = (k, v) => set(k, s[k].includes(v) ? s[k].filter((x) => x !== v) : [...s[k], v])
  const save = async () => { setBusy(true); setErr(null); try { await api.saveAlertSettings(s); setSaved(true); await refreshAll() } catch (e) { setErr(e) } finally { setBusy(false) } }
  const tickers = (hold.data?.holdings || []).map((h) => h.ticker)
  return (
    <Block icon={Wifi} title="Alerts">
      <Row label="Alerts enabled"><Toggle checked={s.enabled} onChange={(v) => set('enabled', v)} label="Alerts enabled" /></Row>
      <div>
        <div className="flex items-baseline justify-between"><label htmlFor="pt" className="text-sm font-semibold">Price move threshold</label><span className="num text-sm font-bold text-accent">±{s.price_threshold_pct}%</span></div>
        <input id="pt" type="range" min="0.5" max="10" step="0.5" value={s.price_threshold_pct} onChange={(e) => set('price_threshold_pct', +e.target.value)} className="mt-2 w-full accent-[rgb(var(--accent))]" />
        <p className="text-xs text-muted">Alert when a daily close moves more than this vs the previous close.</p>
      </div>
      <div>
        <div className="flex items-baseline justify-between"><label htmlFor="vm" className="text-sm font-semibold">Volume spike</label><span className="num text-sm font-bold text-accent">{s.volume_multiple}× 20-day avg</span></div>
        <input id="vm" type="range" min="1" max="10" step="0.5" value={s.volume_multiple} onChange={(e) => set('volume_multiple', +e.target.value)} className="mt-2 w-full accent-[rgb(var(--accent))]" />
        <p className="text-xs text-muted">Alert when volume exceeds this multiple of the prior 20-session average.</p>
      </div>
      <div>
        <p className="mb-2 text-sm font-semibold">Minimum filing priority</p>
        <Segmented value={s.min_priority} onChange={(v) => set('min_priority', v)} options={['low', 'medium', 'high', 'critical'].map((v) => ({ value: v, label: v[0].toUpperCase() + v.slice(1) }))} />
      </div>
      <div>
        <div className="mb-2 flex items-center justify-between"><p className="text-sm font-semibold">Categories <span className="font-normal text-muted">({s.categories.length ? s.categories.length : 'all'} selected)</span></p>
          <button className="text-xs font-semibold text-accent" onClick={() => set('categories', [])}>All</button></div>
        <div className="flex flex-wrap gap-2">{data.all_categories.map((c) => <button key={c} onClick={() => toggle('categories', c)} aria-pressed={s.categories.includes(c)} className={cx('chip', s.categories.includes(c) && '!border-accent !bg-accent/15 !text-accent')}>{CATEGORY_LABEL[c] || c}</button>)}</div>
        <p className="mt-1.5 text-xs text-muted">Leave empty to alert on every category.</p>
      </div>
      <div>
        <div className="mb-2 flex items-center justify-between"><p className="text-sm font-semibold">Companies <span className="font-normal text-muted">({s.tickers.length ? s.tickers.length : 'all'} selected)</span></p>
          <button className="text-xs font-semibold text-accent" onClick={() => set('tickers', [])}>All</button></div>
        <div className="flex flex-wrap gap-1.5">{tickers.map((t) => <button key={t} onClick={() => toggle('tickers', t)} aria-pressed={s.tickers.includes(t)} className={cx('chip', s.tickers.includes(t) && '!border-accent !bg-accent/15 !text-accent')}>{t}</button>)}</div>
      </div>
      <ErrorBox error={err} />
      <button className="btn-primary w-full sm:w-auto" onClick={save} disabled={busy}>{busy ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />} Save & re-evaluate alerts</button>
      {saved && <p className="text-sm text-up" role="status">Saved. Alerts re-evaluated against the new thresholds.</p>}
    </Block>
  )
}

export default function SettingsPage() {
  const { status, theme, setTheme } = useApp()
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div><p className="h-sec">Settings</p><h1 className="mt-1 text-2xl font-extrabold tracking-tight md:text-3xl">Preferences</h1></div>
      <DataSection />
      <AlertSettings />
      <Block icon={Cpu} title="AI engine">
        <Row label="Local LLM (optional)" hint="Only used to refine ambiguous classifications and polish prose. Every LLM output is checked against the source before it is shown.">
          <span className={cx('chip', status?.llm.available ? '!text-up' : '!text-muted')}>{status?.llm.available ? `${status.llm.provider}:${status.llm.model}` : 'Not running'}</span>
        </Row>
        <Row label="Retrieval" hint="Per-company TF-IDF over document passages; no data leaves your machine."><span className="chip">{status?.embeddings || '–'}</span></Row>
        {!status?.llm.available && <p className="rounded-xl bg-raised p-3 text-xs text-muted">FINN is fully functional without an LLM — classification, extraction, scoring, calculations and answers are deterministic. To enable the optional model: install Ollama, run <code className="font-mono text-ink">ollama pull {status?.llm.model || 'llama3.2:3b'}</code>, and set <code className="font-mono text-ink">LLM_PROVIDER=ollama</code>.</p>}
      </Block>
      <Block icon={theme === 'dark' ? Moon : Sun} title="Appearance">
        <Row label="Theme"><Segmented value={theme} onChange={setTheme} options={[{ value: 'dark', label: 'Dark' }, { value: 'light', label: 'Light' }]} /></Row>
      </Block>
      <p className="px-1 text-xs text-faint">FINN summarises public documents for research purposes. It is not investment advice. Prices are end-of-day and may be delayed or unavailable.</p>
    </div>
  )
}
