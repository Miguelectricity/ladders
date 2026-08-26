from typing import Any

from ladders.backend.ingestion.parsers.helpers import collapse, to_clean_string
from ladders.backend.models import CompanyType

COMPANY_TYPES = {
    "directemployer": CompanyType.DIRECT_EMPLOYER,
    "direct": CompanyType.DIRECT_EMPLOYER,
    "employer": CompanyType.DIRECT_EMPLOYER,
    "directhire": CompanyType.DIRECT_EMPLOYER,
    "staffingfirm": CompanyType.STAFFING_FIRM,
    "staffing": CompanyType.STAFFING_FIRM,
    "staffingagency": CompanyType.STAFFING_FIRM,
    "recruiter": CompanyType.STAFFING_FIRM,
    "recruitingagency": CompanyType.STAFFING_FIRM,
    "recruitmentagency": CompanyType.STAFFING_FIRM,
    "consultingagency": CompanyType.CONSULTING_AGENCY,
    "consulting": CompanyType.CONSULTING_AGENCY,
    "consultingfirm": CompanyType.CONSULTING_AGENCY,
    "consultancy": CompanyType.CONSULTING_AGENCY,
}


def parse_company_type(value: Any) -> CompanyType:
    text = to_clean_string(value)
    if text is None:
        return CompanyType.UNKNOWN

    return COMPANY_TYPES.get(collapse(text), CompanyType.UNKNOWN)
