import type { Job } from '../api/types'
import { formatLocation, formatPostingDate, formatSalary, salaryCaveats } from '../format'

export function JobCard({ job }: { job: Job }) {
  const caveats = salaryCaveats(job.salary)

  return (
    <article className="job-card">
      <header className="job-head">
        {/* Approval guarantees a title, but the type doesn't -- and every
            fallback here is a row from the feed the user would otherwise see
            as blank space. */}
        <h3 className="job-title">{job.title ?? 'Untitled role'}</h3>
        <p className="job-company">{job.company ?? 'Company not stated'}</p>
      </header>

      <dl className="job-facts">
        <div className="fact">
          <dt>Location</dt>
          <dd>{formatLocation(job)}</dd>
        </div>
        <div className="fact">
          <dt>Salary</dt>
          <dd>
            <span className="salary">{formatSalary(job.salary)}</span>
            {caveats.map((caveat) => (
              <span key={caveat} className="tag">
                {caveat}
              </span>
            ))}
          </dd>
        </div>
        <div className="fact">
          <dt>Posted</dt>
          <dd>{formatPostingDate(job.posting_date)}</dd>
        </div>
      </dl>

      {job.description !== null && <p className="job-description">{job.description}</p>}
    </article>
  )
}
