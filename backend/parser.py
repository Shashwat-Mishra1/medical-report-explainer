import re

NUM = r"[-+]?\d[\d,]*\.?\d*"

ALIASES = {
    "hb": "Hemoglobin", "hgb": "Hemoglobin", "haemoglobin": "Hemoglobin",
    "hemoglobin": "Hemoglobin",
    "wbc": "WBC Count", "wbc count": "WBC Count", "total leucocyte count": "WBC Count",
    "total leukocyte count": "WBC Count", "tlc": "WBC Count",
    "rbc": "RBC Count", "rbc count": "RBC Count", "total rbc count": "RBC Count",
    "platelets": "Platelet Count", "platelet count": "Platelet Count", "plt": "Platelet Count",
    "fasting glucose": "Fasting Glucose", "fasting blood sugar": "Fasting Glucose",
    "fbs": "Fasting Glucose", "glucose fasting": "Fasting Glucose",
    "glucose - fasting": "Fasting Glucose", "blood sugar fasting": "Fasting Glucose",
    "hba1c": "HbA1c", "glycosylated hemoglobin": "HbA1c", "glycated hemoglobin": "HbA1c",
    "glycosylated haemoglobin": "HbA1c", "hemoglobin a1c": "HbA1c",
    "total cholesterol": "Total Cholesterol", "cholesterol": "Total Cholesterol",
    "cholesterol total": "Total Cholesterol", "cholesterol - total": "Total Cholesterol",
    "ldl": "LDL Cholesterol", "ldl cholesterol": "LDL Cholesterol",
    "ldl-c": "LDL Cholesterol", "ldl cholesterol direct": "LDL Cholesterol",
    "hdl": "HDL Cholesterol", "hdl cholesterol": "HDL Cholesterol", "hdl-c": "HDL Cholesterol",
    "triglycerides": "Triglycerides", "triglyceride": "Triglycerides", "tg": "Triglycerides",
    "tsh": "TSH", "thyroid stimulating hormone": "TSH",
    "tsh (thyroid stimulating hormone)": "TSH",
    "vitamin d": "Vitamin D", "vitamin d (25-oh)": "Vitamin D", "25-oh vitamin d": "Vitamin D",
    "25 hydroxy vitamin d": "Vitamin D", "vitamin d3": "Vitamin D",
    "vitamin b12": "Vitamin B12", "vit b12": "Vitamin B12", "vitamin b-12": "Vitamin B12",
    "cyanocobalamin": "Vitamin B12",
    "creatinine": "Creatinine", "serum creatinine": "Creatinine",
    "blood urea": "Blood Urea", "urea": "Blood Urea", "bun": "Blood Urea",
    "blood urea nitrogen": "Blood Urea",
    "uric acid": "Uric Acid", "serum uric acid": "Uric Acid",
    "sgpt": "ALT (SGPT)", "alt": "ALT (SGPT)", "alt (sgpt)": "ALT (SGPT)",
    "sgpt (alt)": "ALT (SGPT)", "alanine aminotransferase": "ALT (SGPT)",
    "sgot": "AST (SGOT)", "ast": "AST (SGOT)", "ast (sgot)": "AST (SGOT)",
    "sgot (ast)": "AST (SGOT)", "aspartate aminotransferase": "AST (SGOT)",
}


def to_float(s: str) -> float:
    return float(s.replace(",", ""))


def is_number(s: str) -> bool:
    return re.fullmatch(NUM, s.strip()) is not None


def parse_range(s: str):
    s = s.strip()
    m = re.fullmatch(rf"({NUM})\s*(?:-|–|—|to)\s*({NUM})", s)
    if m:
        return to_float(m.group(1)), to_float(m.group(2))
    m = re.fullmatch(rf"(?:<|≤|<=)\s*({NUM})", s)
    if m:
        return None, to_float(m.group(1))
    m = re.fullmatch(rf"(?:>|≥|>=)\s*({NUM})", s)
    if m:
        return to_float(m.group(1)), None
    return None


CANON = sorted(set(ALIASES.values()))
_KEY_TO_CANON = {**{k: v for k, v in ALIASES.items()}, **{c.lower(): c for c in CANON}}


def _distance(a: str, b: str) -> int:
    """Edit distance (insert / delete / replace one character = 1)."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def resolve_name(name: str):
    """Returns (canonical_name, note). note explains a fuzzy match, else None.
    Only near-misses of a few characters are matched, so unrelated tests are never renamed."""
    clean = name.strip()
    key = re.sub(r"\s+", " ", clean.lower())
    if key in _KEY_TO_CANON:
        return _KEY_TO_CANON[key], None
    if len(key) >= 5:
        allowed = 1 if len(key) <= 9 else 2
        best = {}
        for k, canon in _KEY_TO_CANON.items():
            if len(k) >= 5 and abs(len(k) - len(key)) <= allowed:
                d = _distance(key, k)
                if d <= allowed:
                    best[canon] = min(d, best.get(canon, 99))
        if best:
            lowest = min(best.values())
            winners = [c for c, d in best.items() if d == lowest]
            if len(winners) == 1:
                return winners[0], f'The name was read as "{clean}" and matched to {winners[0]}.'
    return clean, None


def canonical_name(name: str) -> str:
    return resolve_name(name)[0]


def plausibility_warning(value: float, low, high):
    """Catch OCR slips such as 4.1 read as 41. These thresholds are project heuristics."""
    if high and value > high * 5:
        return "This value is far above the normal range. A decimal point may have been misread."
    if low and low > 0 and value < low / 5:
        return "This value is far below the normal range. A digit may have been misread."
    if not high and low and value > low * 10:
        return "This value is unusually high. A digit may have been misread."
    return None


def get_status(value, low, high):
    if low is not None and value < low:
        return "critical_low" if value < low * 0.7 else "low"
    if high is not None and value > high:
        return "critical_high" if value > high * 1.5 else "high"
    return "normal"


def make_test(name, value, unit, rng):
    low, high = rng
    v = to_float(value)
    canon, name_note = resolve_name(name)
    parts = [p for p in (name_note, plausibility_warning(v, low, high)) if p]
    return {
        "test": canon,
        "value": v,
        "unit": unit.strip(),
        "ref_low": low,
        "ref_high": high,
        "status": get_status(v, low, high),
        "warning": " ".join(parts) + " Please check it against your report." if parts else None,
    }


ONE_LINE = re.compile(
    rf"^(?P<name>[A-Za-z][A-Za-z0-9 .()/%,-]*?)\s+(?P<value>{NUM})\s+(?P<unit>\S+)\s+(?P<range>.+)$"
)


def parse_report(text: str) -> list[dict]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    tests, i = [], 0
    while i < len(lines):
        m = ONE_LINE.match(lines[i])
        if m and parse_range(m["range"]):
            tests.append(make_test(m["name"], m["value"], m["unit"], parse_range(m["range"])))
            i += 1
            continue
        if i + 3 < len(lines):
            name, val, unit, rng = lines[i : i + 4]
            if (
                is_number(val)
                and not is_number(name)
                and parse_range(rng)
                and not parse_range(name)
            ):
                tests.append(make_test(name, val, unit, parse_range(rng)))
                i += 4
                continue
        i += 1
    return tests