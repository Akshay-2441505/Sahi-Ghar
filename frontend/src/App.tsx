import { Link, Route, Routes } from 'react-router-dom'
import { CheckCircle } from '@phosphor-icons/react'
import Search from './pages/Search'
import TrustPage from './pages/TrustPage'
import { CoverageChip } from './components/CoverageChip'

export default function App() {
  return (
    <div className="flex min-h-dvh flex-col bg-(--color-paper) font-sans text-(--color-ink)">
      <header className="sticky top-0 z-10 border-b border-(--color-border) bg-(--color-paper)">
        <div className="mx-auto flex max-w-5xl flex-col gap-2 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:py-5">
          <div>
            <Link to="/" className="inline-flex items-center gap-2 text-xl font-bold tracking-tight">
              <CheckCircle size={22} weight="fill" className="text-(--color-accent)" />
              Sahi Ghar
            </Link>
            <p className="mt-0.5 text-sm text-(--color-ink-muted)">A public-record lookup of builders' RERA track records</p>
          </div>
          <CoverageChip />
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:py-10">
        <Routes>
          <Route path="/" element={<Search />} />
          <Route path="/projects/:id" element={<TrustPage />} />
        </Routes>
      </main>
      <footer className="border-t border-(--color-border) bg-(--color-surface)">
        <div className="mx-auto max-w-5xl px-4 py-6 text-xs text-(--color-ink-muted)">
          <p>
            Built entirely from official regulatory filings. No builder pays to be listed, ranked, or featured
            here, and none of the figures on this site are advertising.
          </p>
        </div>
      </footer>
    </div>
  )
}
