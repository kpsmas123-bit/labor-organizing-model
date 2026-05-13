import re
from typing import Optional

_HOURLY_RE = re.compile(r'\b(hourly|per\s+hour|/\s*hr)\b', re.IGNORECASE)
_ANNUAL_RE = re.compile(r'\b(annual|per\s+year|/\s*year|yearly|/\s*yr)\b', re.IGNORECASE)
# Matches dollar amounts: optional $, digits+commas, optional .decimals, optional k/K
_AMOUNT_RE = re.compile(r'\$?\s*(\d[\d,]*)(?:\.(\d{1,2}))?([kK])?')


def _parse_amount(int_part: str, dec_part: Optional[str], k_suffix: Optional[str], is_hourly: bool) -> Optional[float]:
    try:
        value = float(int_part.replace(',', ''))
        if dec_part and is_hourly:
            # Preserve cents for hourly rates
            value = float(f"{int(int_part.replace(',', ''))}.{dec_part}")
        if k_suffix:
            value *= 1000
        return round(value, 2)
    except ValueError:
        return None


def parse_salary(salary_raw: str) -> dict:
    """
    Parse salary_raw into salary_min, salary_max, salary_period.

    Returns: {"salary_min": float|None, "salary_max": float|None, "salary_period": str|None}
    salary_period: "hourly" | "annual" | None
    """
    result = {"salary_min": None, "salary_max": None, "salary_period": None}

    if not salary_raw or not salary_raw.strip():
        return result

    text = salary_raw.strip()

    # Determine period from explicit keywords
    if _HOURLY_RE.search(text):
        period = "hourly"
    elif _ANNUAL_RE.search(text):
        period = "annual"
    else:
        period = None  # infer from value magnitude after parsing

    # Find all dollar amounts in the string
    amounts = []
    for m in _AMOUNT_RE.finditer(text):
        int_part = m.group(1)
        dec_part = m.group(2)
        k_suffix = m.group(3)
        # Skip if it looks like a year (4-digit number around 1900-2100 with no $ prefix)
        if not m.group(0).startswith('$') and re.fullmatch(r'(19|20)\d{2}', int_part):
            continue
        val = _parse_amount(int_part, dec_part, k_suffix, is_hourly=(period == "hourly"))
        if val is not None:
            amounts.append(val)

    if not amounts:
        return result

    salary_min = amounts[0]
    salary_max = amounts[1] if len(amounts) >= 2 else None

    # Infer period from magnitude if not explicit
    if period is None:
        ref = salary_min
        period = "hourly" if ref < 500 else "annual"

    result["salary_min"] = salary_min
    result["salary_max"] = salary_max
    result["salary_period"] = period
    return result


if __name__ == "__main__":
    cases = [
        ("Salary: $108,394.48",     {"salary_min": 108394,  "salary_max": None,  "salary_period": "annual"}),
        ("$60k-$75k",               {"salary_min": 60000,   "salary_max": 75000, "salary_period": "annual"}),
        ("$60,000–$75,000",         {"salary_min": 60000,   "salary_max": 75000, "salary_period": "annual"}),
        ("$30/hr",                  {"salary_min": 30.0,    "salary_max": None,  "salary_period": "hourly"}),
        ("$30 per hour",            {"salary_min": 30.0,    "salary_max": None,  "salary_period": "hourly"}),
        ("$30.50/hr",               {"salary_min": 30.50,   "salary_max": None,  "salary_period": "hourly"}),
        ("$30–$35/hr",              {"salary_min": 30.0,    "salary_max": 35.0,  "salary_period": "hourly"}),
        ("$60,000–$75,000 annual",  {"salary_min": 60000,   "salary_max": 75000, "salary_period": "annual"}),
        ("$60k annual",             {"salary_min": 60000,   "salary_max": None,  "salary_period": "annual"}),
        ("$60,000/year",            {"salary_min": 60000,   "salary_max": None,  "salary_period": "annual"}),
        ("No salary listed",        {"salary_min": None,    "salary_max": None,  "salary_period": None}),
        ("",                        {"salary_min": None,    "salary_max": None,  "salary_period": None}),
    ]
    passed = 0
    for raw, expected in cases:
        got = parse_salary(raw)
        ok = got == expected
        status = "PASS" if ok else "FAIL"
        if not ok:
            print(f"{status}: {raw!r}\n  expected {expected}\n  got      {got}")
        else:
            passed += 1
    print(f"{passed}/{len(cases)} passed")
