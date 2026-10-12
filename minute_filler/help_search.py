"""The help's search box: finds the help topics (help_topics) for a question in the user's own words.

Two rankings are joined (reciprocal rank fusion, FUSION_K and MEANING_WEIGHT):
- keywords: BM25 over each topic's title (counted TITLE_WEIGHT times), its extra search words (WORDS_WEIGHT) and its
  text, on simple word stems ("dated", "dates", "dating" -> "dat"), with a few everyday words added to the question
  (SYNONYMS: "bill" also looks for "invoice") and typos forgiven ("invioce" -> "invoice", rapidfuzz);
- meaning: help_meaning's word table, made from EmbeddingGemma 2, which knows that "closed" is close to "holiday"
  even when no word is shared. Left out when its file is missing, and until help_meaning.prepare() has made it
  ready in the background (the first searches may go by keywords alone).

search("why is my invoice dated tuesday") -> [Hit(topic dates-business-days, …), …]. No Qt here: gui/help_window
shows the hits."""
from __future__ import annotations

import html
import math
import re
from collections import Counter
from dataclasses import dataclass

from .help_topics import TOPICS, Topic

TITLE_WEIGHT, WORDS_WEIGHT = 3, 2
K1, B = 1.2, 0.75  # BM25's usual values
FUZZY_SCORE = 80  # how alike (rapidfuzz ratio, 0-100) a typed word must be to a help word to stand for it
FUZZY_SHORTEST = 5  # shorter stems must be typed right (too many short words are near each other)
FUSION_K = 10  # reciprocal rank fusion: 1 / (FUSION_K + rank); small, as there are only ~100 topics
MEANING_WEIGHT = 0.6  # the meaning ranking's weight against the keywords' (1)

STOP = set("""a about after again all also am an and any are as at be been before being but by can could did do
does doing done for from get gets getting go had has have how i if in into is it its just me my need of off on
once only or other our out should so some such than that the their them then there these they this those to too
up use used using very want was way we were what when where which while who whom why will with would you your
yinit yinitagreementform please not many much""".split())  # ("not": "note" stems to "not" too)
# Everyday words for the help's own: each also looks for these (stems are taken of both). A phrase of two words
# ("day off") is matched before its words.
SYNONYMS = {
    "bill": "invoice", "bills": "invoice", "billing": "invoice", "billed": "invoice", "invoiced": "invoice",
    "lawyer": "attorney", "lawyers": "attorney", "counsel": "attorney",
    "day off": "holiday", "days off": "holiday", "closed": "holiday", "closure": "holiday", "closing": "holiday",
    "cost": "price rate", "costs": "price rate", "fee": "price rate", "fees": "price rate", "charge": "price",
    "postdate": "dated business day", "postdated": "dated business day", "backdate": "dated",
    "due": "delivery turnaround", "deadline": "delivery turnaround",
    "partial": "excerpt", "portion": "excerpt", "part of": "excerpt",
    "sign": "signature", "signing": "signature",
    "picture": "photo", "image": "photo", "camera": "photo",
    "crash": "problem", "crashed": "problem", "crashes": "problem", "error": "problem", "bug": "problem",
    "broken": "problem",
    "spreadsheet": "excel", "accountant": "export summary", "taxes": "export summary", "income": "summary",
    "earnings": "summary", "earned": "summary",
    "color": "colour", "colors": "colour", "colored": "colour",
    "hotkey": "shortcut", "hotkeys": "shortcut",
    "bigger": "zoom", "smaller": "zoom", "font": "zoom",
    "laptop": "computer", "pc": "computer",
    "cheque": "paid payment", "payment": "paid", "pay": "paid",
    "penny": "cent rounding", "pennies": "cent rounding",
    "back up": "backup", "backed up": "backup", "wording": "text",
}


@dataclass
class Hit:
    """A topic found: its score (higher is better) and a line of its text with the words found in bold (HTML)."""
    topic: Topic
    score: float
    snippet: str


def stem(word: str) -> str:
    """A rough stem, the same for a word's usual forms: "dated", "dates", "dating" -> "dat"; "parties" -> "party"."""
    w = word
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    for suffix in ("ings", "ing", "ed", "es", "s"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3 and not (suffix == "s" and w.endswith("ss")):
            w = w[:-len(suffix)]
            break
    if len(w) > 3 and w.endswith("e"):
        w = w[:-1]
    return w


def words(text: str) -> list[str]:
    """The words of a text, in lower case, without the stop words ("E-mails" -> "emails")."""
    text = re.sub(r"(?i)\be-mail", "email", text).lower().replace("'s ", " ")
    return [w for w in re.findall(r"[a-z0-9]+", text) if w not in STOP and (len(w) > 1 or w.isdigit())]


def question_stems(text: str) -> dict[str, float]:
    """The question's words as stem -> weight: its own at 1, the SYNONYMS they bring at 0.7. A phrase found
    ("day off") stands for its synonyms alone: its words ("day") are not looked for on their own."""
    out: dict[str, float] = {}

    def add(s: str, weight: float) -> None:
        out[s] = max(out.get(s, 0), weight)

    lower = " ".join(re.findall(r"[a-z0-9]+", re.sub(r"(?i)\be-mail", "email", text).lower()))
    for phrase, extra in SYNONYMS.items():
        if " " in phrase and re.search(rf"\b{phrase}\b", lower):
            lower = re.sub(rf"\b{phrase}\b", " ", lower)
            for w in extra.split():
                add(stem(w), 0.7)
    for w in words(lower):
        add(stem(w), 1.0)
        for x in SYNONYMS.get(w, "").split():
            add(stem(x), 0.7)
    return out


class Index:
    """The topics' words, ready to search: each topic's weighted term counts and length, and how many topics hold
    each stem (for the BM25 weights)."""

    def __init__(self, topics: list[Topic]):
        self.topics = topics
        self.tf: list[Counter] = []
        for t in topics:
            c = Counter()
            for weight, text in ((TITLE_WEIGHT, t.title), (WORDS_WEIGHT, t.words), (1, t.text)):
                for w in words(text):
                    c[stem(w)] += weight
            self.tf.append(c)
        self.lengths = [sum(c.values()) for c in self.tf]
        self.avg = sum(self.lengths) / max(1, len(self.lengths))
        self.df = Counter(s for c in self.tf for s in c)
        self.vocab = sorted(self.df)
        self._fuzzy: dict[str, str | None] = {}

    def idf(self, s: str) -> float:
        """BM25's weight of a stem: high for one only a few topics hold."""
        n = self.df.get(s, 0)
        return math.log(1 + (len(self.topics) - n + 0.5) / (n + 0.5))

    def known(self, s: str) -> str | None:
        """The stem itself when a topic holds it, else the closest one (a typo: "invioc" -> "invoic"), or None."""
        if s in self.df:
            return s
        if len(s) < FUZZY_SHORTEST:
            return None
        if s not in self._fuzzy:
            try:
                from rapidfuzz import fuzz, process
            except ImportError:  # (bundled with the app; without it, typos simply aren't forgiven)
                self._fuzzy[s] = None
            else:
                best = process.extractOne(s, self.vocab, scorer=fuzz.ratio, score_cutoff=FUZZY_SCORE)
                self._fuzzy[s] = best[0] if best else None
        return self._fuzzy[s]

    def terms(self, question: str) -> dict[str, float]:
        """The question's stems as the topics have them (a typo put right), with their weights."""
        terms: dict[str, float] = {}
        for s, weight in question_stems(question).items():
            k = self.known(s)
            if k:
                terms[k] = max(terms.get(k, 0), weight)
        return terms

    def scores(self, question: str) -> list[float]:
        """Each topic's BM25 score for the question (0 when it shares no word with it)."""
        terms = self.terms(question)
        out = []
        for c, length in zip(self.tf, self.lengths):
            total = 0.0
            for s, weight in terms.items():
                f = c.get(s, 0)
                if f:
                    total += weight * self.idf(s) * f * (K1 + 1) / (f + K1 * (1 - B + B * length / self.avg))
            out.append(total)
        return out


_INDEX: dict[int, Index] = {}


def index(topics: list[Topic] = TOPICS) -> Index:
    """The Index of these topics, made once."""
    key = id(topics)
    if key not in _INDEX:
        _INDEX[key] = Index(topics)
    return _INDEX[key]


def _ranks(scores: list[float]) -> dict[int, int]:
    """Topic number -> its place (1 = best) among those that scored above 0."""
    order = sorted((i for i, v in enumerate(scores) if v > 0), key=lambda i: -scores[i])
    return {i: n + 1 for n, i in enumerate(order)}


def search(question: str, topics: list[Topic] = TOPICS, meaning=None, limit: int = 12) -> list[Hit]:
    """The topics that answer the question, best first. meaning: a help_meaning.Meaning of the same topics (None:
    the one made from the bundled word table, when it is ready; False: keywords only)."""
    if not words(question):
        return []
    ix = index(topics)
    kw = ix.scores(question)
    ranked = {i: 1 / (FUSION_K + r) for i, r in _ranks(kw).items()}
    if meaning is None:
        from . import help_meaning
        meaning = help_meaning.ready(topics)
    if meaning:
        sims = meaning.scores(question)
        if sims is not None:
            for i, r in _ranks([max(v, 1e-9) for v in sims]).items():
                ranked[i] = ranked.get(i, 0) + MEANING_WEIGHT / (FUSION_K + r)
    best = sorted(ranked, key=lambda i: (-ranked[i], -kw[i]))[:limit]
    return [Hit(topics[i], ranked[i], snippet(topics[i], question, topics)) for i in best]


def snippet(t: Topic, question: str, topics: list[Topic] = TOPICS, width: int = 150) -> str:
    """The sentence of the topic that holds the question's rarest words (the first, when none does), cut to about
    `width` characters around them, HTML-escaped, the words found in bold."""
    ix = index(topics)
    stems = set(ix.terms(question))
    sentences = [s for s in re.split(r"(?<=[.:;!?])\s+", t.text) if s]

    def worth(s: str) -> float:
        return sum(ix.idf(x) for x in {stem(w) for w in words(s)} & stems)

    pick = max(sentences, key=lambda s: (worth(s), -sentences.index(s))) if sentences else ""
    if len(pick) > width:
        first = next((m.start() for m in re.finditer(r"[A-Za-z0-9]+", pick) if stem(m.group().lower()) in stems), 0)
        start = max(0, first - width // 3)
        if start:  # (from the start of a word: "…the delivery day", not "…ry day")
            start = pick.find(" ", start, first) + 1 or first
        pick = ("…" if start else "") + pick[start:start + width].rsplit(" ", 1)[0] + "…"

    def bold(m: re.Match) -> str:
        w = m.group()
        return f"<b>{w}</b>" if stem(w.lower()) in stems and w.lower() not in STOP else w

    return re.sub(r"[A-Za-z0-9]+", bold, html.escape(pick))


def marked_stems(question: str, topics: list[Topic] = TOPICS) -> list[str]:
    """The stems the Help window highlights in a topic opened from a search: the question's words and the
    synonyms they bring, typos put right, longest first ("add a day off" -> ["holiday", "add"])."""
    return sorted(index(topics).terms(question), key=len, reverse=True)
