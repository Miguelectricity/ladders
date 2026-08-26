// Hand-mirrored from backend/models/Job.py and backend/storage/storage.py.
// The API returns its dataclasses directly, with no response schema in between,
// so these types track the domain models field for field -- nullability included.
// If the API grows, generate this file from /openapi.json instead.

/** backend.models.Job.CountryCode */
export type CountryCode = 'US' | 'CA' | 'other'

/** backend.models.Job.Currency */
export type Currency = 'USD' | 'OTHER'

export type EmploymentType =
  | 'part-time'
  | 'full-time'
  | 'internship'
  | 'contract'
  | 'unknown'

export type CompanyType =
  | 'direct-employer'
  | 'staffing-firm'
  | 'consulting-agency'
  | 'unknown'

export type Language = 'english' | 'french' | 'unknown'

/** backend.storage.storage.SortField */
export type SortField = 'posting_date' | 'salary_annual' | 'salary_hourly' | 'title'

export interface Location {
  /** The scraped original. The API leaks it today; never render it. */
  raw: unknown
  city: string | null
  region: string | null
  country_code: CountryCode | null
}

export interface Salary {
  raw: unknown
  /**
   * At most one of these is set. The feed states either an annual figure or an
   * hourly rate and the parser never derives one from the other, so any display
   * or comparison has to branch on which one is present.
   */
  min_annual: number | null
  min_hourly: number | null
  currency: Currency | null
  /** True when the feed named no currency and USD was assumed. */
  inferred_currency: boolean
  /** True when annual-vs-hourly was guessed from the magnitude of the number. */
  inferred_period: boolean
}

export interface Job {
  id: string
  title: string | null
  description: string | null
  company: string | null
  location: Location | null
  salary: Salary | null
  employment_type: EmploymentType | null
  /** ISO date, e.g. "2023-10-03". Null when the feed's date was unparseable. */
  posting_date: string | null
  company_type: CompanyType | null
  language: Language | null
  is_remote: boolean | null
}

/**
 * backend.storage.storage.Page. Its `total_pages` is a Python property rather
 * than a field, so it is not serialized -- use `totalPages()` below.
 */
export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export type JobPage = Page<Job>

/** One entry from GET /api/countries. `code` is what `?country=` expects back. */
export interface CountryOption {
  code: CountryCode
  label: string
}

export function totalPages(page: JobPage): number {
  return Math.ceil(page.total / page.page_size)
}

// --- Filter state -----------------------------------------------------------

/** Matches DEFAULT_PAGE_SIZE in backend/storage/storage.py. */
export const PAGE_SIZE = 10

export interface JobFilters {
  query: string
  /** '' means "all countries" -- see the note in fetchJobs about why. */
  country: CountryCode | ''
  sortBy: SortField
  descending: boolean
  /** Zero-indexed, as the backend expects. */
  page: number
}

export const DEFAULT_FILTERS: JobFilters = {
  query: '',
  country: '',
  sortBy: 'posting_date',
  descending: true,
  page: 0,
}

export interface SortOption {
  value: SortField
  label: string
}

/**
 * Annual and hourly salary are separate sort fields on the backend, and each
 * ranks only the postings that state pay that way -- the rest fall to the end
 * of the list. Both are offered so neither kind of posting is unreachable.
 */
export const SORT_OPTIONS: readonly SortOption[] = [
  { value: 'posting_date', label: 'Posting date' },
  { value: 'salary_annual', label: 'Salary (annual)' },
  { value: 'salary_hourly', label: 'Salary (hourly)' },
  { value: 'title', label: 'Title' },
]

/**
 * Merge a filter change, returning to page 0 unless the change is itself a page
 * move. Without this, narrowing a search while on page 3 leaves you staring at
 * an empty page of a one-page result set.
 */
export function applyFilterPatch(
  current: JobFilters,
  patch: Partial<JobFilters>,
): JobFilters {
  const merged = { ...current, ...patch }
  return patch.page === undefined ? { ...merged, page: 0 } : merged
}
