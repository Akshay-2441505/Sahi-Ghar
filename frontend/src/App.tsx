import { Link, Route, Routes } from 'react-router-dom'
import Search from './pages/Search'
import TrustPage from './pages/TrustPage'

export default function App() {
  return (
    <div className="min-h-screen bg-stone-50 text-stone-900">
      <header className="border-b border-stone-300 bg-white">
        <div className="mx-auto max-w-4xl px-4 py-3">
          <Link to="/" className="text-lg font-semibold">Sahi Ghar</Link>
          <span className="ml-3 text-sm text-stone-600">A public-record lookup of builders' RERA track records</span>
        </div>
      </header>
      <main className="mx-auto max-w-4xl px-4 py-6">
        <Routes>
          <Route path="/" element={<Search />} />
          <Route path="/projects/:id" element={<TrustPage />} />
        </Routes>
      </main>
    </div>
  )
}
