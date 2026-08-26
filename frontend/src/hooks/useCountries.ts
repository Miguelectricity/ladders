import { useEffect, useState } from 'react'

import { fetchCountries } from '../api/client'
import type { CountryOption } from '../api/types'

/**
 * The country filter's options, fetched once.
 *
 * The backend derives these from the jobs it actually holds, so the dropdown
 * can never offer a filter that matches nothing.
 */
export function useCountries(): CountryOption[] {
  const [countries, setCountries] = useState<CountryOption[]>([])

  useEffect(() => {
    const controller = new AbortController()

    fetchCountries(controller.signal)
      .then(setCountries)
      .catch(() => {
        // Deliberately quiet: losing the options degrades the dropdown to
        // "All countries", which is a working filter. The job list has its own
        // error surface, and two error banners for one dead server is noise.
      })

    return () => controller.abort()
  }, [])

  return countries
}
