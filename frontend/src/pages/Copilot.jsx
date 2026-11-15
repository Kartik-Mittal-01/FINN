import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Bot, History, Loader2, Plus, SendHorizonal, ShieldCheck, ShieldAlert, Trash2, User } from 'lucide-react'
import { api } from '../lib/api'
import { useApp, useLoad } from '../lib/AppContext'
import { Evidence } from '../components/Citation'
import { DemoTag, ErrorBox, Sheet, cx } from '../components/ui'
import { ago } from '../lib/format'

function Answer({ m, onCite }) {
  // [1] markers in the text become tappable chips that open the cited passage.
  const parts = m.content.split(/(\[\d+\])/g)
  const byN = Object.fromEntries((m.citations || []).map((c) => [String(c.n), c]))
  return (
    <p className="whitespace-pre-line text-sm leading-relaxed">
      {parts.map((p, i) => {
        const mm = p.match(/^\[(\d+)\]$/)
        if (mm && byN[mm[1]]) return <button key={i} onClick={() => onCite(byN[mm[1]])} className="num mx-0.5 inline-grid h-[18px] min-w-[18px] -translate-y-px place-items-center rounded-md bg-accent/20 px-1 text-[11px] font-bold text-accent hover:bg-accent/30" aria-label={`Open source ${mm[1]}`}>{mm[1]}</button>
        return <Fragment key={i}>{p}</Fragment>
      })}
    </p>
  )
}

function Table({ t }) {
  const colors = { met: 'text-up', missed: 'text-down', tracking: 'text-info', pending: 'text-muted', not_verifiable: 'text-muted' }
  return (
    <div className="mt-3 overflow-x-auto rounded-xl border border-line">
      <table className="num w-full min-w-[420px] text-xs">
        <thead className="bg-raised text-muted"><tr>{t.columns.map((c) => <th key={c} className="p-2 text-left font-semibold">{c}</th>)}</tr></thead>
        <tbody>{t.rows.map((r, i) => <tr key={i} className="border-t border-line">{r.map((c, j) => <td key={j} className={cx('p-2', colors[c])}>{c ?? '–'}</td>)}</tr>)}</tbody>
      </table>
      {t.unit && <p className="px-2 pb-1.5 text-[10px] text-faint">{t.unit}</p>}
    </div>
  )
}

function Bubble({ m, onCite }) {
  if (m.role === 'user') {
    return <div className="flex justify-end gap-2"><div className="max-w-[85%] rounded-2xl rounded-br-md bg-accent px-3.5 py-2.5 text-sm font-medium text-bg">{m.content}</div></div>
  }
  const meta = m.meta || {}
  return (
    <div className="flex gap-2.5">
      <div className="mt-1 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-raised text-accent"><Bot size={15} /></div>
      <div className={cx('min-w-0 max-w-[92%] rounded-2xl rounded-tl-md border bg-surface px-3.5 py-3', meta.insufficient ? 'border-warn/40' : 'border-line')}>
        <Answer m={m} onCite={onCite} />
        {meta.table && <Table t={meta.table} />}
        <div className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10.5px] text-faint">
          {meta.insufficient ? <span className="flex items-center gap-1 text-warn"><ShieldAlert size={11} /> Not answered – no supporting evidence</span> : <span className="flex items-center gap-1 text-up"><ShieldCheck size={11} /> {meta.verified ? 'Verified against sources' : 'From sources'}</span>}
          <span>· {meta.generated_by}</span>
          {meta.is_demo && <DemoTag />}
        </div>
      </div>
    </div>
  )
}

export default function Copilot() {
  const { ticker: param } = useParams()
  const nav = useNavigate()
  const { version } = useApp()
  const [ticker, setTicker] = useState(param?.toUpperCase() || '')
  const [input, setInput] = useState(param?.toUpperCase() || '')
  const [convId, setConvId] = useState(null)
  const [messages, setMessages] = useState([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [cite, setCite] = useState(null)
  const [histOpen, setHistOpen] = useState(false)
  const [sugg, setSugg] = useState(null)
  const end = useRef(null)

  const holdings = useLoad(() => api.portfolio(), [])
  const defaults = useLoad(() => api.suggestions(), [])
  const convs = useLoad(() => (ticker ? api.conversations(ticker) : Promise.resolve({ conversations: [] })), [ticker])

  const reset = useCallback(() => { setConvId(null); setMessages([]); setError(null); setSugg(null) }, [])
  useEffect(() => { const t = param?.toUpperCase() || ''; setTicker(t); setInput(t); reset() }, [param, version, reset])
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [messages, busy])

  const pick = (t) => { const v = t.trim().toUpperCase().replace(/\.(NS|BO)$/, ''); if (v) nav(`/copilot/${v}`) }
  const send = async (q) => {
    const msg = (q ?? text).trim()
    if (!msg || !ticker || busy) return
    setText(''); setError(null); setBusy(true); setSugg(null)
    setMessages((m) => [...m, { id: `u${Date.now()}`, role: 'user', content: msg }])
    try {
      const r = await api.chat(ticker, msg, convId)
      setConvId(r.conversation_id); setMessages((m) => [...m, r.message]); setSugg(r.suggestions); convs.reload()
    } catch (e) { setError(e) } finally { setBusy(false) }
  }
  const openConv = async (id) => {
    try { const c = await api.conversation(id); setConvId(c.id); setMessages(c.messages); setHistOpen(false); setSugg(null) } catch (e) { setError(e) }
  }
  const del = async (id) => { await api.deleteConversation(id); if (id === convId) reset(); convs.reload() }

  const tickers = (holdings.data?.holdings || []).map((h) => h.ticker)
  const suggestions = sugg?.length ? sugg : defaults.data?.suggestions || []

  return (
    <div className="mx-auto flex h-[calc(100dvh-410px)] min-h-[360px] max-w-3xl flex-col md:h-[calc(100dvh-150px)]">
      <div className="mb-3 space-y-3">
        <div className="flex items-end justify-between gap-3">
          <div><p className="h-sec">Copilot</p><h1 className="mt-1 text-2xl font-extrabold tracking-tight">Ask the documents</h1></div>
          {ticker && <div className="flex gap-2"><button className="btn-ghost !px-3" onClick={reset} aria-label="New conversation"><Plus size={16} /></button><button className="btn-ghost !px-3" onClick={() => setHistOpen(true)} aria-label="Conversation history"><History size={16} /></button></div>}
        </div>
        <form onSubmit={(e) => { e.preventDefault(); pick(input) }} className="flex gap-2">
          <input list="tickers" className="input uppercase" placeholder="Company ticker, e.g. TCS" value={input} onChange={(e) => setInput(e.target.value)} aria-label="Company ticker" autoCapitalize="characters" />
          <datalist id="tickers">{tickers.map((t) => <option key={t} value={t} />)}</datalist>
          <button className="btn-ghost">Select</button>
        </form>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto rounded-2xl border border-line bg-bg/40 p-3 md:p-4">
        {!ticker && <p className="py-10 text-center text-sm text-muted">Choose a company above. Answers come only from its annual report, earnings-call transcripts and extracted financials, and each one cites the page it relied on.</p>}
        {ticker && messages.length === 0 && (
          <div className="py-4">
            <p className="text-center text-sm text-muted">Ask anything about <strong className="text-ink">{ticker}</strong>. If the documents don't support an answer, FINN says so instead of guessing.</p>
            <div className="mt-4 flex flex-wrap justify-center gap-2">{suggestions.map((s) => <button key={s} onClick={() => send(s)} className="chip !whitespace-normal !py-2 text-left hover:!border-accent hover:!text-accent">{s}</button>)}</div>
          </div>
        )}
        {messages.map((m) => <Bubble key={m.id} m={m} onCite={setCite} />)}
        {busy && <div className="flex items-center gap-2 pl-9 text-sm text-muted"><Loader2 size={14} className="animate-spin" /> Searching the documents…</div>}
        {!busy && messages.length > 0 && suggestions.length > 0 && <div className="flex flex-wrap gap-2 pl-9">{suggestions.slice(0, 3).map((s) => <button key={s} onClick={() => send(s)} className="chip !whitespace-normal !py-1.5 text-left hover:!border-accent hover:!text-accent">{s}</button>)}</div>}
        <ErrorBox error={error} />
        <div ref={end} />
      </div>

      <form onSubmit={(e) => { e.preventDefault(); send() }} className="mt-3 flex gap-2">
        <input className="input" placeholder={ticker ? `Ask about ${ticker}…` : 'Select a company first'} value={text} onChange={(e) => setText(e.target.value)} disabled={!ticker || busy} maxLength={1000} aria-label="Your question" />
        <button className="btn-primary !px-4" disabled={!ticker || busy || !text.trim()} aria-label="Send"><SendHorizonal size={18} /></button>
      </form>

      <Sheet open={!!cite} onClose={() => setCite(null)} title={`Source [${cite?.n}]`}>
        {cite && <Evidence e={{ ...cite, kind: cite.kind === 'financial' ? 'financial' : 'excerpt' }} />}
        {cite && cite.kind !== 'financial' && <p className="mt-3 text-xs text-faint">Tap the title to expand the passage, then open the exact page of the original PDF.</p>}
      </Sheet>
      <Sheet open={histOpen} onClose={() => setHistOpen(false)} title={`Conversations · ${ticker}`}>
        {convs.data?.conversations.length === 0 && <p className="text-sm text-muted">No saved conversations for this company yet.</p>}
        <ul className="divide-y divide-line">
          {convs.data?.conversations.map((c) => (
            <li key={c.id} className="flex items-center gap-2 py-2.5">
              <button className="min-w-0 flex-1 text-left" onClick={() => openConv(c.id)}><p className="truncate text-sm font-semibold">{c.title}</p><p className="text-xs text-faint">{ago(c.created_at)}</p></button>
              <button onClick={() => del(c.id)} aria-label="Delete conversation" className="grid h-9 w-9 place-items-center rounded-full text-faint hover:bg-raised hover:text-down"><Trash2 size={16} /></button>
            </li>
          ))}
        </ul>
      </Sheet>
    </div>
  )
}
