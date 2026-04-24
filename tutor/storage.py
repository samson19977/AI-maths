"""
storage.py
SQLite-backed persistence layer for learner profiles, attempt history,
and mastery estimates.  Uses only Python stdlib: sqlite3, json, datetime.
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
_DB_PATH = os.path.join(_HERE, "data", "learner.db")

SKILLS = ["counting", "number_sense", "addition", "subtraction", "word_problem"]


def _get_conn() -> sqlite3.Connection:
    """Open and return a SQLite connection with row_factory enabled."""
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """
    Create all tables if they do not exist.
    Safe to call multiple times (idempotent).
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS learners (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                age         INTEGER NOT NULL,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS attempts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                learner_id  TEXT NOT NULL,
                item_id     TEXT NOT NULL,
                skill       TEXT NOT NULL,
                correct     INTEGER NOT NULL,
                timestamp   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                latency_ms  INTEGER DEFAULT 0,
                FOREIGN KEY (learner_id) REFERENCES learners(id)
            );

            CREATE TABLE IF NOT EXISTS mastery (
                learner_id  TEXT NOT NULL,
                skill       TEXT NOT NULL,
                p_mastery   REAL NOT NULL DEFAULT 0.2,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (learner_id, skill)
            );
        """)
        conn.commit()
    finally:
        conn.close()


def ensure_learner(learner_id: str, name: str = "Child", age: int = 7) -> None:
    """
    Insert a learner row if one does not already exist for learner_id.
    Also initialises mastery rows for all five skills at 0.2.
    """
    init_db()
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO learners (id, name, age) VALUES (?,?,?)",
            (learner_id, name, age),
        )
        for skill in SKILLS:
            cur.execute(
                "INSERT OR IGNORE INTO mastery (learner_id, skill, p_mastery) VALUES (?,?,?)",
                (learner_id, skill, 0.2),
            )
        conn.commit()
    finally:
        conn.close()


def log_attempt(
    learner_id: str,
    item_id: str,
    skill: str,
    correct: int,
    latency_ms: int = 0,
) -> None:
    """
    Record one attempt for a learner.

    Parameters
    ----------
    learner_id : learner UUID / name string
    item_id    : curriculum item id (e.g. 'C001')
    skill      : one of the five skills
    correct    : 1 = correct, 0 = wrong
    latency_ms : milliseconds from question display to answer
    """
    init_db()
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO attempts (learner_id, item_id, skill, correct, latency_ms)
               VALUES (?,?,?,?,?)""",
            (learner_id, item_id, skill, int(correct), int(latency_ms)),
        )
        conn.commit()
    finally:
        conn.close()


def get_mastery(learner_id: str) -> dict:
    """
    Return current mastery estimates for all five skills.

    Returns
    -------
    dict  {skill: float}  — values in [0, 1]
    """
    init_db()
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT skill, p_mastery FROM mastery WHERE learner_id = ?",
            (learner_id,),
        ).fetchall()
        result = {skill: 0.2 for skill in SKILLS}
        for row in rows:
            result[row["skill"]] = row["p_mastery"]
        return result
    finally:
        conn.close()


def set_mastery(learner_id: str, skill: str, p_mastery: float) -> None:
    """
    Upsert a mastery value for one skill.

    Parameters
    ----------
    learner_id : learner id
    skill      : one of the five skills
    p_mastery  : float in [0, 1]
    """
    init_db()
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO mastery (learner_id, skill, p_mastery, updated_at)
               VALUES (?,?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(learner_id, skill)
               DO UPDATE SET p_mastery=excluded.p_mastery,
                             updated_at=excluded.updated_at""",
            (learner_id, skill, float(p_mastery)),
        )
        conn.commit()
    finally:
        conn.close()


def get_attempts(learner_id: str, skill: str = None) -> list:
    """
    Fetch attempt history for a learner, optionally filtered by skill.

    Returns
    -------
    list of dicts with keys: id, learner_id, item_id, skill, correct,
                              timestamp, latency_ms
    """
    init_db()
    conn = _get_conn()
    try:
        if skill:
            rows = conn.execute(
                """SELECT * FROM attempts WHERE learner_id=? AND skill=?
                   ORDER BY timestamp""",
                (learner_id, skill),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM attempts WHERE learner_id=? ORDER BY timestamp",
                (learner_id,),
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_weekly_summary(learner_id: str, week_start: str) -> dict:
    """
    Build a summary dict that matches parent_report_schema.json exactly.

    Parameters
    ----------
    learner_id : learner id
    week_start : ISO date string 'YYYY-MM-DD' for the Monday of the target week

    Returns
    -------
    dict with keys: learner_id, week_starting, sessions, skills,
                    icons_for_parent, voiced_summary_audio
    """
    init_db()
    conn = _get_conn()
    try:
        # parse week boundaries
        ws = datetime.fromisoformat(week_start)
        we = ws + timedelta(days=7)
        prev_ws = ws - timedelta(days=7)

        # count distinct session-days this week
        rows_this = conn.execute(
            """SELECT date(timestamp) AS day FROM attempts
               WHERE learner_id=? AND timestamp>=? AND timestamp<?
               GROUP BY day""",
            (learner_id, ws.isoformat(), we.isoformat()),
        ).fetchall()
        sessions = len(rows_this)

        # current mastery per skill
        mastery_rows = conn.execute(
            "SELECT skill, p_mastery FROM mastery WHERE learner_id=?",
            (learner_id,),
        ).fetchall()
        current = {skill: 0.0 for skill in SKILLS}
        for row in mastery_rows:
            current[row["skill"]] = row["p_mastery"]

        # compute accuracy this week per skill
        this_week_correct = {}
        this_week_total = {}
        for skill in SKILLS:
            rows = conn.execute(
                """SELECT correct FROM attempts
                   WHERE learner_id=? AND skill=?
                     AND timestamp>=? AND timestamp<?""",
                (learner_id, skill, ws.isoformat(), we.isoformat()),
            ).fetchall()
            if rows:
                this_week_correct[skill] = sum(r["correct"] for r in rows)
                this_week_total[skill] = len(rows)
            else:
                this_week_correct[skill] = 0
                this_week_total[skill] = 0

        # accuracy last week per skill for delta
        last_week_acc = {}
        for skill in SKILLS:
            rows = conn.execute(
                """SELECT correct FROM attempts
                   WHERE learner_id=? AND skill=?
                     AND timestamp>=? AND timestamp<?""",
                (learner_id, skill, prev_ws.isoformat(), ws.isoformat()),
            ).fetchall()
            if rows:
                last_week_acc[skill] = sum(r["correct"] for r in rows) / len(rows)
            else:
                last_week_acc[skill] = current[skill]  # no change baseline

        # build skills dict
        skills_dict = {}
        for skill in SKILLS:
            cur_val = current[skill]
            prev_val = last_week_acc[skill]
            skills_dict[skill] = {
                "current": round(cur_val, 3),
                "delta": round(cur_val - prev_val, 3),
            }

        # icons
        best_skill = max(skills_dict, key=lambda s: skills_dict[s]["current"])
        needs_help = min(skills_dict, key=lambda s: skills_dict[s]["current"])
        avg_delta = sum(v["delta"] for v in skills_dict.values()) / len(SKILLS)
        if avg_delta > 0.05:
            overall_arrow = "up"
        elif avg_delta < -0.05:
            overall_arrow = "down"
        else:
            overall_arrow = "flat"

        icons = [overall_arrow, best_skill, needs_help]

        return {
            "learner_id": learner_id,
            "week_starting": week_start,
            "sessions": sessions,
            "skills": skills_dict,
            "icons_for_parent": icons,
            "voiced_summary_audio": "",  # filled in by parent_report.py
        }
    finally:
        conn.close()


def list_learners() -> list:
    """Return all learner records as a list of dicts."""
    init_db()
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT * FROM learners ORDER BY created_at").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialised at", _DB_PATH)
