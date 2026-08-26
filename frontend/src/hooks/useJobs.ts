import { useEffect, useState } from 'react'

import { fetchJobs } from '../api/client'
import type { JobFilters, JobPage } from '../api/types'
import { useDebouncedValue } from './useDebouncedValue'

export interface JobsState {
  page: JobPage | null
  loading: boolean
  error: string | null
}

/** The state settled so far, tagged with the request that produced it. */
interface Settled {
  page: JobPage | null
  error: string | null
  /** null until the first response lands, which is what makes `loading` start true. */
  key: string | null
}

const INITIAL: Settled = { page: null, error: null, key: null }

/**
 * Fetches the current page of jobs, re-running whenever a filter changes.
 *
 * The title search is debounced; every other filter takes effect immediately,
 * since those come from a select and can't fire in a burst.
 */
export function useJobs(filters: JobFilters): JobsState {
  const query = useDebouncedValue(filters.query)
  const [settled, setSettled] = useState<Settled>(INITIAL)

  // Destructured because the effect depends on these values, not on the
  // `filters` object -- which is a fresh reference every render and would
  // re-fire the effect forever.
  const { country, remote, sortBy, descending, page } = filters
  const requestKey = JSON.stringify([query, country, remote, sortBy, descending, page])

  useEffect(() => {
    const controller = new AbortController()

    fetchJobs({ query, country, remote, sortBy, descending, page }, controller.signal)
      .then((result) => setSettled({ page: result, error: null, key: requestKey }))
      .catch((error: unknown) => {
        // An aborted request isn't a failure -- a newer one superseded it, and
        // that one owns the state now.
        if (controller.signal.aborted) return
        const message = error instanceof Error ? error.message : 'Something went wrong'
        setSettled({ page: null, error: message, key: requestKey })
      })

    // Aborting on cleanup is what stops a slow request for "eng" from landing
    // after a fast one for "engineer" and overwriting fresher results.
    // Debouncing makes that rare; only cancellation makes it impossible.
    return () => controller.abort()
  }, [requestKey, query, country, remote, sortBy, descending, page])

  // Derived, not stored: we are loading exactly when the settled state belongs
  // to some earlier request. Setting a flag in the effect instead would cost a
  // second render pass on every keystroke.
  const loading = settled.key !== requestKey

  return {
    // Previous results stay on screen while the next page loads, so the list
    // doesn't blink empty on every filter change.
    page: settled.page,
    loading,
    // A stale error belongs to a request we've already moved on from.
    error: loading ? null : settled.error,
  }
}
