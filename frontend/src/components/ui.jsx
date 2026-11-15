import { useEffect } from 'react'
import { AlertTriangle, Inbox, X, FlaskConical, ShieldCheck, ShieldAlert, Shield } from 'lucide-react'

export const cx = (...a) => a.filter(Boolean).join(' ')

const PRI = {
  critical: 'bg-crit/15 text-crit border-crit/40',
  high: 'bg-high/15 text-high border-high/40',
  medium: 'bg-med/15 text-med border-med/40',
  low: 'bg-raised text-muted border-line',
}
export function PriorityBadge({ priority, score }) {
  return (
    <span className={cx('inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide', PRI[priority] || PRI.low)}>
      {priority}{score !== undefined && <span className="num font-semibold opacity-80">{score}</span>}
    </span>
  )
}

export function DemoTag({ className }) {
  return (
    <span title="Synthetic sample data – not a real filing, price or report" className={cx('inline-flex items-center gap-1 rounded-md border border-warn/50 bg-warn/10 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-warn', className)}>
      <FlaskConical size={10} /> Sample
    </span>
  )
}

export function Skeleton({ className }) { return <div className={cx('skel', className)} /> }
export function SkeletonList({ n = 3, h = 'h-24' }) { return <div className="space-y-3">{Array.from({ length: n }).map((_, i) => <Skeleton key={i} className={h} />)}</div> }

export function Empty({ icon: Icon = Inbox, title, children, action }) {
  return (
    <div className="card flex flex-col items-center gap-2 px-6 py-10 text-center">
      <Icon className="text-faint" size={28} />
      <p className="font-semibold">{title}</p>
      {children && <p className="max-w-sm text-sm text-muted">{children}</p>}
      {action}
    </div>
  )
}

export function ErrorBox({ error, onRetry }) {
  if (!error) return null
  return (
    <div role="alert" className="card flex items-start gap-3 border-down/40 p-4">
      <AlertTriangle className="mt-0.5 shrink-0 text-down" size={18} />
      <div className="min-w-0 flex-1 text-sm">
        <p className="font-semibold text-down">Something went wrong</p>
        <p className="mt-0.5 break-words text-muted">{error.message || String(error)}</p>
      </div>
      {onRetry && <button className="btn-ghost !min-h-[34px] !px-3" onClick={onRetry}>Retry</button>}
    </div>
  )
}

export function Sheet({ open, onClose, title, children, wide }) {
  useEffect(() => {
    if (!open) return
    const k = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', k)
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', k); document.body.style.overflow = '' }
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center md:items-center" role="dialog" aria-modal="true" aria-label={title}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className={cx('sheet-in relative flex max-h-[92dvh] w-full flex-col rounded-t-3xl border border-line bg-surface md:rounded-3xl', wide ? 'md:max-w-3xl' : 'md:max-w-xl')}>
        <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          <h2 className="min-w-0 truncate text-base font-bold">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-raised text-muted hover:text-ink"><X size={18} /></button>
        </div>
        <div className="overflow-y-auto px-4 py-4 safe-b">{children}</div>
      </div>
    </div>
  )
}

export function Segmented({ value, onChange, options, className }) {
  return (
    <div className={cx('inline-flex rounded-xl border border-line bg-raised p-1', className)} role="tablist">
      {options.map((o) => (
        <button key={o.value} role="tab" aria-selected={value === o.value} onClick={() => onChange(o.value)}
          className={cx('min-h-[34px] rounded-lg px-3 text-xs font-semibold transition', value === o.value ? 'bg-accent text-bg' : 'text-muted hover:text-ink')}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

const CONF = {
  high: { icon: ShieldCheck, cls: 'text-up border-up/40 bg-up/10', label: 'High confidence' },
  medium: { icon: Shield, cls: 'text-warn border-warn/40 bg-warn/10', label: 'Medium confidence' },
  low: { icon: ShieldAlert, cls: 'text-down border-down/40 bg-down/10', label: 'Low confidence' },
}
export function Confidence({ c }) {
  if (!c) return null
  const m = CONF[c.level] || CONF.low
  const Icon = m.icon
  return (
    <span title={c.reason} className={cx('inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold', m.cls)}>
      <Icon size={12} /> {m.label}
    </span>
  )
}

export function Toggle({ checked, onChange, label }) {
  return (
    <button role="switch" aria-checked={checked} aria-label={label} onClick={() => onChange(!checked)}
      className={cx('relative h-7 w-12 shrink-0 rounded-full border transition', checked ? 'border-accent bg-accent' : 'border-line bg-raised')}>
      <span className={cx('absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all', checked ? 'left-[22px]' : 'left-0.5')} />
    </button>
  )
}

export function Stat({ label, value, sub, subClass }) {
  return (
    <div className="min-w-0">
      <p className="h-sec">{label}</p>
      <p className="num mt-1 truncate text-lg font-bold">{value}</p>
      {sub && <p className={cx('num text-xs', subClass || 'text-muted')}>{sub}</p>}
    </div>
  )
}
