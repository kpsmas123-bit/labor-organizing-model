"""
Special requirements extractor — scans job description for structured tags.

Returns a list of strings like ["bilingual Spanish", "travel 50%", "driver's license"].
"""
import re
from typing import List

_BILINGUAL_RE = re.compile(
    r'\bbilingual\b(?:\s+(?:in\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?))?',
    re.IGNORECASE
)
_TRAVEL_RE = re.compile(
    r'\btravel\b(?:[^.]{0,30}?(\d{1,3})\s*%)?',
    re.IGNORECASE
)
_LICENSE_RE = re.compile(
    r"\b(driver'?s?\s+license|valid\s+(?:driver'?s?\s+)?license)\b",
    re.IGNORECASE
)
_NIGHTS_WEEKENDS_RE = re.compile(
    r'\b(nights?\s+and\s+weekends?|evening\s+hours?|weekend\s+work|nights/weekends?)\b',
    re.IGNORECASE
)
_RELOCATION_RE = re.compile(
    r'\b(relocation|must\s+relocate|willing\s+to\s+relocate|required\s+to\s+relocate)\b',
    re.IGNORECASE
)

# Known language names to validate bilingual extraction
_LANGUAGES = re.compile(
    r'\b(Spanish|Mandarin|Cantonese|Chinese|Vietnamese|Korean|Tagalog|Arabic|French'
    r'|Portuguese|Russian|Haitian\s+Creole|Somali|Hmong|Amharic|Khmer|Punjabi'
    r'|Hindi|Urdu|Polish|Italian|German|Japanese)\b',
    re.IGNORECASE
)


def extract_special_requirements(description: str) -> List[str]:
    """
    Returns list of special requirement tags found in description.
    """
    if not description:
        return []

    tags = []
    text = description

    # Bilingual
    m = _BILINGUAL_RE.search(text)
    if m:
        lang_match = _LANGUAGES.search(text[max(0, m.start() - 5):m.end() + 80])
        if lang_match:
            tags.append(f'bilingual {lang_match.group(0).capitalize()}')
        else:
            tags.append('bilingual')

    # Travel
    m = _TRAVEL_RE.search(text)
    if m:
        pct = m.group(1)
        tags.append(f'travel {pct}%' if pct else 'travel required')

    # Driver's license
    if _LICENSE_RE.search(text):
        tags.append("driver's license")

    # Nights/weekends
    if _NIGHTS_WEEKENDS_RE.search(text):
        tags.append('nights/weekends')

    # Relocation
    if _RELOCATION_RE.search(text):
        tags.append('relocation required')

    return tags


if __name__ == '__main__':
    cases = [
        ('Must be bilingual in Spanish and English.',        ['bilingual Spanish']),
        ('Bilingual preferred.',                             ['bilingual']),
        ('Requires travel 50% of the time.',                 ['travel 50%']),
        ('Requires significant travel.',                     ['travel required']),
        ('Valid driver\'s license required.',                ["driver's license"]),
        ('Must work evenings and weekend work expected.',    ['nights/weekends']),
        ('Relocation to Chicago required.',                  ['relocation required']),
        ('No special requirements.',                         []),
        ('Bilingual Mandarin; travel 30%; must relocate.',   ['bilingual Mandarin', 'travel 30%', 'relocation required']),
    ]
    passed = 0
    for desc, expected in cases:
        got = extract_special_requirements(desc)
        ok = got == expected
        if not ok:
            print(f'FAIL: {desc!r}')
            print(f'  expected {expected}')
            print(f'  got      {got}')
        else:
            passed += 1
    print(f'{passed}/{len(cases)} passed')
