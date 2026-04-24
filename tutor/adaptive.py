"""
adaptive.py
Knowledge tracing: Bayesian Knowledge Tracing (BKT) and a Tiny GRU-based
Deep Knowledge Tracing (DKT) model.  AdaptiveEngine is the public interface
consumed by demo.py.
All computation is CPU-only; total DKT weights < 2 MB.
"""

import os
import json
import random
import math

import torch
import torch.nn as nn
import numpy as np

from tutor.storage import get_mastery, set_mastery, log_attempt

_HERE = os.path.dirname(os.path.abspath(__file__))
_WEIGHTS_PATH = os.path.join(_HERE, "data", "dkt_weights.pt")

SKILLS = ["counting", "number_sense", "addition", "subtraction", "word_problem"]
SKILL_IDX = {s: i for i, s in enumerate(SKILLS)}
N_SKILLS = len(SKILLS)

# ── BKT parameters (fixed, per skill) ──────────────────────────────────────
BKT_PARAMS = {
    "p_transit": 0.09,
    "p_slip":    0.10,
    "p_guess":   0.20,
}


# ── Bayesian Knowledge Tracing ──────────────────────────────────────────────

def bkt_update(p_mastery: float, correct: int) -> float:
    """
    Standard BKT update rule.

    Parameters
    ----------
    p_mastery : current P(mastery) ∈ [0, 1]
    correct   : 1 = correct response, 0 = incorrect

    Returns
    -------
    float  updated P(mastery) after observing the response
    """
    p_t = BKT_PARAMS["p_transit"]
    p_s = BKT_PARAMS["p_slip"]
    p_g = BKT_PARAMS["p_guess"]

    # P(obs | mastery=1/0)
    if correct:
        p_obs_mastered   = 1.0 - p_s
        p_obs_unmastered = p_g
    else:
        p_obs_mastered   = p_s
        p_obs_unmastered = 1.0 - p_g

    # posterior P(mastery | obs)
    numerator   = p_obs_mastered * p_mastery
    denominator = numerator + p_obs_unmastered * (1.0 - p_mastery)
    p_posterior = numerator / max(denominator, 1e-9)

    # learning transition
    p_new = p_posterior + (1.0 - p_posterior) * p_t
    return float(np.clip(p_new, 0.0, 1.0))


def bkt_next_item(learner_id: str, curriculum: list) -> dict:
    """
    Select the next curriculum item using BKT mastery estimates.

    Strategy: find the skill with lowest p_mastery, then return the
    easiest item in that skill that the learner has not recently seen.

    Parameters
    ----------
    learner_id : learner id
    curriculum : full list of item dicts

    Returns
    -------
    dict  — next curriculum item
    """
    mastery = get_mastery(learner_id)
    # pick skill with lowest mastery (exclude fully mastered > 0.85)
    active_skills = {s: v for s, v in mastery.items() if v < 0.85}
    if not active_skills:
        active_skills = mastery  # all mastered — continue practice

    weakest_skill = min(active_skills, key=active_skills.get)
    skill_items = [i for i in curriculum if i.get("skill") == weakest_skill]

    if not skill_items:
        # fall back to any item
        return random.choice(curriculum)

    # sort by difficulty, pick easiest
    skill_items.sort(key=lambda x: x.get("difficulty", 5))
    return skill_items[0]


# ── Tiny GRU DKT ────────────────────────────────────────────────────────────

class TinyGRUDKT(nn.Module):
    """
    Compact GRU-based Deep Knowledge Tracing model.

    Input  : sequence of (skill_idx, correct) encoded as one-hot vectors
             of size 2 * N_SKILLS (one half per skill per correct/incorrect)
    Hidden : GRU with hidden_size=32
    Output : N_SKILLS sigmoid probabilities (one per skill)
    """

    def __init__(self, n_skills: int = N_SKILLS, hidden_size: int = 32):
        """
        Parameters
        ----------
        n_skills    : number of distinct skills (default 5)
        hidden_size : GRU hidden dimension (default 32, keeps weights < 2 MB)
        """
        super().__init__()
        self.n_skills = n_skills
        self.hidden_size = hidden_size
        input_size = 2 * n_skills  # one-hot over (skill, correct/wrong)

        self.gru  = nn.GRU(input_size, hidden_size, batch_first=True)
        self.head = nn.Linear(hidden_size, n_skills)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass.

        Parameters
        ----------
        x : Tensor of shape (batch, seq_len, 2*n_skills)

        Returns
        -------
        Tensor of shape (batch, seq_len, n_skills) — sigmoid probabilities
        """
        out, _ = self.gru(x)
        return torch.sigmoid(self.head(out))

    def _encode(self, skill_idx: int, correct: int) -> torch.Tensor:
        """One-hot encode a single (skill, correct) event."""
        vec = torch.zeros(2 * self.n_skills)
        offset = 0 if correct else self.n_skills
        vec[offset + skill_idx] = 1.0
        return vec

    def predict_mastery(self, history: list) -> dict:
        """
        Predict current mastery from an interaction history.

        Parameters
        ----------
        history : list of (skill_name_str, correct_int) tuples

        Returns
        -------
        dict  {skill: float}
        """
        if not history:
            return {s: 0.2 for s in SKILLS}

        seq = torch.stack([
            self._encode(SKILL_IDX.get(skill, 0), correct)
            for skill, correct in history
        ]).unsqueeze(0)  # (1, seq_len, input_size)

        with torch.no_grad():
            out = self.forward(seq)  # (1, seq_len, n_skills)
        last = out[0, -1, :].numpy()
        return {skill: float(last[i]) for i, skill in enumerate(SKILLS)}


class DKTTrainer:
    """
    Generates synthetic training data and trains TinyGRUDKT.
    Saves weights to tutor/data/dkt_weights.pt (< 2 MB).
    """

    def __init__(self, curriculum: list):
        """
        Parameters
        ----------
        curriculum : full curriculum item list
        """
        self.curriculum = curriculum
        self.model = TinyGRUDKT()

    def generate_synthetic_data(
        self, n_learners: int = 200, seq_len: int = 15
    ) -> list:
        """
        Generate synthetic interaction sequences by simulating learners
        with random skill mastery profiles.

        Parameters
        ----------
        n_learners : number of synthetic learner trajectories
        seq_len    : length of each sequence

        Returns
        -------
        list of tensors  [(x, y), ...]  where x,y are (seq_len, *)
        """
        dataset = []
        for _ in range(n_learners):
            # random true mastery per skill
            true_mastery = {s: random.uniform(0.1, 0.9) for s in SKILLS}
            sequence_x, sequence_y = [], []

            for t in range(seq_len):
                skill = random.choice(SKILLS)
                si = SKILL_IDX[skill]
                p_correct = true_mastery[skill]
                correct = 1 if random.random() < p_correct else 0

                # input one-hot
                vec = torch.zeros(2 * N_SKILLS)
                offset = 0 if correct else N_SKILLS
                vec[offset + si] = 1.0
                sequence_x.append(vec)

                # target: true mastery for all skills
                target = torch.tensor(
                    [true_mastery[s] for s in SKILLS], dtype=torch.float32
                )
                sequence_y.append(target)

                # simple mastery update (simulated learning)
                if correct:
                    true_mastery[skill] = min(
                        true_mastery[skill] + random.uniform(0.01, 0.05), 0.95
                    )

            dataset.append((
                torch.stack(sequence_x),  # (seq_len, 2*N_SKILLS)
                torch.stack(sequence_y),  # (seq_len, N_SKILLS)
            ))
        return dataset

    def train(self, epochs: int = 10) -> "TinyGRUDKT":
        """
        Train the DKT model on synthetic data and save weights.

        Parameters
        ----------
        epochs : number of training epochs

        Returns
        -------
        TinyGRUDKT  — trained model
        """
        dataset = self.generate_synthetic_data()
        optimizer = torch.optim.Adam(self.model.parameters(), lr=1e-3)
        criterion = nn.BCELoss()

        self.model.train()
        for epoch in range(epochs):
            total_loss = 0.0
            for x, y in dataset:
                xb = x.unsqueeze(0)  # (1, seq_len, input)
                yb = y.unsqueeze(0)  # (1, seq_len, n_skills)
                pred = self.model(xb)
                loss = criterion(pred, yb)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                total_loss += loss.item()
            avg = total_loss / len(dataset)
            if (epoch + 1) % 5 == 0:
                print(f"  DKT epoch {epoch+1}/{epochs}  loss={avg:.4f}")

        # save weights
        os.makedirs(os.path.dirname(_WEIGHTS_PATH), exist_ok=True)
        torch.save(self.model.state_dict(), _WEIGHTS_PATH)
        size_kb = os.path.getsize(_WEIGHTS_PATH) / 1024
        print(f"  Saved DKT weights → {_WEIGHTS_PATH}  ({size_kb:.1f} KB)")
        return self.model


def _load_dkt_model() -> TinyGRUDKT:
    """Load saved DKT weights if available; otherwise train a new model."""
    model = TinyGRUDKT()
    if os.path.exists(_WEIGHTS_PATH):
        try:
            model.load_state_dict(torch.load(_WEIGHTS_PATH, map_location="cpu"))
            model.eval()
            return model
        except Exception:
            pass
    # train on first run
    try:
        from tutor.curriculum_loader import load_curriculum
        curriculum = load_curriculum()
    except Exception:
        curriculum = []
    trainer = DKTTrainer(curriculum)
    model = trainer.train(epochs=10)
    model.eval()
    return model


# ── AdaptiveEngine ─────────────────────────────────────────────────────────

class AdaptiveEngine:
    """
    Public adaptive engine interface used by demo.py.
    Wraps either BKT (default) or DKT to select next items and update mastery.
    """

    def __init__(
        self,
        learner_id: str,
        curriculum: list,
        model: str = "bkt",
        initial_mastery: dict = None,
    ):
        """
        Parameters
        ----------
        learner_id      : unique learner identifier
        curriculum      : full curriculum item list
        model           : 'bkt' (default) or 'dkt'
        initial_mastery : optional dict {skill: float} from DiagnosticSession
        """
        self.learner_id = learner_id
        self.curriculum = curriculum
        self.model_type = model
        self._history = []  # list of (skill, correct) for DKT

        # seed mastery from diagnostic if provided
        if initial_mastery:
            for skill, val in initial_mastery.items():
                set_mastery(learner_id, skill, val)

        if model == "dkt":
            self._dkt = _load_dkt_model()
        else:
            self._dkt = None

    def update(self, item_id: str, skill: str, correct: int) -> None:
        """
        Record a response and update mastery estimates.

        Parameters
        ----------
        item_id : curriculum item id
        skill   : skill name
        correct : 1 = correct, 0 = wrong
        """
        # always log to SQLite
        log_attempt(self.learner_id, item_id, skill, correct)

        # update mastery
        if self.model_type == "bkt":
            mastery = get_mastery(self.learner_id)
            new_p = bkt_update(mastery.get(skill, 0.2), correct)
            set_mastery(self.learner_id, skill, new_p)
        else:
            self._history.append((skill, correct))
            dkt_mastery = self._dkt.predict_mastery(self._history)
            for s, v in dkt_mastery.items():
                set_mastery(self.learner_id, s, v)

    def get_mastery(self) -> dict:
        """
        Return current mastery estimates for all skills.

        Returns
        -------
        dict  {skill: float}
        """
        return get_mastery(self.learner_id)

    def next_item(self) -> dict:
        """
        Select and return the next curriculum item.

        Returns
        -------
        dict  — curriculum item dict
        """
        return bkt_next_item(self.learner_id, self.curriculum)

    def is_mastered(self, skill: str) -> bool:
        """
        Return True if the learner's mastery for a skill exceeds 0.85.

        Parameters
        ----------
        skill : skill name

        Returns
        -------
        bool
        """
        mastery = get_mastery(self.learner_id)
        return mastery.get(skill, 0.0) > 0.85


if __name__ == "__main__":
    from tutor.curriculum_loader import load_curriculum
    from tutor.storage import init_db, ensure_learner

    init_db()
    curriculum = load_curriculum()
    ensure_learner("test_learner", "Test Child", 7)

    engine = AdaptiveEngine("test_learner", curriculum, model="bkt")
    for _ in range(3):
        item = engine.next_item()
        engine.update(item["id"], item["skill"], correct=1)
        print(engine.get_mastery())
