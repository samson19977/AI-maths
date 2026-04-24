"""
demo.py — Mwalimu wa Hesabu (Math Teacher)
Offline AI Math Tutor · Rwanda · ages 5–9

Launch:  python demo.py   (auto-relaunches via streamlit run)

Audio features
--------------
TTS  : pyttsx3 → .wav file played via st.audio()
       Fallback: silent (UI text only)
ASR  : Whisper-tiny via st.audio_input() microphone widget
       Fallback 1: low-confidence → show text input alongside mic
       Fallback 2: Whisper not installed → text input only
       Fallback 3: silence detected → re-prompt with hint
"""

import os
import sys
import io
import logging

# ── Auto-relaunch so `python demo.py` works like `streamlit run demo.py` ──────
def _is_streamlit_context() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx() is not None
    except Exception:
        return False

if __name__ == "__main__" and not _is_streamlit_context():
    import subprocess
    print("Launching Mwalimu wa Hesabu…")
    print("Opening http://localhost:8501")
    result = subprocess.run(
        [sys.executable, "-m", "streamlit", "run", __file__,
         "--server.headless", "false",
         "--server.port", "8501",
         "--browser.gatherUsageStats", "false"],
        check=False,
    )
    sys.exit(result.returncode)
# ─────────────────────────────────────────────────────────────────────────────

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
from PIL import Image, ImageDraw, ImageFont

from tutor.curriculum_loader import load_curriculum
from tutor.storage import (
    init_db, ensure_learner, log_attempt,
    set_mastery as db_set_mastery,
    get_mastery as db_get_mastery,
)
from tutor.diagnostics import DiagnosticSession
from tutor.adaptive import bkt_update, SKILLS
from tutor.feedback import FeedbackEngine
from tutor.tts import TutorTTS
from tutor.asr_adapt import ChildASR
from tutor.utils import normalize_answer

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Mwalimu wa Hesabu 🌟",
    page_icon="🌟",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #FFF8DC; }
    html, body, [class*="css"] { font-size: 20px !important; }
    h1 { color: #2E7D32; font-size: 2.2rem !important; }
    h2 { color: #1565C0; font-size: 1.7rem !important; }
    h3 { color: #333;    font-size: 1.4rem !important; }
    .stButton > button[kind="primary"] {
        background: #4CAF50 !important; color: white !important;
        font-size: 20px !important; border-radius: 14px !important;
        padding: 10px 28px !important; border: none !important;
    }
    .stButton > button[kind="secondary"] {
        background: #FF9800 !important; color: white !important;
        font-size: 18px !important; border-radius: 14px !important;
        border: none !important;
    }
    .stTextInput > div > div > input {
        font-size: 22px !important; border-radius: 10px !important;
        padding: 10px !important;
    }
    .fb-correct {
        background:#E8F5E9; border-left:6px solid #4CAF50;
        padding:14px; border-radius:8px; font-size:20px; margin:8px 0;
    }
    .fb-wrong {
        background:#FFF3E0; border-left:6px solid #FF9800;
        padding:14px; border-radius:8px; font-size:20px; margin:8px 0;
    }
    .tts-label { color:#555; font-size:15px; margin-top:4px; }
    .asr-status { color:#1565C0; font-size:15px; font-style:italic; }
</style>
""", unsafe_allow_html=True)

# ── Cached resource loading (runs once per Streamlit server lifetime) ──────────
@st.cache_resource
def _load_resources():
    init_db()
    tts = TutorTTS()
    asr = ChildASR(model_size="tiny")
    return {
        "curriculum": load_curriculum(),
        "tts":        tts,
        "asr":        asr,
        "feedback":   FeedbackEngine(),
        "tts_ok":     tts.is_available,
        "asr_ok":     asr.is_available,
    }

res        = _load_resources()
CURRICULUM = res["curriculum"]
TTS        = res["tts"]
ASR        = res["asr"]
FEEDBACK   = res["feedback"]
TTS_OK     = res["tts_ok"]
ASR_OK     = res["asr_ok"]

# ── Colours ───────────────────────────────────────────────────────────────────
IMG_BG = "#FFF8DC"
GREEN  = "#4CAF50"
YELLOW = "#FFC107"
RED    = "#F44336"
ORANGE = "#FF9800"
DARK   = "#333333"
COLORS = ["#E74C3C","#3498DB","#2ECC71","#F39C12",
          "#9B59B6","#1ABC9C","#E67E22","#E91E63"]

# ─────────────────────────────────────────────────────────────────────────────
# Visual rendering
# ─────────────────────────────────────────────────────────────────────────────

def _font(size=24):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arial.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _draw_circles(draw, n, x0, y0, x1, y1, crossed=0):
    if n <= 0:
        return
    cols   = min(n, 5)
    rows   = (n + cols - 1) // cols
    cell_w = (x1 - x0) // cols
    cell_h = (y1 - y0) // max(rows, 1)
    radius = min(cell_w, cell_h) // 3
    for i in range(n):
        cx = x0 + (i % cols) * cell_w + cell_w // 2
        cy = y0 + (i // cols) * cell_h + cell_h // 2
        col = COLORS[i % len(COLORS)]
        bb  = [cx-radius, cy-radius, cx+radius, cy+radius]
        draw.ellipse(bb, fill=col, outline="white", width=2)
        if i >= n - crossed:
            lw = max(2, radius // 3)
            draw.line([cx-radius, cy-radius, cx+radius, cy+radius],
                      fill="#CC0000", width=lw)
            draw.line([cx+radius, cy-radius, cx-radius, cy+radius],
                      fill="#CC0000", width=lw)


def render_visual(item: dict) -> Image.Image:
    """Return a 400×300 PIL image for the item's visual field."""
    W, H   = 400, 300
    img    = Image.new("RGB", (W, H), IMG_BG)
    draw   = ImageDraw.Draw(img)
    visual = (item.get("visual") or "")
    answer = max(1, min(item.get("answer_int", 1), 30))
    parts  = visual.split("_") if visual else []
    stem   = (item.get("stem_en") or "")[:58]

    try:
        if parts and parts[0] == "compare" and len(parts) >= 3:
            draw.text((30, 70),  parts[1], fill=DARK,   font=_font(64))
            draw.text((185, 90), "vs",     fill=ORANGE,  font=_font(30))
            draw.text((255, 70), parts[2], fill=DARK,   font=_font(64))
        elif "plus" in parts:
            idx = parts.index("plus")
            a   = int(parts[idx-1]) if idx > 0 else 2
            b   = int(parts[idx+1]) if idx+1 < len(parts) else 3
            _draw_circles(draw, a, 10, 50, 170, 230)
            draw.text((173, 105), "+", fill=GREEN, font=_font(56))
            _draw_circles(draw, b, 215, 50, 390, 230)
        elif "minus" in parts:
            idx     = parts.index("minus")
            total   = int(parts[idx-1]) if idx > 0 else 8
            crossed = int(parts[idx+1]) if idx+1 < len(parts) else 3
            _draw_circles(draw, total, 10, 50, 390, 230, crossed=crossed)
        elif len(parts) >= 2:
            try:
                n = int(parts[-1])
            except ValueError:
                n = answer
            draw.text((10, 6), parts[0].capitalize(), fill=DARK, font=_font(26))
            _draw_circles(draw, n, 10, 44, 390, 240)
        else:
            _draw_circles(draw, answer, 10, 50, 390, 240)
    except Exception as exc:
        logger.warning("render_visual '%s': %s", visual, exc)
        _draw_circles(draw, answer, 10, 50, 390, 240)

    draw.text((8, 258), stem, fill=DARK, font=_font(17))
    return img


def _stars_img(n: int) -> Image.Image:
    img  = Image.new("RGB", (300, 60), IMG_BG)
    draw = ImageDraw.Draw(img)
    draw.text((8, 4), ("★" * n) + ("☆" * (5-n)), fill="#F39C12", font=_font(40))
    return img


def _finger_hint(n: int) -> Image.Image:
    img  = Image.new("RGB", (260, 150), IMG_BG)
    draw = ImageDraw.Draw(img)
    draw.text((10, 10), "Count:", fill=DARK, font=_font(22))
    draw.text((95, 40), str(n), fill=GREEN, font=_font(76))
    return img

# ─────────────────────────────────────────────────────────────────────────────
# TTS helper — plays audio in the UI if pyttsx3 produced a file
# ─────────────────────────────────────────────────────────────────────────────

def _play_tts(text: str, lang: str = "en", label: str = "") -> None:
    """Synthesise text and embed an st.audio() player if a file was produced."""
    if not TTS_OK:
        return
    try:
        path = TTS.speak(text, lang)
        if path and os.path.exists(path) and os.path.getsize(path) > 0:
            with open(path, "rb") as f:
                audio_bytes = f.read()
            st.audio(audio_bytes, format="audio/wav")
            if label:
                st.markdown(f'<p class="tts-label">🔊 {label}</p>',
                            unsafe_allow_html=True)
    except Exception as exc:
        logger.warning("_play_tts error: %s", exc)


def _play_feedback_tts(correct: bool, lang: str) -> None:
    """Play correct/wrong feedback audio."""
    if not TTS_OK:
        return
    try:
        path = TTS.speak_feedback(correct, lang)
        if path and os.path.exists(path) and os.path.getsize(path) > 0:
            with open(path, "rb") as f:
                st.audio(f.read(), format="audio/wav")
    except Exception as exc:
        logger.warning("_play_feedback_tts: %s", exc)

# ─────────────────────────────────────────────────────────────────────────────
# ASR helper — mic widget + fallback text box, returns (answer_int, source)
# ─────────────────────────────────────────────────────────────────────────────

def _asr_input_widget(form_key: str, lang: str, silence_count: int) -> tuple:
    """
    Render the answer input section.

    Returns
    -------
    (answer_int | None, source_str, submitted_bool)
    source_str is one of: 'mic', 'text', 'none'
    """
    asr_result = None
    text_result = None
    submitted   = False
    source      = "none"

    # ── Status badge ────────────────────────────────────────────────────
    if ASR_OK:
        st.markdown('<p class="asr-status">🎤 Speak your answer — or type below</p>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<p class="asr-status">⌨️ Type your answer below</p>',
                    unsafe_allow_html=True)

    # ── After silence twice, show a larger text box prominently ─────────
    show_text_prominent = silence_count >= 2

    # Bug-fix (1 & 2): st.audio_input MUST live inside the same st.form as
    # the Submit button so both widgets participate in the same interaction
    # cycle. When they were in different cycles the mic recording was
    # discarded before the form submission ran.
    # Bug-fix (2): after the form submits, Streamlit creates a new
    # UploadedFile object; we call .seek(0) before .read() to guarantee the
    # cursor is at the start regardless of whether anything read it earlier.
    with st.form(key=f"answer_form_{form_key}"):
        # Microphone widget — inside the form
        audio_val = None
        try:
            audio_val = st.audio_input(
                "🎤 Tap to record your answer",
                key=f"mic_{form_key}",
                sample_rate=16000,
            )
        except Exception as exc:
            logger.warning("st.audio_input unavailable: %s", exc)
            audio_val = None

        text_ans = st.text_input(
            "Or type your answer here:" if not show_text_prominent
            else "✏️ Type your answer (number):",
            placeholder="e.g. 5",
            key=f"text_{form_key}",
        )
        col1, col2 = st.columns([1, 2])
        with col1:
            submitted = st.form_submit_button(
                "Submit ✅", type="primary", use_container_width=True
            )

    # ── Process whichever input arrived ─────────────────────────────────
    answer_int = None

    if submitted:
        # Priority 1: recorded audio (if new recording available)
        if audio_val is not None and ASR_OK:
            try:
                audio_val.seek(0)   # Bug-fix: reset cursor before read
                wav_bytes  = audio_val.read()
                asr_result = ASR.transcribe_bytes(wav_bytes, language_hint=lang)
                if asr_result.get("silent"):
                    st.warning("🔇 No speech detected — please try again or type.")
                elif asr_result.get("answer") is not None:
                    answer_int = asr_result["answer"]
                    source     = "mic"
                    transcript = asr_result.get("transcript", "")
                    st.caption(f"🎤 Heard: *{transcript}* → **{answer_int}**")
                else:
                    # Whisper heard something but couldn't parse a number
                    transcript = asr_result.get("transcript", "")
                    st.caption(f"🎤 Heard: *{transcript}* — trying as text…")
                    answer_int = normalize_answer(transcript, lang)
                    source = "mic"
            except Exception as exc:
                logger.error("ASR processing error: %s", exc)

        # Priority 2: typed text box
        if answer_int is None and text_ans.strip():
            tr = ASR.transcribe_text(text_ans, lang)
            answer_int = tr.get("answer")
            source     = "text"

        # Priority 3: audio available but Whisper not loaded — parse text
        if answer_int is None and audio_val is not None and not ASR_OK:
            st.info("💡 Whisper not loaded. Please type your answer.")

    elif audio_val is not None and not submitted:
        # Audio recorded but submit not pressed yet — show preview
        st.audio(audio_val, format="audio/wav")

    return answer_int, source, submitted

# ─────────────────────────────────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────────────────────────────────

SKILL_LABELS = {
    "counting":     "🔢 Counting",
    "number_sense": "🧠 Number Sense",
    "addition":     "➕ Addition",
    "subtraction":  "➖ Subtraction",
    "word_problem": "📖 Word Problems",
}


def _init_state():
    defaults = {
        "screen":        "welcome",
        "learner_id":    "",
        "name":          "Child",
        "age":           7,
        "language":      "en",
        "probe_items":   [],
        "probe_index":   0,
        "probe_answers": [],
        "mastery":       {s: 0.2 for s in SKILLS},
        "current_item":  None,
        "attempt_num":   1,
        "q_count":       0,
        "last_feedback": None,
        "show_hint":     False,
        "silence_count": 0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ─────────────────────────────────────────────────────────────────────────────
# BKT helpers
# ─────────────────────────────────────────────────────────────────────────────

def _bkt_step(mastery: dict, skill: str, correct: int) -> dict:
    m = dict(mastery)
    m[skill] = bkt_update(m.get(skill, 0.2), correct)
    return m


def _pick_next(mastery: dict) -> dict:
    import random
    active  = {s: v for s, v in mastery.items() if v < 0.85} or mastery
    weakest = min(active, key=active.get)
    pool    = sorted(
        [i for i in CURRICULUM if i.get("skill") == weakest],
        key=lambda x: x.get("difficulty", 5),
    )
    return pool[0] if pool else random.choice(CURRICULUM)


def _get_stem(item: dict, lang: str) -> str:
    key = {"kin": "stem_kin", "fr": "stem_fr"}.get(lang, "stem_en")
    return item.get(key) or item.get("stem_en", "")


def _show_bars(mastery: dict):
    for skill, label in SKILL_LABELS.items():
        val = float(mastery.get(skill, 0.0))
        pct = int(val * 100)
        c1, c2 = st.columns([4, 1])
        with c1:
            st.progress(val, text=label)
        with c2:
            colour = "green" if val >= 0.7 else ("orange" if val >= 0.4 else "red")
            st.markdown(f"**:{colour}[{pct}%]**")

# ═════════════════════════════════════════════════════════════════════════════
# SCREEN 1 — Welcome
# ═════════════════════════════════════════════════════════════════════════════

def screen_welcome():
    st.title("🌟 Mwalimu wa Hesabu")
    st.subheader("Your Offline Math Teacher · Rwanda · Ages 5–9")

    # Audio/ASR status badge
    tts_badge = "🔊 TTS: ON" if TTS_OK else "🔇 TTS: OFF (install pyttsx3)"
    asr_badge = "🎤 Mic: ON (Whisper)" if ASR_OK else "⌨️ Mic: Text-only (Whisper not loaded)"
    st.caption(f"{tts_badge}   |   {asr_badge}")
    st.divider()

    with st.form("registration"):
        name = st.text_input("Child's name / Izina ryawe", placeholder="e.g. Amara")
        age  = st.selectbox("Age / Imyaka", options=[5, 6, 7, 8, 9], index=2)
        lang = st.radio(
            "Language / Ururimi",
            options=["English", "Kinyarwanda", "Both"],
            horizontal=True,
        )
        submitted = st.form_submit_button(
            "▶ Start / Tangira", type="primary", use_container_width=True
        )

    if submitted:
        lang_map  = {"English": "en", "Kinyarwanda": "kin", "Both": "mixed"}
        lang_code = lang_map[lang]
        name      = name.strip() or "Child"
        lid       = f"{name.lower().replace(' ', '_')}_{age}"

        ensure_learner(lid, name, int(age))

        diag   = DiagnosticSession(language=lang_code)
        probes = diag.get_probe_items()

        st.session_state.update({
            "screen":        "diagnostic",
            "learner_id":    lid,
            "name":          name,
            "age":           int(age),
            "language":      lang_code,
            "probe_items":   probes,
            "probe_index":   0,
            "probe_answers": [],
            "mastery":       {s: 0.2 for s in SKILLS},
            "silence_count": 0,
        })

        # Greeting TTS
        greeting_text = (
            "Muraho! Nitwa Mwalimu. Reka tugerageze guharura hamwe!"
            if lang_code in ("kin", "mixed") or int(age) <= 6
            else "Hello! I am your Math Teacher. Let us start!"
        )
        _play_tts(greeting_text, lang_code)
        st.rerun()

# ═════════════════════════════════════════════════════════════════════════════
# SCREEN 2 — Diagnostic probes
# ═════════════════════════════════════════════════════════════════════════════

def screen_diagnostic():
    probes  = st.session_state.probe_items
    idx     = st.session_state.probe_index
    lang    = st.session_state.language
    total   = len(probes)
    probe   = probes[idx]

    st.markdown("## 🔍 Let's see what you know!")
    st.caption(f"Question {idx+1} of {total}")
    st.progress(idx / total)
    st.divider()

    col_img, col_q = st.columns([2, 3], gap="large")

    with col_img:
        st.image(render_visual(probe), use_container_width=True)

    with col_q:
        question = _get_stem(probe, lang)
        st.markdown(f"### {question}")

        answer_int, source, submitted = _asr_input_widget(
            form_key=f"diag_{idx}",
            lang=lang,
            silence_count=st.session_state.silence_count,
        )

    # Bug-fix (6): play TTS outside the closed column context so st.audio()
    # renders at the top level, not inside a stale column scope on rerun.
    _play_tts(question, lang)

    if submitted:
        if answer_int is None:
            # Nothing parseable — increment silence count
            st.session_state.silence_count = st.session_state.get("silence_count", 0) + 1
            if st.session_state.silence_count >= 3:
                # Show finger hint
                st.image(_finger_hint(probe["answer_int"]), width=200)
                st.info("The answer is shown above. Try saying or typing it!")
            st.rerun()

        correct = (int(answer_int) == probe["answer_int"])
        st.session_state.probe_answers.append(answer_int)
        st.session_state.silence_count = 0

        _play_feedback_tts(correct, lang)
        if correct:
            st.success(f"✅ Correct! / Ni byiza!")
        else:
            st.error(f"❌ The answer was **{probe['answer_int']}**")

        import time; time.sleep(0.7)

        next_idx = idx + 1
        st.session_state.probe_index = next_idx

        if next_idx >= total:
            diag_sess = DiagnosticSession(language=lang)
            mastery   = diag_sess.run_probes(st.session_state.probe_answers)
            st.session_state.mastery = mastery
            for skill, val in mastery.items():
                db_set_mastery(st.session_state.learner_id, skill, val)
            item = _pick_next(mastery)
            st.session_state.update({
                "screen":        "learning",
                "current_item":  item,
                "attempt_num":   1,
                "q_count":       0,
                "last_feedback": None,
                "show_hint":     False,
                "silence_count": 0,
            })
            st.balloons()

        st.rerun()

# ═════════════════════════════════════════════════════════════════════════════
# SCREEN 3 — Adaptive learning
# ═════════════════════════════════════════════════════════════════════════════

def screen_learning():
    item    = st.session_state.current_item
    lang    = st.session_state.language
    mastery = st.session_state.mastery
    attempt = st.session_state.attempt_num
    q_count = st.session_state.q_count
    name    = st.session_state.name

    if not item:
        st.error("No item loaded — please restart.")
        return

    skill    = item["skill"]
    question = _get_stem(item, lang)

    # ── Header ────────────────────────────────────────────────────────────
    mastered_n = sum(1 for v in mastery.values() if v > 0.85)
    st.markdown(f"## 📚 Learning Time, {name}!")
    st.caption(
        f"Q{q_count+1}  |  {SKILL_LABELS.get(skill, skill)}  "
        f"|  Difficulty {item.get('difficulty','?')}  |  "
        f"Mastered: {mastered_n}/5"
    )
    st.divider()

    # ── Two-column layout ────────────────────────────────────────────────
    col_img, col_q = st.columns([2, 3], gap="large")

    with col_img:
        st.image(render_visual(item), use_container_width=True)

        # Finger hint below image when triggered
        if st.session_state.show_hint:
            st.image(_finger_hint(item.get("answer_int", 1)), width=200)
            st.caption("Count the number above!")

    with col_q:
        st.markdown(f"### {question}")

        # Previous feedback
        fb = st.session_state.last_feedback
        if fb is not None:
            cls = "fb-correct" if fb["correct"] else "fb-wrong"
            hint_html = (f"<br><em>💡 {fb['hint']}</em>"
                         if fb.get("hint") else "")
            st.markdown(
                f'<div class="{cls}">'
                f'{fb["emoji"]} <b>{fb["text"]}</b><br>'
                f'<small>{fb["encouragement"]}</small>'
                f'{hint_html}</div>',
                unsafe_allow_html=True,
            )
            st.write("")

        answer_int, source, submitted = _asr_input_widget(
            form_key=f"learn_{q_count}_{attempt}",
            lang=lang,
            silence_count=st.session_state.silence_count,
        )

    # Bug-fix (6): _play_tts calls st.audio() internally. st.audio() must be
    # invoked at the top-level render scope — not inside a `with col_q:`
    # block that has already been closed. On a rerun Streamlit would attempt
    # to render the audio widget inside the stale column context, causing it
    # to silently appear in the wrong place or not at all.
    # Play question TTS (only first time this item is shown) — outside cols.
    tts_key = f"tts_played_{item['id']}_{q_count}_{attempt}"
    if tts_key not in st.session_state:
        _play_tts(question, lang)
        st.session_state[tts_key] = True

    # ── Sidebar progress ─────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 📊 Progress")
        _show_bars(mastery)
        avg   = sum(mastery.values()) / max(len(mastery), 1)
        stars = max(1, min(5, int(avg * 5) + 1))
        st.markdown(f"**{'⭐' * stars}**")

    # ── Process answer ───────────────────────────────────────────────────
    if submitted:
        if answer_int is None:
            sc = st.session_state.silence_count + 1
            st.session_state.silence_count = sc
            if sc == 1:
                _play_tts(question, lang)   # re-play question
                st.warning("🔇 Didn't catch that — try again!")
            elif sc == 2:
                st.warning("✏️ Please type your answer in the box.")
            else:
                st.session_state.show_hint = True
                st.info("💡 Here's a hint — count the dots in the image!")
            st.rerun()

        # Got a valid answer
        st.session_state.silence_count = 0
        correct = (int(answer_int) == item.get("answer_int"))

        mastery = _bkt_step(mastery, skill, int(correct))
        st.session_state.mastery = mastery

        try:
            log_attempt(st.session_state.learner_id, item["id"], skill, int(correct))
            db_set_mastery(st.session_state.learner_id, skill, mastery[skill])
        except Exception as e:
            logger.warning("DB: %s", e)

        fb_dict = FEEDBACK.get_feedback(
            correct=correct, skill=skill,
            p_mastery=mastery[skill],
            language=lang, attempt_num=attempt, item=item,
        )
        fb_dict["correct"] = correct
        _play_feedback_tts(correct, lang)
        st.session_state.last_feedback = fb_dict
        st.session_state.show_hint     = False

        q_count += 1
        st.session_state.q_count = q_count

        # Session end?
        mastered_n = sum(1 for v in mastery.values() if v > 0.85)
        if mastered_n >= 3 or q_count >= 20:
            # Bug-fix (4): the original code used
            #   TTS.speak_session_end.__doc__ and f"Well done…"
            # which evaluates the method's docstring (truthy) as the text
            # to speak, then discards it because 'and' returns the last
            # operand — so _play_tts was called with the real string, but
            # speak_session_end was ALSO called right after, synthesising
            # and playing the audio a second time. Simply call
            # speak_session_end once and play the resulting file.
            path = TTS.speak_session_end(name, lang)
            if path and os.path.exists(path):
                with open(path, "rb") as f:
                    st.audio(f.read(), format="audio/wav")
            st.session_state.screen = "end"
            st.rerun()
            return

        # Next item
        if fb_dict.get("drop_difficulty") or (not correct and attempt >= 3):
            easier = sorted(
                [i for i in CURRICULUM
                 if i.get("skill") == skill
                 and i.get("difficulty", 5) < item.get("difficulty", 5)],
                key=lambda x: x.get("difficulty", 5),
            )
            next_item = easier[0] if easier else _pick_next(mastery)
            st.session_state.attempt_num = 1
        elif correct:
            next_item = _pick_next(mastery)
            st.session_state.attempt_num = 1
        else:
            next_item = item
            st.session_state.attempt_num = attempt + 1

        st.session_state.current_item = next_item
        st.rerun()

# ═════════════════════════════════════════════════════════════════════════════
# SCREEN 4 — Session End
# ═════════════════════════════════════════════════════════════════════════════

def screen_end():
    mastery = st.session_state.mastery
    name    = st.session_state.name
    q_count = st.session_state.q_count

    avg     = sum(mastery.values()) / max(len(mastery), 1)
    stars   = max(1, min(5, int(avg * 5) + 1))
    best    = max(mastery, key=mastery.get)
    weakest = min(mastery, key=mastery.get)

    st.title(f"🌟 Well done, {name}!")
    st.balloons()
    st.image(_stars_img(stars), width=300)
    st.markdown(f"You answered **{q_count}** questions!")
    st.divider()

    st.markdown("### Your Skills")
    _show_bars(mastery)
    st.divider()

    c1, c2 = st.columns(2)
    with c1:
        st.success(f"⭐ Best:\n**{SKILL_LABELS.get(best, best)}**")
    with c2:
        st.warning(f"💡 Practise more:\n**{SKILL_LABELS.get(weakest, weakest)}**")

    st.divider()
    b1, b2 = st.columns(2)

    with b1:
        if st.button("📄 Parent Report", type="secondary", use_container_width=True):
            try:
                import parent_report, datetime
                today  = datetime.date.today()
                monday = today - datetime.timedelta(days=today.weekday())
                parent_report.generate_report(
                    st.session_state.learner_id, monday.isoformat()
                )
                st.success("Saved to `tutor/reports/` ✅")
                png = (f"tutor/reports/report_{st.session_state.learner_id}"
                       f"_{monday.isoformat()}.png")
                if os.path.exists(png):
                    st.image(png, use_container_width=True)
            except Exception as exc:
                st.error(f"Report error: {exc}")

    with b2:
        if st.button("🔄 Play Again", type="primary", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            _init_state()
            st.rerun()

# ═════════════════════════════════════════════════════════════════════════════
# Router
# ═════════════════════════════════════════════════════════════════════════════

screen = st.session_state.get("screen", "welcome")

if   screen == "welcome":    screen_welcome()
elif screen == "diagnostic": screen_diagnostic()
elif screen == "learning":   screen_learning()
elif screen == "end":        screen_end()
else:
    st.error(f"Unknown screen: {screen!r}")
    if st.button("Reset"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()
