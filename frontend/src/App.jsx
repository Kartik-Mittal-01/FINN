import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Home from './pages/Home'
import Portfolio from './pages/Portfolio'
import Research from './pages/Research'
import Copilot from './pages/Copilot'
import SettingsPage from './pages/Settings'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="portfolio" element={<Portfolio />} />
        <Route path="research" element={<Research />} />
        <Route path="research/:ticker" element={<Research />} />
        <Route path="copilot" element={<Copilot />} />
        <Route path="copilot/:ticker" element={<Copilot />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<div className="card p-8 text-center text-muted">Page not found.</div>} />
      </Route>
    </Routes>
  )
}
