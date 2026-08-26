import type { CountryCode, Job, Salary, SortField } from './api/types'

// Mirrors COUNTRY_LABELS in backend/api.py, minus the 'other' bucket: "Other"
// is a policy category, not a place, and printing it on a card reads as noise.
const COUNTRY_LABELS: Record<CountryCode, string | null> = {
  US: 'United States',
  CA: 'Canada',
  other: null,
}

const USD_ANNUAL = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
})

// Hourly rates keep their cents: $62.50/hr rounded to $63/hr is a different wage.
const USD_HOURLY = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
})

// The backend narrows currency to USD or OTHER, so a non-USD amount can only be
// shown as a bare number -- see the "non-USD" tag on the card.
const PLAIN = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 })

const POSTED = new Intl.DateTimeFormat('en-US', {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
})

export function formatSalary(salary: Salary | null): string {
  if (salary === null) return 'Salary not stated'

  const isUsd = salary.currency === 'USD'

  // Annual and hourly are alternatives, never both, so this branches rather
  // than trying to reconcile them.
  if (salary.min_hourly !== null) {
    const amount = isUsd ? USD_HOURLY.format(salary.min_hourly) : PLAIN.format(salary.min_hourly)
    return `${amount}/hr`
  }
  if (salary.min_annual !== null) {
    return isUsd ? USD_ANNUAL.format(salary.min_annual) : PLAIN.format(salary.min_annual)
  }
  return 'Salary not stated'
}

/**
 * Short flags for salary the pipeline had to guess at. Scraped feeds omit the
 * currency and the pay period constantly, and a number shown without that
 * caveat is a number the user will trust more than we do.
 */
export function salaryCaveats(salary: Salary | null): string[] {
  if (salary === null) return []

  const caveats: string[] = []
  if (salary.currency === 'OTHER') caveats.push('non-USD')
  else if (salary.inferred_currency) caveats.push('currency assumed')
  if (salary.inferred_period) caveats.push('rate inferred')
  return caveats
}

export function formatLocation(job: Job): string {
  const location = job.location
  const country = location?.country_code ? COUNTRY_LABELS[location.country_code] : null

  // A typed predicate rather than `.filter(Boolean)`, which doesn't narrow away
  // null under strict mode.
  const place = [location?.city, location?.region, country]
    .filter((part): part is string => Boolean(part))
    .join(', ')

  if (!place) return job.is_remote ? 'Remote' : 'Location not stated'
  return job.is_remote ? `${place} (Remote)` : place
}

export function formatPostingDate(iso: string | null): string {
  if (iso === null) return 'Date not stated'

  // Built from parts instead of `new Date(iso)`: that parses a bare YYYY-MM-DD
  // as UTC midnight, which renders as the previous day west of Greenwich.
  const [year, month, day] = iso.split('-').map(Number)
  if (!year || !month || !day) return iso
  return POSTED.format(new Date(year, month - 1, day))
}

/** Direction labels that read naturally for whichever field is being sorted. */
export function orderLabels(sortBy: SortField): { descending: string; ascending: string } {
  switch (sortBy) {
    case 'posting_date':
      return { descending: 'Newest first', ascending: 'Oldest first' }
    case 'title':
      return { descending: 'Z to A', ascending: 'A to Z' }
    default:
      return { descending: 'Highest first', ascending: 'Lowest first' }
  }
}
