import { useState } from 'react'
import { BookOpenText, ChevronDown, ExternalLink, FileText } from 'lucide-react'
import { DemoTag, cx } from './ui'

const TYPE = { annual_report: 'Annual report', concall: 'Earnings call', presentation: 'Presentation' }

// One cited source passage. Opens the original PDF at the cited page.
export function Citation({ c, n, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen)
  if (!c) return null
  return (
    <div className="rounded-xl border border-line bg-raised/60 text-sm">
      <button onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-center gap-2 px-3 py-2 text-left">
        {n !== undefined && n !== null && <span className="num grid h-5 min-w-5 place-items-center rounded-md bg-accent/20 px-1 text-[11px] font-bold text-accent">{n}</span>}
        <FileText size={14} className="shrink-0 text-faint" />
        <span className="min-w-0 flex-1 truncate text-xs font-semibold">{c.title}</span>
        <span className="num shrink-0 text-[11px] text-faint">p.{c.page}</span>
        {c.is_demo && <DemoTag />}
        <ChevronDown size={14} className={cx('shrink-0 text-faint transition', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="border-t border-line px-3 py-2.5">
          <p className="text-[11px] text-faint">{TYPE[c.doc_type] || c.doc_type}{c.period ? ` · ${c.period}` : ''}</p>
          <p className="mt-1 whitespace-pre-line text-[13px] leading-relaxed text-muted">“{c.excerpt}”</p>
          <div className="mt-2 flex flex-wrap gap-3">
            <a href={c.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs font-semibold text-accent"><BookOpenText size={13} /> Open page {c.page} in the PDF</a>
            {c.source_url && <a href={c.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs font-semibold text-muted"><ExternalLink size={13} /> Original source</a>}
          </div>
        </div>
      )}
    </div>
  )
}

export function CitationList({ items, label = 'Sources' }) {
  if (!items?.length) return null
  return (
    <div className="mt-3 space-y-1.5">
      <p className="h-sec">{label}</p>
      {items.map((c, i) => <Citation key={i} c={c} n={c.n ?? undefined} />)}
    </div>
  )
}

// Inline evidence: either a document passage or a block of reported figures.
export function Evidence({ e }) {
  if (e?.kind === 'financial') {
    return (
      <div className="rounded-xl border border-line bg-raised/60 px-3 py-2">
        <p className="text-xs font-semibold">{e.label}</p>
        <div className="num mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-muted">
          {e.periods.map((p, i) => <span key={p}><span className="text-faint">{p}</span> {Array.isArray(e.values[i]) ? e.values[i].map((x) => Number(x).toLocaleString('en-IN')).join(' / ') : Number(e.values[i]).toLocaleString('en-IN')}</span>)}
        </div>
        <p className="mt-1 text-[10.5px] text-faint">{e.source}</p>
      </div>
    )
  }
  return <Citation c={e} />
}
