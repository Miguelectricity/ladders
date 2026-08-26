import type { CountryCode, CountryOption, JobFilters, SortField } from '../api/types'
import { SORT_OPTIONS } from '../api/types'
import { orderLabels } from '../format'

interface Props {
  filters: JobFilters
  countries: CountryOption[]
  onChange: (patch: Partial<JobFilters>) => void
}

export function FilterBar({ filters, countries, onChange }: Props) {
  const order = orderLabels(filters.sortBy)

  return (
    // A form for the semantics and the search landmark; there's nothing to
    // submit, since every control applies as soon as it changes.
    <form className="filter-bar" role="search" onSubmit={(event) => event.preventDefault()}>
      <label className="field field-search">
        <span>Search by title</span>
        <input
          type="search"
          value={filters.query}
          placeholder="e.g. engineer"
          onChange={(event) => onChange({ query: event.target.value })}
        />
      </label>

      {/* Country and remote are separate questions -- where the job is, and how
          it is worked -- so they are separate controls that narrow together
          rather than one dropdown that mixes the two. */}
      <div className="field-location">
        <label className="field">
          <span>Location</span>
          <select
            value={filters.country}
            onChange={(event) => onChange({ country: event.target.value as CountryCode | '' })}
          >
            <option value="">All countries</option>
            {countries.map((country) => (
              <option key={country.code} value={country.code}>
                {country.label}
              </option>
            ))}
          </select>
        </label>

        <label className="toggle">
          <input
            type="checkbox"
            checked={filters.remote}
            onChange={(event) => onChange({ remote: event.target.checked })}
          />
          <span>Remote only</span>
        </label>
      </div>

      <label className="field">
        <span>Sort by</span>
        <select
          value={filters.sortBy}
          onChange={(event) => onChange({ sortBy: event.target.value as SortField })}
        >
          {SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label className="field">
        <span>Order</span>
        {/* Labels track the sort field, so the choice reads as "Newest first"
            on dates and "Highest first" on salary rather than "Descending". */}
        <select
          value={filters.descending ? 'desc' : 'asc'}
          onChange={(event) => onChange({ descending: event.target.value === 'desc' })}
        >
          <option value="desc">{order.descending}</option>
          <option value="asc">{order.ascending}</option>
        </select>
      </label>
    </form>
  )
}
