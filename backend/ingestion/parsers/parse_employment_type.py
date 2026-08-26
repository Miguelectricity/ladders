from typing import Any

from ladders.backend.ingestion.parsers.helpers import collapse, to_clean_string
from ladders.backend.models import EmploymentType

EMPLOYMENT_TYPES = {
    "fulltime": EmploymentType.FULL_TIME,
    "ft": EmploymentType.FULL_TIME,
    "permanent": EmploymentType.FULL_TIME,
    "parttime": EmploymentType.PART_TIME,
    "pt": EmploymentType.PART_TIME,
    "internship": EmploymentType.INTERNSHIP,
    "intern": EmploymentType.INTERNSHIP,
    "coop": EmploymentType.INTERNSHIP,
    "contract": EmploymentType.CONTRACT,
    "contractor": EmploymentType.CONTRACT,
    "contracttohire": EmploymentType.CONTRACT,
    "freelance": EmploymentType.CONTRACT,
    "temporary": EmploymentType.CONTRACT,
    "temp": EmploymentType.CONTRACT,
}


def parse_employment_type(value: Any) -> EmploymentType:
    text = to_clean_string(value)
    if text is None:
        return EmploymentType.UNKNOWN

    return EMPLOYMENT_TYPES.get(collapse(text), EmploymentType.UNKNOWN)
