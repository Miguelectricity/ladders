from ladders.backend.models import CountryCode, EmploymentType, Job


def approve_jobs(jobs: list[Job]):
    approved = []
    rejected_with_reasons = []
    
    for job in jobs:
        if job.title == None:
            rejected_with_reasons.append((job, "No title"))
            continue
        
        if not job.is_remote:
            if job.location.country not in (CountryCode.US, CountryCode.CA):
                rejected_with_reasons.append((job, "Not in USA or Canada"))
                continue
        
        if job.employment_type != EmploymentType.FULL_TIME:
            rejected_with_reasons.append((job, "Not full-time"))
            continue
            
        approved.append(job)
    
    return approved # log rejected later

