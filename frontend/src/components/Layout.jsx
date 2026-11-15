import { NavLink, Outlet } from 'react-router-dom'
import { Bell, Bot, FlaskConical, Home, Microscope, Settings, Wallet, WifiOff } from 'lucide-react'
import { useApp } from '../lib/AppContext'
import { cx } from './ui'

const NAV = [
  { to: '/', label: 'Feed', icon: Home, end: true },
  { to: '/portfolio', label: 'Portfolio', icon: Wallet },
  { to: '/research', label: 'Research', icon: Microscope },
  { to: '/copilot', label: 'Copilot', icon: Bot },
  { to: '/settings', label: 'Settings', icon: Settings },
]

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="grid h-9 w-9 place-items-center rounded-xl bg-accent text-lg font-black text-bg">F</div>
      <div className="leading-tight">
        <p className="text-base font-extrabold tracking-tight">FINN</p>
        <p className="text-[10px] uppercase tracking-[.16em] text-faint">Investment agent</p>
      </div>
    </div>
  )
}

export default function Layout() {
  const { status, statusError, demo, unread } = useApp()
  return (
    <div className="mx-auto flex min-h-full max-w-[1400px]">
      {/* desktop sidebar */}
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r border-line px-4 py-6 md:flex">
        <Logo />
        <nav className="mt-8 flex flex-col gap-1" aria-label="Main">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => cx('flex min-h-[44px] items-center gap-3 rounded-xl px-3 text-sm font-semibold transition', isActive ? 'bg-accent/15 text-accent' : 'text-muted hover:bg-raised hover:text-ink')}>
              <Icon size={19} /> {label}
              {label === 'Feed' && unread > 0 && <span className="num ml-auto rounded-full bg-crit px-1.5 text-[10px] font-bold text-white">{unread}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto space-y-2 text-xs text-faint">
          <p>Not investment advice. Analytical summaries of public documents.</p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-line bg-bg/85 px-4 py-3 backdrop-blur md:px-8">
          <div className="md:hidden"><Logo /></div>
          <div className="hidden text-sm text-muted md:block">{status?.latest_price_date ? <>Prices as of <span className="num font-semibold text-ink">{status.latest_price_date}</span> · end-of-day, not real-time</> : 'End-of-day data'}</div>
          <div className="flex items-center gap-2">
            {demo ? (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-warn/50 bg-warn/10 px-3 py-1.5 text-xs font-bold uppercase tracking-wide text-warn"><FlaskConical size={13} /> Demo data</span>
            ) : status ? (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-up/40 bg-up/10 px-3 py-1.5 text-xs font-bold uppercase tracking-wide text-up"><span className="h-1.5 w-1.5 rounded-full bg-up" /> Live</span>
            ) : null}
            <NavLink to="/" aria-label={`${unread} unread alerts`} className="relative grid h-10 w-10 place-items-center rounded-full border border-line bg-raised text-muted md:hidden"><Bell size={18} />{unread > 0 && <span className="num absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-crit px-1 text-[9px] font-bold text-white">{unread}</span>}</NavLink>
          </div>
        </header>

        {statusError && (
          <div role="alert" className="mx-4 mt-4 flex items-center gap-2 rounded-xl border border-down/40 bg-down/10 px-3 py-2 text-sm text-down md:mx-8"><WifiOff size={16} /> {statusError.message}</div>
        )}
        {demo && (
          <div className="mx-4 mt-4 rounded-xl border border-warn/30 bg-warn/5 px-3 py-2 text-xs text-warn md:mx-8">
            <strong>Sample data.</strong> Prices, filings, financials and reports below are synthetic, generated for demonstration, and are not real. Switch to Live in Settings to use public exchange sources.
          </div>
        )}

        <main className="flex-1 px-4 pb-28 pt-5 md:px-8 md:pb-12"><Outlet /></main>
      </div>

      {/* mobile bottom nav */}
      <nav aria-label="Main" className="safe-b fixed inset-x-0 bottom-0 z-40 grid grid-cols-5 border-t border-line bg-surface/95 backdrop-blur md:hidden">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) => cx('flex min-h-[58px] flex-col items-center justify-center gap-0.5 text-[10.5px] font-semibold', isActive ? 'text-accent' : 'text-faint')}>
            <Icon size={21} /> {label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
