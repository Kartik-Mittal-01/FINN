import { useState } from 'react'
import { ChevronRight, ExternalLink, FileText, Info, Search, UserRound } from 'lucide-react'
import { PriorityBadge, DemoTag, Sheet, ErrorBox, Skeleton, cx } from './ui'
import { api } from '../lib/api'
import { useLoad } from '../lib/AppContext'
import { ago, catLabel, cr, num, pct, tone, when } from '../lib/format'

const EDGE = { critical: 'before:bg-crit', high: 'before:bg-high', medium: 'before:bg-med', low: 'before:bg-line' }

export function AnnouncementCard({ a, onOpen, compact }) {
  return (
    <button onClick={() => onOpen(a.id)} className={cx('card relative w-full overflow-hidden p-4 pl-5 text-left transition hover:border-accent/50 before:absolute before:inset-y-0 before:left-0 before:w-1', EDGE[a.priority])}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
        <span className="rounded-md bg-raised px-1.5 py-0.5 text-xs font-extrabold tracking-wide">{a.ticker}</span>
        <PriorityBadge priority={a.priority} score={a.attention_score} />
        <span className="chip !py-0.5">{catLabel(a.category)}</span>
        {a.is_demo && <DemoTag />}
        {a.is_new && <span className="rounded-full bg-accent/15 px-2 py-0.5 text-[10px] font-bold uppercase text-accent">New</span>}
        <span className="num ml-auto text-xs text-faint">{ago(a.filed_at)}</span>
      </div>
      <p className="mt-2 text-[15px] font-semibold leading-snug">{a.headline}</p>
      {!compact && a.summary?.what && a.summary.what !== a.headline && <p className="mt-1.5 line-clamp-2 text-sm text-muted">{a.summary.what}</p>}
      <div className="mt-2 flex items-center justify-between text-xs text-faint">
        <span className="truncate">{a.company_name} · {a.exchange}</span>
        <span className="flex shrink-0 items-center gap-0.5 font-semibold text-accent">Details <ChevronRight size={14} /></span>
      </div>
    </button>
  )
}

function ResultsTable({ r }) {
  const labels = { revenue: 'Revenue', ebitda: 'EBITDA', pbt: 'PBT', pat: 'PAT' }
  const [cur, prev, ya] = r.periods || ['Current', 'Previous qtr', 'Year-ago']
  const rows = Object.entries(r.metrics || {})
  if (!rows.length) return null
  return (
    <section>
      <h3 className="h-sec mb-2">Results · {r.basis} · {r.unit}</h3>
      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="num w-full min-w-[480px] text-sm">
          <thead className="bg-raised text-xs text-muted">
            <tr><th className="p-2 text-left font-semibold">Metric</th><th className="p-2 text-right font-semibold">{cur}</th><th className="p-2 text-right font-semibold">{prev}</th><th className="p-2 text-right font-semibold">{ya}</th><th className="p-2 text-right font-semibold">QoQ</th><th className="p-2 text-right font-semibold">YoY</th></tr>
          </thead>
          <tbody>
            {rows.map(([k, m]) => (
              <tr key={k} className="border-t border-line">
                <td className="p-2 font-semibold">{labels[k] || k}{m.derived && <span title="Derived: PBT + finance costs + depreciation − other income" className="ml-1 rounded bg-warn/15 px-1 text-[9px] font-bold uppercase text-warn">derived</span>}</td>
                <td className="p-2 text-right font-semibold">{num(m.current)}</td>
                <td className="p-2 text-right text-muted">{num(m.previous)}</td>
                <td className="p-2 text-right text-muted">{num(m.year_ago)}</td>
                <td className={cx('p-2 text-right font-semibold', tone(m.qoq?.pct))} title={m.qoq?.note || ''}>{m.qoq?.pct == null ? 'n.m.' : pct(m.qoq.pct)}</td>
                <td className={cx('p-2 text-right font-semibold', tone(m.yoy?.pct))} title={m.yoy?.note || ''}>{m.yoy?.pct == null ? 'n.m.' : pct(m.yoy.pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!r.column_order_verified && <p className="mt-2 flex gap-1.5 text-xs text-warn"><Info size={13} className="mt-0.5 shrink-0" /> Column order could not be verified from period headers – check against the filing.</p>}
      {(r.notes || []).map((n, i) => <p key={i} className="mt-1.5 flex gap-1.5 text-xs text-muted"><Info size={13} className="mt-0.5 shrink-0" /> {n}</p>)}
    </section>
  )
}

function Changes({ x }) {
  return (
    <section className="space-y-3">
      <h3 className="h-sec">Management change{x.changes.length > 1 ? 's' : ''}</h3>
      {x.changes.map((c, i) => (
        <div key={i} className="rounded-xl border border-line bg-raised p-3">
          <div className="flex items-start gap-3">
            <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-surface text-muted"><UserRound size={20} /></div>
            <div className="min-w-0">
              <p className="font-bold">{c.person}</p>
              <p className="text-sm text-muted"><span className="font-semibold capitalize text-ink">{c.event}</span>{c.designation && <> · {c.designation}</>}</p>
              <p className="num mt-0.5 text-xs text-faint">{c.effective_date ? `Effective ${c.effective_date}` : 'Effective date not stated'}{c.previous_designation && ` · previously ${c.previous_designation}`}</p>
            </div>
          </div>
          {c.brief_profile ? (
            <blockquote className="mt-3 border-l-2 border-accent/60 pl-3 text-sm italic text-muted">“{c.brief_profile}”<footer className="mt-1 text-[11px] not-italic text-faint">{c.profile_source || 'Quoted from the filing'}</footer></blockquote>
          ) : <p className="mt-3 text-sm text-faint">The filing includes no profile for this person.</p>}
          {c.profile_search_url && <a href={c.profile_search_url} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1.5 text-xs font-semibold text-accent"><Search size={13} /> Look up background (opens a web search)</a>}
        </div>
      ))}
      {(x.notes || []).map((n, i) => <p key={i} className="flex gap-1.5 text-xs text-muted"><Info size={13} className="mt-0.5 shrink-0" /> {n}</p>)}
    </section>
  )
}

export function AnnouncementSheet({ id, onClose }) {
  const { data: a, loading, error } = useLoad(() => (id ? api.announcement(id) : Promise.resolve(null)), [id])
  const [showText, setShowText] = useState(false)
  return (
    <Sheet open={!!id} onClose={onClose} title={a ? `${a.ticker} · ${catLabel(a.category)}` : 'Filing'} wide>
      {loading && <div className="space-y-3"><Skeleton className="h-8" /><Skeleton className="h-32" /><Skeleton className="h-24" /></div>}
      <ErrorBox error={error} />
      {a && !loading && (
        <div className="space-y-5">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <PriorityBadge priority={a.priority} score={a.attention_score} />
              {a.is_demo && <DemoTag />}
              <span className="num text-xs text-faint">{when(a.filed_at)} · {a.exchange}</span>
            </div>
            <h3 className="mt-2 text-lg font-bold leading-snug">{a.headline}</h3>
            <p className="text-sm text-muted">{a.company_name}</p>
          </div>

          <section className="space-y-3 rounded-xl bg-raised p-3.5">
            {[['What happened', a.summary?.what], ['Why it matters', a.summary?.why], ['What to monitor', a.summary?.watch]].map(([t, v]) => v && (
              <div key={t}><p className="h-sec">{t}</p><p className="mt-0.5 text-sm">{v}</p></div>
            ))}
            <p className="text-[11px] text-faint">Summary written by {a.summary?.by === 'rules' ? 'deterministic rules from the extracted fields' : a.summary?.by}. No buy/sell view is expressed.</p>
          </section>

          {a.extracted?.metrics && <ResultsTable r={a.extracted} />}
          {a.extracted?.changes && <Changes x={a.extracted} />}
          {a.category === 'results' && !a.extracted?.metrics && <p className="flex gap-1.5 text-sm text-muted"><Info size={15} className="mt-0.5 shrink-0" /> No financial table could be extracted from this filing's text. Open the original filing for the numbers.</p>}

          <section>
            <h3 className="h-sec mb-2">Why this attention score ({a.attention_score}/100)</h3>
            <ul className="space-y-1.5 text-sm">
              {(a.score_reasons || []).map((r, i) => <li key={i} className="flex gap-2"><span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-accent" /><span className="text-muted">{r}</span></li>)}
            </ul>
            <p className="mt-3 text-xs text-faint">Classified as <strong className="text-muted">{catLabel(a.category)}</strong> ({Math.round((a.category_confidence || 0) * 100)}% confidence, {a.classifier}). {(a.classifier_reasons || []).join(' · ')}</p>
          </section>

          <section className="flex flex-wrap gap-2">
            <button onClick={() => setShowText((s) => !s)} className="btn-ghost"><FileText size={16} /> {showText ? 'Hide' : 'Show'} filing text</button>
            <a className="btn-ghost" href={a.url?.startsWith('http') ? a.url : a.url} target="_blank" rel="noreferrer"><ExternalLink size={16} /> Open filing</a>
          </section>
          {showText && <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-xl border border-line bg-bg p-3 font-mono text-xs leading-relaxed text-muted">{a.body_text || 'No text available.'}</pre>}
        </div>
      )}
    </Sheet>
  )
}
