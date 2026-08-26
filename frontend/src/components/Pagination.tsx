import type { JobPage } from '../api/types'
import { totalPages } from '../api/types'

interface Props {
  page: JobPage
  onPageChange: (page: number) => void
}

export function Pagination({ page, onPageChange }: Props) {
  const pages = totalPages(page)
  if (pages <= 1) return null

  const first = page.page * page.page_size + 1
  const last = first + page.items.length - 1

  return (
    <nav className="pagination" aria-label="Result pages">
      <button
        type="button"
        disabled={page.page === 0}
        onClick={() => onPageChange(page.page - 1)}
      >
        Previous
      </button>

      {/* aria-live so the range is announced after a page move, which is
          otherwise a silent change for a screen reader user. */}
      <p className="page-count" aria-live="polite">
        {page.items.length > 0
          ? `Showing ${first}–${last} of ${page.total}`
          : `No results on page ${page.page + 1}`}
      </p>

      <button
        type="button"
        disabled={page.page >= pages - 1}
        onClick={() => onPageChange(page.page + 1)}
      >
        Next
      </button>
    </nav>
  )
}
