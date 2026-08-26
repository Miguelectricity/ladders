import type { CountryOption, JobFilters, JobPage } from './types'
import { PAGE_SIZE } from './types'

// Relative by default: vite.config.ts proxies /api to uvicorn, so requests are
// same-origin in dev and stay correct in production where the built frontend is
// served alongside the API. Point VITE_API_BASE at a host to bypass the proxy
// (the CORS middleware in backend/api.py allows the dev origin for that case).
const API_BASE: string = import.meta.env.VITE_API_BASE ?? ''

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function getJson<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { signal })
  if (!response.ok) {
    throw new ApiError(`GET ${path} failed (${response.status})`, response.status)
  }
  return (await response.json()) as T
}

export function fetchJobs(filters: JobFilters, signal: AbortSignal): Promise<JobPage> {
  // URLSearchParams does the escaping. A hand-concatenated query string breaks
  // on the first title search for something like "C++ & Rust".
  const params = new URLSearchParams({
    sort_by: filters.sortBy,
    descending: String(filters.descending),
    page: String(filters.page),
    page_size: String(PAGE_SIZE),
  })

  // Empty filters are omitted, not sent blank. `country=` is the one that
  // matters: the endpoint types it as a CountryCode enum, so an empty string is
  // a 422 rather than "no filter".
  const query = filters.query.trim()
  if (query) params.set('query', query)
  if (filters.country) params.set('country', filters.country)

  return getJson<JobPage>(`/api/jobs?${params}`, signal)
}

export function fetchCountries(signal: AbortSignal): Promise<CountryOption[]> {
  return getJson<CountryOption[]>('/api/countries', signal)
}
