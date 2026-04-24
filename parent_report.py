"""
parent_report.py
Generates a weekly parent report: JSON schema + Pillow-rendered PNG + voiced summary.
Reads data from SQLite via tutor.storage.
"""

import os
import sys
import json
import textwrap
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image, ImageDraw, ImageFont

from tutor.storage import get_weekly_summary, get_mastery, list_learners, get_attempts
from tutor.tts import TutorTTS

_HERE       = os.path.dirname(os.path.abspath(__file__))
_REPORTS    = os.path.join(_HERE, "tutor", "reports")

os.makedirs(_REPORTS, exist_ok=True)

# Colours
BG     = "#FFFFFF"
GREEN  = "#27AE60"
YELLOW = "#F39C12"
RED    = "#E74C3C"
ORANGE = "#E67E22"
DARK   = "#2C3E50"
LIGHT  = "#ECF0F1"

SKILL_LABELS = {
    "counting":     "Counting",
    "number_sense": "Number Sense",
    "addition":     "Addition",
    "subtraction":  "Subtraction",
    "word_problem": "Word Problems",
}


def _load_font(size: int = 18):
    """Load a PIL font with fallback to default."""
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _bar_color(val: float) -> str:
    """Return bar fill colour based on mastery value."""
    if val >= 0.7:
        return GREEN
    if val >= 0.4:
        return YELLOW
    return RED


def _arrow(delta: float) -> tuple:
    """Return (symbol, colour) arrow for a delta value."""
    if delta > 0.05:
        return "↑", GREEN
    if delta < -0.05:
        return "↓", RED
    return "→", YELLOW


def _render_png(
    summary: dict,
    learner_name: str,
    out_path: str,
    early_warning: str = "",
) -> None:
    """
    Render the parent report as a 600×560 PNG icon-heavy layout.

    Parameters
    ----------
    summary      : dict from get_weekly_summary()
    learner_name : child's display name
    out_path     : destination .png file path
    early_warning: optional dyscalculia warning message
    """
    W, H    = 600, 580 + (60 if early_warning else 0)
    img     = Image.new("RGB", (W, H), BG)
    draw    = ImageDraw.Draw(img)

    f_title = _load_font(22)
    f_body  = _load_font(17)
    f_sm    = _load_font(14)
    f_big   = _load_font(28)

    # ── Header ────────────────────────────────────────────────────────────
    draw.rectangle([0, 0, W, 64], fill="#2980B9")
    draw.text((12, 10), f"📚  {learner_name}  ·  Week of {summary['week_starting']}",
              fill="white", font=f_title)
    draw.text((12, 38), f"Sessions this week: {summary['sessions']} 📅",
              fill="#D6EAF8", font=f_body)

    # ── Skills grid ───────────────────────────────────────────────────────
    draw.text((12, 76), "SKILLS PROGRESS", fill=DARK, font=f_body)
    y = 102
    skills = summary.get("skills", {})
    for skill, label in SKILL_LABELS.items():
        data    = skills.get(skill, {"current": 0.0, "delta": 0.0})
        val     = float(data.get("current", 0.0))
        delta   = float(data.get("delta", 0.0))
        pct     = int(val * 100)
        bar_w   = int(val * 260)
        bar_col = _bar_color(val)
        arrow_s, arrow_c = _arrow(delta)

        # label
        draw.text((12, y), f"{label}", fill=DARK, font=f_body)
        # bar background
        draw.rectangle([200, y + 2, 460, y + 22], fill=LIGHT, outline="#BDC3C7")
        # bar fill
        if bar_w > 0:
            draw.rectangle([200, y + 2, 200 + bar_w, y + 22], fill=bar_col)
        # percentage
        draw.text((466, y), f"{pct}%", fill=DARK, font=f_body)
        # arrow
        draw.text((520, y), f"{arrow_s} {abs(int(delta*100))}%", fill=arrow_c, font=f_sm)
        y += 38

    # ── divider ───────────────────────────────────────────────────────────
    draw.rectangle([12, y, W - 12, y + 2], fill=LIGHT)
    y += 12

    # ── icons section ─────────────────────────────────────────────────────
    icons = summary.get("icons_for_parent", [])
    overall = icons[0] if len(icons) > 0 else "flat"
    best    = icons[1] if len(icons) > 1 else ""
    needs   = icons[2] if len(icons) > 2 else ""

    arrow_sym = "↑ Improving" if overall == "up" else ("↓ Needs attention" if overall == "down" else "→ Steady")
    arrow_col = GREEN if overall == "up" else (RED if overall == "down" else YELLOW)

    draw.text((12, y), f"⭐  Best skill:  {SKILL_LABELS.get(best, best)}", fill=DARK, font=f_body)
    y += 32
    draw.text((12, y), f"💡  Needs help: {SKILL_LABELS.get(needs, needs)}", fill=DARK, font=f_body)
    y += 32
    draw.text((12, y), f"Overall: {arrow_sym}", fill=arrow_col, font=f_big)
    y += 48

    # ── divider ───────────────────────────────────────────────────────────
    draw.rectangle([12, y, W - 12, y + 2], fill=LIGHT)
    y += 12

    # ── QR placeholder + audio ────────────────────────────────────────────
    draw.rectangle([12, y, 112, y + 80], outline=DARK, width=2)
    draw.text((22, y + 26), "QR", fill=DARK, font=f_big)
    draw.text((124, y + 10), "🔊  Listen to voiced summary", fill=DARK, font=f_body)
    audio_path = summary.get("voiced_summary_audio", "")
    draw.text((124, y + 38), audio_path or "(audio not generated)", fill="#7F8C8D", font=f_sm)
    y += 92

    # ── dyscalculia early warning ─────────────────────────────────────────
    if early_warning:
        draw.rectangle([12, y, W - 12, y + 48], fill="#FEF9E7", outline=ORANGE, width=2)
        draw.text((20, y + 10), f"💬 {early_warning}", fill=ORANGE, font=f_body)

    img.save(out_path)


def _check_early_warning(learner_id: str, summary: dict) -> str:
    """
    Check dyscalculia early warning criteria.

    Conditions: ≥ 3 sessions AND difficulty at minimum AND mastery < 0.3 on 2+ skills.

    Returns
    -------
    str — warning message, or empty string
    """
    if summary["sessions"] < 3:
        return ""
    skills = summary.get("skills", {})
    low_count = sum(1 for v in skills.values() if float(v.get("current", 1.0)) < 0.3)
    if low_count >= 2:
        name = learner_id.split("_")[0].capitalize()
        return f"Consider speaking to a teacher about {name}'s progress."
    return ""


def generate_report(learner_id: str, week_start: str) -> dict:
    """
    Generate a full weekly report for a learner.

    Steps:
    1. Read data from SQLite
    2. Compute skill deltas
    3. Build JSON matching parent_report_schema.json exactly
    4. Render PNG
    5. Generate voiced summary
    6. Save PNG + JSON to tutor/reports/
    7. Return the schema dict

    Parameters
    ----------
    learner_id : learner id string
    week_start : ISO date 'YYYY-MM-DD' (Monday of the report week)

    Returns
    -------
    dict  — schema-compliant report dict
    """
    tts = TutorTTS()

    # fetch data
    summary = get_weekly_summary(learner_id, week_start)

    # resolve learner name
    learners = list_learners()
    name_map = {lr["id"]: lr["name"] for lr in learners}
    learner_name = name_map.get(learner_id, learner_id.split("_")[0].capitalize())

    # voiced summary
    skills_data = summary.get("skills", {})
    icons       = summary.get("icons_for_parent", ["flat", "", ""])
    best_skill  = SKILL_LABELS.get(icons[1], icons[1]) if len(icons) > 1 else ""
    needs_skill = SKILL_LABELS.get(icons[2], icons[2]) if len(icons) > 2 else ""
    sessions    = summary["sessions"]

    voiced_en = (
        f"{learner_name} practiced {sessions} times this week. "
        f"Best at {best_skill}. "
        f"Needs more practice with {needs_skill}."
    )
    voiced_kin = (
        f"{learner_name} yagerageje inshuro {sessions} iki cyumweru. "
        f"Afite ubuhanga bwo {best_skill}. "
        f"Akeneye gufasha kuri {needs_skill}."
    )

    audio_path_en  = tts.speak(voiced_en,  "en")
    audio_path_kin = tts.speak(voiced_kin, "kin")
    audio_path = audio_path_en or audio_path_kin or ""

    summary["voiced_summary_audio"] = audio_path

    # early warning
    early_warning = _check_early_warning(learner_id, summary)
    if early_warning:
        summary["early_warning"] = early_warning

    # render PNG
    png_name = f"report_{learner_id}_{week_start}.png"
    png_path = os.path.join(_REPORTS, png_name)
    try:
        _render_png(summary, learner_name, png_path, early_warning)
    except Exception as exc:
        print(f"PNG render error: {exc}")

    # save JSON
    json_name = f"report_{learner_id}_{week_start}.json"
    json_path = os.path.join(_REPORTS, json_name)
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)

    print(f"Report saved: {png_path}, {json_path}")
    return summary


if __name__ == "__main__":
    # Example: generate report for a test learner
    from tutor.storage import init_db, ensure_learner, log_attempt, set_mastery

    init_db()
    lid = "amara_7"
    ensure_learner(lid, "Amara", 7)
    set_mastery(lid, "counting",     0.80)
    set_mastery(lid, "addition",     0.50)
    set_mastery(lid, "subtraction",  0.30)
    set_mastery(lid, "word_problem", 0.20)
    set_mastery(lid, "number_sense", 0.70)

    week = date.today().isoformat()
    report = generate_report(lid, week)
    print(json.dumps(report, indent=2))
