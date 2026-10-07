"""{{convert}} / {{cvt}} measurements written out as readable text (shared by every
Wikipedia-text extractor: the species leads, the field-note candidates, the
ecoregion leads). strip_code() drops templates whole, so a measurement has to be
written out BEFORE it runs — the old two-argument regex kept "35 –" of
{{convert|35|–|46|cm}} and lost the rest ("grows to a length of 35 –.").

Written the way Wikipedia itself shows the INPUT side, abbreviated:
  {{convert|35|cm}}          35 cm          {{convert|35|–|46|cm|in}}   35–46 cm
  {{convert|35|to|46|cm}}    35 to 46 cm    {{convert|35|and|46|cm}}    35 and 46 cm
  {{convert|6|by|4|m}}       6 by 4 m       {{convert|5|ft|2|in|cm}}    5 ft 2 in
"to"/"and"/"or" stay words because the sentence around them needs them
("between 599 and 685 g", "males and females weighing 3.5 and 1.8 kg, respectively").

READABLE TEXT ONLY: Wikipedia text is field notes, never a source of card facts —
nothing here parses a size out; card sizes come from the trait sources."""
import re

# one level of templates inside is allowed: {{cvt|17|{{ndash}}|30.5|cm}}
CONVERT_RE = re.compile(r"\{\{\s*(?:convert|cvt)\s*\|((?:[^{}]|\{\{[^{}]*\}\})*)\}\}", re.I)
INNER_DASH_RE = re.compile(r"\{\{\s*(?:ndash|en ?dash|–|snd|spnd|spaced (?:ndash|en dash))\s*\}\}", re.I)
INNER_RE = re.compile(r"\{\{[^{}]*\}\}")
BIG = {"3": "thousand", "6": "million", "9": "billion", "12": "trillion"}      # {{convert|5.4|e6kg}}

_NUM = r"[-−+]?(?:\d[\d,]*(?:\.\d*)?|\.\d+)(?:\+\d+/\d+|/\d+)?"          # "3." is typed often enough
NUM_RE = re.compile(_NUM)
NUM_RANGE_RE = re.compile(rf"({_NUM})\s*[-–—]\s*({_NUM})")      # a range typed into ONE argument: 0.4-1.2
DASH = "–"
JOIN = {"-": DASH, "–": DASH, "—": DASH, "&ndash;": DASH, "to(-)": " to ", "to-": " to ",
        "to": " to ", "to about": " to about ", "and": " and ", "and(-)": " and ", "or": " or ",
        "by": " by ", "x": " × ", "×": " × ", "xx": " × ", "*": " × ",
        "+/-": " ± ", "±": " ± ", "&plusmn;": " ± ", ",": ", ", ", and": ", and ", ", or": ", or "}
# second input unit of a two-part measurement ({{convert|5|ft|2|in}})
SECOND_UNIT = {"ft": {"in"}, "yd": {"ft"}, "mi": {"ft", "yd"}, "lb": {"oz"}, "st": {"lb"}, "h": {"min"}, "min": {"s"}}
UNIT = {"C": "°C", "F": "°F", "C-change": "°C", "F-change": "°F", "sqmi": "sq mi", "mi2": "sq mi",
        "sqft": "sq ft", "ft2": "sq ft", "sqin": "sq in", "in2": "sq in", "sqyd": "sq yd", "sqkm": "km²", "sqm": "m²",
        "cuft": "cu ft", "cuin": "cu in", "tonne": "t", "tonnes": "t", "MT": "t", "ST": "short tons", "LT": "long tons",
        "acre": "acres", "foot": "ft", "feet": "ft", "inch": "in", "mile": "miles", "lbs": "lb", "kph": "km/h",
        "um": "μm", "USgal": "US gal", "impgal": "imp gal"}

def _unit(u):
    big = re.fullmatch(r"e(3|6|9|12)(\S.*)", u)
    if big: return f"{BIG[big.group(1)]} {_unit(big.group(2))}"
    pre = "/" if u.startswith("/") else ""          # densities: /km2
    u = u[len(pre):]
    if u in UNIT: return pre + UNIT[u]
    return pre + re.sub(r"(?<=[A-Za-zμ])([23])$", lambda m: "²" if m.group(1) == "2" else "³", u)

def _num(n):
    n = re.sub(r"^-", "−", n).rstrip(".")           # a real minus sign, as Wikipedia shows it
    # 11100000 km2 -> 11,100,000 km² (five digits and up; 1500 m reads fine as it is)
    return re.sub(r"^([−+]?)(\d{5,})(?=$|\.)", lambda m: m.group(1) + f"{int(m.group(2)):,}", n)

def convert_text(args):
    """the readable text of one {{convert}}, given what is between its first | and }}"""
    args = INNER_RE.sub("", INNER_DASH_RE.sub(DASH, args))
    parts = [a.strip() for a in args.split("|")]
    named = {a.split("=", 1)[0].strip(): a.split("=", 1)[1].strip() for a in parts if "=" in a}
    pos = [a for a in parts if "=" not in a and a]
    if not pos: return ""
    i = 1
    if NUM_RE.fullmatch(pos[0]):
        out = _num(pos[0]); negative = pos[0][0] in "-−"
        while i + 1 < len(pos) and pos[i].lower() in JOIN and NUM_RE.fullmatch(pos[i + 1]):
            join = JOIN[pos[i].lower()]; negative = negative or pos[i + 1][0] in "-−"
            if join == DASH and negative: join = " to "        # −5–−2 is unreadable
            out += join + _num(pos[i + 1]); i += 2
    else:
        m = NUM_RANGE_RE.fullmatch(pos[0])
        if not m:                                   # not a number at all: what the old regex did
            return " ".join(pos[:2])
        out = _num(m.group(1)) + DASH + _num(m.group(2))
    if i < len(pos) and not NUM_RE.fullmatch(pos[i]):
        unit = pos[i]; i += 1
        out += ("" if unit.startswith("/") else " ") + _unit(unit)
        if i + 1 < len(pos) and NUM_RE.fullmatch(pos[i]) and pos[i + 1] in SECOND_UNIT.get(unit, ()):
            out += f" {_num(pos[i])} {_unit(pos[i + 1])}"; i += 2
        if named.get("adj") == "mid":               # {{convert|28|cm|adj=mid|-long}} -> 28 cm-long
            mid = next((a for a in pos[i:] if re.fullmatch(r"-[A-Za-z][A-Za-z -]*", a)), "")
            out += mid
    return out

def render_converts(wt):
    """every {{convert}}/{{cvt}} in the wikitext replaced by its readable text"""
    return CONVERT_RE.sub(lambda m: convert_text(m.group(1)), wt or "")

# what shipped before 2026-09-29 — kept so the re-extraction can prove it is looking
# at the same article text the shipped note came from (reextract_convert_notes.py)
LEGACY_CONVERT_RE = re.compile(r"\{\{(?:convert|cvt)\s*\|\s*([^|}]+)\s*\|\s*([^|}]+)[^}]*\}\}", re.I)
def render_converts_legacy(wt):
    return LEGACY_CONVERT_RE.sub(r"\1 \2", wt or "")

if __name__ == "__main__":
    CASES = [
        ("{{convert|35|–|46|cm}}", "35–46 cm"),
        ("{{convert|35|-|46|cm|in|abbr=on}}", "35–46 cm"),
        ("{{convert|35|to|46|cm}}", "35 to 46 cm"),
        ("{{convert|35|and|46|cm}}", "35 and 46 cm"),
        ("{{cvt|35|–|46|cm}}", "35–46 cm"),
        ("{{Convert | 35 | – | 46 | cm | in }}", "35–46 cm"),
        ("{{convert|35|&ndash;|46|cm}}", "35–46 cm"),
        ("{{convert|35|to(-)|46|cm}}", "35 to 46 cm"),
        ("{{convert|575|m}}", "575 m"),
        ("{{convert|575|m|ft|0}}", "575 m"),
        ("{{convert|70|cm|in|abbr=on}}", "70 cm"),
        ("{{convert|2.7|and|3.2|m|ftin}}", "2.7 and 3.2 m"),
        ("{{convert|6|by|4|m}}", "6 by 4 m"),
        ("{{convert|6|x|4|x|2|cm}}", "6 × 4 × 2 cm"),
        ("{{convert|5|ft|2|in|cm}}", "5 ft 2 in"),
        ("{{convert|5|ft|2}}", "5 ft"),
        ("{{convert|0.4-1.2|mi2|km2}}", "0.4–1.2 sq mi"),
        ("{{convert|1–3.5|cm}}", "1–3.5 cm"),
        ("{{convert|3|to|5|km2|sqmi}}", "3 to 5 km²"),
        ("{{convert|3|/km2|/sqmi}}", "3/km²"),
        ("{{convert|20|-|25|C|F}}", "20–25 °C"),
        ("{{convert|-5|-|-2|C}}", "−5 to −2 °C"),
        ("{{convert|-40|°C}}", "−40 °C"),
        ("{{convert|1,200|-|3,000|m}}", "1,200–3,000 m"),
        ("{{convert|1/2|in}}", "1/2 in"),
        ("{{cvt|17|{{ndash}}|30.5|cm}}", "17–30.5 cm"),
        ("{{convert|5|m|ft|abbr={{yes}}}}", "5 m"),
        ("{{convert|5.4|e6kg}}", "5.4 million kg"),
        ("{{convert|1.5|-|3.|kg}}", "1.5–3 kg"),
        ("{{convert|11100000|km2}}", "11,100,000 km²"),
        ("{{convert|12500.5|-|1500|ha}}", "12,500.5–1500 ha"),
        ("{{convert|28|–|33|cm|in|adj=mid|-long}}", "28–33 cm-long"),
        ("{{convert|28|cm|adj=on}}", "28 cm"),
        ("{{convert|6|-|8|tonne}}", "6–8 t"),
        ("{{convert|several|m}}", "several m"),
        ("grows to {{convert|35|–|46|cm}} and weighs {{cvt|250|to|450|g|oz}}.", "grows to 35–46 cm and weighs 250 to 450 g."),
    ]
    bad = [(w, render_converts(w), want) for w, want in CASES if render_converts(w) != want]
    for w, got, want in bad: print(f"FAIL {w}\n   got  {got!r}\n   want {want!r}")
    print(f"{len(CASES) - len(bad)}/{len(CASES)} convert forms render as expected")
    raise SystemExit(1 if bad else 0)
