# Mwalimu wa Hesabu 🌟
### Offline AI Math Tutor — Children aged 5–9 in Rwanda

> Fully offline · CPU-only · English + Kinyarwanda + French · < 2 MB on-device footprint

---

## Quick Start

```bash
pip install -r requirements.txt
python demo.py
```

Open http://localhost:7860 in a browser. That is it.

---

## Project Structure

```
tutor/
├── __init__.py
├── curriculum_loader.py    # Seed → 60+ item curriculum
├── adaptive.py             # BKT + Tiny GRU DKT + AdaptiveEngine
├── asr_adapt.py            # Whisper-tiny + child-speech corrections
├── tts.py                  # pyttsx3 offline TTS + cache
├── storage.py              # SQLite learner profiles & mastery
├── feedback.py             # Rule-based child-friendly feedback
├── diagnostics.py          # 5-probe diagnostic session
├── utils.py                # Language detection & answer normalisation
├── data/
│   ├── curriculum_full.json  (auto-generated ≥ 60 items)
│   └── learner.db            (auto-created SQLite)
├── tts_cache/               (excluded from 75 MB footprint)
└── reports/                 (weekly parent reports)

demo.py           # Gradio app — launch point
parent_report.py  # Weekly report generator
kt_eval.ipynb     # BKT vs DKT vs Elo evaluation notebook
requirements.txt
README.md
footprint_report.md
process_log.md
```

---

## How Each Seed File Is Used

| Seed file | How used |
|---|---|
| `curriculum_seed.json` | 12 authentic items loaded by `curriculum_loader.py`; extended programmatically to ≥ 60 items covering all 5 skills × 4 age bands |
| `diagnostic_probes_seed.csv` | 5 probes (P001–P005) loaded by `DiagnosticSession`; answers seed BKT p_init values |
| `child_utt_sample_seed.csv` | Patterns used to build `CHILD_CORRECTIONS` map in `asr_adapt.py` (e.g. "esheshatu"→"gatatu", "twewenti"→"twenty") |
| `parent_report_schema.json` | Exact field names enforced in `storage.get_weekly_summary()` and `parent_report.generate_report()` |
| `child_utt_index.md` | Links to public corpora (Mozilla Common Voice, DigitalUmuganda) for future ASR fine-tuning |

---

## Knowledge Tracing

### Bayesian Knowledge Tracing (BKT)
Default model. Parameters per skill:

| Parameter | Value | Meaning |
|---|---|---|
| p_transit | 0.09 | Probability of learning per attempt |
| p_slip | 0.10 | Error despite mastery |
| p_guess | 0.20 | Correct without mastery |
| p_init | from DiagnosticSession | Seeded by 5 probes |

Update rule: standard BKT posterior → learning transition.

### Tiny GRU DKT
- **Architecture**: GRU (hidden=32) + linear head → sigmoid
- **Input**: one-hot (skill, correct/wrong), size = 2×5 = 10
- **Output**: P(mastery) per skill (5 values)
- **Weights**: `tutor/data/dkt_weights.pt` < 2 MB
- **Training**: 200 synthetic learners × 15 steps, 10 epochs, Adam lr=1e-3
- **CPU latency**: < 80 ms per forward pass

### Evaluation Results (from `kt_eval.ipynb`)

| Model | AUC | Notes |
|---|---|---|
| BKT | ~0.70 | No training required |
| DKT | ~0.68 | Improves with real data |
| Elo | ~0.60 | Item-response baseline |

---

## Multilingual Support

### Language Detection (`tutor/utils.detect_language`)
- Counts keyword matches per language (EN/KIN/FR lexicons)
- Returns `'mixed'` if two languages each score ≥ 1 match
- Kinyarwanda keywords: `zingahe`, `angahe`, `rimwe`, `kabiri`, `cyangwa`, …
- French keywords: `combien`, `quel`, `plus`, `moins`, `égale`, …

### Answer Normalisation (`tutor/utils.normalize_answer`)
1. Try direct integer parse (`"5"` → 5)
2. Exact word lookup in all language dictionaries
3. Fuzzy Levenshtein match (distance ≤ 2) for misspellings
   - `"twewenti"` → 20, `"tu"` → 2, `"esheshatu"` → 3 (gatatu)

### Code-switching
Mixed responses like `"gatanu plus five"` are handled via `mixed_language_response()`:
dominant language is detected, answer extracted from the normalised combined text.

---

## Parent Report

```bash
python parent_report.py
```

Or click **"Generate Parent Report"** in the app after a session ends.

Outputs saved to `tutor/reports/`:
- `report_{learner_id}_{week}.png` — icon-heavy 1-pager readable in 60 s
- `report_{learner_id}_{week}.json` — schema-compliant JSON

The PNG includes:
- Skill progress bars (green ≥ 70%, yellow 40–70%, red < 40%)
- Delta arrows (↑ / → / ↓) per skill
- Best skill & needs-help icons
- Voiced summary audio path (pyttsx3 .wav)
- Dyscalculia early warning if triggered

---

## Deployment Story

### First 90 seconds UX (6-year-old Kinyarwanda speaker)

1. **App opens** → warm yellow screen: `"Mwalimu wa Hesabu 🌟"`.
2. Teacher types or taps the child's name (e.g. *Kagabo*) and age 6.
3. Selects **Kinyarwanda**. Presses **Tangira**.
4. TTS plays immediately: *"Muraho! Nitwa Mwalimu. Reka tugerageze guharura hamwe!"*
   (Hello! I am Teacher. Let's try counting together!)
5. Screen 2 shows the first diagnostic probe: a picture of **4 fingers** and the spoken question.
6. Kagabo says *"kane"* (4 in Kinyarwanda) — the app normalises via `normalize_answer()` → correct feedback plays.
7. **If Kagabo stays silent for 10 seconds**: the question audio replays automatically.
8. **After a second silence**: a large text input box appears prominently.
9. **After a third silence**: a finger-counting visual shows the count on screen as a hint.

### Shared Tablet (3 children, community centre)

- Each child gets their own **learner profile** in SQLite (`learners` table), keyed by `name_age` (e.g. `kagabo_6`, `amara_7`).
- The **Welcome screen** is always shown on launch — each child taps their name to start a fresh session.
- Mastery and attempt data are stored per `learner_id` — completely separate rows, no cross-contamination.
- **On reboot mid-session**: SQLite is ACID-compliant; the last completed attempt is always committed. On next launch the child re-enters name/age and continues from their stored mastery state. No data is lost.
- **Privacy**: no passwords or biometrics — separation is by name only. Appropriate for a community setting where children do not share devices simultaneously.

### Non-literate Parent Report

A parent who cannot read can understand the weekly report in under 60 seconds:

1. **Large arrow (↑ / → / ↓)** at the bottom of the PNG tells at a glance whether the child is improving, steady, or declining.
2. **Coloured progress bars** (green = good, yellow = learning, red = needs help) for each of the 5 skills — no numbers needed.
3. **Star icon** marks the best skill; **light-bulb icon** marks the skill needing most practice.
4. **Voiced summary** (pyttsx3 .wav): teacher plays the audio aloud — available in both English and Kinyarwanda.
   - EN: *"Kagabo practiced 4 times this week. Best at counting. Needs more practice with word problems."*
   - KIN: *"Kagabo yagerageje inshuro 4 iki cyumweru. Afite ubuhanga bwo guharura. Akeneye gufasha kuri word problems."*
5. **QR code placeholder** (production version links to a hosted audio file).

---

## Footprint Confirmation

See `footprint_report.md`.  
Total on-device code + data < **2 MB** (without optional Whisper-tiny at 39 MB).  
Both variants are well under the 75 MB limit. ✅
