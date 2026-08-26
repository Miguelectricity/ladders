import type { Job } from '../api/types'
import { JobCard } from './JobCard'

export function JobList({ jobs }: { jobs: Job[] }) {
  return (
    <ul className="job-list">
      {jobs.map((job) => (
        // The id is the content hash from ingestion, so it's stable across
        // refetches and React can keep card state where it belongs.
        <li key={job.id}>
          <JobCard job={job} />
        </li>
      ))}
    </ul>
  )
}
