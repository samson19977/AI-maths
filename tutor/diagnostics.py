"""
diagnostics.py
Five-probe diagnostic session that seeds the BKT model with initial
p_mastery estimates based on diagnostic_probes_seed.csv data.
"""

import os
import csv

_HERE = os.path.dirname(os.path.abspath(__file__))
_SEED_DIR = os.path.join(_HERE, "..", "seed_extract", "T3.1_Math_Tutor")
_PROBE_CSV = os.path.join(_SEED_DIR, "diagnostic_probes_seed.csv")

# Fallback probe definitions if CSV is not found
_DEFAULT_PROBES = [
    {"id": "P001", "skill": "counting",      "difficulty": 2, "answer_int": 4},
    {"id": "P002", "skill": "addition",      "difficulty": 4, "answer_int": 7},
    {"id": "P003", "skill": "subtraction",   "difficulty": 5, "answer_int": 3},
    {"id": "P004", "skill": "word_problem",  "difficulty": 6, "answer_int": 9},
    {"id": "P005", "skill": "number_sense",  "difficulty": 3, "answer_int": 8},
]

# Human-readable stems for each probe (matched to curriculum seed)
_PROBE_STEMS = {
    "P001": {
        "stem_en": "How many fingers am I showing? (hold up 4)",
        "stem_kin": "Intoki zingahe mpakanye? (erekana 4)",
        "stem_fr": "Combien de doigts je montre? (montrer 4)",
    },
    "P002": {
        "stem_en": "3 plus 4 equals?",
        "stem_kin": "3 + 4 ni angahe?",
        "stem_fr": "3 plus 4 égale?",
    },
    "P003": {
        "stem_en": "6 minus 3 equals?",
        "stem_kin": "6 - 3 ni angahe?",
        "stem_fr": "6 moins 3 égale?",
    },
    "P004": {
        "stem_en": "A boy has 5 mangoes. He gives 4 away. How many does he have?",
        "stem_kin": "Umuhungu afite imyembe 9. Ayiha inshuti. Yasigaye afite ingahe?",
        "stem_fr": "Un garçon a 9 mangues. Il en donne. Combien reste-t-il?",
    },
    "P005": {
        "stem_en": "Which is bigger: 8 or 5?",
        "stem_kin": "Ni iyihe nimero nini: 8 cyangwa 5?",
        "stem_fr": "Quel nombre est plus grand: 8 ou 5?",
    },
}


def _load_probe_csv() -> list:
    """Load diagnostic_probes_seed.csv; fall back to defaults if missing."""
    if not os.path.exists(_PROBE_CSV):
        # Try relative to package location (when running from project root)
        alt = os.path.join(os.path.dirname(_HERE), "seed_extract",
                           "T3.1_Math_Tutor", "diagnostic_probes_seed.csv")
        if os.path.exists(alt):
            probe_path = alt
        else:
            return _DEFAULT_PROBES
    else:
        probe_path = _PROBE_CSV

    probes = []
    try:
        with open(probe_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                probes.append({
                    "id": row["id"].strip(),
                    "skill": row["skill"].strip(),
                    "difficulty": int(row["difficulty"]),
                    "answer_int": int(row["answer_int"]),
                })
    except Exception:
        return _DEFAULT_PROBES
    return probes if probes else _DEFAULT_PROBES


class DiagnosticSession:
    """
    Runs five diagnostic probes to seed initial p_mastery values for BKT.

    Usage
    -----
    session = DiagnosticSession()
    probes  = session.get_probe_items()     # list of 5 dicts
    mastery = session.run_probes([4, 7, 3, 9, 8])  # user answers
    """

    def __init__(self, language: str = "en"):
        """
        Parameters
        ----------
        language : preferred language ('en', 'kin', 'fr')
        """
        self.language = language
        self._probes = _load_probe_csv()

    def get_probe_items(self) -> list:
        """
        Return the 5 probe items enriched with question stems.

        Returns
        -------
        list of dicts with keys: id, skill, difficulty, answer_int,
                                  stem_en, stem_kin, stem_fr
        """
        result = []
        for probe in self._probes:
            item = dict(probe)
            stems = _PROBE_STEMS.get(probe["id"], {
                "stem_en": f"Answer: {probe['answer_int']}?",
                "stem_kin": f"Subiza: {probe['answer_int']}?",
                "stem_fr": f"Répondre: {probe['answer_int']}?",
            })
            item.update(stems)
            item["visual"] = f"probe_{probe['skill']}"
            result.append(item)
        return result

    def run_probes(self, responses: list) -> dict:
        """
        Evaluate probe responses and return initial p_mastery estimates.

        Parameters
        ----------
        responses : list of int answers (one per probe, order P001→P005)

        Returns
        -------
        dict  {skill: float}  — correct → 0.6, wrong → 0.2
        """
        probes = self.get_probe_items()
        mastery = {}
        for probe, answer in zip(probes, responses):
            skill = probe["skill"]
            correct = (int(answer) == probe["answer_int"])
            mastery[skill] = 0.6 if correct else 0.2
        return mastery

    def next_probe_language(self, lang: str) -> str:
        """
        Return the stem field name for the given language.

        Parameters
        ----------
        lang : 'en', 'kin', or 'fr'

        Returns
        -------
        str  — 'stem_en', 'stem_kin', or 'stem_fr'
        """
        mapping = {"en": "stem_en", "kin": "stem_kin", "fr": "stem_fr"}
        return mapping.get(lang, "stem_en")


if __name__ == "__main__":
    session = DiagnosticSession()
    probes = session.get_probe_items()
    for p in probes:
        print(f"{p['id']} [{p['skill']}] → {p['stem_en']}")
    # Simulate all correct
    mastery = session.run_probes([p["answer_int"] for p in probes])
    print("All correct:", mastery)
