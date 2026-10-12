"""How well the help search finds the right topic: the questions of tests/help_questions.py, each with the topics
that answer it, run through the search in several ways, and the share found first (top 1) and among the first three
(top 3) printed for each:

- keywords: help_search alone (words, synonyms, typos);
- keywords + table: with help_meaning's word table (what the app does);
- table alone: the word table's ranking by itself;
- keywords + full model, full model alone (--full): EmbeddingGemma 2 itself on each question, to see what bundling
  the whole model would add. This runs in the model's environment (build_table.py makes it).

    .venv\\Scripts\\python tools\\meaning\\score.py [--full] [--table FILE] [--misses] [--sweep]

--misses lists the questions the app's search gets wrong; --sweep tries other weights for the fusion of the two
rankings (help_search.FUSION_K, MEANING_WEIGHT)."""
import importlib.util
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import build_table  # noqa: E402  (the model's environment, its name and revision, isolate())


def questions() -> list[tuple[str, tuple[str, ...]]]:
    """QUESTIONS of tests/help_questions.py, loaded from its file (tests is not a package)."""
    spec =importlib.util.spec_from_file_location("help_questions", ROOT / "tests" / "help_questions.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.QUESTIONS


def rate(rank, qs) -> tuple[float, float, list]:
    """(top-1 share, top-3 share, misses: (question, wanted, got the first 3)) of a ranking function."""
    one = three = 0
    misses = []
    for q, ok in qs:
        got = rank(q)
        one += bool(got) and got[0] in ok
        if any(g in ok for g in got[:3]):
            three += 1
        else:
            misses.append((q, ok, got[:3]))
    return one / len(qs), three / len(qs), misses


class FullModel:
    """EmbeddingGemma 2 itself, as a help_meaning.Meaning: each topic embedded as a document, each question as a
    query."""

    def __init__(self, topics):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(build_table.MODEL, revision=build_table.REVISION, device="cpu")
        docs = [f"title: {t.title} | text: {t.words}. {t.text}" for t in topics]
        self.docs = self.model.encode(docs, normalize_embeddings=True, convert_to_tensor=True)
        self.seen: dict[str, list[float]] = {}  # (--sweep asks about each question many times)

    def scores(self, question):
        if question not in self.seen:
            q = self.model.encode([question], prompt_name="query", normalize_embeddings=True,
                                  convert_to_tensor=True)
            self.seen[question] = (self.docs @ q[0]).tolist()
        return self.seen[question]


def main(argv: list[str]) -> int:
    """Prints the scores (and the misses or the sweep, when asked). With --full, outside the model's environment,
    runs this script again there (with --inside)."""
    full, misses, sweep ="--full" in argv, "--misses" in argv, "--sweep" in argv
    table_path = Path(argv[argv.index("--table") + 1]) if "--table" in argv else None
    if full and "--inside" not in argv:
        py = build_table.ensure_env()
        return subprocess.run([str(py), __file__, "--inside", *argv]).returncode
    build_table.isolate()
    sys.path.insert(0, str(ROOT))
    from minute_filler import help_meaning, help_search
    from minute_filler.help_topics import TOPICS

    qs = questions()
    path = table_path or help_meaning.TABLE
    table = help_meaning.Table(path) if path.exists() else None
    meaning = help_meaning.Meaning(TOPICS, table) if table else False
    ids = [t.id for t in TOPICS]

    def fused(m):
        return lambda q: [h.topic.id for h in help_search.search(q, meaning=m)]

    def alone(m):
        def rank(q):
            s = m.scores(q)
            return [] if s is None else [ids[i] for i in sorted(range(len(ids)), key=lambda i: -s[i])]
        return rank

    ways = [("keywords", fused(False))]
    if meaning:
        ways += [("keywords + table", fused(meaning)), ("table alone", alone(meaning))]
    if full:
        model = FullModel(TOPICS)
        ways += [("keywords + full model", fused(model)), ("full model alone", alone(model))]
    print(f"{len(qs)} questions; " + (f"table {table.header.get('count')} words, {table.dims} dims, prompt "
                                      f"{table.header.get('prompt')}" if table else f"no table ({path.name})"))
    for name, rank in ways:
        one, three, _ = rate(rank, qs)
        print(f"  {name:24s} top 1: {one:5.1%}   top 3: {three:5.1%}")
    if sweep:
        kept = help_search.FUSION_K, help_search.MEANING_WEIGHT  # (put back after, for --misses)
        for name, m in ([("table", meaning)] if meaning else []) + ([("full model", model)] if full else []):
            print(f"\nSweep, keywords + {name} (FUSION_K, MEANING_WEIGHT -> top 1, top 3):")
            for k in (5, 10, 20, 60):
                for w in (0.3, 0.5, 0.6, 0.8, 1.0, 1.5):
                    help_search.FUSION_K, help_search.MEANING_WEIGHT = k, w
                    one, three, _ = rate(fused(m), qs)
                    print(f"  {k:3d} {w:4.1f} -> {one:5.1%} {three:5.1%}")
        help_search.FUSION_K, help_search.MEANING_WEIGHT = kept
    if misses:
        _, _, missed = rate(fused(meaning), qs)
        print(f"\nMissed by {'keywords + table' if meaning else 'keywords'} ({len(missed)}):")
        for q, ok, got in missed:
            print(f"  {q!r}: wanted {', '.join(ok)}; got {', '.join(got)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
