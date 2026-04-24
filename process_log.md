# Process Log — Mwalimu wa Hesabu

---

## Honor Code (verbatim from AIMS KTT brief)

> *"I confirm that all work submitted is my own. Any use of AI tools, external code,
> or reference material has been fully declared below. I have not shared my solution
> with other participants, nor have I copied from others."*

**Signature:** ______________________________  
**Date:** ______________________________

---

## Hour-by-Hour Timeline

| Hour | Time block | Activity | Key decisions |
|------|-----------|----------|---------------|
| 1 | 00:00 – 01:00 | Seed file analysis (Step 0); project scaffold; `curriculum_loader.py`, `storage.py` | Chose SQLite over JSON files for multi-profile support |
| 2 | 01:00 – 02:00 | `adaptive.py` (BKT + DKT), `diagnostics.py`, `utils.py`, `asr_adapt.py` | Kept DKT hidden=32 to stay < 2 MB; pyttsx3 over Coqui for zero-download TTS |
| 3 | 02:00 – 03:00 | `tts.py`, `feedback.py`, `demo.py` (Gradio app), visual rendering | Chose Pillow-only rendering — no image files needed; silence fallback with finger-counting hint |
| 4 | 03:00 – 04:00 | `parent_report.py`, `kt_eval.ipynb`, `README.md`, `footprint_report.md`, testing | Added dyscalculia early-warning; wrote deployment story for shared tablet + non-literate parent |

---

## LLM / Tool Use Declaration

| Tool | Version | How used | Output incorporated? |
|------|---------|----------|----------------------|
| Claude (Anthropic) | claude-sonnet-4-6 | Structured code generation from detailed spec | Yes — all files |
| No other LLM or tool | — | — | — |

*All seed file content was read verbatim; no curriculum items were invented without reference to the seed schema.*

---

## Sample Prompts

### Prompt 1 — Seed file extraction
```
Read the ZIP, print every file, and tell me how each will be used before writing any code.
```

### Prompt 2 — BKT implementation
```
Implement bkt_update() following the standard BKT posterior formula:
P(mastery | obs) = P(obs | mastered) * P(mastery) / P(obs)
Then apply the learning transition: P_new = P_posterior + (1 - P_posterior) * p_transit
```

### Prompt 3 — Pillow-only visual rendering
```
Implement render_visual(item) using only Pillow.  Parse the visual field:
'beads_2_plus_3' → two groups of circles with + sign,
'drums_8_minus_3' → 8 circles with 3 crossed out in red.
No external image files. 400×300 px, #FFF8DC background.
```

---

## Discarded Prompt / Approach

**Discarded:** Using Coqui TTS (tts library) for Kinyarwanda synthesis.

**Reason:** Coqui's Kinyarwanda voice model is ~120 MB — exceeds the 75 MB footprint budget and requires a separate download. Switched to pyttsx3 (< 2 MB, included with system voices) with a caching layer. The tradeoff is lower voice quality for Kinyarwanda, but the system remains fully offline with no download required.

---

## Hardest Decision

**The hardest decision was how to handle Kinyarwanda TTS quality within the 75 MB constraint.**

pyttsx3 uses system-installed voices, which typically do not include a native Kinyarwanda voice. The implemented solution synthesises Kinyarwanda text using the English voice engine (which mispronounces it, but is intelligible for simple number words) and caches the output. The voiced summary in the parent report is generated in both English and Kinyarwanda so parents can choose the version they prefer.

A production deployment should replace pyttsx3 with a quantised Kinyarwanda TTS model (e.g. a fine-tuned Coqui VITS at < 40 MB) or pre-generate all TTS audio during installation and bundle only the cache files. The architecture is designed for this swap — `TutorTTS.speak()` is the single integration point.
