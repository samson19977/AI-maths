"""
curriculum_loader.py
Loads curriculum_seed.json (12 items) and extends it programmatically
to ≥ 60 items covering all 5 skills × 4 age bands.
Saves to tutor/data/curriculum_full.json.
"""

import json
import os

# ── paths ──────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(_HERE, "data")
_SEED_PATH = os.path.join(_DATA_DIR, "curriculum_seed.json")
_FULL_PATH = os.path.join(_DATA_DIR, "curriculum_full.json")

# ── constants ──────────────────────────────────────────────────────────────
SKILLS = ["counting", "number_sense", "addition", "subtraction", "word_problem"]
AGE_BANDS = ["5-6", "6-7", "7-8", "8-9"]

# Kinyarwanda number words (1–20)
KIN_NUMS = {
    1: "rimwe", 2: "kabiri", 3: "gatatu", 4: "kane", 5: "gatanu",
    6: "gatandatu", 7: "karindwi", 8: "umunani", 9: "icyenda", 10: "icumi",
    11: "cumi na rimwe", 12: "cumi na kabiri", 13: "cumi na gatatu",
    14: "cumi na kane", 15: "cumi na gatanu", 16: "cumi na gatandatu",
    17: "cumi na karindwi", 18: "cumi na umunani", 19: "cumi na icyenda",
    20: "makumyabiri",
}

FRENCH_NUMS = {
    1: "un", 2: "deux", 3: "trois", 4: "quatre", 5: "cinq",
    6: "six", 7: "sept", 8: "huit", 9: "neuf", 10: "dix",
    11: "onze", 12: "douze", 13: "treize", 14: "quatorze", 15: "quinze",
    16: "seize", 17: "dix-sept", 18: "dix-huit", 19: "dix-neuf", 20: "vingt",
}

# Local objects familiar to Rwandan children
OBJECTS_EN = ["apples", "goats", "mangoes", "beans", "bananas", "eggs",
              "fish", "stones", "birds", "flowers", "drums", "baskets"]
OBJECTS_KIN = ["pome", "ihene", "imyembe", "ibishyimbo", "ingbindo", "amagi",
               "amafi", "amabuye", "inyoni", "indabo", "ingoma", "ingobyi"]
OBJECTS_FR = ["pommes", "chèvres", "mangues", "haricots", "bananes", "œufs",
              "poissons", "pierres", "oiseaux", "fleurs", "tambours", "paniers"]


def _kin_num(n: int) -> str:
    """Return Kinyarwanda word for integer n (1–20), else digit string."""
    return KIN_NUMS.get(n, str(n))


def _fr_num(n: int) -> str:
    """Return French word for integer n (1–20), else digit string."""
    return FRENCH_NUMS.get(n, str(n))


def _build_generated_items() -> list:
    """
    Programmatically generate curriculum items so the full curriculum
    has ≥ 60 items covering all 5 skills and all 4 age bands evenly.
    Returns a list of item dicts (no duplicates with seed ids).
    """
    items = []
    counter = 200  # start above seed ids

    # ── COUNTING (age 5-6: count 1-5; 6-7: 6-10; 7-8: 11-15; 8-9: 16-20) ──
    counting_spec = [
        ("5-6", list(range(1, 6)),   1),
        ("6-7", list(range(6, 11)),  2),
        ("7-8", list(range(11, 16)), 3),
        ("8-9", list(range(16, 21)), 4),
    ]
    for band, counts, diff_base in counting_spec:
        for idx, n in enumerate(counts):
            obj_i = (counter + idx) % len(OBJECTS_EN)
            obj_en = OBJECTS_EN[obj_i]
            obj_kin = OBJECTS_KIN[obj_i]
            obj_fr = OBJECTS_FR[obj_i]
            items.append({
                "id": f"GC{counter:03d}",
                "skill": "counting",
                "difficulty": diff_base + (idx % 2),
                "age_band": band,
                "stem_en": f"How many {obj_en}?",
                "stem_kin": f"{obj_kin.capitalize()} zingahe?",
                "stem_fr": f"Combien de {obj_fr}?",
                "visual": f"{obj_en.rstrip('s')}_{n}",
                "answer_int": n,
            })
            counter += 1

    # ── NUMBER SENSE ──────────────────────────────────────────────────────
    ns_pairs = [
        ("5-6", [(1,3), (2,4), (1,5)],          2),
        ("6-7", [(4,7), (3,8), (5,9)],           3),
        ("7-8", [(10,15), (12,18), (11,17)],     5),
        ("8-9", [(23,31), (45,52), (67,74)],     7),
    ]
    for band, pairs, diff_base in ns_pairs:
        for idx, (a, b) in enumerate(pairs):
            bigger = max(a, b)
            items.append({
                "id": f"GN{counter:03d}",
                "skill": "number_sense",
                "difficulty": diff_base + idx,
                "age_band": band,
                "stem_en": f"Which number is bigger: {a} or {b}?",
                "stem_kin": f"Ni iyihe nimero nini: {a} cyangwa {b}?",
                "stem_fr": f"Quel nombre est plus grand: {a} ou {b}?",
                "visual": f"compare_{a}_{b}",
                "answer_int": bigger,
            })
            counter += 1

    # ── ADDITION ─────────────────────────────────────────────────────────
    add_items = [
        ("5-6", [(1,1), (1,2), (2,2)],          1),
        ("6-7", [(2,3), (3,3), (4,2)],          3),
        ("7-8", [(5,4), (6,5), (7,3), (8,4)],   5),
        ("8-9", [(13,9), (15,7), (18,12)],       7),
    ]
    for band, pairs, diff_base in add_items:
        for idx, (a, b) in enumerate(pairs):
            ans = a + b
            items.append({
                "id": f"GA{counter:03d}",
                "skill": "addition",
                "difficulty": diff_base + idx,
                "age_band": band,
                "stem_en": f"{a} plus {b} equals?",
                "stem_kin": f"{a} + {b} ni angahe?",
                "stem_fr": f"{a} plus {b} égale?",
                "visual": f"beads_{a}_plus_{b}",
                "answer_int": ans,
            })
            counter += 1

    # ── SUBTRACTION ───────────────────────────────────────────────────────
    sub_items = [
        ("5-6", [(3,1), (4,2), (5,1)],          2),
        ("6-7", [(6,2), (7,3), (8,4)],          4),
        ("7-8", [(10,4), (12,5), (15,6)],       5),
        ("8-9", [(20,8), (25,9), (30,12)],      7),
    ]
    for band, pairs, diff_base in sub_items:
        for idx, (a, b) in enumerate(pairs):
            ans = a - b
            items.append({
                "id": f"GS{counter:03d}",
                "skill": "subtraction",
                "difficulty": diff_base + idx,
                "age_band": band,
                "stem_en": f"{a} minus {b} equals?",
                "stem_kin": f"{a} - {b} ni angahe?",
                "stem_fr": f"{a} moins {b} égale?",
                "visual": f"drums_{a}_minus_{b}",
                "answer_int": ans,
            })
            counter += 1

    # ── WORD PROBLEMS ─────────────────────────────────────────────────────
    wp_items = [
        {
            "age_band": "5-6", "difficulty": 3,
            "stem_en": "Amara has 2 mangoes. Her friend gives her 1 more. How many does she have?",
            "stem_kin": "Amara afite imyembe 2. Inshuti ye amuhaye imyembe 1. Afite ingahe ubu?",
            "stem_fr": "Amara a 2 mangues. Son amie lui en donne 1 de plus. Combien en a-t-elle?",
            "visual": "mango_2_plus_1", "answer_int": 3,
        },
        {
            "age_band": "6-7", "difficulty": 4,
            "stem_en": "There are 5 birds on a tree. 2 fly away. How many remain?",
            "stem_kin": "Hariho inyoni 5 ku giti. 2 zagurutse. Zingahe zasize?",
            "stem_fr": "Il y a 5 oiseaux sur un arbre. 2 s'envolent. Combien restent-il?",
            "visual": "birds_5_minus_2", "answer_int": 3,
        },
        {
            "age_band": "6-7", "difficulty": 5,
            "stem_en": "Mama buys 3 eggs Monday and 4 eggs Tuesday. How many total?",
            "stem_kin": "Mama yaguze amagi 3 kuwa mbere, amagi 4 kuwa kabiri. Amagi angahe?",
            "stem_fr": "Maman achète 3 œufs lundi et 4 œufs mardi. Combien au total?",
            "visual": "eggs_3_plus_4", "answer_int": 7,
        },
        {
            "age_band": "7-8", "difficulty": 6,
            "stem_en": "A farmer has 10 goats. He sells 4. How many does he have left?",
            "stem_kin": "Umuhinzi afite ihene 10. Agurishije 4. Afite ingahe?",
            "stem_fr": "Un fermier a 10 chèvres. Il en vend 4. Combien lui en reste-t-il?",
            "visual": "goat_10_minus_4", "answer_int": 6,
        },
        {
            "age_band": "7-8", "difficulty": 7,
            "stem_en": "2 children share 8 bananas equally. How many does each get?",
            "stem_kin": "Abana 2 batandukanya ingbindo 8. Umwana wese ahabwa ingahe?",
            "stem_fr": "2 enfants partagent 8 bananes. Combien chacun reçoit-il?",
            "visual": "bananas_8_div_2", "answer_int": 4,
        },
        {
            "age_band": "8-9", "difficulty": 7,
            "stem_en": "A school has 15 girls and 13 boys. How many pupils in total?",
            "stem_kin": "Ishuri rifite abakobwa 15 n'abahungu 13. Hafi bangahe bose?",
            "stem_fr": "Une école a 15 filles et 13 garçons. Combien d'élèves au total?",
            "visual": "pupils_15_plus_13", "answer_int": 28,
        },
        {
            "age_band": "8-9", "difficulty": 8,
            "stem_en": "Kagabo saves 50 RWF each day for 6 days. How much has he saved?",
            "stem_kin": "Kagabo bika amafaranga 50 buri munsi mu minsi 6. Yibitse angahe?",
            "stem_fr": "Kagabo épargne 50 FRW par jour pendant 6 jours. Combien a-t-il épargné?",
            "visual": "coins_50_times_6", "answer_int": 300,
        },
    ]
    for wp in wp_items:
        items.append({
            "id": f"GW{counter:03d}",
            "skill": "word_problem",
            **wp,
        })
        counter += 1

    return items


def _load_or_generate() -> list:
    """
    Load curriculum_full.json if it exists; otherwise build it from
    seed + generated items and write it to disk.
    """
    if os.path.exists(_FULL_PATH):
        with open(_FULL_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)

    # load seed
    try:
        with open(_SEED_PATH, "r", encoding="utf-8") as fh:
            curriculum = json.load(fh)
    except FileNotFoundError:
        curriculum = []

    # generate extra items
    extra = _build_generated_items()
    curriculum = curriculum + extra

    # ensure ≥ 60 items
    assert len(curriculum) >= 60, f"Only {len(curriculum)} items — need ≥ 60"

    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_FULL_PATH, "w", encoding="utf-8") as fh:
        json.dump(curriculum, fh, ensure_ascii=False, indent=2)

    return curriculum


# ── public API ──────────────────────────────────────────────────────────────

def load_curriculum() -> list:
    """Load and return the full curriculum as a list of item dicts."""
    return _load_or_generate()


def get_by_skill(skill: str) -> list:
    """Return all curriculum items whose skill matches the given skill name."""
    return [item for item in load_curriculum() if item.get("skill") == skill]


def get_by_difficulty(min_d: int, max_d: int) -> list:
    """Return items with difficulty in [min_d, max_d] inclusive."""
    return [
        item for item in load_curriculum()
        if min_d <= item.get("difficulty", 0) <= max_d
    ]


def get_by_age_band(band: str) -> list:
    """Return all items whose age_band matches band (e.g. '5-6')."""
    return [item for item in load_curriculum() if item.get("age_band") == band]


if __name__ == "__main__":
    curriculum = load_curriculum()
    print(f"Loaded {len(curriculum)} items")
    for skill in SKILLS:
        items = get_by_skill(skill)
        print(f"  {skill}: {len(items)} items")
