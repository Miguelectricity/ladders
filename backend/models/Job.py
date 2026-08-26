from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

class EmploymentType(StrEnum):
    PART_TIME = "part-time"
    FULL_TIME = "full-time"
    INTERNSHIP = "internship"
    CONTRACT = "contract"
    UNKNOWN = "unknown"
    
class CompanyType(StrEnum):
    DIRECT_EMPLOYER = "direct-employer"
    STAFFING_FIRM = "staffing-firm"
    CONSULTING_AGENCY = "consulting-agency"
    UNKNOWN = "unknown"
    
class Language(StrEnum):
    EN = "english"
    FR = "french"
    UNKNOWN = "unknown"
    
class CountryCode(StrEnum):
    US = "US"
    CA = "CA"
    OTHER = "other"
    
class Currency(StrEnum):
    USD = "USD"
    OTHER = "OTHER"
    
@dataclass
class Salary:
    raw: Any
    min_annual: Decimal | None
    min_hourly: Decimal | None
    currency: Currency | None
    inferred_currency: bool = False
    inferred_period: bool = False

@dataclass
class Location:
    raw: Any
    city: str | None
    region: str | None
    country_code: CountryCode | None

@dataclass
class Job:
    id: str
    title: str | None
    description: str | None
    company: str | None
    location: Location | None
    salary: Salary | None
    employment_type: EmploymentType | None
    posting_date: date | None
    company_type: CompanyType | None
    language: Language | None
    is_remote: bool | None



