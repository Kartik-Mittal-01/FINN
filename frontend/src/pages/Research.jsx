import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, Link } from 'react-router-dom'
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis, Cell, Pie, PieChart } from 'recharts'
import { AlertTriangle, Bot, CheckCircle2, Circle, CircleDashed, Loader2, Microscope, RefreshCw, Search, Upload, XCircle, Minus, TrendingUp, TrendingDown } from 'lucide-react'
import { api } from '../lib/api'
import { useApp } from '../lib/AppContext'
import { Citation, Evidence } from '../components/Citation'
import { Confidence, DemoTag, Empty, ErrorBox, Sheet, Skeleton, Stat, cx } from '../components/ui'
import { cr, num, pct, tone } from '../lib/format'

const AX = { fill: 'rgb(var(--faint))', fontSize: 10 }
const TIP = { contentStyle: { background: 'rgb(var(--surface))', border: '1px solid rgb(var(--line))', borderRadius: 12, fontSize: 12 }, labelStyle: { color: 'rgb(var(--muted))' } }
const C = { rev: 'rgb(var(--info))', ebitda: 'rgb(var(--accent))', pat: 'rgb(var(--warn))', line: 'rgb(var(--crit))', debt: 'rgb(var(--down))', eq: 'rgb(var(--info))' }
const fmtAxis = (v) => (Math.abs(v) >= 1e5 ? `${(v / 1e5).toFixed(1)}L` : Math.abs(v) >= 1e3 ? `${(v / 1e3).toFixed(0)}k` : v)

function SectionCard({ title, subtitle, confidence, note, children, id }) {
  return (
    <section id={id} className="card scroll-mt-24 p-4 md:p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0"><h2 className="text-lg font-extrabold tracking-tight">{title}</h2>{subtitle && <p className="text-xs text-faint">{subtitle}</p>}</div>
        <Confidence c={confidence} />
      </div>
      <div className="mt-4 space-y-4">{children}</div>
      {note && <p className="mt-4 border-t border-line pt-3 text-xs text-faint">{note}</p>}
    </section>
  )
}
const NotApplicable = ({ why }) => <p className="rounded-xl bg-raised p-3 text-sm text-muted">{why || 'Not applicable for this type of company.'}</p>
const Growth = ({ g }) => <span className={cx('num', tone(g?.pct))} title={g?.note || ''}>{g?.pct == null ? 'n.m.' : pct(g.pct)}</span>

function Business({ s }) {
  const colors = ['#10b981', '#60a5fa', '#fbbf24', '#f472b6', '#a78bfa', '#fb923c', '#34d399', '#94a3b8']
  return (
    <SectionCard title={s.title} confidence={s.confidence} note={s.note}>
      {s.description && <p className="text-sm leading-relaxed text-muted">{s.description} <span className="ml-1 text-[11px] text-faint">({s.description_by === 'extractive' ? 'quoted from the report' : s.description_by})</span></p>}
      {s.segments?.length > 0 && (
        <div className="grid items-center gap-4 sm:grid-cols-[180px_1fr]">
          <div style={{ height: 170 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart><Pie data={s.segments.filter((x) => x.pct != null)} dataKey="pct" nameKey="name" innerRadius={44} outerRadius={74} paddingAngle={2} stroke="none">
                {s.segments.map((_, i) => <Cell key={i} fill={colors[i % colors.length]} />)}</Pie><Tooltip formatter={(v) => `${v}%`} {...TIP} /></PieChart>
            </ResponsiveContainer>
          </div>
          <ul className="space-y-2">
            {s.segments.map((x, i) => (
              <li key={x.name} className="flex items-start gap-2 text-sm"><span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: colors[i % colors.length] }} />
                <span className="min-w-0"><strong>{x.name}</strong> <span className="num text-muted">{x.pct != null ? `${x.pct}%` : ''}</span>{x.description && <span className="block text-xs text-faint">{x.description}</span>}</span></li>
            ))}
          </ul>
        </div>
      )}
      {s.evidence?.map((e, i) => <Citation key={i} c={e} n={i + 1} />)}
    </SectionCard>
  )
}

function Snapshot({ s }) {
  const a = s.annual, q = s.quarter
  return (
    <SectionCard title={s.title} subtitle={s.source} confidence={s.confidence}>
      {a && (
        <div>
          <p className="h-sec mb-2">Latest year · {a.period}</p>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Stat label="Revenue" value={cr(a.revenue)} sub={<><Growth g={a.revenue_yoy} /> YoY</>} />
            <Stat label="EBITDA" value={cr(a.ebitda)} sub={a.ebitda_margin != null ? `${a.ebitda_margin}% margin` : 'not reported'} />
            <Stat label="PAT" value={cr(a.pat)} sub={<><Growth g={a.pat_yoy} /> YoY</>} />
            <Stat label="PAT margin" value={a.pat_margin != null ? `${a.pat_margin}%` : '–'} />
            <Stat label="Debt / equity" value={a.debt_to_equity ?? '–'} />
            <Stat label="ROE" value={a.roe != null ? `${a.roe}%` : '–'} />
            <Stat label="ROCE" value={a.roce != null ? `${a.roce}%` : '–'} />
            <Stat label="Cash" value={cr(a.cash)} />
          </div>
        </div>
      )}
      {q && (
        <div>
          <p className="h-sec mb-2">Latest quarter · {q.period}</p>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Stat label="Revenue" value={cr(q.revenue)} sub={<><Growth g={q.revenue_yoy} /> YoY · <Growth g={q.revenue_qoq} /> QoQ</>} />
            <Stat label="EBITDA" value={cr(q.ebitda)} sub={q.ebitda_margin != null ? `${q.ebitda_margin}% margin` : undefined} />
            <Stat label="PAT" value={cr(q.pat)} sub={<><Growth g={q.pat_yoy} /> YoY · <Growth g={q.pat_qoq} /> QoQ</>} />
          </div>
        </div>
      )}
      {(s.notes || []).map((n, i) => <p key={i} className="text-xs text-muted">{n}</p>)}
      <details className="rounded-xl bg-raised p-3 text-xs text-muted">
        <summary className="cursor-pointer font-semibold text-ink">How these are calculated</summary>
        <dl className="mt-2 space-y-1.5">{Object.entries(s.methodology || {}).map(([k, v]) => <div key={k}><dt className="inline font-semibold text-ink">{k.replace(/_/g, ' ')}: </dt><dd className="inline">{v}</dd></div>)}</dl>
      </details>
    </SectionCard>
  )
}

const DIR = { improving: 'text-up', growing: 'text-up', declining: 'text-down', stagnant: 'text-muted', volatile: 'text-warn' }
function Trajectory({ s }) {
  return (
    <SectionCard title={s.title} subtitle={`${s.source} · ₹ crore`} confidence={s.confidence}>
      <div style={{ height: 260 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={s.series} margin={{ left: -8, right: 4, top: 6, bottom: 0 }}>
            <CartesianGrid stroke="rgb(var(--line))" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="period" tick={AX} axisLine={false} tickLine={false} />
            <YAxis yAxisId="l" tick={AX} tickFormatter={fmtAxis} axisLine={false} tickLine={false} width={44} />
            <YAxis yAxisId="r" orientation="right" tick={AX} tickFormatter={(v) => `${v}%`} axisLine={false} tickLine={false} width={40} />
            <Tooltip {...TIP} formatter={(v, n) => (n === 'EBITDA margin' ? [`${v}%`, n] : [num(v), n])} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar yAxisId="l" dataKey="revenue" name="Revenue" fill={C.rev} radius={[4, 4, 0, 0]} />
            <Bar yAxisId="l" dataKey="ebitda" name="EBITDA" fill={C.ebitda} radius={[4, 4, 0, 0]} />
            <Bar yAxisId="l" dataKey="pat" name="PAT" fill={C.pat} radius={[4, 4, 0, 0]} />
            <Line yAxisId="r" dataKey="ebitda_margin" name="EBITDA margin" stroke={C.line} strokeWidth={2} dot={{ r: 2 }} connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <ul className="space-y-2">
        {s.highlights.map((h, i) => (
          <li key={i} className="rounded-xl bg-raised p-3">
            <p className="flex items-center gap-2 text-sm font-semibold">{h.direction === 'declining' ? <TrendingDown size={15} className="text-down" /> : <TrendingUp size={15} className={DIR[h.direction]} />}{h.label} <span className={cx('text-xs font-bold uppercase', DIR[h.direction])}>{h.direction}</span></p>
            <div className="mt-1.5"><Evidence e={h.evidence} /></div>
          </li>
        ))}
      </ul>
    </SectionCard>
  )
}

function BalanceSheet({ s }) {
  return (
    <SectionCard title={s.title} subtitle={s.source} confidence={s.confidence} note={s.note}>
      {!s.applicable ? <NotApplicable why={s.note} /> : (
        <>
          <div style={{ height: 230 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={s.series} margin={{ left: -8, right: 4, top: 6, bottom: 0 }}>
                <CartesianGrid stroke="rgb(var(--line))" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="period" tick={AX} axisLine={false} tickLine={false} />
                <YAxis yAxisId="l" tick={AX} tickFormatter={fmtAxis} axisLine={false} tickLine={false} width={44} />
                <YAxis yAxisId="r" orientation="right" tick={AX} axisLine={false} tickLine={false} width={34} />
                <Tooltip {...TIP} formatter={(v, n) => [n === 'Debt / equity' ? v : num(v), n]} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar yAxisId="l" dataKey="equity" name="Equity" fill={C.eq} radius={[4, 4, 0, 0]} />
                <Bar yAxisId="l" dataKey="debt" name="Debt" fill={C.debt} radius={[4, 4, 0, 0]} />
                <Line yAxisId="r" dataKey="debt_to_equity" name="Debt / equity" stroke={C.pat} strokeWidth={2} dot={{ r: 2 }} connectNulls />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          {s.leverage_direction && <p className="text-sm">Leverage trend: <strong className="capitalize">{s.leverage_direction}</strong>{s.funding && <span className="text-muted"> · funded {s.funding.debt_pct}% debt / {s.funding.equity_pct}% equity ({s.funding.period})</span>}</p>}
          {s.series.some((r) => r.receivable_days != null) && (
            <div className="overflow-x-auto rounded-xl border border-line"><table className="num w-full min-w-[420px] text-xs"><thead className="bg-raised text-muted"><tr><th className="p-2 text-left">Working capital (days)</th>{s.series.slice(-5).map((r) => <th key={r.period} className="p-2 text-right">{r.period}</th>)}</tr></thead>
              <tbody>{[['Receivable', 'receivable_days'], ['Inventory', 'inventory_days'], ['Payable', 'payable_days'], ['Cash cycle', 'cash_cycle_days']].map(([l, k]) => <tr key={k} className="border-t border-line"><td className="p-2">{l}</td>{s.series.slice(-5).map((r) => <td key={r.period} className="p-2 text-right">{r[k] ?? '–'}</td>)}</tr>)}</tbody></table></div>
          )}
          <ul className="space-y-2">{s.highlights.map((h, i) => <li key={i} className="rounded-xl bg-raised p-3 text-sm"><p className="font-semibold">{h.label}</p><div className="mt-1.5"><Evidence e={h.evidence} /></div></li>)}</ul>
        </>
      )}
    </SectionCard>
  )
}

function CashQuality({ s }) {
  return (
    <SectionCard title={s.title} subtitle={s.source} confidence={s.confidence} note={s.note}>
      {!s.applicable ? <NotApplicable why={s.note} /> : (
        <>
          <div style={{ height: 230 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={s.series} margin={{ left: -8, right: 4, top: 6, bottom: 0 }}>
                <CartesianGrid stroke="rgb(var(--line))" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="period" tick={AX} axisLine={false} tickLine={false} />
                <YAxis tick={AX} tickFormatter={fmtAxis} axisLine={false} tickLine={false} width={44} />
                <Tooltip {...TIP} formatter={(v, n) => [num(v), n]} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="pat" name="PAT" fill={C.pat} radius={[4, 4, 0, 0]} />
                <Bar dataKey="cfo" name="Operating cash flow" fill={C.ebitda} radius={[4, 4, 0, 0]} />
                <Line dataKey="fcf" name="Free cash flow" stroke={C.rev} strokeWidth={2} dot={{ r: 2 }} connectNulls />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          {s.verdict && <p className="text-sm">Verdict: <strong className="capitalize">{s.verdict}</strong></p>}
          <ul className="space-y-2">{s.highlights.map((h, i) => <li key={i} className="rounded-xl bg-raised p-3 text-sm"><p className="font-semibold">{h.label}</p><div className="mt-1.5"><Evidence e={h.evidence} /></div></li>)}</ul>
        </>
      )}
    </SectionCard>
  )
}

const STATUS = {
  met: { icon: CheckCircle2, cls: 'text-up bg-up/10 border-up/40', label: 'Delivered' },
  missed: { icon: XCircle, cls: 'text-down bg-down/10 border-down/40', label: 'Missed' },
  tracking: { icon: CircleDashed, cls: 'text-info bg-info/10 border-info/40', label: 'Tracking (H1)' },
  pending: { icon: Circle, cls: 'text-muted bg-raised border-line', label: 'Pending' },
  not_verifiable: { icon: Minus, cls: 'text-muted bg-raised border-line', label: 'Not verifiable' },
}
const MET = { revenue_growth: 'Revenue growth', ebitda_margin: 'EBITDA margin', pat_margin: 'PAT margin', capex: 'Capex', capacity: 'Capacity', outlook: 'Outlook' }
const fmtRange = (r) => (r.unit === 'INR_crore' ? `≈ ₹${num(r.low)} cr` : r.high != null ? `${r.low}–${r.high}%` : `~${r.low}%`)

function Narrative({ s, guidance }) {
  const [filter, setFilter] = useState('all')
  const rows = s.rows.filter((r) => filter === 'all' || r.status === filter)
  const commentary = guidance.items.filter((i) => i.kind === 'commentary')
  return (
    <SectionCard title="Narrative vs numbers" subtitle="What management promised vs what was reported" confidence={s.confidence} note={s.note}>
      {s.rows.length === 0 ? <NotApplicable why="No explicit numeric guidance was found in the earnings-call transcripts available for this company." /> : (
        <>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => setFilter('all')} className={cx('chip', filter === 'all' && '!border-accent !text-accent')}>All {s.rows.length}</button>
            {Object.entries(s.summary).filter(([, n]) => n > 0).map(([k, n]) => <button key={k} onClick={() => setFilter(k)} className={cx('chip', filter === k && '!border-accent !text-accent')}>{STATUS[k].label} {n}</button>)}
          </div>
          <ul className="space-y-3">
            {rows.map((r, i) => {
              const st = STATUS[r.status] || STATUS.pending, Icon = st.icon
              return (
                <li key={i} className="rounded-xl border border-line p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-bold">{r.fy} · {MET[r.metric] || r.metric}</span>
                    <span className={cx('inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-bold', st.cls)}><Icon size={12} /> {st.label}</span>
                    {r.revisions > 1 && <span className="chip !py-0.5" title="Guidance for this year was stated on several calls">stated {r.revisions}×{r.is_latest ? ' · latest' : ''}</span>}
                    {r.is_demo && <DemoTag />}
                  </div>
                  <div className="mt-2 grid gap-2 text-sm sm:grid-cols-2">
                    <div className="rounded-lg bg-raised p-2.5"><p className="h-sec">Guided ({r.call_period})</p><p className="num font-bold">{fmtRange(r.range)}</p></div>
                    <div className="rounded-lg bg-raised p-2.5"><p className="h-sec">{r.actual?.label || 'Reported'}</p><p className="num font-bold">{r.actual ? (r.actual.unit === 'INR_crore' ? `₹${num(r.actual.value)} cr` : `${Number(r.actual.value).toFixed(1)}%`) : '–'}</p></div>
                  </div>
                  <p className="mt-2 text-xs text-muted">{r.detail}</p>
                  <div className="mt-2"><Citation c={r.citation} /></div>
                </li>
              )
            })}
          </ul>
        </>
      )}
      {commentary.length > 0 && (
        <details className="rounded-xl bg-raised p-3 text-sm">
          <summary className="cursor-pointer font-semibold">Qualitative commentary ({commentary.length}) – no numeric target stated</summary>
          <ul className="mt-3 space-y-2">{commentary.map((c, i) => <li key={i}><p className="text-xs text-faint">{MET[c.metric]} · {c.doc_period}</p><Citation c={c.citation} /></li>)}</ul>
        </details>
      )}
    </SectionCard>
  )
}

function BullBear({ s }) {
  const Col = ({ title, items, cls }) => (
    <div className="min-w-0">
      <h3 className={cx('mb-2 text-sm font-extrabold uppercase tracking-wide', cls)}>{title}</h3>
      {items.length === 0 ? <p className="rounded-xl bg-raised p-3 text-sm text-muted">No evidence-backed points found.</p> : (
        <ul className="space-y-2.5">{items.map((p, i) => (
          <li key={i} className="rounded-xl border border-line p-3"><p className="text-sm font-semibold leading-snug">{p.text}</p>
            <details className="mt-2"><summary className="cursor-pointer text-xs font-semibold text-accent">Evidence ({p.evidence.length})</summary><div className="mt-2 space-y-1.5">{p.evidence.map((e, j) => <Evidence key={j} e={e} />)}</div></details></li>
        ))}</ul>
      )}
    </div>
  )
  return (
    <SectionCard title={s.title} subtitle="Every point is backed by reported figures or company text" confidence={s.confidence} note={s.note}>
      <div className="grid gap-5 md:grid-cols-2"><Col title="Bull case" items={s.bull} cls="text-up" /><Col title="Bear case" items={s.bear} cls="text-down" /></div>
    </SectionCard>
  )
}

function Risks({ s }) {
  const FL = { clean: 'text-up', watch: 'text-warn', info: 'text-info' }
  return (
    <SectionCard title={s.title} confidence={s.confidence} note={s.note}>
      {s.flags.length > 0 && <ul className="space-y-2">{s.flags.map((f, i) => <li key={i} className="rounded-xl bg-raised p-3"><p className={cx('flex items-start gap-2 text-sm font-semibold', FL[f.status])}>{f.status === 'watch' ? <AlertTriangle size={15} className="mt-0.5 shrink-0" /> : <CheckCircle2 size={15} className="mt-0.5 shrink-0" />}{f.label}</p><div className="mt-2"><Citation c={f.citation} /></div></li>)}</ul>}
      {s.risks.length > 0 ? (
        <div><p className="h-sec mb-2">Risks stated by management</p><ul className="space-y-2">{s.risks.map((r, i) => <li key={i} className="rounded-xl border border-line p-3"><p className="text-sm font-semibold">{r.text}</p><div className="mt-2"><Citation c={r.citation} /></div></li>)}</ul></div>
      ) : <NotApplicable why="No risk section could be located in the available documents." />}
    </SectionCard>
  )
}

function Coverage({ r }) {
  return (
    <div className="card space-y-3 p-4 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        {r.is_demo ? <DemoTag /> : <span className="chip !text-up">Live sources</span>}
        <span className="text-faint">Generated {new Date(r.generated_at.endsWith('Z') ? r.generated_at : r.generated_at + 'Z').toLocaleString('en-IN')} · {r.generated_by}</span>
      </div>
      {r.data_label && <p className="text-xs text-warn">{r.data_label}</p>}
      <div className="grid gap-x-6 gap-y-1 text-xs text-muted sm:grid-cols-2">
        <p><strong className="text-ink">Financials:</strong> {r.coverage.financial_source} — {r.coverage.annual_periods.length} annual ({r.coverage.annual_periods[0]}–{r.coverage.annual_periods.at(-1)}), {r.coverage.quarterly_periods.length} quarterly periods</p>
        <p><strong className="text-ink">Documents read ({r.coverage.documents.length}):</strong> {r.coverage.documents.map((d) => `${d.period || ''} ${d.type === 'annual_report' ? 'AR' : 'call'}`).join(', ')}</p>
      </div>
      {r.missing?.length > 0 && <ul className="space-y-1">{r.missing.map((m, i) => <li key={i} className="flex gap-2 text-xs text-warn"><AlertTriangle size={13} className="mt-0.5 shrink-0" /> {m}</li>)}</ul>}
      <p className="text-[11px] text-faint">{r.disclaimer}</p>
    </div>
  )
}

function UploadSheet({ ticker, open, onClose, onDone }) {
  const [file, setFile] = useState(null); const [type, setType] = useState('annual_report'); const [period, setPeriod] = useState(''); const [busy, setBusy] = useState(false); const [err, setErr] = useState(null)
  const submit = async (e) => {
    e.preventDefault(); if (!file) return
    setBusy(true); setErr(null)
    try { await api.upload(ticker, file, type, period.trim() || undefined, file.name.replace(/\.pdf$/i, '')); setFile(null); onDone() } catch (x) { setErr(x) } finally { setBusy(false) }
  }
  return (
    <Sheet open={open} onClose={onClose} title={`Upload a document for ${ticker}`}>
      <form onSubmit={submit} className="space-y-4">
        <p className="text-sm text-muted">If automatic discovery missed a document, upload the PDF yourself (annual report or earnings-call transcript). It is processed locally and used exactly like a fetched one.</p>
        <label className="block text-xs text-muted">Type<select className="input mt-1" value={type} onChange={(e) => setType(e.target.value)}><option value="annual_report">Annual report</option><option value="concall">Earnings-call transcript</option></select></label>
        <label className="block text-xs text-muted">Period (optional, e.g. FY26 or Q2FY27)<input className="input mt-1" value={period} onChange={(e) => setPeriod(e.target.value)} placeholder={type === 'annual_report' ? 'FY26' : 'Q2FY27'} /></label>
        <label className="block text-xs text-muted">PDF file<input type="file" accept="application/pdf,.pdf" className="input mt-1 !py-2" onChange={(e) => setFile(e.target.files?.[0] || null)} /></label>
        <ErrorBox error={err} />
        <button className="btn-primary w-full" disabled={!file || busy}>{busy ? <><Loader2 className="animate-spin" size={16} /> Processing…</> : <><Upload size={16} /> Upload & extract</>}</button>
      </form>
    </Sheet>
  )
}

function Progress({ job }) {
  const names = { validate: 'Resolving company', discover: 'Finding & reading primary documents', analyse: 'Building evidence-grounded report' }
  return (
    <div className="card p-5">
      <div className="flex items-center gap-3"><Loader2 className="animate-spin text-accent" size={20} /><p className="font-bold">Researching {job.ticker}…</p></div>
      <ul className="mt-4 space-y-2.5 text-sm">
        {job.steps.map((s, i) => (
          <li key={i} className="flex items-start gap-2.5">
            {s.state === 'done' ? <CheckCircle2 size={16} className="mt-0.5 text-up" /> : s.state === 'error' ? <XCircle size={16} className="mt-0.5 text-down" /> : s.state === 'skipped' ? <Minus size={16} className="mt-0.5 text-faint" /> : <Loader2 size={16} className="mt-0.5 animate-spin text-accent" />}
            <span><span className="font-semibold">{names[s.step] || s.step}</span><span className="block text-xs text-muted">{s.detail}</span></span>
          </li>
        ))}
      </ul>
      <p className="mt-4 text-xs text-faint">For a new company this downloads annual reports and call transcripts from public sources and can take a minute or two.</p>
    </div>
  )
}

const QUICK = ['TCS', 'RELIANCE', 'HDFCBANK', 'TATASTEEL', 'ITC', 'ETERNAL']

export default function Research() {
  const { ticker: param } = useParams()
  const nav = useNavigate()
  const { demo, version } = useApp()
  const [input, setInput] = useState(param || '')
  const [report, setReport] = useState(null); const [job, setJob] = useState(null); const [error, setError] = useState(null); const [loading, setLoading] = useState(false)
  const [uploadOpen, setUploadOpen] = useState(false)
  const timer = useRef(null)
  const ticker = param?.toUpperCase()

  const stopPoll = () => { clearInterval(timer.current); timer.current = null }
  const load = useCallback(async (t) => {
    stopPoll(); setError(null); setReport(null); setJob(null); setLoading(true)
    try {
      const st = await api.researchStatus(t)
      if (st.job?.state === 'running') { setJob(st.job); poll(t); return }
      if (st.has_report) { setReport(await api.report(t)); return }
      const r = await api.runResearch(t); setJob(r.job); poll(t)
    } catch (e) { setError(e) } finally { setLoading(false) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  function poll(t) {
    stopPoll()
    timer.current = setInterval(async () => {
      try {
        const st = await api.researchStatus(t)
        if (st.job) setJob(st.job)
        if (st.job?.state === 'done') { stopPoll(); setReport(await api.report(t)); setJob(null) }
        else if (st.job?.state === 'error') { stopPoll(); setError(new Error(st.job.error || 'Research failed')); setJob(null) }
      } catch (e) { stopPoll(); setError(e) }
    }, 1200)
  }
  const rerun = async (refresh) => { stopPoll(); setError(null); setReport(null); try { const r = await api.runResearch(ticker, refresh); setJob(r.job); poll(ticker) } catch (e) { setError(e) } }
  useEffect(() => { if (ticker) { setInput(ticker); load(ticker) } else { stopPoll(); setReport(null); setJob(null); setError(null) } return stopPoll }, [ticker, version, load])

  const go = (e) => { e?.preventDefault(); const t = input.trim().toUpperCase().replace(/\.(NS|BO)$/, ''); if (t) nav(`/research/${t}`) }
  const S = report?.sections
  const insufficient = report && report.status !== 'ok'

  return (
    <div className="space-y-5">
      <div><p className="h-sec">Pull · on-demand research</p><h1 className="mt-1 text-2xl font-extrabold tracking-tight md:text-3xl">Research any NSE company</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted">Built only from the company's own annual reports and earnings-call transcripts. No broker reports, no news, no model memory — every claim carries its source page.</p></div>

      <form onSubmit={go} className="flex gap-2 md:max-w-xl">
        <div className="relative flex-1"><Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
          <input className="input !pl-9 uppercase" placeholder="NSE ticker, e.g. TCS" value={input} onChange={(e) => setInput(e.target.value)} aria-label="NSE ticker" autoCapitalize="characters" /></div>
        <button className="btn-primary">Research</button>
      </form>
      {!ticker && (
        <div className="space-y-3">
          <p className="h-sec">{demo ? 'Companies in the sample dataset' : 'Try one'}</p>
          <div className="flex flex-wrap gap-2">{QUICK.map((t) => <Link key={t} to={`/research/${t}`} className="chip !py-2 hover:!border-accent hover:!text-accent">{t}</Link>)}</div>
          {demo ? <p className="text-xs text-warn">Demo mode: only the 18 sample companies have (synthetic) documents. Switch to Live in Settings to research any ticker from real filings.</p>
            : <p className="text-xs text-muted">Live mode: FINN finds annual reports and concall transcripts on screener.in / company IR pages, reads them, and builds the report. First run for a company can take a couple of minutes.</p>}
        </div>
      )}

      <ErrorBox error={error} onRetry={ticker ? () => load(ticker) : undefined} />
      {(loading && !job && !report) && <div className="space-y-3"><Skeleton className="h-40" /><Skeleton className="h-64" /></div>}
      {job && <Progress job={job} />}

      {report && (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <div className="min-w-0 flex-1"><h2 className="text-xl font-extrabold">{report.company} <span className="text-muted">· {report.ticker}</span></h2><p className="text-xs text-faint">{report.sector}</p></div>
            <Link to={`/copilot/${report.ticker}`} className="btn-primary"><Bot size={16} /> Ask Copilot</Link>
            <button onClick={() => rerun(true)} className="btn-ghost"><RefreshCw size={16} /> Refresh</button>
            <button onClick={() => setUploadOpen(true)} className="btn-ghost"><Upload size={16} /> Add document</button>
          </div>
          <Coverage r={report} />
          {insufficient ? (
            <Empty icon={Microscope} title="Not enough primary data to build a report">{report.missing?.[0] || 'No financials or documents were found for this ticker.'} You can upload an annual report or transcript PDF to proceed.</Empty>
          ) : (
            <>
              <nav className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 md:mx-0 md:px-0" aria-label="Report sections">
                {[['business', 'Business'], ['snapshot', 'Snapshot'], ['trajectory', 'Trajectory'], ['balance', 'Balance sheet'], ['cash', 'Cash'], ['narrative', 'Narrative'], ['bullbear', 'Bull/Bear'], ['risks', 'Risks']].map(([id, l]) => <a key={id} href={`#r-${id}`} className="chip shrink-0 !py-1.5">{l}</a>)}
              </nav>
              <div className="space-y-4">
                <div id="r-business" className="scroll-mt-24"><Business s={S.business} /></div>
                <div id="r-snapshot" className="scroll-mt-24"><Snapshot s={S.snapshot} /></div>
                <div id="r-trajectory" className="scroll-mt-24"><Trajectory s={S.trajectory} /></div>
                <div id="r-balance" className="scroll-mt-24"><BalanceSheet s={S.balance_sheet} /></div>
                <div id="r-cash" className="scroll-mt-24"><CashQuality s={S.cash_quality} /></div>
                <div id="r-narrative" className="scroll-mt-24"><Narrative s={S.narrative} guidance={S.guidance} /></div>
                <div id="r-bullbear" className="scroll-mt-24"><BullBear s={S.bull_bear} /></div>
                <div id="r-risks" className="scroll-mt-24"><Risks s={S.risks} /></div>
              </div>
            </>
          )}
        </>
      )}
      {ticker && error && <button className="btn-ghost" onClick={() => setUploadOpen(true)}><Upload size={16} /> Upload a document manually</button>}
      {ticker && <UploadSheet ticker={ticker} open={uploadOpen} onClose={() => setUploadOpen(false)} onDone={() => { setUploadOpen(false); rerun(false) }} />}
    </div>
  )
}
