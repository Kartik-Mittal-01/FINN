import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, Bar, BarChart } from 'recharts'
import { Bot, Microscope, Plus, Search, Trash2, TrendingDown, TrendingUp, Wallet } from 'lucide-react'
import { api } from '../lib/api'
import { useApp, useLoad } from '../lib/AppContext'
import Spark from '../components/Spark'
import { DemoTag, Empty, ErrorBox, Sheet, Skeleton, SkeletonList, cx, PriorityBadge } from '../components/ui'
import { num, pct, price, tone } from '../lib/format'

function AddHolding({ onAdded }) {
  const [q, setQ] = useState(''); const [res, setRes] = useState([]); const [busy, setBusy] = useState(false); const [err, setErr] = useState(null)
  useEffect(() => {
    if (!q.trim()) { setRes([]); return }
    const t = setTimeout(() => api.search(q.trim()).then((r) => setRes(r.results)).catch(() => setRes([])), 220)
    return () => clearTimeout(t)
  }, [q])
  const add = async (ticker) => {
    setBusy(true); setErr(null)
    try { await api.addHolding(ticker); setQ(''); setRes([]); onAdded() } catch (e) { setErr(e) } finally { setBusy(false) }
  }
  const typed = q.trim().toUpperCase().replace(/\.(NS|BO)$/, '')
  return (
    <div className="card p-4">
      <p className="h-sec mb-2">Add a company</p>
      <div className="relative">
        <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
        <input className="input !pl-9" placeholder="Search name or NSE ticker (e.g. INFY)" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search companies" />
      </div>
      {q.trim() && (
        <ul className="mt-2 divide-y divide-line overflow-hidden rounded-xl border border-line">
          {res.map((r) => (
            <li key={r.ticker} className="flex items-center gap-3 px-3 py-2.5">
              <div className="min-w-0 flex-1"><p className="text-sm font-bold">{r.ticker} <span className="font-normal text-muted">· {r.name}</span></p><p className="text-xs text-faint">{r.sector}</p></div>
              {r.held ? <span className="text-xs text-faint">In portfolio</span> : <button disabled={busy} onClick={() => add(r.ticker)} className="btn-primary !min-h-[34px] !px-3"><Plus size={14} /> Add</button>}
            </li>
          ))}
          {/^[A-Z0-9&-]{1,20}$/.test(typed) && !res.some((r) => r.ticker === typed) && (
            <li className="flex items-center gap-3 px-3 py-2.5">
              <p className="min-w-0 flex-1 text-sm">Add <strong>{typed}</strong> as an NSE ticker <span className="text-xs text-faint">(not in our directory)</span></p>
              <button disabled={busy} onClick={() => add(typed)} className="btn-ghost !min-h-[34px] !px-3"><Plus size={14} /> Add</button>
            </li>
          )}
        </ul>
      )}
      <ErrorBox error={err} />
    </div>
  )
}

function Exposure() {
  const { data, error, loading } = useLoad(() => api.exposure(), [])
  if (loading) return <Skeleton className="h-56" />
  if (error) return <ErrorBox error={error} />
  const p = data.performance
  const sectors = [...data.sectors].sort((a, b) => b.weight_pct - a.weight_pct)
  return (
    <div className="card p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2"><p className="h-sec">Portfolio snapshot</p><p className="text-[11px] text-faint">{data.weighting}</p></div>
      <div className="mt-3 grid grid-cols-3 gap-3 text-center">
        {[['Day', p.day], ['Week', p.week], ['Month', p.month]].map(([l, v]) => (
          <div key={l} className="rounded-xl bg-raised py-2.5"><p className="text-[11px] text-faint">{l}</p><p className={cx('num text-lg font-extrabold', tone(v))}>{pct(v, 2)}</p></div>
        ))}
      </div>
      <p className="mt-2 text-center text-xs text-muted"><span className="font-semibold text-up">{p.advancers} up</span> · <span className="font-semibold text-down">{p.decliners} down</span> today</p>
      <p className="h-sec mb-1 mt-4">Sector exposure</p>
      <div style={{ height: Math.max(120, sectors.length * 26) }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={sectors} layout="vertical" margin={{ left: 0, right: 24, top: 0, bottom: 0 }}>
            <XAxis type="number" hide domain={[0, 'dataMax']} />
            <YAxis type="category" dataKey="sector" width={110} tick={{ fill: 'rgb(var(--muted))', fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip cursor={{ fill: 'rgb(var(--raised))' }} formatter={(v) => [`${v}%`, 'Weight']} contentStyle={{ background: 'rgb(var(--surface))', border: '1px solid rgb(var(--line))', borderRadius: 12, fontSize: 12 }} />
            <Bar dataKey="weight_pct" fill="rgb(var(--accent))" radius={[0, 6, 6, 0]} barSize={14} label={{ position: 'right', fill: 'rgb(var(--muted))', fontSize: 11, formatter: (v) => `${v}%` }} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function HoldingSheet({ h, onClose, onRemove }) {
  const { data, loading, error } = useLoad(() => (h ? api.history(h.ticker, 120) : Promise.resolve(null)), [h?.ticker])
  if (!h) return null
  const s = h.stats
  const bars = (data?.bars || []).map((b) => ({ d: b.date.slice(5), c: b.close, v: b.volume }))
  const up = (s.month_pct ?? 0) >= 0
  return (
    <Sheet open onClose={onClose} title={`${h.ticker} · ${h.name}`} wide>
      <div className="space-y-4">
        <div className="flex flex-wrap items-end gap-x-4 gap-y-1">
          <p className="num text-3xl font-extrabold">{price(s.close)}</p>
          <p className={cx('num text-lg font-bold', tone(s.change_pct))}>{pct(s.change_pct, 2)}</p>
          {data?.source === 'demo' && <DemoTag />}
        </div>
        {s.available ? (
          <>
            <div style={{ height: 220 }}>
              {loading ? <Skeleton className="h-full" /> : (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={bars} margin={{ left: 0, right: 4, top: 6, bottom: 0 }}>
                    <defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={up ? 'rgb(var(--up))' : 'rgb(var(--down))'} stopOpacity={0.35} /><stop offset="100%" stopColor={up ? 'rgb(var(--up))' : 'rgb(var(--down))'} stopOpacity={0} /></linearGradient></defs>
                    <CartesianGrid stroke="rgb(var(--line))" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="d" tick={{ fill: 'rgb(var(--faint))', fontSize: 10 }} interval={Math.floor(bars.length / 5)} axisLine={false} tickLine={false} />
                    <YAxis domain={['auto', 'auto']} width={44} tick={{ fill: 'rgb(var(--faint))', fontSize: 10 }} axisLine={false} tickLine={false} />
                    <Tooltip formatter={(v) => [price(v), 'Close']} contentStyle={{ background: 'rgb(var(--surface))', border: '1px solid rgb(var(--line))', borderRadius: 12, fontSize: 12 }} />
                    <Area type="monotone" dataKey="c" stroke={up ? 'rgb(var(--up))' : 'rgb(var(--down))'} strokeWidth={2} fill="url(#g)" />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </div>
            <ErrorBox error={error} />
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[['1 week', pct(s.week_pct), tone(s.week_pct)], ['1 month', pct(s.month_pct), tone(s.month_pct)], ['Volume vs 20d avg', s.volume_ratio ? `${s.volume_ratio.toFixed(1)}×` : '–', s.volume_ratio >= 2 ? 'text-warn' : ''], ['30d volatility', s.volatility_30d ? `${s.volatility_30d.toFixed(1)}%` : '–', '']].map(([l, v, c]) => (
                <div key={l} className="rounded-xl bg-raised p-3"><p className="text-[11px] text-faint">{l}</p><p className={cx('num text-base font-bold', c)}>{v}</p></div>
              ))}
            </div>
            <p className="text-xs text-faint">End-of-day closes as of {s.as_of} · source: {s.source}{s.stale_days > 3 ? ` · ${s.stale_days} days old` : ''}. Not real-time.</p>
          </>
        ) : <p className="rounded-xl bg-raised p-3 text-sm text-muted">{s.note || 'No price data available.'}</p>}
        <div className="flex flex-wrap gap-2">
          <Link to={`/research/${h.ticker}`} className="btn-primary" onClick={onClose}><Microscope size={16} /> Research</Link>
          <Link to={`/copilot/${h.ticker}`} className="btn-ghost" onClick={onClose}><Bot size={16} /> Ask Copilot</Link>
          <button className="btn-ghost ml-auto !text-down" onClick={() => onRemove(h.ticker)}><Trash2 size={16} /> Remove</button>
        </div>
      </div>
    </Sheet>
  )
}

export default function Portfolio() {
  const { reloadStatus } = useApp()
  const { data, error, loading, reload } = useLoad(() => api.portfolio(), [])
  const [sel, setSel] = useState(null)
  const [sort, setSort] = useState('alerts')
  const holdings = [...(data?.holdings || [])].sort((a, b) => {
    if (sort === 'name') return a.ticker.localeCompare(b.ticker)
    if (sort === 'move') return Math.abs(b.stats.change_pct || 0) - Math.abs(a.stats.change_pct || 0)
    return (b.last_24h.critical * 100 + b.last_24h.high * 10 + b.last_24h.total) - (a.last_24h.critical * 100 + a.last_24h.high * 10 + a.last_24h.total)
  })
  const changed = () => { reload(); reloadStatus() }
  const remove = async (t) => { await api.removeHolding(t); setSel(null); changed() }
  return (
    <div className="space-y-5">
      <div><p className="h-sec">Portfolio</p><h1 className="mt-1 text-2xl font-extrabold tracking-tight md:text-3xl">Your companies</h1></div>
      <ErrorBox error={error} onRetry={reload} />
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm text-muted">{data ? `${holdings.length} companies` : ' '}</p>
            <div className="flex items-center gap-1.5 text-xs text-muted">Sort
              <select className="rounded-lg border border-line bg-raised px-2 py-1.5 text-xs text-ink" value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort holdings">
                <option value="alerts">Most news</option><option value="move">Biggest move</option><option value="name">Ticker</option>
              </select>
            </div>
          </div>
          {loading && !data && <SkeletonList n={6} h="h-[72px]" />}
          {data && holdings.length === 0 && <Empty icon={Wallet} title="No companies yet">Add a company to start receiving its filings in your digest.</Empty>}
          {holdings.map((h) => {
            const s = h.stats
            return (
              <button key={h.ticker} onClick={() => setSel(h)} className="card flex w-full items-center gap-3 p-3.5 text-left transition hover:border-accent/50">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1"><p className="font-extrabold">{h.ticker}</p>
                    {h.last_24h.critical > 0 && <PriorityBadge priority="critical" score={h.last_24h.critical} />}
                    {h.last_24h.high > 0 && <PriorityBadge priority="high" score={h.last_24h.high} />}
                  </div>
                  <p className="truncate text-xs text-muted">{h.name} · {h.sector}</p>
                </div>
                {s.available ? (
                  <>
                    <div className="shrink-0"><Spark data={s.spark} up={(s.month_pct ?? 0) >= 0} /></div>
                    <div className="w-[88px] shrink-0 text-right">
                      <p className="num text-sm font-bold">{price(s.close)}</p>
                      <p className={cx('num flex items-center justify-end gap-0.5 text-xs font-semibold', tone(s.change_pct))}>{s.change_pct > 0 ? <TrendingUp size={12} /> : s.change_pct < 0 ? <TrendingDown size={12} /> : null}{pct(s.change_pct, 2)}</p>
                      {s.volume_ratio >= 2 && <p className="num text-[10px] font-bold text-warn">{s.volume_ratio.toFixed(1)}× vol</p>}
                    </div>
                  </>
                ) : <p className="max-w-[40%] text-right text-xs text-faint">{s.note || 'No price data'}</p>}
              </button>
            )
          })}
        </div>
        <div className="min-w-0 space-y-4">
          <AddHolding onAdded={changed} />
          {data && <Exposure key={holdings.length} />}
        </div>
      </div>
      <HoldingSheet h={sel} onClose={() => setSel(null)} onRemove={remove} />
    </div>
  )
}
