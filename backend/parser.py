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


# Typical lower / upper limits of each test's normal range. Only used to notice a range whose
# decimal point was lost by OCR (4.5-5.9 read as 45-59). Bands are deliberately wide.
BANDS = {
    "Hemoglobin": {"low": (10, 15), "high": (14, 18.5)},
    "WBC Count": {"low": (3000, 5000), "high": (10000, 12000)},
    "RBC Count": {"low": (3.5, 5.0), "high": (5.0, 6.5)},
    "Platelet Count": {"low": (100000, 200000), "high": (350000, 500000)},
    "Fasting Glucose": {"low": (60, 80), "high": (95, 126)},
    "HbA1c": {"low": (3.5, 4.6), "high": (5.5, 6.5)},
    "Total Cholesterol": {"high": (170, 240)},
    "LDL Cholesterol": {"high": (70, 160)},
    "HDL Cholesterol": {"low": (35, 60)},
    "Triglycerides": {"high": (130, 200)},
    "TSH": {"low": (0.2, 0.6), "high": (3.5, 6.0)},
    "Vitamin D": {"low": (20, 40), "high": (80, 120)},
    "Vitamin B12": {"low": (150, 300), "high": (800, 1200)},
    "Creatinine": {"low": (0.4, 0.8), "high": (1.0, 1.5)},
    "Blood Urea": {"low": (10, 20), "high": (35, 50)},
    "Uric Acid": {"low": (2.0, 4.0), "high": (5.5, 8.0)},
    "ALT (SGPT)": {"low": (5, 15), "high": (35, 60)},
    "AST (SGOT)": {"low": (5, 15), "high": (30, 50)},
}


def repair_bound(canon: str, which: str, x):
    """If x is outside its usual band but x/10 or x/100 is inside, the decimal point was probably lost."""
    band = BANDS.get(canon, {}).get(which)
    if x is None or band is None or band[0] <= x <= band[1]:
        return x, False
    for div in (10, 100):
        y = x / div
        if band[0] <= y <= band[1]:
            return round(y, 2), True
    return x, False


def fmt_bound(x) -> str:
    return f"{x:g}"


def show_range(low, high) -> str:
    if low is not None and high is not None:
        return f"{low:g}-{high:g}"
    return f"below {high:g}" if high is not None else f"above {low:g}"


def make_test(name, value, unit, rng):
    low, high = rng
    v = to_float(value)
    canon, name_note = resolve_name(name)
    notes = [name_note]
    new_low, fixed_low = repair_bound(canon, "low", low)
    new_high, fixed_high = repair_bound(canon, "high", high)
    if fixed_low or fixed_high:
        notes.append(f"The normal range looked misread ({show_range(low, high)}) "
                     f"and was corrected to {show_range(new_low, new_high)}.")
        low, high = new_low, new_high
    notes.append(plausibility_warning(v, low, high))
    parts = [p for p in notes if p]
    return {
        "test": canon,
        "value": v,
        "unit": unit.strip(),
        "ref_low": low,
        "ref_high": high,
        "status": get_status(v, low, high),
        "warning": " ".join(parts) + " Please check it against your report." if parts else None,
    }


FLAGS = {"h", "l", "hh", "ll", "high", "low", "h*", "l*", "*", "↑", "↓"}
ONE_LINE = re.compile(
    rf"^(?P<name>[A-Za-z][A-Za-z0-9 .()/%,-]*?)\s+(?P<value>{NUM})(?:\s+(?:H|L|HH|LL|High|Low|\*|↑|↓))?"
    rf"\s+(?P<unit>\S+)\s+(?P<range>.+)$"
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
        # Format B2: like B, with an extra H / L flag line after the value
        if i + 4 < len(lines):
            name, val, flag, unit, rng = lines[i : i + 5]
            if (
                is_number(val) and not is_number(name) and flag.lower() in FLAGS
                and parse_range(rng) and not parse_range(name)
            ):
                tests.append(make_test(name, val, unit, parse_range(rng)))
                i += 5
                continue
        # Format B: name / value / unit / range on four separate lines (text PDFs)
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