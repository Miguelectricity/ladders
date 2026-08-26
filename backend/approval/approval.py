import logging
from backend.models import (
    MARKETS,
    CompanyType,
    Currency,
    EmploymentType,
    Job,
    Market,
)

logger = logging.getLogger(__name__)

def is_job_in_market(job: Job, market: Market):
    job_country_code = job.location.country_code if job.location else None
    if market.countries is not None and job_country_code not in market.countries:
        return False
    
    if market.remote_only:
        if not job.is_remote:
            return False
        
    # assumption - checking only USD currency
    if job.salary is None:
        return False
    else:
        if job.salary.currency is Currency.USD:
            if job.salary.min_annual is not None and market.min_annual_salary is not None:
                if job.salary.min_annual < market.min_annual_salary:
                    return False
            elif job.salary.min_hourly is not None and market.min_hourly_salary is not None:
                if job.salary.min_hourly < market.min_hourly_salary:
                    return False    
            
    if market.languages:
        if job.language not in market.languages:
            return False
        
    return True
        
            

def approve_jobs(jobs: list[Job]):
    approved = []
    rejected_with_reasons = []
    
    for job in jobs:
        if not (job.title or "").strip():
            rejected_with_reasons.append((job, "No title"))
            continue
        
        if job.employment_type != EmploymentType.FULL_TIME:
            rejected_with_reasons.append((job, "Not full-time"))
            continue
        
        if job.company_type is CompanyType.STAFFING_FIRM:
            rejected_with_reasons.append((job, "Staffing firm"))
            continue
        
        is_in_at_least_one_market = False
        for market in MARKETS:
            if is_job_in_market(job, market):
                is_in_at_least_one_market = True
                break
        
        if is_in_at_least_one_market == False:
            rejected_with_reasons.append((job, "Not in any approved markets"))
            continue
        
        approved.append(job)
        
    
    # could store this more persistently later
    for job, reason in rejected_with_reasons:
        logger.info(f"Rejected {job.id} '{job.title}' at {job.company}: {reason}")
    
    return (approved, rejected_with_reasons)

