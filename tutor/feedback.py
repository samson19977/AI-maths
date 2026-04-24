"""
feedback.py
Rule-based, child-friendly feedback engine.
Returns localised feedback text, emoji, and encouragement
based on correctness, mastery level, attempt number, and language.
"""

from tutor.utils import get_stem


class FeedbackEngine:
    """
    Generates child-appropriate feedback for each response.

    All rules are deterministic and run offline.
    """

    # Feedback templates per rule × language
    _TEMPLATES = {
        "correct_high": {
            "en":    ("Amazing! You are a star! ⭐",    "You can do anything! 🌟"),
            "kin":   ("Ni byiza cyane! Uri inyenyeri!", "Ubishoboye! 🌟"),
            "fr":    ("Incroyable! Tu es une étoile! ⭐", "Tu peux tout faire! 🌟"),
            "mixed": ("Amazing! Ni byiza cyane! ⭐",    "Uri inyenyeri! 🌟"),
        },
        "correct_low": {
            "en":    ("Great job! Keep going! 🎉",  "You are getting better! 💪"),
            "kin":   ("Akazi keza! Komeza! 🎉",     "Uriyongera! 💪"),
            "fr":    ("Bon travail! Continue! 🎉",  "Tu t'améliores! 💪"),
            "mixed": ("Great job! Komeza! 🎉",       "Uri inyenyeri! 💪"),
        },
        "wrong_1": {
            "en":    ("Almost! Try once more 🤔",    "You can do it! 💪"),
            "kin":   ("Hafi! Gerageza nanone 🤔",    "Ubishoboye! 💪"),
            "fr":    ("Presque! Réessaie 🤔",        "Tu peux le faire! 💪"),
            "mixed": ("Almost! Gerageza nanone 🤔",  "Ubishoboye! 💪"),
        },
        "wrong_2_hint": {
            "en":    ("Let me give you a hint! 💡",  "Think carefully! 🧠"),
            "kin":   ("Ndagufasha gutekereza! 💡",  "Tekereza neza! 🧠"),
            "fr":    ("Voici un indice! 💡",         "Réfléchis bien! 🧠"),
            "mixed": ("Hint! Tekereza neza! 💡",     "Think! 🧠"),
        },
        "wrong_3": {
            "en":    ("Let's try something easier. You can do it! 💪",
                      "Every mistake helps us learn! 📚"),
            "kin":   ("Reka tugerageze ibintu byoroshye. Ubishoboye! 💪",
                      "Amakosa atugirira akamaro! 📚"),
            "fr":    ("Essayons quelque chose de plus facile. Tu y arriveras! 💪",
                      "Chaque erreur nous aide à apprendre! 📚"),
            "mixed": ("Let's try easier! Reka tugerageze! 💪",
                      "Amakosa atugirira akamaro! 📚"),
        },
    }

    def get_feedback(
        self,
        correct: bool,
        skill: str,
        p_mastery: float,
        language: str,
        attempt_num: int,
        item: dict = None,
    ) -> dict:
        """
        Generate feedback for a child's response.

        Parameters
        ----------
        correct     : whether the answer was correct
        skill       : skill name (for context)
        p_mastery   : current mastery probability for this skill
        language    : 'en', 'kin', 'fr', or 'mixed'
        attempt_num : 1-based attempt counter for this item
        item        : optional curriculum item dict (used to generate hints)

        Returns
        -------
        dict with keys:
            text          : str — main feedback sentence
            emoji         : str — leading emoji character
            encouragement : str — secondary encouragement line
            hint          : str — hint text (only on 2nd wrong attempt)
            drop_difficulty: bool — True on 3rd wrong (signal to lower difficulty)
        """
        lang = language if language in self._TEMPLATES["correct_high"] else "en"
        hint = ""
        drop_difficulty = False

        if correct:
            if p_mastery > 0.7:
                tmpl = self._TEMPLATES["correct_high"][lang]
                emoji = "⭐"
            else:
                tmpl = self._TEMPLATES["correct_low"][lang]
                emoji = "🎉"
        else:
            if attempt_num == 1:
                tmpl  = self._TEMPLATES["wrong_1"][lang]
                emoji = "🤔"
            elif attempt_num == 2:
                tmpl  = self._TEMPLATES["wrong_2_hint"][lang]
                emoji = "💡"
                # Generate a hint from the item's answer
                if item:
                    answer = item.get("answer_int", "?")
                    first_digit = str(answer)[0]
                    if lang == "kin":
                        hint = f"Igisubizo gitangira na {first_digit}..."
                    elif lang == "fr":
                        hint = f"La réponse commence par {first_digit}..."
                    else:
                        hint = f"The answer starts with {first_digit}..."
            else:  # attempt_num >= 3
                tmpl = self._TEMPLATES["wrong_3"][lang]
                emoji = "💪"
                drop_difficulty = True

        text, encouragement = tmpl
        return {
            "text":           text,
            "emoji":          emoji,
            "encouragement":  encouragement,
            "hint":           hint,
            "drop_difficulty": drop_difficulty,
        }

    def get_mastery_message(self, skill: str, p_mastery: float, language: str) -> str:
        """
        Return a short mastery progress message for the skill.

        Parameters
        ----------
        skill      : skill name
        p_mastery  : current mastery value
        language   : preferred language

        Returns
        -------
        str  — progress message
        """
        skill_labels = {
            "counting":     {"en": "counting",      "kin": "guharura",       "fr": "compter"},
            "number_sense": {"en": "number sense",  "kin": "ubunyamahanga",  "fr": "sens des nombres"},
            "addition":     {"en": "addition",      "kin": "gushora",        "fr": "addition"},
            "subtraction":  {"en": "subtraction",   "kin": "gukuraho",       "fr": "soustraction"},
            "word_problem": {"en": "word problems", "kin": "ibibazo by'andi", "fr": "problèmes"},
        }
        lang = language if language in ("en", "kin", "fr") else "en"
        skill_name = skill_labels.get(skill, {}).get(lang, skill)

        pct = int(p_mastery * 100)
        if lang == "kin":
            return f"{skill_name}: {pct}%"
        elif lang == "fr":
            return f"{skill_name}: {pct}% maîtrisé"
        else:
            return f"{skill_name}: {pct}% mastered"


if __name__ == "__main__":
    engine = FeedbackEngine()
    item = {"answer_int": 7, "stem_en": "How many?"}
    for lang in ("en", "kin", "fr"):
        fb = engine.get_feedback(
            correct=True, skill="counting", p_mastery=0.8,
            language=lang, attempt_num=1, item=item
        )
        print(f"[{lang}] correct+high:", fb["text"])
        fb2 = engine.get_feedback(
            correct=False, skill="addition", p_mastery=0.3,
            language=lang, attempt_num=2, item=item
        )
        print(f"[{lang}] wrong+2:", fb2["text"], "| hint:", fb2["hint"])
