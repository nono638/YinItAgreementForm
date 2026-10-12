"""The help search's sense of meaning: a table of word vectors made once from EmbeddingGemma 2 (Google, Apache 2.0)
by tools/meaning/build_table.py, so the app needs no model, no Ollama and no numpy to know that "closed" is near
"holiday" and "lawyer" near "attorney".

A text's vector is the mean of its words' vectors, each weighted by how rare the word is in the help; a question is
compared with each topic's vector (cosine). Plain Python: about 100 topics take a second or so to prepare
(prepare() does it once, in the background when the help window opens; ready() gives it once done) and a
question a few milliseconds.

The table (data/help_words.bin): b"YINW1\\n", a line of JSON (model, revision, dims, count, prompt, top,
words_bytes), the words (UTF-8, one per line), a float32 scale for each word, then each word's vector as int8
(scale * int8 = the value; the vectors are unit length)."""
from __future__ import annotations

import json
import math
import threading
from array import array
from pathlib import Path

from . import help_search
from .help_topics import Topic

TABLE = Path(__file__).parent / "data" / "help_words.bin"
MAGIC = b"YINW1\n"


class Table:
    """The word vectors: vector(word) gives a word's (unit) vector, or None for a word it doesn't have."""

    def __init__(self, path: Path = TABLE):
        data = path.read_bytes()
        if not data.startswith(MAGIC):
            raise ValueError(f"{path.name} is not a word table")
        end = data.index(b"\n", len(MAGIC))
        self.header = json.loads(data[len(MAGIC):end])
        self.dims, n = int(self.header["dims"]), int(self.header["count"])
        start = end + 1
        blob = data[start:start + int(self.header["words_bytes"])].decode("utf-8")
        self.index = {w: i for i, w in enumerate(blob.split("\n"))}
        start += int(self.header["words_bytes"])
        self.scales = array("f")
        self.scales.frombytes(data[start:start + 4 * n])
        start += 4 * n
        self.values = array("b")
        self.values.frombytes(data[start:start + n * self.dims])
        if len(self.index) != n or len(self.values) != n * self.dims:
            raise ValueError(f"{path.name} is cut short")

    def vector(self, word: str) -> list[float] | None:
        """The word's vector; for a word not in the table, its stem's, or its singular's ("holidays")."""
        for w in (word, help_search.stem(word), word[:-1] if word.endswith("s") else ""):
            i = self.index.get(w) if w else None
            if i is not None:
                scale, d = self.scales[i], self.dims
                return [scale * v for v in self.values[i * d:(i + 1) * d]]
        return None


def _unit(v: list[float]) -> list[float] | None:
    """v scaled to length 1, or None for a vector of zeros (it points nowhere)."""
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else None


class Meaning:
    """The topics' vectors, made from a Table; scores(question) gives each topic's likeness to it (cosine, -1..1),
    or None when none of the question's words is in the table."""

    def __init__(self, topics: list[Topic], table: Table):
        self.table = table
        ix = help_search.index(topics)
        self.ix = ix
        self.top = math.log(1 + (len(topics) + 0.5) / 0.5)  # the weight of a word no topic has
        # stem -> the help's commonest word with it that the table has ("holiday"), for typos put right
        seen: dict[str, dict[str, int]] = {}
        for t in topics:
            for w in help_search.words(" ".join((t.title, t.words, t.text))):
                forms = seen.setdefault(help_search.stem(w), {})
                forms[w] = forms.get(w, 0) + 1
        self.spelled = {}
        for s, forms in seen.items():
            w = next((w for w in sorted(forms, key=lambda w: -forms[w]) if w in table.index), None)
            if w:
                self.spelled[s] = w
        # (the title twice: it says most about what the topic answers; the keyword search weighs it more too)
        self.vectors = [self.vector(" ".join((t.title, t.title, t.words, t.text)), ix) for t in topics]

    def vector(self, text: str, ix=None) -> list[float] | None:
        """The text's vector: its words' vectors, each weighted by how rare it is, added up, unit length. A word
        the table lacks that the keyword search reads as a typo of a help word ("holliday") counts as that word."""
        ix = ix or self.ix
        counts: dict[str, int] = {}
        for w in help_search.words(text):
            counts[w] = counts.get(w, 0) + 1
        acc = [0.0] * self.table.dims
        found = False
        for w, n in counts.items():
            s = help_search.stem(w)
            v = self.table.vector(w)
            if v is None:
                k = ix.known(s)
                if not k or k not in self.spelled:
                    continue
                s, v = k, self.table.vector(self.spelled[k])
            weight = (ix.idf(s) if s in ix.df else self.top) * (1 + math.log(n))
            acc = [a + weight * x for a, x in zip(acc, v)]
            found = True
        return _unit(acc) if found else None

    def scores(self, question: str) -> list[float] | None:
        """Each topic's likeness to the question, in the topics' order (0 for a topic without a vector), or None
        when no word of the question is in the table."""
        q = self.vector(question)
        if q is None:
            return None
        return [sum(a * b for a, b in zip(q, v)) if v else 0.0 for v in self.vectors]


_READY: dict[int, Meaning | None] = {}
_LOCK = threading.Lock()


def load(topics: list[Topic], path: Path = TABLE) -> Meaning | None:
    """Makes (once) and returns the Meaning of these topics; None when the table is missing or unreadable (the
    search then goes by keywords alone)."""
    key = id(topics)
    with _LOCK:
        if key not in _READY:
            try:
                _READY[key] = Meaning(topics, Table(path))
            except Exception:  # (missing, cut short or damaged in any way: a header of the wrong shape raises
                # TypeError, and this runs in prepare()'s thread, where an error would be the crash box each time)
                _READY[key] = None
        return _READY[key]


def ready(topics: list[Topic]) -> Meaning | None:
    """The Meaning of these topics if load() has finished making it, else None (it is never waited for)."""
    return _READY.get(id(topics))


def prepare(topics: list[Topic]) -> None:
    """Starts load() in a background thread (the help window calls this when it opens)."""
    if id(topics) not in _READY:
        threading.Thread(target=_load_ahead, args=(topics,), daemon=True).start()


def _load_ahead(topics: list[Topic]) -> None:
    """load(), after importing rapidfuzz for the keyword search's typo fixing: on a cold disk that takes seconds,
    which the first search with a typo would otherwise spend waiting in the window."""
    try:
        import rapidfuzz.process  # noqa: F401
    except Exception:  # (missing or broken: the search then just forgives no typos, help_search.Index.known)
        pass
    load(topics)
