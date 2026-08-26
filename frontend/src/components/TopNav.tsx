/**
 * Site chrome around the job search. Every control here is a placeholder for a
 * page that doesn't exist yet, so they are buttons without handlers rather than
 * links: a bare `href="#"` would still change the URL and scroll the page.
 */
const NAV_PAGES = ['Apply4Me', 'For Employers', 'Resume Services']

export function TopNav() {
  return (
    <nav className="top-nav" aria-label="Main">
      <div className="top-nav-inner">
        <span className="brand">Ladders</span>

        <ul className="nav-pages">
          {NAV_PAGES.map((page) => (
            <li key={page}>
              <button type="button" className="nav-link">
                {page}
              </button>
            </li>
          ))}
        </ul>

        <button type="button" className="nav-auth">
          Sign In / Sign Up
        </button>
      </div>
    </nav>
  )
}
