"""Makes the help search's word table, minute_filler/data/help_words.bin, from EmbeddingGemma 2.

The app can't carry the model (174 MB and more, every update), so its sense of meaning is worked out here once: the
model gives a vector for each of the 30,000 commonest whole English words of its own vocabulary, plus every word of
the help (help_topics), and the app looks them up (help_meaning). Run it again only when the help gains many new
words or the model changes:

    .venv\\Scripts\\python tools\\meaning\\build_table.py                   the table the app uses
    .venv\\Scripts\\python tools\\meaning\\build_table.py --top 0 --prompt document --out x.bin
                                                                    a small trial table (help words only)

Options: --top N (words of the model's vocabulary, default 30000), --dims D (default 256), --prompt
none|query|document (default query), --out FILE.

How it runs:
- the model needs torch and sentence-transformers, which must never reach .venv (PyInstaller would bundle them):
  like tools/mutate.py, this installs tools/meaning/requirements.txt into an environment of its own,
  %LOCALAPPDATA%\\YinItMeaning\\venv (again when that file changes), and runs itself there. The model is downloaded
  to the Hugging Face cache the first time (about 1 GB), at the revision pinned in REVISION.
- the words are the model's own (its tokenizer's whole lower-case words, in its order, which is roughly how common
  they are), so no word list under another licence is needed. Each is embedded on its own (with the model's prompt
  for --prompt), the vectors are centred (all words share a common direction that says nothing), cut to --dims by
  PCA, made unit length and stored as int8 with a scale per word (help_meaning describes the file).
- the model is Apache 2.0 (Google, EmbeddingGemma 2): data/help_words.LICENSE.txt says so beside the table."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
REQUIREMENTS = Path(__file__).with_name("requirements.txt")
VENV = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "YinItMeaning" / "venv"
MODEL = "google/embeddinggemma-2"
REVISION = "914f7f89142e33e77833254d9c9b90c3cef7303b"  # 2026-10-06; change only together with a new table
OUT = ROOT / "minute_filler" / "data" / "help_words.bin"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _base_found(venv: Path) -> bool:
    """Whether the Python an environment was made from (pyvenv.cfg's home) is still there."""
    try:
        cfg = (venv / "pyvenv.cfg").read_text(encoding="utf-8")
    except OSError:
        return False
    home = next((v.strip() for k, _, v in (l.partition("=") for l in cfg.splitlines()) if k.strip() == "home"), "")
    return bool(home) and (Path(home) / "python.exe").is_file()


def ensure_env() -> Path:
    """The model's own environment (its python.exe), made from requirements.txt the first time and again when that
    file changes."""
    py = VENV / "Scripts" / "python.exe"
    want = _sha(REQUIREMENTS)
    marker = VENV / "requirements.sha256"
    if py.exists() and not _base_found(VENV):
        shutil.rmtree(VENV)
    if py.exists() and marker.exists() and marker.read_text() == want:
        return py
    print(f"Installing torch and sentence-transformers (requirements.txt) in {VENV} ...", flush=True)
    if not py.exists():
        subprocess.run([str(APP_PYTHON), "-m", "venv", str(VENV)], check=True)
    subprocess.run([str(py), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", str(REQUIREMENTS)],
                   check=True)
    marker.write_text(want)
    return py


def help_words() -> set[str]:
    """Every word of the help topics (help_search.words), lower case."""
    sys.path.insert(0, str(ROOT))
    from minute_filler.help_search import words
    from minute_filler.help_topics import TOPICS
    return {w for t in TOPICS for w in words(" ".join((t.title, t.words, t.text))) if w.isalpha()}


def vocabulary(tokenizer, top: int) -> list[str]:
    """The first `top` whole lower-case words of the model's vocabulary ("▁holiday" -> "holiday"), in its order."""
    out, seen = [], set()
    for piece in tokenizer.convert_ids_to_tokens(list(range(len(tokenizer)))):
        if len(out) >= top:
            break
        if piece and piece[0] == "▁" and re.fullmatch(r"[a-z]{2,}", piece[1:]) and piece[1:] not in seen:
            seen.add(piece[1:])
            out.append(piece[1:])
    return out


def build(top: int, dims: int, prompt: str, out: Path) -> None:
    """Embeds the words, centres them, cuts them to `dims` by PCA and writes the table to `out`."""
    import torch
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL, revision=REVISION, device="cpu")
    words = vocabulary(model.tokenizer, top)
    extra = sorted(help_words() - set(words))
    words += extra
    print(f"{len(words)} words ({len(extra)} from the help not among the model's first {top})", flush=True)
    vecs = model.encode(words, prompt_name=None if prompt == "none" else prompt, batch_size=256,
                        convert_to_tensor=True, normalize_embeddings=True, show_progress_bar=True).float()
    vecs = vecs - vecs.mean(dim=0, keepdim=True)
    _, _, v = torch.linalg.svd(vecs, full_matrices=False)
    vecs = vecs @ v[:dims].T
    vecs = vecs / vecs.norm(dim=1, keepdim=True).clamp_min(1e-12)
    scales = vecs.abs().max(dim=1).values.clamp_min(1e-12) / 127
    q = torch.round(vecs / scales[:, None]).clamp(-127, 127).to(torch.int8)
    blob = "\n".join(words).encode("utf-8")
    header = {"model": MODEL, "revision": REVISION, "dims": dims, "count": len(words), "prompt": prompt,
              "top": top, "words_bytes": len(blob)}
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        f.write(b"YINW1\n" + json.dumps(header).encode() + b"\n" + blob)
        f.write(scales.numpy().astype("<f4").tobytes())
        f.write(q.numpy().tobytes())
    print(f"Wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")


def main(argv: list[str]) -> int:
    """Reads the options; outside the model's environment, runs this script again there (with --inside), where it
    builds the table. 0 when done, 2 for options it can't read."""
    args = dict(top=30000, dims=256, prompt="query", out=str(OUT))
    rest = list(argv)
    inside = "--inside" in rest
    if inside:
        rest.remove("--inside")
    for i in range(0, len(rest), 2):
        key = rest[i].lstrip("-")
        if key not in args or i + 1 >= len(rest):
            print(__doc__)
            return 2
        args[key] = rest[i + 1]
    if args["prompt"] not in ("none", "query", "document"):
        print("--prompt is none, query or document")
        return 2
    if not inside:
        py = ensure_env()
        return subprocess.run([str(py), __file__, "--inside", *argv]).returncode
    isolate()
    build(int(args["top"]), int(args["dims"]), args["prompt"], Path(args["out"]))
    return 0


def isolate() -> None:
    """Points APPDATA, USERPROFILE and HOME at an empty folder before minute_filler is imported, as every script
    importing it does (so nothing can reach the user's records), keeping the Hugging Face cache where it is."""
    os.environ.setdefault("HF_HOME", str(Path.home() / ".cache" / "huggingface"))
    home = tempfile.mkdtemp()
    for key in ("APPDATA", "USERPROFILE", "HOME"):
        os.environ[key] = home


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
