import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api } from './api'

const Ctx = createContext(null)
export const useApp = () => useContext(Ctx)

export function AppProvider({ children }) {
  const [status, setStatus] = useState(null)
  const [statusError, setStatusError] = useState(null)
  const [unread, setUnread] = useState(0)
  const [version, setVersion] = useState(0)   // bump to make pages refetch after a mode change / refresh
  const [theme, setThemeState] = useState(() => { try { return localStorage.getItem('finn-theme') || 'dark' } catch { return 'dark' } })

  const setTheme = useCallback((t) => {
    setThemeState(t)
    document.documentElement.dataset.theme = t
    try { localStorage.setItem('finn-theme', t) } catch { /* private mode */ }
  }, [])
  useEffect(() => { document.documentElement.dataset.theme = theme }, [theme])

  const reloadStatus = useCallback(async () => {
    try { setStatus(await api.status()); setStatusError(null) } catch (e) { setStatusError(e) }
    try { setUnread((await api.alerts()).unread) } catch { /* alerts are non-critical here */ }
  }, [])
  useEffect(() => { reloadStatus() }, [reloadStatus])
  const refreshAll = useCallback(async () => { await reloadStatus(); setVersion((v) => v + 1) }, [reloadStatus])

  const value = useMemo(() => ({ status, statusError, unread, setUnread, reloadStatus, refreshAll, version, theme, setTheme, demo: status?.mode === 'demo' }),
    [status, statusError, unread, reloadStatus, refreshAll, version, theme, setTheme])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

// Small data-fetching hook: { data, error, loading, reload }. Re-runs when deps or the global version change.
export function useLoad(fn, deps = []) {
  const { version } = useApp()
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const [n, setN] = useState(0)
  useEffect(() => {
    let live = true
    setState((s) => ({ ...s, loading: true, error: null }))
    fn().then((data) => live && setState({ data, error: null, loading: false }))
      .catch((error) => live && setState({ data: null, error, loading: false }))
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, version, n])
  return { ...state, reload: () => setN((x) => x + 1) }
}
