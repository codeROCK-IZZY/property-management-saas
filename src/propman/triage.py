"""Triage: how urgent a maintenance request is and which trade it needs, from the tenant's words.

Two steps (ADR 1):

1. **Hazard screen.** A short lexicon of the many ways people describe the dangers a property manager must answer
   at once: water escaping, heat or fire, gas or fumes, no power, a home that can't be secured, a structure failing,
   dangerous cold. "Smoking", "scorched", "burning" and "hot to touch" all mean heat where it shouldn't be. Any
   hazard sends the request to the on-call coordinator for a call-back now.
2. **Learned model.** Two multinomial logistic regressions (urgency and trade), fitted with numpy on words, word
   pairs and the lexicon's concepts. Words are regularised harder than concepts, so what is learned from one way of
   saying a thing carries over to another. The model also raises an emergency on its own when its probability passes
   a threshold, and it decides urgent or routine and the trade for everything else.

The threshold and the regularisation are set by cross-validation that holds out whole phrasings, so they reflect
how the model does on wording it has not seen. The emergency threshold is the lowest one whose false alarms, added to
the screen's, stay within a call-back budget. Every decision says what drove it.

`rules` is the keyword triage many property managers start with: emergency words, then each trade's words.
"""

from __future__ import annotations

import itertools
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from .corpus import TRADES, URGENCIES, Request

TOKEN = re.compile(r"[a-z]+")

# Each concept fires when a word starts with one of its stems, or the text contains one of its phrases.
HAZARDS: dict[str, tuple[str, ...]] = {
    "water escaping": (
        "pour",
        "flood",
        "gush",
        "spray",
        "burst",
        "overflow",
        "soak",
        "sewage",
        "stopcock",
        "water everywhere",
        "water coming",
        "water is coming",
        "water keeps",
        "through the ceiling",
        "into their",
        "dripping into",
        "pouring",
    ),
    "heat or fire": ("smok", "burn", "scorch", "spark", "fire", "flame", "melt", "hot to touch", "singe", "fuse box"),
    "gas or fumes": ("gas", "rotten egg", "carbon monoxide", "co alarm", "co detector", "fume", "dizzy", "headache"),
    "no power": ("no power", "power cut", "power is off", "blackout", "outage", "no electric", "no electricity"),
    "home not secure": (
        "locked out",
        "can't get in",
        "cannot get in",
        "kicked in",
        "broke in",
        "broken into",
        "break-in",
        "burgl",
        "intruder",
        "stranger",
        "can't be secured",
        "cannot be secured",
        "can't lock",
        "won't lock and",
    ),
    "structure failing": (
        "collaps",
        "fell off",
        "fell in",
        "falling",
        "fallen",
        "gave way",
        "given way",
        "caving",
        "glass everywhere",
        "smash",
        "through the roof",
        "roof off",
        "big crack",
    ),
    "dangerous cold": ("freezing", "no heating at all", "no heat at all", "frozen"),
}
SIGNS: dict[str, tuple[str, ...]] = {
    "not working": (
        "not working",
        "stopped",
        "won't",
        "doesn't",
        "isn't",
        "broken",
        "died",
        "dead",
        "cuts out",
        "tripping",
        "error",
        "no hot water",
        "blocked",
        "jammed",
    ),
    "pests or damp": ("mould", "mold", "damp", "mice", "mouse", "rats", "cockroach", "bugs", "insect", "rain"),
    "plumbing parts": ("tap", "toilet", "drain", "sink", "shower", "bath", "pipe", "water", "leak", "plumb", "flush"),
    "electrical parts": (
        "socket",
        "power",
        "light",
        "bulb",
        "switch",
        "wire",
        "breaker",
        "fuse",
        "electric",
        "doorbell",
        "circuit",
        "smoke alarm",
    ),
    "heating parts": ("boiler", "heating", "radiator", "thermostat", "air con", "cooling unit", "extractor", "vent"),
    "appliances": (
        "fridge",
        "freezer",
        "oven",
        "hob",
        "cooker",
        "dishwasher",
        "washing machine",
        "microwave",
        "dryer",
        "kettle",
    ),
    "locks and keys": ("lock", "key", "latch", "deadbolt", "padlock", "letterbox"),
    "building fabric": (
        "ceiling",
        "wall",
        "roof",
        "window",
        "floor",
        "door",
        "stair",
        "fence",
        "carpet",
        "paint",
        "cupboard",
        "hinge",
        "rail",
        "balcony",
    ),
}
CONCEPTS = {**HAZARDS, **SIGNS}
PREFIX = "@"


# Safety equipment named in a message is not itself a hazard: "the smoke alarm battery chirps" is routine.
EQUIPMENT = ("smoke alarm", "smoke detector", "fire alarm", "fire door", "fire extinguisher", "fire blanket")


def concepts(text: str) -> list[str]:
    full = text.lower().replace("’", "'")
    calm = full
    for phrase in EQUIPMENT:
        calm = calm.replace(phrase, " ")
    found = []
    for name, cues in CONCEPTS.items():
        low = calm if name in HAZARDS else full
        words = TOKEN.findall(low)
        for c in cues:
            hit = c in low if (" " in c or "-" in c or "'" in c) else any(w.startswith(c) for w in words)
            if hit:
                found.append(PREFIX + name)
                break
    return found


def hazards(text: str) -> list[str]:
    return [c[len(PREFIX) :] for c in concepts(text) if c[len(PREFIX) :] in HAZARDS]


def tokens(text: str, lexicon: bool = True) -> list[str]:
    words = TOKEN.findall(text.lower())
    pairs = [f"{a}_{b}" for a, b in itertools.pairwise(words)]
    return words + pairs + concepts(text) if lexicon else words + pairs


@dataclass
class Softmax:
    vocab: dict[str, int]
    classes: tuple[str, ...]
    w: np.ndarray  # (features + 1, classes)
    lexicon: bool = True

    def vector(self, text: str) -> np.ndarray:
        x = np.zeros(len(self.vocab) + 1)
        x[-1] = 1.0
        for t in tokens(text, self.lexicon):
            i = self.vocab.get(t)
            if i is not None:
                x[i] = 1.0
        return x

    def proba(self, text: str) -> dict[str, float]:
        z = self.vector(text) @ self.w
        p = np.exp(z - z.max())
        p /= p.sum()
        return {c: float(p[i]) for i, c in enumerate(self.classes)}

    def reasons(self, text: str, cls: str, k: int = 3) -> list[str]:
        """The features in this text pushing hardest towards `cls`."""
        j = self.classes.index(cls)
        found = [(t, float(self.w[self.vocab[t], j])) for t in set(tokens(text, self.lexicon)) if t in self.vocab]
        return [t.replace("_", " ") for t, v in sorted(found, key=lambda tv: (-tv[1], tv[0]))[:k] if v > 0]


def fit_softmax(
    texts: Sequence[str],
    labels: Sequence[str],
    classes: tuple[str, ...],
    l2_words: float = 0.03,
    l2_concepts: float = 1e-4,
    lexicon: bool = True,
    min_count: int = 2,
    steps: int = 300,
    lr: float = 0.5,
) -> Softmax:
    counts = Counter(t for text in texts for t in set(tokens(text, lexicon)))
    vocab = {t: i for i, t in enumerate(sorted(t for t, c in counts.items() if c >= min_count))}
    model = Softmax(vocab, classes, np.zeros((len(vocab) + 1, len(classes))), lexicon)
    reg = np.array([l2_concepts if t.startswith(PREFIX) else l2_words for t in vocab] + [0.0])[:, None]
    x = np.array([model.vector(t) for t in texts])
    y = np.zeros((len(texts), len(classes)))
    for i, lab in enumerate(labels):
        y[i, classes.index(lab)] = 1.0
    for _ in range(steps):
        z = x @ model.w
        p = np.exp(z - z.max(axis=1, keepdims=True))
        p /= p.sum(axis=1, keepdims=True)
        model.w -= lr * (x.T @ (p - y) / len(texts) + reg * model.w)
    return model


@dataclass
class Decision:
    urgency: str
    trade: str
    p_emergency: float
    hazards: list[str] = field(default_factory=list)
    why: list[str] = field(default_factory=list)


@dataclass
class Triage:
    urgency: Softmax
    trade: Softmax
    emergency_threshold: float = 0.5
    lexicon: bool = True

    def decide(self, text: str) -> Decision:
        pu = self.urgency.proba(text)
        found = hazards(text) if self.lexicon else []
        if found or pu["emergency"] >= self.emergency_threshold:
            urg = "emergency"
        else:
            urg = max(("urgent", "routine"), key=lambda c: pu[c])
        pt = self.trade.proba(text)
        trade = max(TRADES, key=lambda c: pt[c])
        why = [f"hazard: {h}" for h in found] + self.urgency.reasons(text, urg) + self.trade.reasons(text, trade, 2)
        return Decision(urg, trade, round(pu["emergency"], 3), found, list(dict.fromkeys(why)))


def out_of_fold(
    requests: Sequence[Request], l2_words: float, lexicon: bool = True
) -> list[tuple[Request, dict[str, float], dict[str, float]]]:
    """Each request's urgency and trade probabilities from a model that never saw its phrasing."""
    out = []
    for k in sorted({r.phrasing for r in requests}):
        fit = [r for r in requests if r.phrasing != k]
        held = [r for r in requests if r.phrasing == k]
        if not fit or not held:
            continue
        mu = fit_softmax([r.text for r in fit], [r.urgency for r in fit], URGENCIES, l2_words, lexicon=lexicon)
        mt = fit_softmax([r.text for r in fit], [r.trade for r in fit], TRADES, l2_words, lexicon=lexicon)
        out += [(r, mu.proba(r.text), mt.proba(r.text)) for r in held]
    return out


def pick_threshold(
    oof: Sequence[tuple[Request, dict[str, float], dict[str, float]]], false_alarm_budget: float, lexicon: bool = True
) -> float:
    """The lowest threshold whose false alarms, together with the screen's, stay within the budget."""
    calm = [(pu["emergency"], bool(hazards(r.text)) and lexicon) for r, pu, _ in oof if r.urgency != "emergency"]
    if not calm:
        return 0.5
    best = 0.5
    for th in np.round(np.arange(0.5, 0.0, -0.01), 2):
        fa = sum(screen or p >= th for p, screen in calm) / len(calm)
        if fa > false_alarm_budget:
            break
        best = float(th)
    return best


def train(
    requests: Sequence[Request], l2_words: float = 0.03, false_alarm_budget: float = 0.15, lexicon: bool = True
) -> Triage:
    """Fit both models on all the requests, with the emergency threshold from phrasing-held-out predictions.

    `lexicon=False` is the ablation: words and word pairs only, and no hazard screen.
    """
    th = pick_threshold(out_of_fold(requests, l2_words, lexicon), false_alarm_budget, lexicon)
    texts = [r.text for r in requests]
    urg = fit_softmax(texts, [r.urgency for r in requests], URGENCIES, l2_words, lexicon=lexicon)
    trade = fit_softmax(texts, [r.trade for r in requests], TRADES, l2_words, lexicon=lexicon)
    return Triage(urg, trade, th, lexicon)


EMERGENCY_WORDS = (
    "gas",
    "flood",
    "burst",
    "sparks",
    "fire",
    "smoke",
    "carbon monoxide",
    "collapsed",
    "locked out",
    "no heating",
    "no power",
    "sewage",
    "urgent",
    "asap",
    "emergency",
)
URGENT_WORDS = ("no hot water", "not working", "stopped", "broken", "blocked", "won't", "mould", "mice", "leak")
TRADE_WORDS = {
    "plumbing": ("water", "pipe", "leak", "tap", "toilet", "drain", "sink", "shower", "sewage", "bath"),
    "electrical": ("socket", "power", "light", "bulb", "switch", "wire", "breaker", "fuse", "electric", "doorbell"),
    "heating": ("boiler", "heating", "radiator", "gas", "thermostat", "air conditioning", "carbon monoxide"),
    "appliance": ("fridge", "freezer", "oven", "hob", "dishwasher", "washing machine", "microwave", "dryer"),
    "locks": ("lock", "key", "latch", "deadbolt"),
}


def rules(text: str) -> Decision:
    """Keyword triage: any emergency word makes an emergency, then urgent words, else routine."""
    low = text.lower()
    hit = [w for w in EMERGENCY_WORDS if w in low]
    urg = "emergency" if hit else "urgent" if any(w in low for w in URGENT_WORDS) else "routine"
    trade = next((t for t, ws in TRADE_WORDS.items() if any(w in low for w in ws)), "general")
    return Decision(urg, trade, 1.0 if hit else 0.0, [], hit)


# Chosen by `propman evaluate` (phrasing-held-out cross-validation on the tuning messages); see the report.
TUNED_L2_WORDS = 0.03
TUNED_THRESHOLD = 0.12


def fit(requests: Sequence[Request], l2_words: float = TUNED_L2_WORDS, threshold: float = TUNED_THRESHOLD) -> Triage:
    """Fit with settings already chosen, skipping the cross-validation (for the console and the CLI)."""
    texts = [r.text for r in requests]
    urg = fit_softmax(texts, [r.urgency for r in requests], URGENCIES, l2_words)
    trade = fit_softmax(texts, [r.trade for r in requests], TRADES, l2_words)
    return Triage(urg, trade, threshold)
