"""
utils.py
Language detection, answer normalisation, and stem selection utilities.
All logic is pure Python — no external API calls.
Includes Levenshtein-based fuzzy matching for child mispronunciations.
"""

import re
import unicodedata

# ── Number word dictionaries ────────────────────────────────────────────────

NUMBER_WORDS = {
    "en": {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
        "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
        "nineteen": 19, "twenty": 20,
    },
    "kin": {
        "rimwe": 1, "kabiri": 2, "gatatu": 3, "kane": 4, "gatanu": 5,
        "gatandatu": 6, "karindwi": 7, "umunani": 8, "icyenda": 9,
        "icumi": 10, "cumi na rimwe": 11, "cumi na kabiri": 12,
    },
    "fr": {
        "un": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
        "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
        "onze": 11, "douze": 12, "treize": 13, "quatorze": 14,
        "quinze": 15, "seize": 16, "dix-sept": 17, "dix-huit": 18,
        "dix-neuf": 19, "vingt": 20,
    },
}

# Language detection keywords (non-numeric, language-distinctive)
_LANG_KEYWORDS = {
    "en":  {"how", "many", "which", "bigger", "plus", "minus", "equals",
            "number", "between", "and", "the", "is", "what", "does"},
    "kin": {"zingahe", "angahe", "rimwe", "kabiri", "gatatu", "kane",
            "gatanu", "gatandatu", "karindwi", "umunani", "icyenda",
            "icumi", "cyangwa", "nimero", "nini", "ni", "pome", "ihene",
            "imyembe", "gerageza", "muraho", "byiza"},
    "fr":  {"combien", "quel", "nombre", "plus", "moins", "égale",
            "grand", "entre", "les", "de", "est", "qu", "ou", "des"},
}


def _levenshtein(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if not s2:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            ins  = prev[j + 1] + 1
            dlt  = curr[j] + 1
            sub  = prev[j] + (c1 != c2)
            curr.append(min(ins, dlt, sub))
        prev = curr
    return prev[-1]


def _normalise_text(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace."""
    text = text.lower().strip()
    # unicode normalise
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"\s+", " ", text)
    return text


def detect_language(text: str) -> str:
    """
    Detect the dominant language of a text string.

    Logic: count keyword matches per language; return the dominant one.
    Returns 'mixed' if two languages each have ≥ 1 match.

    Parameters
    ----------
    text : raw input string

    Returns
    -------
    str  — 'en', 'kin', 'fr', or 'mixed'
    """
    norm = _normalise_text(text)
    tokens = set(re.findall(r"[a-z\-]+", norm))

    scores = {}
    for lang, keywords in _LANG_KEYWORDS.items():
        scores[lang] = len(tokens & keywords)

    # also check number words
    for lang, nums in NUMBER_WORDS.items():
        for word in nums:
            if word in norm:
                scores[lang] = scores.get(lang, 0) + 1

    above_zero = {lang: v for lang, v in scores.items() if v > 0}
    if not above_zero:
        return "en"  # default
    if len(above_zero) >= 2:
        return "mixed"
    return max(above_zero, key=above_zero.get)


def normalize_answer(text: str, language: str = "en"):
    """
    Parse a child's spoken/typed answer into an integer.

    Handles:
    - Digit strings: "5", "12"
    - Word forms: "five", "gatanu", "cinq"
    - Fuzzy match: Levenshtein distance ≤ 2 for misspellings
      e.g. "twewenti" → 20, "tu" → 2, "esheshatu" → 3 (gatatu)

    Parameters
    ----------
    text     : raw answer string
    language : detected or preferred language ('en', 'kin', 'fr', 'mixed')

    Returns
    -------
    int or None  — parsed answer, or None if unparseable
    """
    # Child-speech correction map (mirrors asr_adapt.CHILD_CORRECTIONS)
    _CHILD_CORRECTIONS = {
        "twewenti": "twenty", "tweny": "twenty", "toenty": "twenty",
        "tu": "two", "fife": "five", "treee": "three", "fore": "four",
        "nyne": "nine", "ayght": "eight", "siks": "six",
        "eleben": "eleven", "twelv": "twelve",
        "esheshatu": "gatatu", "gatato": "gatatu", "gataro": "gatatu",
        "iycumi": "icumi", "icyumi": "icumi",
        "karindui": "karindwi", "umuani": "umunani",
    }

    norm = _normalise_text(text)
    norm_stripped = re.sub(r"[^a-z0-9\s\-]", "", norm).strip()

    # Apply child correction map first
    if norm_stripped in _CHILD_CORRECTIONS:
        norm_stripped = _CHILD_CORRECTIONS[norm_stripped]
    else:
        # token-level correction
        tokens = norm_stripped.split()
        corrected_tokens = []
        for tok in tokens:
            corrected_tokens.append(_CHILD_CORRECTIONS.get(tok, tok))
        norm_stripped = " ".join(corrected_tokens)

    # 1. Try direct integer parse
    try:
        return int(norm_stripped)
    except ValueError:
        pass

    # extract first digit sequence
    m = re.search(r"\d+", norm_stripped)
    if m:
        return int(m.group())

    # 2. Try exact word match — always search all dicts after child correction
    # (correction may map a KIN/FR mispronunciation to an EN canonical form)
    langs_to_try = list(NUMBER_WORDS.keys())

    for lang in langs_to_try:
        num_dict = NUMBER_WORDS[lang]
        # check multi-word first (e.g. "cumi na rimwe" = 11)
        for phrase in sorted(num_dict.keys(), key=len, reverse=True):
            if phrase in norm_stripped:
                return num_dict[phrase]

    # 3. Fuzzy match (Levenshtein ≤ 2)
    best_val  = None
    best_dist = 3  # threshold
    all_words = {}
    for lang in langs_to_try:
        all_words.update(NUMBER_WORDS[lang])

    for word, val in all_words.items():
        dist = _levenshtein(norm_stripped, word)
        if dist < best_dist:
            best_dist = dist
            best_val  = val

    return best_val  # None if no match within distance 2


def get_stem(item: dict, language: str) -> str:
    """
    Return the question stem in the preferred language.

    Falls back to stem_en if the requested language stem is missing.

    Parameters
    ----------
    item     : curriculum item dict
    language : 'en', 'kin', 'fr', or 'mixed'

    Returns
    -------
    str  — question stem text
    """
    mapping = {
        "kin":   "stem_kin",
        "fr":    "stem_fr",
        "mixed": "stem_en",
    }
    key = mapping.get(language, "stem_en")
    return item.get(key) or item.get("stem_en", "")


def mixed_language_response(text: str) -> dict:
    """
    Analyse a code-switched / multilingual response.

    Parameters
    ----------
    text : raw response string

    Returns
    -------
    dict with keys:
        dominant  : str ('en', 'kin', 'fr', or 'mixed')
        secondary : str (second detected language or '')
        answer    : int or None
    """
    norm = _normalise_text(text)
    tokens = set(re.findall(r"[a-z\-]+", norm))

    scores = {}
    for lang, keywords in _LANG_KEYWORDS.items():
        scores[lang] = len(tokens & keywords)

    sorted_langs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    dominant  = sorted_langs[0][0] if sorted_langs[0][1] > 0 else "en"
    secondary = sorted_langs[1][0] if len(sorted_langs) > 1 and sorted_langs[1][1] > 0 else ""

    answer = normalize_answer(text, dominant)
    return {"dominant": dominant, "secondary": secondary, "answer": answer}


if __name__ == "__main__":
    tests = [
        ("five", "en"),
        ("tu", "fr"),
        ("esheshatu", "kin"),
        ("twewenti", "en"),
        ("neuf", "fr"),
        ("3", "en"),
        ("gatanu", "kin"),
        ("icumi", "kin"),
    ]
    for text, lang in tests:
        detected = detect_language(text)
        ans = normalize_answer(text, lang)
        print(f"  '{text}' lang={detected} → {ans}")
