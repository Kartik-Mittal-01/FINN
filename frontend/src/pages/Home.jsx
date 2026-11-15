import { useMemo, useState } from 'react'
import { Bell, CheckCheck, ChevronDown, Filter, Newspaper, Radar, RefreshCw } from 'lucide-react'
import { api } from '../lib/api'
import { useApp, useLoad } from '../lib/AppContext'
import { AnnouncementCard, AnnouncementSheet } from '../components/Announcement'
import { Empty, ErrorBox, Segmented, SkeletonList, Skeleton, cx, PriorityBadge, DemoTag } from '../components/ui'
import { CATEGORY_LABEL, ago, catLabel } from '../lib/format'

const WINDOWS = [{ value: '24h', label: '24h' }, { value: '3d', label: '3 days' }, { value: '7d', label: '7 days' }, { value: 'custom', label: 'Custom' }]
const today = () => new Date().toISOString().slice(0, 10)
const daysAgo = (n) => new Date(Date.now() - n * 864e5).toISOString().slice(0, 10)

function Section({ title, tone, items, onOpen, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen)
  if (!items.length) return null
  return (
    <section>
      <button onClick={() => setOpen(!open)} className="mb-2 flex w-full items-center gap-2 text-left" aria-expanded={open}>
        <span className={cx('h-2 w-2 rounded-full', tone)} />
        <h2 className="h-sec">{title}</h2><span className="num text-xs text-faint">{items.length}</span>
        <ChevronDown size={16} className={cx('ml-auto text-faint transition', open && 'rotate-180')} />
      </button>
      {open && <div className="grid gap-3 lg:grid-cols-2">{items.map((a) => <AnnouncementCard key={a.id} a={a} onOpen={onOpen} />)}</div>}
    </section>
  )
}

function AlertsPanel() {
  const { setUnread } = useApp()
  const { data, error, loading, reload } = useLoad(() => api.alerts(), [])
  const [open, setOpen] = useState(false)
  const alerts = data?.alerts || []
  const unread = alerts.filter((a) => !a.read)
  const sev = { critical: 'text-crit', high: 'text-high', info: 'text-info', medium: 'text-med' }
  const readAll = async () => { await api.readAllAlerts(); setUnread(0); reload() }
  const readOne = async (a) => { if (!a.read) { await api.readAlert(a.id); setUnread(Math.max(0, unread.length - 1)); reload() } }
  if (loading) return <Skeleton className="h-16" />
  if (error) return <ErrorBox error={error} onRetry={reload} />
  return (
    <section className="card">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-3 p-4 text-left" aria-expanded={open}>
        <div className="relative grid h-9 w-9 place-items-center rounded-xl bg-raised text-accent"><Bell size={18} />{unread.length > 0 && <span className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-crit" />}</div>
        <div className="min-w-0 flex-1"><p className="font-bold">Alerts</p><p className="text-xs text-muted">{unread.length ? `${unread.length} unread of ${alerts.length}` : alerts.length ? 'All caught up' : 'No alerts match your thresholds'}</p></div>
        <ChevronDown size={18} className={cx('text-faint transition', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="border-t border-line">
          {alerts.length === 0 && <p className="p-4 text-sm text-muted">Nothing has crossed your thresholds. Adjust them in Settings.</p>}
          {unread.length > 0 && <div className="flex justify-end px-4 pt-2"><button onClick={readAll} className="flex items-center gap-1 text-xs font-semibold text-accent"><CheckCheck size={14} /> Mark all read</button></div>}
          <ul className="max-h-80 divide-y divide-line overflow-y-auto">
            {alerts.map((a) => (
              <li key={a.id}>
                <button onClick={() => readOne(a)} className={cx('flex w-full gap-3 px-4 py-3 text-left', a.read && 'opacity-55')}>
                  <span className={cx('mt-1.5 h-2 w-2 shrink-0 rounded-full', a.read ? 'bg-line' : 'bg-accent')} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold"><span className={sev[a.severity] || 'text-muted'}>{a.ticker}</span> · {a.title} {a.is_demo && <DemoTag className="ml-1" />}</p>
                    <p className="mt-0.5 text-xs text-muted">{a.detail}</p>
                  </div>
                  <span className="num shrink-0 text-[11px] text-faint">{ago(a.created_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

export default function Home() {
  const { reloadStatus } = useApp()
  const [win, setWin] = useState('24h')
  const [start, setStart] = useState(daysAgo(14)); const [end, setEnd] = useState(today())
  const [category, setCategory] = useState(''); const [priority, setPriority] = useState(''); const [scope, setScope] = useState('holdings')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [openId, setOpenId] = useState(null)
  const params = useMemo(() => ({ window: win, ...(win === 'custom' ? { start, end } : {}), category, priority, scope }), [win, start, end, category, priority, scope])
  const { data, error, loading, reload } = useLoad(() => api.digest(params), [JSON.stringify(params)])

  const crit = data?.material.filter((a) => a.priority === 'critical') || []
  const high = data?.material.filter((a) => a.priority === 'high') || []
  const med = data?.material.filter((a) => a.priority === 'medium') || []
  const markSeen = async () => { await api.markSeen(); reload(); reloadStatus() }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="h-sec">Push digest</p>
          <h1 className="mt-1 text-2xl font-extrabold tracking-tight md:text-3xl">What needs your attention</h1>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setFiltersOpen(!filtersOpen)} className={cx('btn-ghost', filtersOpen && '!border-accent')} aria-expanded={filtersOpen}><Filter size={16} /> Filters{(category || priority || scope !== 'holdings') && <span className="h-1.5 w-1.5 rounded-full bg-accent" />}</button>
          <button onClick={reload} aria-label="Refresh digest" className="btn-ghost !px-3"><RefreshCw size={16} /></button>
        </div>
      </div>

      <Segmented value={win} onChange={setWin} options={WINDOWS} className="w-full md:w-auto [&>button]:flex-1 md:[&>button]:flex-none" />

      {win === 'custom' && (
        <div className="grid grid-cols-2 gap-3 md:max-w-md">
          <label className="text-xs text-muted">From<input type="date" className="input mt-1" value={start} max={end} onChange={(e) => setStart(e.target.value)} /></label>
          <label className="text-xs text-muted">To<input type="date" className="input mt-1" value={end} min={start} max={today()} onChange={(e) => setEnd(e.target.value)} /></label>
        </div>
      )}

      {filtersOpen && (
        <div className="card grid gap-3 p-4 sm:grid-cols-3">
          <label className="text-xs text-muted">Category
            <select className="input mt-1" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">All categories</option>
              {Object.entries(CATEGORY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="text-xs text-muted">Priority
            <select className="input mt-1" value={priority} onChange={(e) => setPriority(e.target.value)}>
              <option value="">All priorities</option>
              <option value="critical">Critical</option><option value="critical,high">High and above</option><option value="critical,high,medium">Medium and above</option>
            </select>
          </label>
          <label className="text-xs text-muted">Companies
            <select className="input mt-1" value={scope} onChange={(e) => setScope(e.target.value)}>
              <option value="holdings">My portfolio</option><option value="all">All companies in database</option>
            </select>
          </label>
          {(category || priority || scope !== 'holdings') && <button className="btn-ghost sm:col-span-3" onClick={() => { setCategory(''); setPriority(''); setScope('holdings') }}>Clear filters</button>}
        </div>
      )}

      <ErrorBox error={error} onRetry={reload} />

      {loading && !data && <SkeletonList n={4} />}

      {data && (
        <>
          <div className="card overflow-hidden">
            <div className="flex flex-wrap items-center gap-x-6 gap-y-3 p-4">
              <div className="min-w-0 flex-1 basis-60">
                <p className="text-xs text-muted">{data.window.label} · {data.counts.total} filings</p>
                <p className="mt-0.5 text-base font-bold leading-snug">{data.headline}</p>
              </div>
              <div className="flex gap-2">
                {[['critical', data.counts.critical], ['high', data.counts.high], ['medium', data.counts.medium], ['low', data.counts.low]].map(([p, n]) => (
                  <div key={p} className="flex flex-col items-center gap-1"><span className="num text-xl font-extrabold">{n}</span><PriorityBadge priority={p} /></div>
                ))}
              </div>
            </div>
            {data.new_since_last_seen > 0 && (
              <div className="flex flex-wrap items-center gap-3 border-t border-line bg-accent/10 px-4 py-2.5 text-sm">
                <Radar size={16} className="text-accent" />
                <span><strong className="num">{data.new_since_last_seen}</strong> new since your last visit {data.last_seen && <span className="text-muted">({ago(data.last_seen)})</span>}</span>
                <button onClick={markSeen} className="ml-auto flex items-center gap-1 text-xs font-bold text-accent"><CheckCheck size={14} /> Mark seen</button>
              </div>
            )}
          </div>

          <AlertsPanel />

          {data.counts.total === 0 && <Empty icon={Newspaper} title="No filings in this window">Try a longer window{data.mode === 'live' ? ', or pull the latest exchange filings from Settings → Refresh live data.' : '.'}</Empty>}
          <Section title="Critical" tone="bg-crit" items={crit} onOpen={setOpenId} />
          <Section title="High" tone="bg-high" items={high} onOpen={setOpenId} />
          <Section title="Medium" tone="bg-med" items={med} onOpen={setOpenId} />
          <Section title="Routine updates – collapsed" tone="bg-line" items={data.routine} onOpen={setOpenId} defaultOpen={false} />
        </>
      )}
      <AnnouncementSheet id={openId} onClose={() => setOpenId(null)} />
    </div>
  )
}
