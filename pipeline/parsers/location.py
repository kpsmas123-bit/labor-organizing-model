import re

_REMOTE_RE = re.compile(r'\bremote\b', re.IGNORECASE)
_REMOTE_SLASH_RE = re.compile(r'(^remote\s*/|/\s*remote\b)', re.IGNORECASE)
_MULTIPLE_RE = re.compile(r'\bmultiple\s+locations?\b', re.IGNORECASE)
_SPLIT_RE = re.compile(r'\s*(?:;|\bor\b)\s*', re.IGNORECASE)


def parse_location(location_raw: str) -> dict:
    """
    Parse location_raw into city, state_abbr, is_remote.

    Returns: {"city": str|None, "state_abbr": str|None, "is_remote": bool}
    """
    result = {"city": None, "state_abbr": None, "is_remote": False}

    if not location_raw or not location_raw.strip():
        return result

    text = location_raw.strip()

    # Pure "Remote"
    if re.fullmatch(r'\s*remote\s*', text, re.IGNORECASE):
        result["is_remote"] = True
        return result

    # Contains "/ Remote" or "Remote /"
    if _REMOTE_SLASH_RE.search(text):
        result["is_remote"] = True
        # Strip the remote part and parse remaining
        text = _REMOTE_SLASH_RE.sub('', text).strip().strip('/').strip()
        if not text:
            return result

    # "Multiple locations"
    if _MULTIPLE_RE.search(text):
        return result

    # Multi-city string (separated by ";" or "or") — take first segment
    segments = _SPLIT_RE.split(text)
    text = segments[0].strip()

    # Standard "City, ST" — split on last comma
    if ',' in text:
        city_part, state_part = text.rsplit(',', 1)
        city = city_part.strip()
        state = state_part.strip()
        # Validate state looks like a 2-letter abbreviation
        if re.fullmatch(r'[A-Za-z]{2}', state):
            result["city"] = city if city else None
            result["state_abbr"] = state.upper()
            return result

    # Fallback — no parseable structure
    return result


if __name__ == "__main__":
    cases = [
        ("Washington, DC",           {"city": "Washington",   "state_abbr": "DC", "is_remote": False}),
        ("Remote",                   {"city": None,           "state_abbr": None, "is_remote": True}),
        ("remote",                   {"city": None,           "state_abbr": None, "is_remote": True}),
        ("Oakland, CA / Remote",     {"city": "Oakland",      "state_abbr": "CA", "is_remote": True}),
        ("Remote / Oakland, CA",     {"city": "Oakland",      "state_abbr": "CA", "is_remote": True}),
        ("Multiple Locations",       {"city": None,           "state_abbr": None, "is_remote": False}),
        ("Oakland, CA; San Francisco, CA", {"city": "Oakland","state_abbr": "CA", "is_remote": False}),
        ("Oakland, CA or Chicago, IL",     {"city": "Oakland","state_abbr": "CA", "is_remote": False}),
        ("",                         {"city": None,           "state_abbr": None, "is_remote": False}),
        ("Anywhere",                 {"city": None,           "state_abbr": None, "is_remote": False}),
    ]
    passed = 0
    for raw, expected in cases:
        got = parse_location(raw)
        ok = got == expected
        status = "PASS" if ok else "FAIL"
        if not ok:
            print(f"{status}: {raw!r}\n  expected {expected}\n  got      {got}")
        else:
            passed += 1
    print(f"{passed}/{len(cases)} passed")
