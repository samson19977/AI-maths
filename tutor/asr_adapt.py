"""
tutor/asr_adapt.py
Child-speech-adapted ASR using openai-whisper (tiny model, CPU).

Input path
----------
Streamlit's st.audio_input() returns an UploadedFile whose .read()
gives raw WAV bytes at 16 kHz.  Pass those bytes to transcribe_bytes().

Fallback chain
--------------
1. Whisper tiny      — downloaded once (~39 MB), runs on CPU in <2 s
2. Text input        — if Whisper fails to load or audio is too short/silent
3. Silence detected  — returns {"transcript": "", "silent": True} so the
                       UI can re-prompt without showing an error

Child-speech adaptation
-----------------------
- Post-correction map (Levenshtein ≤ 2) for common mispronunciations
  derived from child_utt_sample_seed.csv
- Optional +4-semitone pitch shift via scipy (no librosa needed) to
  simulate adult ASR on child voice
"""

import io
import os
import logging
import tempfile

from tutor.utils import detect_language, _levenshtein, normalize_answer

logger = logging.getLogger(__name__)

# ── Child speech correction map ───────────────────────────────────────────────
CHILD_CORRECTIONS = {
    # English mispronunciations (from child_utt_sample_seed.csv)
    "twewenti": "twenty",  "tweny": "twenty", "toenty": "twenty",
    "tu":       "two",     "fife":  "five",   "treee":  "three",
    "fore":     "four",    "nyne":  "nine",   "ayght":  "eight",
    "siks":     "six",     "eleben":"eleven", "twelv":  "twelve",
    # Kinyarwanda phonetic approximations
    "esheshatu": "gatatu",  "gatato": "gatatu",
    "gataro":    "gatatu",  "gatazo": "gatatu",
    "iycumi":    "icumi",   "icyumi": "icumi",
    "karindui":  "karindwi","umuani": "umunani",
    # French
    "dixt": "dix", "neuff": "neuf", "sis": "six",
}

# Whisper language hints
_WHISPER_LANG = {"en": "en", "kin": None, "fr": "fr", "mixed": None}
# Kinyarwanda is not in Whisper's official list; None = auto-detect

# Minimum audio duration to attempt transcription (seconds)
_MIN_DURATION_S = 0.3

# ── Pitch shift via scipy (no librosa required) ───────────────────────────────

def _pitch_shift_scipy(samples, sr: int, semitones: float = 4.0):
    """
    Resample audio to simulate pitch shift.
    Shifting up by N semitones = speeding up by 2^(N/12), then
    downsampling back to sr.  Crude but zero extra dependencies.
    Returns shifted samples array.
    """
    try:
        import numpy as np
        from scipy.signal import resample_poly
        from math import gcd

        ratio   = 2 ** (semitones / 12.0)   # >1 = pitch up
        # integer rational approximation  p/q ≈ ratio
        q       = 1000
        p       = int(round(ratio * q))
        g       = gcd(p, q)
        samples = resample_poly(samples, q // g, p // g)
        return samples.astype(np.float32)
    except Exception as exc:
        logger.debug("pitch_shift_scipy failed: %s", exc)
        return samples


def _wav_bytes_to_float32(wav_bytes: bytes):
    """
    Decode WAV bytes → (float32 numpy array at 16 kHz, sample_rate).
    Uses scipy.io.wavfile (stdlib-adjacent, always available).
    Returns (None, None) on failure.
    """
    try:
        import numpy as np
        from scipy.io import wavfile

        buf = io.BytesIO(wav_bytes)
        sr, data = wavfile.read(buf)

        # Normalise to float32 [-1, 1]
        if data.dtype.kind == 'i':
            data = data.astype(np.float32) / float(2 ** (data.dtype.itemsize * 8 - 1))
        elif data.dtype.kind == 'u':
            data = (data.astype(np.float32) - 128.0) / 128.0
        else:
            data = data.astype(np.float32)

        # Mono
        if data.ndim > 1:
            data = data.mean(axis=1)

        # Resample to 16 kHz if needed
        if sr != 16000:
            from math import gcd
            from scipy.signal import resample_poly
            g = gcd(16000, sr)
            data = resample_poly(data, 16000 // g, sr // g).astype(np.float32)
            sr = 16000

        return data, sr
    except Exception as exc:
        logger.error("wav decode error: %s", exc)
        return None, None


# ── Correction helpers ────────────────────────────────────────────────────────

# All valid number words across languages — never fuzzy-correct these
_VALID_NUMBER_WORDS = {
    # English
    "one","two","three","four","five","six","seven","eight","nine","ten",
    "eleven","twelve","thirteen","fourteen","fifteen","sixteen",
    "seventeen","eighteen","nineteen","twenty",
    # Kinyarwanda
    "rimwe","kabiri","gatatu","kane","gatanu","gatandatu",
    "karindwi","umunani","icyenda","icumi",
    "cumi","na",   # parts of compound numbers
    # French
    "un","deux","trois","quatre","cinq","six","sept",
    "huit","neuf","dix","onze","douze","treize",
    "quatorze","quinze","seize","vingt",
}


def _apply_corrections(text: str) -> str:
    """
    Apply child-speech correction map.
    Exact match always applies.
    Fuzzy match (Levenshtein <= 2) only applied to tokens that are NOT
    already valid number words — prevents e.g. gatanu->gatatu.
    """
    text = text.lower().strip()
    if text in CHILD_CORRECTIONS:
        return CHILD_CORRECTIONS[text]

    # Token-level
    tokens = text.split()
    out    = []
    for tok in tokens:
        # exact correction
        if tok in CHILD_CORRECTIONS:
            out.append(CHILD_CORRECTIONS[tok])
            continue
        # skip fuzzy if already a valid number word
        if tok in _VALID_NUMBER_WORDS:
            out.append(tok)
            continue
        # fuzzy match against correction keys
        best_k, best_d = None, 3
        for key in CHILD_CORRECTIONS:
            # only correct towards keys that are not valid words themselves
            d = _levenshtein(tok, key)
            if d < best_d:
                best_d, best_k = d, key
        out.append(CHILD_CORRECTIONS[best_k] if best_k else tok)
    return " ".join(out)


# ── Main ASR class ────────────────────────────────────────────────────────────

class ChildASR:
    """
    Wraps openai-whisper (tiny) for child-speech recognition.

    Usage
    -----
    asr = ChildASR()
    result = asr.transcribe_bytes(wav_bytes)
    # result = {"transcript": "five", "language": "en",
    #            "confidence": 0.82, "silent": False, "answer": 5}
    """

    def __init__(self, model_size: str = "tiny"):
        self._model      = None
        self._available  = False
        self._model_size = model_size
        self._try_load()

    def _try_load(self) -> None:
        """Attempt to load Whisper; mark unavailable without crashing."""
        try:
            import whisper
            logger.info("Loading Whisper-%s …", self._model_size)
            self._model     = whisper.load_model(self._model_size)
            self._available = True
            logger.info("Whisper-%s loaded OK", self._model_size)
        except Exception as exc:
            logger.warning(
                "Whisper unavailable (%s). "
                "ASR will fall back to text input.", exc
            )
            self._available = False

    @property
    def is_available(self) -> bool:
        """True when Whisper loaded successfully."""
        return self._available

    # ── Public API ────────────────────────────────────────────────────────

    def transcribe_bytes(self, wav_bytes: bytes,
                         language_hint: str = "en",
                         pitch_shift: bool = True) -> dict:
        """
        Transcribe raw WAV bytes from st.audio_input().

        Parameters
        ----------
        wav_bytes     : bytes from UploadedFile.read()
        language_hint : preferred language ('en', 'kin', 'fr', 'mixed')
        pitch_shift   : apply +4-semitone shift to help with child voice

        Returns
        -------
        dict with keys:
            transcript  : str   — corrected transcript
            language    : str   — detected language
            confidence  : float — 0–1
            silent      : bool  — True if audio was blank/too short
            answer      : int|None — normalised integer if parseable
        """
        _empty = {"transcript": "", "language": language_hint,
                  "confidence": 0.0, "silent": True, "answer": None}

        if not wav_bytes:
            return _empty

        # ── Decode WAV ──────────────────────────────────────────────────
        samples, sr = _wav_bytes_to_float32(wav_bytes)
        if samples is None:
            return _empty

        duration = len(samples) / max(sr, 1)
        if duration < _MIN_DURATION_S:
            logger.debug("Audio too short (%.2f s) — treated as silence", duration)
            return _empty

        # ── Check for silence (RMS threshold) ──────────────────────────
        try:
            import numpy as np
            rms = float(np.sqrt(np.mean(samples ** 2)))
            if rms < 0.002:   # ~-54 dBFS
                logger.debug("Audio is silent (RMS %.4f)", rms)
                return _empty
        except Exception:
            pass

        if not self._available:
            logger.debug("Whisper not available — returning empty for text fallback")
            return _empty

        # ── Optional pitch shift (child → adult) ───────────────────────
        if pitch_shift:
            try:
                import numpy as np
                samples = _pitch_shift_scipy(samples, sr, semitones=4.0)
            except Exception:
                pass

        # ── Whisper transcription ───────────────────────────────────────
        try:
            import whisper as _whisper
            import numpy as np

            # Whisper needs a file path or numpy float32 at 16 kHz
            audio_np = samples.astype(np.float32)
            # Pad / trim to 30 s
            audio_np = _whisper.pad_or_trim(audio_np)

            # Language hint
            lang_arg = _WHISPER_LANG.get(language_hint, None)

            result = self._model.transcribe(
                audio_np,
                language=lang_arg,
                temperature=0.0,
                beam_size=5,
                best_of=5,
                fp16=False,      # CPU inference
                condition_on_previous_text=False,
            )

            raw_text  = (result.get("text") or "").strip()
            detected  = result.get("language", language_hint)[:2]
            lang_map  = {"rw": "kin"}
            detected  = lang_map.get(detected, detected)

            # Confidence from segment avg log-prob
            segs = result.get("segments", [])
            if segs:
                avg_lp     = sum(s.get("avg_logprob", -1.0) for s in segs) / len(segs)
                confidence = float(min(max(1.0 + avg_lp / 3.0, 0.0), 1.0))
            else:
                confidence = 0.5

            corrected = _apply_corrections(raw_text)
            answer    = normalize_answer(corrected, detected)

            logger.info(
                "Whisper: %r → corrected %r  lang=%s  conf=%.2f  answer=%s",
                raw_text, corrected, detected, confidence, answer
            )

            return {
                "transcript": corrected,
                "language":   detected,
                "confidence": confidence,
                "silent":     False,
                "answer":     answer,
            }

        except Exception as exc:
            logger.error("Whisper transcription error: %s", exc)
            return _empty

    def transcribe_text(self, text: str, language_hint: str = "en") -> dict:
        """
        Pass-through for typed input — normalise and wrap in the same dict.
        Used when microphone is unavailable or child prefers typing.
        """
        corrected = _apply_corrections(text.strip())
        lang      = detect_language(corrected) if corrected else language_hint
        answer    = normalize_answer(corrected, lang)
        return {
            "transcript": corrected,
            "language":   lang,
            "confidence": 1.0,
            "silent":     False,
            "answer":     answer,
        }
