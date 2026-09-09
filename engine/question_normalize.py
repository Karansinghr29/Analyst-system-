"""
question_normalize.py -- Owner-question cleanup before understanding.

Strips role address labels and applies *generic* typo-tolerant repair against a closed
vocabulary of time expressions and concept phrases. Never invents a metric_id: fuzzy
repair only rewrites surface text toward known catalogue phrases.
"""
import re
from functools import lru_cache

# Multi-word titles first so "data analyst" wins over bare "analyst".
_ROLE_LABELS = (
    "data analyst",
    "risk analyst",
    "financial analyst",
    "business analyst",
    "operations analyst",
    "management reporting analyst",
    "decision support analyst",
    "bi analyst",
    "data scientist",
    "risk dq analyst",
    "manager",
    "owner",
    "analyst",
)

_PROTECTED_OWNER = re.compile(
    r"\b(?:the|my|our|an)\s+(?:owner|manager)\s*$", re.I)

_ROLE_ALT = "|".join(re.escape(r) for r in _ROLE_LABELS)
_TRAILING_ROLE = re.compile(
    rf"^(?P<body>.+?)(?:\s*[,;:\-–—]\s*|\s+)(?P<role>{_ROLE_ALT})\s*$",
    re.I | re.S,
)
_WHOLE_ROLE = re.compile(rf"^(?:{_ROLE_ALT})\s*$", re.I)

# Canonical relative periods. Compact forms catch "thismonth" / split "thi smonth".
_TIME_PHRASES = (
    "this month", "current month", "last month", "previous month",
    "next month", "coming month", "upcoming month", "following month",
    "this year", "current year", "last year", "previous year",
    "this quarter", "current quarter", "last quarter", "previous quarter",
    "next quarter", "next year", "year to date", "ytd",
)

_MONTH_CANONICAL = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
)

# Common English that must NEVER be fuzzy-rewritten into catalogue tokens.
# ("there"→"where" was corrupting anomaly questions into different semantics.)
# ("went"→"rent" corrupted change questions into nonsense.)
# ("change"/"changed"/"changes"→"charged" and "previously"→"previous" silently turned every
#  change question into a lookup: "how did revenue change?" became "how did revenue charged",
#  which carries no trend, comparison or driver marker at all. Only words whose rewrite was
#  actually demonstrated are listed for that reason -- "changing", "history", "historical",
#  "growth", "movement", "compared", "comparison", "prior" and "last" survive the repair on
#  their own, and locking them would be guessing at a defect rather than fixing one. That they
#  survive is asserted in tests/test_change_semantics.py, so a future vocabulary change that
#  breaks one is caught rather than pre-empted here. `recent` joined them on the same
#  evidence: it was being rewritten to `receipt`, which turned "recent 3 months" into a
#  question about receipts.)
_ENGLISH_LOCKED = frozenset("""
a an the and or but if or as at by for from in into of on onto to with without
is are was were be been being am do does did doing done have has had having
not no nor so than then that this these those there their them they
what when where which who whom whose why how
can could may might must shall should will would
all any each every few more most other some such only own same
about above after again against all around because before below between both
during except inside outside over under until upon within
get got getting better worse down up high low still just also very too
unusual usual anything something nothing everything
make made making show shown tell told look looking ask asked
go going went gone come came
increase increased increasing decrease decreased decreasing
rise rose risen fall fell drop dropped grow grew grown
change changed changing changes history historical previously recent
lower higher more less
my our your his her its we you he she it
risk risks risky worry worrying worried
problem problems issue issues concern concerns concerning
area areas
need needs needed needing
""".split())

# Bilingual / colloquial vocabulary → English semantic tokens.
#
# This is vocabulary normalisation, not canned-question routing: each entry maps ONE word to the
# English word carrying the same meaning, and everything downstream -- intent classification,
# concept matching, period resolution -- then works on the English exactly as it always has.
# Adding a phrasing here therefore teaches the whole pipeline at once, which is the point. A
# handler per sentence would teach it nothing.
#
# The entries that matter most are the ones carrying ANALYTICAL meaning. "revenue epdi
# poguthu?" is a trend question and "revenue evlo?" is a lookup, and the only difference is a
# verb; dropping that verb as noise (which the earlier "" mappings did to `irukku`) collapsed
# every Tanglish question into a bare lookup of whatever measure it named.
_DEIXIS_AND_PARTICLES = {
    # -- deixis and interrogatives ---------------------------------------------------------
    "intha": "this", "inda": "this", "indha": "this", "inta": "this",
    "andha": "that", "antha": "that",
    "entha": "which", "enna": "what", "ennaa": "what",
    "yaaru": "who", "yar": "who",
    "edhavadhu": "any", "ethavathu": "any", "edhavathu": "any",
    "evlo": "how much", "evalo": "how much", "yevlo": "how much", "evvalavu": "how much",
    "epdi": "how", "eppadi": "how", "eppadiya": "how", "epdiya": "how",
    "yen": "why", "een": "why", "yaen": "why",
    "romba": "very", "konjam": "slightly",

    # -- movement and direction ---------------------------------------------------------------
    # A trend question in Tanglish is carried by the verb of motion, not by the word "trend".
    "poguthu": "trending", "pogudhu": "trending", "poothu": "trending",
    "poitu": "trending", "poyitu": "trending", "porathu": "trending",
    "aagudha": "improving", "aaguda": "improving", "agudha": "improving",
    "koranjucha": "decreased", "kurainjucha": "decreased", "koranjutha": "decreased",
    "koranjuthu": "decreased", "kurainjuthu": "decreased", "kuranjuchu": "decreased",
    "kammi": "decreased", "kuraiv": "decreased", "kurainthathu": "decreased",
    "kooduthal": "increased", "athigam": "increased", "adhigam": "increased",
    "yeruchu": "increased", "erunthuchu": "increased", "yerudhu": "increased",

    # -- tense and modality --------------------------------------------------------------------
    # These decide forecast vs history, so they must survive rather than be dropped as noise.
    "irukkum": "will be", "irukum": "will be", "varuma": "will",
    "varum": "will", "vanthuchu": "came", "nadanthuchu": "changed",
    "nadakuthu": "happening", "nadakkudhu": "happening",

    # -- verbs that carry no analytical meaning and only confuse the matcher ---------------------
    "sollu": "", "solunga": "", "kaamikka": "", "kaattu": "", "paaru": "",
    "pannu": "", "panna": "", "pannunga": "",
    "aacha": "", "acha": "", "aachaa": "", "aachu": "",
    "iruka": "", "irukku": "", "irukka": "", "irukkaa": "",
    "ah": "", "aa": "", "la": "", "le": "",
}


def _edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if abs(len(a) - len(b)) > 2:
        return 99
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            ins, delete, sub = cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb)
            cur.append(min(ins, delete, sub))
        prev = cur
    return prev[-1]


def _max_edits(word: str) -> int:
    n = len(word)
    if n < 4:
        return 0
    if n < 6:
        return 1
    return 2


def _best_vocab_match(token: str, vocab) -> str:
    """Return the unique closest vocabulary item within edit budget, else ''."""
    t = (token or "").lower()
    if not t or t in vocab:
        return t if t in vocab else ""
    if t in _ENGLISH_LOCKED:
        return ""
    budget = _max_edits(t)
    if budget <= 0:
        return ""
    hits = []
    for v in vocab:
        if v in _ENGLISH_LOCKED and v not in _MONTH_CANONICAL and v not in {
                "month", "months", "year", "years", "quarter", "quarters",
                "this", "last", "next", "current", "previous"}:
            continue
        # Never rewrite across a different initial letter (went→rent, full→july class).
        if t[0] != v[0]:
            continue
        d = _edit_distance(t, v)
        if d <= budget and d <= _max_edits(v):
            # Prefer shared prefix so "revenu"→"revenue" wins over unrelated edits.
            prefix = 0
            for a, b in zip(t, v):
                if a != b:
                    break
                prefix += 1
            if d >= 1 and prefix < min(3, len(t), len(v)) and len(t) >= 5:
                continue
            hits.append((d, -prefix, len(v), v))
    if not hits:
        return ""
    hits.sort()
    best_d = hits[0][0]
    same = [h for h in hits if h[0] == best_d]
    names = {h[3] for h in same}
    if len(names) > 1:
        return ""
    return hits[0][3]


def _stem_concept_plural(token: str, concept_words) -> str:
    t = (token or "").lower()
    if len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
        stem = t[:-1]
        if stem in concept_words:
            return stem
    return ""


@lru_cache(maxsize=1)
def _concept_vocab():
    from engine import concept_map
    words = set()
    phrases = []
    for c in concept_map.all_concepts():
        for p in c.phrases:
            pl = p.lower().strip()
            if not pl:
                continue
            phrases.append(pl)
            for w in re.findall(r"[a-z]{4,}", pl):
                if w not in _ENGLISH_LOCKED:
                    words.add(w)
    words.update({
        "revenue", "expense", "expenses", "collections", "occupancy", "profit",
        "invoice", "invoices", "deposit", "deposits", "maintenance", "tenant",
        "tenants", "receivable", "receivables", "dues", "sales", "income",
    })
    # Drop any locked English that leaked in from phrases ("where", "what", …).
    words -= _ENGLISH_LOCKED
    return frozenset(words), tuple(sorted(phrases, key=len, reverse=True))


def _time_vocab():
    words = set()
    for p in _TIME_PHRASES:
        for w in p.split():
            if len(w) >= 3:
                words.add(w)
    words.update(_MONTH_CANONICAL)
    words.update({"month", "months", "year", "years", "quarter", "quarters"})
    return frozenset(words)


def _strip_roles(text: str):
    stripped = []
    while True:
        if _PROTECTED_OWNER.search(text):
            break
        m = _TRAILING_ROLE.match(text)
        if not m:
            break
        role = m.group("role").strip().lower()
        body = m.group("body").strip().rstrip(",;:-–—").strip()
        if not body:
            break
        stripped.append(role)
        text = body
    if _WHOLE_ROLE.match(text) and not _PROTECTED_OWNER.search(text):
        stripped.append(text.strip().lower())
        text = ""
    return text, tuple(stripped)


def _repair_split_time_phrases(text: str) -> str:
    """Join adjacent tokens that form a known time phrase (handles 'thi smonth')."""
    tokens = text.split()
    if len(tokens) < 2:
        return text
    compact_map = {p.replace(" ", ""): p for p in _TIME_PHRASES}
    out = []
    i = 0
    while i < len(tokens):
        if i + 1 < len(tokens):
            glued = re.sub(r"[^a-z]", "", (tokens[i] + tokens[i + 1]).lower())
            # Exact compact hit or unique near-match against compact forms.
            hit = compact_map.get(glued)
            if not hit:
                cand = _best_vocab_match(glued, tuple(compact_map.keys()))
                hit = compact_map.get(cand) if cand else ""
            if hit:
                out.append(hit)
                i += 2
                continue
        out.append(tokens[i])
        i += 1
    return " ".join(out)


def _repair_tokens(text: str) -> str:
    concept_words, _concept_phrases = _concept_vocab()
    time_words = _time_vocab()
    # Fuzzy targets are domain/time only — never the broad English lexicon.
    vocab = tuple(sorted(concept_words | time_words | set(_MONTH_CANONICAL),
                         key=len, reverse=True))

    repaired = []
    for tok in text.split():
        low = re.sub(r"[^a-z]", "", tok.lower())
        if not low:
            repaired.append(tok)
            continue
        if low in _ENGLISH_LOCKED:
            repaired.append(tok)
            continue
        plural = _stem_concept_plural(low, concept_words)
        if plural:
            repaired.append(plural)
            continue
        # Leading 'a' glued to a concept ("arevenue" → "revenue").
        if len(low) >= 6 and low.startswith("a"):
            rest = _best_vocab_match(low[1:], vocab)
            if rest and rest in concept_words:
                repaired.append(rest)
                continue
        match = _best_vocab_match(low, vocab)
        repaired.append(match if match else tok)

    text = " ".join(repaired)
    text = re.sub(r"\s+", " ", text).strip()

    compact_map = {p.replace(" ", ""): p for p in _TIME_PHRASES}
    parts = []
    for tok in text.split():
        key = re.sub(r"[^a-z]", "", tok.lower())
        if key in _ENGLISH_LOCKED and key not in compact_map:
            parts.append(tok)
            continue
        if key in compact_map:
            parts.append(compact_map[key])
            continue
        near = _best_vocab_match(key, tuple(compact_map.keys()))
        if near:
            parts.append(compact_map[near])
            continue
        parts.append(tok)
    return " ".join(parts)


def _apply_deixis_and_particles(text: str) -> str:
    """Map colloquial/bilingual deixis and intensifiers to English semantic tokens."""
    parts = []
    for tok in text.split():
        # Possessives on time words: "month's" → "month" so "this month's revenue" keeps period.
        key = re.sub(r"[^a-z]", "", tok.lower())
        if key.endswith("s") and key[:-1] in {"month", "year", "quarter"}:
            key = key[:-1]
            tok = key
        mapped = _DEIXIS_AND_PARTICLES.get(key)
        if mapped is None:
            parts.append(tok)
        elif mapped == "":
            continue
        else:
            parts.extend(mapped.split())
    return " ".join(parts)


def normalize_owner_question(question: str) -> tuple:
    """Return (cleaned_question, stripped_labels).

    1) Strip trailing role address labels.
    2) Map bilingual deixis/particles to English semantic tokens.
    3) Typo-tolerant repair against time + concept vocabulary (never invents metric ids).
    """
    text = (question or "").strip()
    if not text:
        return "", ()

    text, stripped = _strip_roles(text)
    if not text.strip():
        return "", stripped

    text = text.lower()
    text = _apply_deixis_and_particles(text)
    text = _repair_split_time_phrases(text)
    text = _repair_tokens(text)
    text = _repair_split_time_phrases(text)  # second pass after token fixes
    text = re.sub(r"\s+", " ", text).strip()
    return text, stripped
