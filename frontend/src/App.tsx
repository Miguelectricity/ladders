import { useState } from 'react'

import type { JobFilters } from './api/types'
import { DEFAULT_FILTERS, applyFilterPatch } from './api/types'
import { FilterBar } from './components/FilterBar'
import { JobList } from './components/JobList'
import { Pagination } from './components/Pagination'
import { useCountries } from './hooks/useCountries'
import { useJobs } from './hooks/useJobs'
import './App.css'

function App() {
  // One piece of state drives the whole screen: the filters are the URL of this
  // app in all but name, and every fetch is derived from them.
  const [filters, setFilters] = useState<JobFilters>(DEFAULT_FILTERS)
  const countries = useCountries()
  const { page, loading, error } = useJobs(filters)

  // applyFilterPatch, not a bare spread: changing a filter has to send us back
  // to page 0 or a narrowed search lands on a page that no longer exists.
  const change = (patch: Partial<JobFilters>) =>
    setFilters((current) => applyFilterPatch(current, patch))

  const empty = page !== null && page.items.length === 0 && !loading

  return (
    <div className="app">
      <header className="app-header">
        <h1>Job search</h1>
        <p>Approved postings from the ingestion pipeline.</p>
      </header>

      <FilterBar filters={filters} countries={countries} onChange={change} />

      {/* aria-busy plus the dimming in App.css: results stay readable while the
          next page loads instead of flashing a spinner on every keystroke. */}
      <main className="results" aria-busy={loading}>
        {error !== null && (
          <p className="notice notice-error" role="alert">
            Couldn’t load jobs: {error}
          </p>
        )}

        {page === null && loading && <p className="notice">Loading jobs…</p>}

        {empty && (
          <p className="notice">No jobs match these filters. Try widening your search.</p>
        )}

        {page !== null && page.items.length > 0 && <JobList jobs={page.items} />}

        {page !== null && (
          <Pagination page={page} onPageChange={(next) => change({ page: next })} />
        )}
      </main>
    </div>
  )
}

export default App
