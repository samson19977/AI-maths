"""
demo.py — Mwalimu wa Hesabu (Math Teacher)
Offline AI Math Tutor · Rwanda · ages 5–9

Launch:  python demo.py   (auto-relaunches via streamlit run)

Kid-friendly redesign
---------------------
- Giant, colourful tap buttons for answers (no typing required for young children)
- Animated emoji celebration on correct answers  
- Warm, simple feedback in child's language
- Visual progress with stars and skill bars
- Finger-counting hint images on repeated wrong answers
- Auto-play TTS question audio
- Microphone with clear visual cue
- Silence fallback: big hint after 2 non-answers
"""

import os
import sys
import io
import logging
import random

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

# ── Kid-friendly CSS ──────────────────────────────────────────────────────────
# Big buttons, bright colours, large readable text, warm background
st.markdown("""
<style>
    /* ── Global warm background ── */
    .stApp { background: linear-gradient(160deg, #FFF8DC 0%, #FFF0C0 100%) !important; }
    html, body, [class*="css"] { font-size: 22px !important; font-family: 'Comic Sans MS', 'Chalkboard SE', cursive, sans-serif !important; }

    /* ── Headings ── */
    h1 { color: #D84315 !important; font-size: 2.6rem !important; text-align: center; }
    h2 { color: #1565C0 !important; font-size: 1.9rem !important; }
    h3 { color: #2E7D32 !important; font-size: 1.5rem !important; }

    /* ── Primary (green) button — big tap target ── */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #43A047, #1B5E20) !important;
        color: white !important;
        font-size: 26px !important;
        font-weight: 900 !important;
        border-radius: 20px !important;
        padding: 16px 32px !important;
        border: none !important;
        box-shadow: 0 6px 16px rgba(0,0,0,0.25) !important;
        transition: transform 0.1s, box-shadow 0.1s !important;
        min-height: 70px !important;
    }
    .stButton > button[kind="primary"]:hover {
        transform: translateY(-3px) scale(1.03) !important;
        box-shadow: 0 10px 22px rgba(0,0,0,0.3) !important;
    }
    .stButton > button[kind="primary"]:active {
        transform: translateY(1px) scale(0.98) !important;
    }

    /* ── Secondary (orange) button ── */
    .stButton > button[kind="secondary"] {
        background: linear-gradient(135deg, #FB8C00, #E65100) !important;
        color: white !important;
        font-size: 22px !important;
        font-weight: 800 !important;
        border-radius: 18px !important;
        border: none !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2) !important;
        min-height: 60px !important;
    }

    /* ── Answer choice buttons (huge tap targets for kids) ── */
    .answer-btn button {
        background: linear-gradient(135deg, #1976D2, #0D47A1) !important;
        color: white !important;
        font-size: 52px !important;
        font-weight: 900 !important;
        border-radius: 24px !important;
        width: 100% !important;
        min-height: 110px !important;
        border: none !important;
        box-shadow: 0 6px 18px rgba(0,0,0,0.3) !important;
        transition: all 0.15s !important;
    }
    .answer-btn button:hover {
        background: linear-gradient(135deg, #42A5F5, #1565C0) !important;
        transform: scale(1.05) !important;
    }
    .answer-btn button:active {
        transform: scale(0.97) !important;
    }

    /* ── Feedback boxes ── */
    .fb-correct {
        background: linear-gradient(135deg, #C8E6C9, #A5D6A7);
        border-left: 8px solid #2E7D32;
        padding: 20px 18px;
        border-radius: 18px;
        font-size: 24px;
        font-weight: 700;
        margin: 10px 0;
        animation: pop 0.4s ease;
    }
    .fb-wrong {
        background: linear-gradient(135deg, #FFE0B2, #FFCC80);
        border-left: 8px solid #E65100;
        padding: 20px 18px;
        border-radius: 18px;
        font-size: 24px;
        font-weight: 700;
        margin: 10px 0;
    }
    .fb-hint {
        background: #E3F2FD;
        border-left: 8px solid #1565C0;
        padding: 16px 18px;
        border-radius: 16px;
        font-size: 22px;
        margin: 8px 0;
    }

    /* ── Question card ── */
    .question-card {
        background: white;
        border-radius: 24px;
        padding: 24px 22px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.12);
        font-size: 28px;
        font-weight: 800;
        color: #1A237E;
        text-align: center;
        margin-bottom: 18px;
        border: 3px solid #90CAF9;
    }

    /* ── Star display ── */
    .stars { font-size: 48px; text-align: center; letter-spacing: 4px; }

    /* ── Name badge ── */
    .name-badge {
        background: linear-gradient(135deg, #7E57C2, #4527A0);
        color: white;
        border-radius: 999px;
        padding: 8px 24px;
        font-size: 20px;
        font-weight: 700;
        display: inline-block;
        margin-bottom: 12px;
    }

    /* ── Progress bar label ── */
    .stProgress > div > div { border-radius: 99px !important; }

    /* ── Form inputs ── */
    .stTextInput > div > div > input {
        font-size: 26px !important;
        border-radius: 14px !important;
        padding: 14px !important;
        border: 3px solid #90CAF9 !important;
        background: white !important;
    }
    .stSelectbox > div > div > div {
        font-size: 22px !important;
        border-radius: 14px !important;
    }

    /* ── TTS label ── */
    .tts-label { color: #555; font-size: 14px; margin-top: 2px; }
    .asr-status { color: #1565C0; font-size: 15px; font-style: italic; }

    /* ── Pop animation ── */
    @keyframes pop {
        0%   { transform: scale(0.8); opacity: 0; }
        60%  { transform: scale(1.06); }
        100% { transform: scale(1.0); opacity: 1; }
    }

    /* ── Celebration ── */
    .celebrate { font-size: 60px; text-align: center; animation: pop 0.5s ease; }

    /* ── Divider ── */
    hr { border-color: #FFD54F !important; border-width: 2px !important; }

    /* ── Caption / small text ── */
    .stCaption, small, caption { font-size: 16px !important; }

    /* ── Radio labels larger ── */
    .stRadio label { font-size: 22px !important; }

    /* ── Welcome emoji banner ── */
    .welcome-banner {
        text-align: center;
        font-size: 72px;
        margin: 10px 0;
        animation: pop 0.6s ease;
    }
</style>
""", unsafe_allow_html=True)

# ── Cached resource loading (once per server lifetime) ────────────────────────
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

# ── Colour palettes ───────────────────────────────────────────────────────────
IMG_BG  = "#FFF8DC"
GREEN   = "#4CAF50"
YELLOW  = "#FFC107"
RED     = "#F44336"
ORANGE  = "#FF9800"
DARK    = "#333333"
COLORS  = ["#E74C3C","#3498DB","#2ECC71","#F39C12",
           "#9B59B6","#1ABC9C","#E67E22","#E91E63"]

# Answer-button colours: vivid & distinguishable
ANSWER_COLORS = [
    ("#E53935", "#B71C1C"),   # red
    ("#1E88E5", "#0D47A1"),   # blue
    ("#43A047", "#1B5E20"),   # green
    ("#FB8C00", "#E65100"),   # orange
]

# ─────────────────────────────────────────────────────────────────────────────
# Visual rendering helpers
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
        draw.ellipse(bb, fill=col, outline="white", width=3)
        if i >= n - crossed:
            lw = max(2, radius // 3)
            draw.line([cx-radius, cy-radius, cx+radius, cy+radius],
                      fill="#CC0000", width=lw)
            draw.line([cx+radius, cy-radius, cx-radius, cy+radius],
                      fill="#CC0000", width=lw)


def render_visual(item: dict) -> Image.Image:
    """Return a 420×310 PIL image for the item's visual field."""
    W, H   = 420, 310
    img    = Image.new("RGB", (W, H), "#FFFDE7")  # warm cream
    draw   = ImageDraw.Draw(img)

    # rounded rect border
    draw.rounded_rectangle([4, 4, W-4, H-4], radius=24,
                            outline="#FFD54F", width=4)

    visual = (item.get("visual") or "")
    answer = max(1, min(item.get("answer_int", 1), 30))
    parts  = visual.split("_") if visual else []
    stem   = (item.get("stem_en") or "")[:55]

    try:
        if parts and parts[0] == "compare" and len(parts) >= 3:
            draw.text((45, 60),  parts[1], fill="#E53935", font=_font(80))
            draw.text((185, 80), "vs",     fill=ORANGE,   font=_font(36))
            draw.text((260, 60), parts[2], fill="#1E88E5", font=_font(80))
        elif "plus" in parts:
            idx = parts.index("plus")
            a   = int(parts[idx-1]) if idx > 0 else 2
            b   = int(parts[idx+1]) if idx+1 < len(parts) else 3
            _draw_circles(draw, a, 14,  50, 185, 240)
            draw.text((180, 100), "+", fill=GREEN, font=_font(64))
            _draw_circles(draw, b, 230, 50, 406, 240)
        elif "minus" in parts:
            idx     = parts.index("minus")
            total   = int(parts[idx-1]) if idx > 0 else 8
            crossed = int(parts[idx+1]) if idx+1 < len(parts) else 3
            _draw_circles(draw, total, 14, 50, 406, 240, crossed=crossed)
        elif len(parts) >= 2:
            try:
                n = int(parts[-1])
            except ValueError:
                n = answer
            draw.text((14, 10), parts[0].capitalize(), fill=DARK, font=_font(28))
            _draw_circles(draw, n, 14, 50, 406, 240)
        else:
            _draw_circles(draw, answer, 14, 50, 406, 240)
    except Exception as exc:
        logger.warning("render_visual '%s': %s", visual, exc)
        _draw_circles(draw, answer, 14, 50, 406, 240)

    draw.text((10, 270), stem, fill="#555", font=_font(16))
    return img


def _stars_img(n: int) -> Image.Image:
    img  = Image.new("RGB", (340, 72), IMG_BG)
    draw = ImageDraw.Draw(img)
    stars  = "★" * n + "☆" * (5-n)
    draw.text((10, 6), stars, fill="#F39C12", font=_font(48))
    return img


def _finger_hint(n: int) -> Image.Image:
    """Big, cheerful hint image showing the answer."""
    img  = Image.new("RGB", (280, 180), "#E3F2FD")
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([4, 4, 275, 175], radius=20,
                            outline="#1565C0", width=4)
    draw.text((14, 12), "The answer is:", fill="#1565C0", font=_font(22))
    draw.text((80, 54), str(n),          fill="#E53935",  font=_font(88))
    return img


# ─────────────────────────────────────────────────────────────────────────────
# TTS helpers
# ─────────────────────────────────────────────────────────────────────────────

def _play_tts(text: str, lang: str = "en", label: str = "") -> None:
    if not TTS_OK:
        return
    try:
        path = TTS.speak(text, lang)
        if path and os.path.exists(path) and os.path.getsize(path) > 0:
            with open(path, "rb") as f:
                audio_bytes = f.read()
            st.audio(audio_bytes, format="audio/wav", autoplay=True)
            if label:
                st.markdown(f'<p class="tts-label">🔊 {label}</p>',
                            unsafe_allow_html=True)
    except Exception as exc:
        logger.warning("_play_tts error: %s", exc)


def _play_feedback_tts(correct: bool, lang: str) -> None:
    if not TTS_OK:
        return
    try:
        path = TTS.speak_feedback(correct, lang)
        if path and os.path.exists(path) and os.path.getsize(path) > 0:
            with open(path, "rb") as f:
                st.audio(f.read(), format="audio/wav", autoplay=True)
    except Exception as exc:
        logger.warning("_play_feedback_tts: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Distractors — generate multiple-choice options around the correct answer
# ─────────────────────────────────────────────────────────────────────────────

def _make_choices(answer: int, n: int = 4) -> list[int]:
    """Return n distinct integer choices including answer, shuffled."""
    opts = {answer}
    deltas = [-3,-2,-1,1,2,3,4,-4,5,-5]
    random.shuffle(deltas)
    for d in deltas:
        if len(opts) >= n:
            break
        c = max(0, answer + d)
        opts.add(c)
    out = sorted(opts)[:n]
    if answer not in out:
        out[-1] = answer
        out.sort()
    random.shuffle(out)
    return out


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

SKILL_EMOJI = {
    "counting":     "🔢",
    "number_sense": "🧠",
    "addition":     "➕",
    "subtraction":  "➖",
    "word_problem": "📖",
}


def _init_state():
    defaults = {
        "screen":         "welcome",
        "learner_id":     "",
        "name":           "Child",
        "age":            7,
        "language":       "en",
        "probe_items":    [],
        "probe_index":    0,
        "probe_answers":  [],
        "mastery":        {s: 0.2 for s in SKILLS},
        "current_item":   None,
        "current_choices": [],
        "attempt_num":    1,
        "q_count":        0,
        "last_feedback":  None,
        "show_hint":      False,
        "silence_count":  0,
        "streak":         0,        # consecutive correct answers
        "total_correct":  0,
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


def _pick_next(mastery: dict, avoid_id: str = "") -> dict:
    active  = {s: v for s, v in mastery.items() if v < 0.85} or mastery
    weakest = min(active, key=active.get)
    pool    = sorted(
        [i for i in CURRICULUM
         if i.get("skill") == weakest and i.get("id") != avoid_id],
        key=lambda x: x.get("difficulty", 5),
    )
    return pool[0] if pool else random.choice(CURRICULUM)


def _get_stem(item: dict, lang: str) -> str:
    key = {"kin": "stem_kin", "fr": "stem_fr"}.get(lang, "stem_en")
    return item.get(key) or item.get("stem_en", "")


def _show_bars(mastery: dict, compact: bool = False):
    for skill, label in SKILL_LABELS.items():
        val = float(mastery.get(skill, 0.0))
        pct = int(val * 100)
        if compact:
            st.progress(val, text=f"{label}  {pct}%")
        else:
            c1, c2 = st.columns([5, 1])
            with c1:
                st.progress(val, text=label)
            with c2:
                colour = "green" if val >= 0.7 else ("orange" if val >= 0.4 else "red")
                st.markdown(f"**:{colour}[{pct}%]**")


def _streak_banner(streak: int) -> str:
    if streak >= 5:
        return "🔥🔥🔥 Amazing streak! Keep going!"
    if streak >= 3:
        return "🔥 Great streak!"
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Big colourful answer buttons
# ─────────────────────────────────────────────────────────────────────────────

def _render_answer_buttons(choices: list[int], item: dict, lang: str) -> int | None:
    """
    Display 4 large colourful buttons, one per choice.
    Returns the tapped answer integer, or None if nothing tapped yet.
    """
    # Two columns of two buttons each
    pairs = [choices[:2], choices[2:]] if len(choices) >= 4 else [choices]
    tapped = None

    st.markdown("### 👇 Tap the right answer!")

    for row in pairs:
        cols = st.columns(len(row), gap="medium")
        for i, (col, val) in enumerate(zip(cols, row)):
            grad_light, grad_dark = ANSWER_COLORS[choices.index(val) % len(ANSWER_COLORS)]
            # Inject per-button CSS so each is a distinct colour
            col.markdown(f"""
            <style>
            div[data-testid="column"]:nth-of-type({choices.index(val)+1}) .stButton > button {{
                background: linear-gradient(135deg, {grad_light}, {grad_dark}) !important;
                min-height: 110px !important;
                font-size: 54px !important;
                font-weight: 900 !important;
                border-radius: 24px !important;
                border: none !important;
                color: white !important;
                box-shadow: 0 6px 18px rgba(0,0,0,0.3) !important;
            }}
            </style>
            """, unsafe_allow_html=True)
            if col.button(str(val), key=f"choice_{val}_{st.session_state.q_count}_{st.session_state.attempt_num}", use_container_width=True):
                tapped = val

    return tapped


# ─────────────────────────────────────────────────────────────────────────────
# Microphone widget — minimal friction, always optional
# ─────────────────────────────────────────────────────────────────────────────

def _mic_section(lang: str) -> int | None:
    """Show microphone and optional text box. Returns parsed answer or None."""
    with st.expander("🎤 Say your answer (optional)", expanded=False):
        if ASR_OK:
            st.markdown('<p class="asr-status">🎤 Record, then press Submit</p>',
                        unsafe_allow_html=True)
        else:
            st.markdown('<p class="asr-status">⌨️ Whisper not loaded — type below</p>',
                        unsafe_allow_html=True)

        with st.form(key=f"mic_form_{st.session_state.q_count}_{st.session_state.attempt_num}"):
            audio_val = None
            if ASR_OK:
                try:
                    audio_val = st.audio_input(
                        "🎤 Tap mic, speak, then Submit",
                        key=f"mic_{st.session_state.q_count}_{st.session_state.attempt_num}",
                        sample_rate=16000,
                    )
                except Exception as exc:
                    logger.warning("st.audio_input unavailable: %s", exc)

            text_ans = st.text_input(
                "Or type a number:",
                placeholder="e.g. 5",
                key=f"text_{st.session_state.q_count}_{st.session_state.attempt_num}",
            )
            submitted = st.form_submit_button("Submit ✅", type="primary", use_container_width=True)

        if not submitted:
            return None

        answer_int = None

        if audio_val is not None and ASR_OK:
            try:
                audio_val.seek(0)
                wav_bytes  = audio_val.read()
                asr_result = ASR.transcribe_bytes(wav_bytes, language_hint=lang)
                if not asr_result.get("silent") and asr_result.get("answer") is not None:
                    answer_int = asr_result["answer"]
                    st.caption(f"🎤 Heard: *{asr_result.get('transcript','')}* → **{answer_int}**")
                elif asr_result.get("transcript"):
                    answer_int = normalize_answer(asr_result["transcript"], lang)
            except Exception as exc:
                logger.error("ASR error: %s", exc)

        if answer_int is None and text_ans.strip():
            tr = ASR.transcribe_text(text_ans, lang)
            answer_int = tr.get("answer")

        return answer_int


# ═════════════════════════════════════════════════════════════════════════════
# SCREEN 1 — Welcome
# ═════════════════════════════════════════════════════════════════════════════

def screen_welcome():
    st.markdown('<div class="welcome-banner">🌟📚✏️</div>', unsafe_allow_html=True)
    st.title("Mwalimu wa Hesabu")
    st.markdown(
        "<h3 style='text-align:center;color:#555;'>Your offline math teacher · Rwanda · Ages 5–9</h3>",
        unsafe_allow_html=True,
    )

    tts_badge = "🔊 Voice: ON" if TTS_OK else "🔇 Voice: OFF"
    asr_badge = "🎤 Mic: ON" if ASR_OK else "⌨️ Mic: text only"
    st.caption(f"{tts_badge}   |   {asr_badge}")
    st.divider()

    with st.form("registration"):
        st.markdown("### 👶 Who are you?")
        name = st.text_input(
            "Your name / Izina ryawe",
            placeholder="e.g. Amara",
            help="Type your name here!",
        )
        age  = st.selectbox("Age / Imyaka", options=[5, 6, 7, 8, 9], index=2)
        lang = st.radio(
            "Language / Ururimi",
            options=["English", "Kinyarwanda", "Both"],
            horizontal=True,
        )
        submitted = st.form_submit_button(
            "▶ Start! / Tangira!", type="primary", use_container_width=True
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
            "screen":         "diagnostic",
            "learner_id":     lid,
            "name":           name,
            "age":            int(age),
            "language":       lang_code,
            "probe_items":    probes,
            "probe_index":    0,
            "probe_answers":  [],
            "mastery":        {s: 0.2 for s in SKILLS},
            "silence_count":  0,
            "streak":         0,
            "total_correct":  0,
        })

        greeting_text = (
            f"Muraho {name}! Nitwa Mwalimu. Reka tugerageze guharura hamwe!"
            if lang_code in ("kin", "mixed") or int(age) <= 6
            else f"Hello {name}! I am your Math Teacher. Let us start!"
        )
        _play_tts(greeting_text, lang_code)
        st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
# SCREEN 2 — Diagnostic probes
# ═════════════════════════════════════════════════════════════════════════════

def screen_diagnostic():
    probes = st.session_state.probe_items
    idx    = st.session_state.probe_index
    lang   = st.session_state.language
    total  = len(probes)
    probe  = probes[idx]
    name   = st.session_state.name

    # Header
    st.markdown(
        f'<div class="name-badge">👤 {name}</div>',
        unsafe_allow_html=True,
    )
    st.markdown("## 🔍 Let's see what you know!")
    st.progress((idx) / total, text=f"Question {idx+1} of {total}")
    st.divider()

    # Image + question
    col_img, col_q = st.columns([2, 3], gap="large")
    with col_img:
        st.image(render_visual(probe), use_container_width=True)
    with col_q:
        question = _get_stem(probe, lang)
        st.markdown(f'<div class="question-card">{question}</div>',
                    unsafe_allow_html=True)

    # Play question audio (outside column context)
    _play_tts(question, lang)

    # Multiple choice buttons (easier for young children)
    choices = _make_choices(probe["answer_int"], n=4)
    tapped  = _render_answer_buttons(choices, probe, lang)

    # Also show mic/text expander
    mic_ans = _mic_section(lang)
    answer_int = tapped if tapped is not None else mic_ans

    if answer_int is not None:
        correct = (int(answer_int) == probe["answer_int"])
        st.session_state.probe_answers.append(answer_int)
        st.session_state.silence_count = 0

        _play_feedback_tts(correct, lang)

        if correct:
            st.markdown('<div class="fb-correct">✅ Correct! / Ni byiza! 🎉</div>',
                        unsafe_allow_html=True)
            st.markdown('<div class="celebrate">🥳</div>', unsafe_allow_html=True)
        else:
            st.markdown(
                f'<div class="fb-wrong">The answer was <b>{probe["answer_int"]}</b> — try the next one! 💪</div>',
                unsafe_allow_html=True,
            )

        import time; time.sleep(0.9)

        next_idx = idx + 1
        st.session_state.probe_index = next_idx

        if next_idx >= total:
            diag_sess = DiagnosticSession(language=lang)
            mastery   = diag_sess.run_probes(st.session_state.probe_answers)
            st.session_state.mastery = mastery
            for skill, val in mastery.items():
                db_set_mastery(st.session_state.learner_id, skill, val)
            item    = _pick_next(mastery)
            choices = _make_choices(int(item["answer_int"]), n=4)
            st.session_state.update({
                "screen":          "learning",
                "current_item":    item,
                "current_choices": choices,
                "attempt_num":     1,
                "q_count":         0,
                "last_feedback":   None,
                "show_hint":       False,
                "silence_count":   0,
            })
            st.balloons()

        st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
# SCREEN 3 — Adaptive learning (main child view)
# ═════════════════════════════════════════════════════════════════════════════

def screen_learning():
    item    = st.session_state.current_item
    lang    = st.session_state.language
    mastery = st.session_state.mastery
    attempt = st.session_state.attempt_num
    q_count = st.session_state.q_count
    name    = st.session_state.name
    streak  = st.session_state.get("streak", 0)

    if not item:
        st.error("No item loaded — please restart.")
        return

    skill    = item["skill"]
    question = _get_stem(item, lang)

    # ── Header ────────────────────────────────────────────────────────────
    mastered_n = sum(1 for v in mastery.values() if v > 0.85)
    avg        = sum(mastery.values()) / max(len(mastery), 1)
    stars_n    = max(1, min(5, int(avg * 5) + 1))

    col_name, col_stars, col_q_n = st.columns([3, 3, 2])
    with col_name:
        st.markdown(f'<div class="name-badge">👤 {name}</div>', unsafe_allow_html=True)
    with col_stars:
        st.markdown(f'<div class="stars">{"⭐" * stars_n}{"☆" * (5-stars_n)}</div>',
                    unsafe_allow_html=True)
    with col_q_n:
        st.markdown(
            f"<p style='text-align:right;color:#555;font-size:18px;margin-top:8px;'>"
            f"Q{q_count+1} &nbsp;|&nbsp; {SKILL_EMOJI.get(skill,'📖')}</p>",
            unsafe_allow_html=True,
        )

    # Streak banner
    banner = _streak_banner(streak)
    if banner:
        st.markdown(f"<p style='text-align:center;font-size:22px;font-weight:800;'>{banner}</p>",
                    unsafe_allow_html=True)

    st.divider()

    # ── Visual + question ─────────────────────────────────────────────────
    col_img, col_q = st.columns([2, 3], gap="large")

    with col_img:
        st.image(render_visual(item), use_container_width=True)
        if st.session_state.show_hint:
            st.image(_finger_hint(item.get("answer_int", 1)), use_container_width=True)

    with col_q:
        st.markdown(f'<div class="question-card">{question}</div>',
                    unsafe_allow_html=True)

        # Previous feedback
        fb = st.session_state.last_feedback
        if fb is not None:
            cls = "fb-correct" if fb["correct"] else "fb-wrong"
            hint_html = (f"<br><em>💡 {fb['hint']}</em>" if fb.get("hint") else "")
            st.markdown(
                f'<div class="{cls}">'
                f'{fb["emoji"]} <b>{fb["text"]}</b><br>'
                f'<small>{fb["encouragement"]}</small>'
                f'{hint_html}</div>',
                unsafe_allow_html=True,
            )

    # ── Play question audio (outside column context) ───────────────────────
    tts_key = f"tts_{item['id']}_{q_count}_{attempt}"
    if tts_key not in st.session_state:
        _play_tts(question, lang)
        st.session_state[tts_key] = True

    st.divider()

    # ── Big answer buttons ────────────────────────────────────────────────
    choices = st.session_state.get("current_choices") or _make_choices(int(item["answer_int"]), 4)
    tapped  = _render_answer_buttons(choices, item, lang)

    # ── Microphone / text fallback (inside expander — low friction) ────────
    mic_ans = _mic_section(lang)

    # Resolve answer
    answer_int = tapped if tapped is not None else mic_ans

    # ── Sidebar progress ──────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 📊 My Progress")
        _show_bars(mastery, compact=True)
        st.markdown(f"**{'⭐' * stars_n}** {mastered_n}/5 mastered")
        st.divider()
        st.caption(f"Q{q_count+1} · {SKILL_LABELS.get(skill, skill)} · diff {item.get('difficulty','?')}")

    # ── Process answer ────────────────────────────────────────────────────
    if answer_int is None:
        # No answer yet — just show the buttons (already rendered)
        # Silence handling: after 3 non-interactions show hint
        # (This branch only runs if mic form submitted with empty input)
        return

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

    # Update streak & correct count
    if correct:
        st.session_state.streak         = streak + 1
        st.session_state.total_correct  = st.session_state.get("total_correct", 0) + 1
    else:
        st.session_state.streak = 0

    st.session_state.last_feedback = fb_dict
    st.session_state.show_hint     = False

    q_count += 1
    st.session_state.q_count = q_count

    # Session end?
    mastered_n = sum(1 for v in mastery.values() if v > 0.85)
    if mastered_n >= 3 or q_count >= 20:
        path = TTS.speak_session_end(name, lang)
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                st.audio(f.read(), format="audio/wav", autoplay=True)
        st.session_state.screen = "end"
        st.rerun()
        return

    # Next item selection
    if fb_dict.get("drop_difficulty") or (not correct and attempt >= 3):
        easier = sorted(
            [i for i in CURRICULUM
             if i.get("skill") == skill
             and i.get("difficulty", 5) < item.get("difficulty", 5)],
            key=lambda x: x.get("difficulty", 5),
        )
        next_item = easier[0] if easier else _pick_next(mastery, avoid_id=item["id"])
        st.session_state.attempt_num = 1
        st.session_state.show_hint   = False
    elif correct:
        next_item = _pick_next(mastery, avoid_id=item["id"])
        st.session_state.attempt_num = 1
        st.session_state.show_hint   = False
    else:
        next_item = item          # retry same item
        st.session_state.attempt_num = attempt + 1
        if attempt >= 2:
            st.session_state.show_hint = True

    st.session_state.current_item    = next_item
    st.session_state.current_choices = _make_choices(int(next_item["answer_int"]), 4)
    st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
# SCREEN 4 — Session End
# ═════════════════════════════════════════════════════════════════════════════

def screen_end():
    mastery       = st.session_state.mastery
    name          = st.session_state.name
    q_count       = st.session_state.q_count
    total_correct = st.session_state.get("total_correct", 0)
    lang          = st.session_state.language

    avg     = sum(mastery.values()) / max(len(mastery), 1)
    stars   = max(1, min(5, int(avg * 5) + 1))
    best    = max(mastery, key=mastery.get)
    weakest = min(mastery, key=mastery.get)

    st.markdown('<div class="welcome-banner">🎉🌟🎊</div>', unsafe_allow_html=True)
    st.title(f"Well done, {name}!")
    st.balloons()

    st.image(_stars_img(stars), width=360)
    st.markdown(
        f"<p style='text-align:center;font-size:26px;font-weight:700;'>"
        f"You answered <b>{q_count}</b> questions!<br>"
        f"✅ Correct: <b>{total_correct}</b></p>",
        unsafe_allow_html=True,
    )
    st.divider()

    st.markdown("### 📊 Your Skills")
    _show_bars(mastery)
    st.divider()

    c1, c2 = st.columns(2)
    with c1:
        st.success(f"⭐ Best skill:\n**{SKILL_LABELS.get(best, best)}**")
    with c2:
        st.warning(f"💪 Practise more:\n**{SKILL_LABELS.get(weakest, weakest)}**")

    st.divider()

    # Encouragement message
    encouragement = {
        "en":    f"Keep practising, {name}! You are getting smarter every day! 🚀",
        "kin":   f"Komeza gukora, {name}! Uriyongera buri munsi! 🚀",
        "fr":    f"Continue à pratiquer, {name}! Tu progresses chaque jour! 🚀",
        "mixed": f"Keep going, {name}! Komeza! 🚀",
    }.get(lang, f"Keep going, {name}! 🚀")

    st.markdown(
        f"<p style='text-align:center;font-size:22px;color:#2E7D32;font-weight:700;'>"
        f"{encouragement}</p>",
        unsafe_allow_html=True,
    )

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
        if st.button("🔄 Play Again!", type="primary", use_container_width=True):
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
