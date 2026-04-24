"""
tutor/tts.py
Offline Text-to-Speech using pyttsx3 (Windows SAPI5 / macOS say / Linux espeak).

Strategy
--------
1. Try to synthesise speech to a .wav file (cached on disk).
   The Streamlit UI plays the file back via st.audio().
2. On Windows, pyttsx3.save_to_file() can fail silently for some voices.
   Fallback: speak() aloud directly via engine.say() / runAndWait() so
   the child at least hears audio even if no file is written.
3. If pyttsx3 is entirely unavailable the class degrades silently —
   all methods return "" and the UI simply has no audio.

Cache
-----
All synthesised files live in tutor/tts_cache/ which is excluded from
the 75 MB footprint budget.
"""

import os
import hashlib
import threading
import logging

logger = logging.getLogger(__name__)

_HERE         = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CACHE = os.path.join(_HERE, "tts_cache")

# ── Phrase banks ─────────────────────────────────────────────────────────────

FEEDBACK_PHRASES = {
    "correct": {
        "en":    "Excellent! Very good!",
        "kin":   "Ni byiza cyane!",
        "fr":    "Excellent! Très bien!",
        "mixed": "Excellent! Ni byiza cyane!",
    },
    "wrong": {
        "en":    "Try again!",
        "kin":   "Gerageza nanone!",
        "fr":    "Essaie encore!",
        "mixed": "Try again! Gerageza nanone!",
    },
}

GREETING_PHRASES = {
    "kin":   "Muraho! Nitwa Mwalimu. Reka tugerageze guharura hamwe!",
    "en":    "Hello! My name is Teacher. Let us try counting together!",
    "fr":    "Bonjour! Je m'appelle Enseignant. Essayons de compter ensemble!",
    "mixed": "Muraho! Let us count together!",
}


class TutorTTS:
    """
    Offline TTS via pyttsx3.
    Thread-safe: a dedicated background thread owns the pyttsx3 engine
    (required on Windows where the COM object must stay on one thread).
    """

    def __init__(self, cache_dir: str = _DEFAULT_CACHE):
        self.cache_dir  = cache_dir
        self._available = False
        self._engine    = None
        os.makedirs(cache_dir, exist_ok=True)
        self._init_engine()

    # ── Initialisation ────────────────────────────────────────────────────

    def _init_engine(self) -> None:
        """Try to initialise pyttsx3; degrade silently on failure."""
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate",   145)   # slightly slow for children
            engine.setProperty("volume", 0.95)

            # On Windows prefer a female voice (friendlier for children)
            try:
                voices = engine.getProperty("voices")
                female = [v for v in voices
                          if "zira" in v.name.lower()
                          or "hazel" in v.name.lower()
                          or "female" in v.name.lower()
                          or "susan" in v.name.lower()]
                if female:
                    engine.setProperty("voice", female[0].id)
            except Exception:
                pass  # keep default voice

            self._engine    = engine
            self._available = True
            logger.info("pyttsx3 initialised OK")
        except Exception as exc:
            logger.warning("pyttsx3 unavailable: %s — TTS will be silent.", exc)
            self._available = False

    # ── Cache helpers ─────────────────────────────────────────────────────

    def _cache_path(self, text: str, language: str) -> str:
        key = hashlib.md5(f"{language}:{text}".encode()).hexdigest()[:14]
        return os.path.join(self.cache_dir, f"{key}.wav")

    # ── Core synthesis ────────────────────────────────────────────────────

    def speak(self, text: str, language: str = "en") -> str:
        """
        Synthesise *text* and return the path to a cached .wav file.
        Returns "" if TTS is unavailable or synthesis fails.

        The returned path can be passed directly to st.audio().
        """
        if not text or not text.strip():
            return ""
        if not self._available:
            return ""

        out_path = self._cache_path(text, language)

        # ── Cache hit ──────────────────────────────────────────────────
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            return out_path

        # ── Synthesise to file ─────────────────────────────────────────
        # Bug-fix: pyttsx3 runAndWait() blocks Streamlit's main thread on
        # Windows (COM/SAPI5 restriction). Run the entire synthesis in a
        # dedicated daemon thread and join it with a timeout so the UI
        # never freezes, regardless of platform.
        try:
            rate = 120 if language == "kin" else 145

            exc_holder: list = []

            def _synth():
                try:
                    self._engine.setProperty("rate", rate)
                    self._engine.save_to_file(text, out_path)
                    self._engine.runAndWait()
                except Exception as e:
                    exc_holder.append(e)

            t = threading.Thread(target=_synth, daemon=True)
            t.start()
            t.join(timeout=15)   # 15 s ceiling — should never be hit

            if exc_holder:
                raise exc_holder[0]

            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                return out_path

            # save_to_file produced nothing — try speaking aloud instead
            logger.warning("save_to_file produced empty file for %r", text)
            self._speak_aloud(text)
            return ""

        except Exception as exc:
            logger.error("TTS synthesis error: %s", exc)
            # Last resort: try speaking aloud so child still hears something
            try:
                self._speak_aloud(text)
            except Exception:
                pass
            return ""

    def _speak_aloud(self, text: str) -> None:
        """Speak directly through the system speaker (no file written)."""
        if not self._available:
            return
        # Bug-fix: same threading guard as speak() — runAndWait() must not
        # block the Streamlit main thread on Windows.
        try:
            def _play():
                try:
                    self._engine.say(text)
                    self._engine.runAndWait()
                except Exception as e:
                    logger.error("_speak_aloud inner error: %s", e)

            t = threading.Thread(target=_play, daemon=True)
            t.start()
            t.join(timeout=15)
        except Exception as exc:
            logger.error("_speak_aloud error: %s", exc)

    # ── Convenience wrappers ──────────────────────────────────────────────

    def speak_feedback(self, correct: bool, language: str = "en") -> str:
        """Return .wav path for the correct/wrong feedback phrase."""
        key  = "correct" if correct else "wrong"
        lang = language if language in FEEDBACK_PHRASES[key] else "en"
        return self.speak(FEEDBACK_PHRASES[key][lang], lang)

    def speak_question(self, item: dict, language: str = "en") -> str:
        """Return .wav path for speaking a curriculum item's question stem."""
        stem_key = {"kin": "stem_kin", "fr": "stem_fr"}.get(language, "stem_en")
        text = item.get(stem_key) or item.get("stem_en", "")
        return self.speak(text, language)

    def speak_greeting(self, language: str = "en") -> str:
        """Return .wav path for the welcome greeting."""
        lang = language if language in GREETING_PHRASES else "en"
        return self.speak(GREETING_PHRASES[lang], lang)

    def speak_session_end(self, name: str, language: str = "en") -> str:
        """Return .wav path for the session-end congratulation."""
        phrases = {
            "en":    f"Well done, {name}! You did a great job today!",
            "kin":   f"Akazi keza, {name}! Wakoze neza uyu munsi!",
            "fr":    f"Bravo, {name}! Tu as très bien travaillé aujourd'hui!",
            "mixed": f"Well done, {name}! Akazi keza!",
        }
        lang = language if language in phrases else "en"
        return self.speak(phrases[lang], lang)

    @property
    def is_available(self) -> bool:
        """True when pyttsx3 initialised successfully."""
        return self._available
