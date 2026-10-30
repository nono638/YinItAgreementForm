"""A small log file to help with problem reports: %APPDATA%\\YinItAgreementForm\\logs\\app.log

It records what the program did and what went wrong (versions, file types, crashes with their
tracebacks), never what the documents said. Anything that could come from a document - file
names, e-mail addresses, index numbers, long digit strings - is removed by `scrub` before it is
written, and nothing is sent anywhere. The file stays under about 3 MB (1 MB, plus two older copies; it can
grow past 1 MB for a while when two copies of the app write it at once: _SharedFile).
"""
from __future__ import annotations

import logging
import os
import platform
import re
import sys
import threading
import time
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable

from . import __version__
from .settings import settings_dir

NAME = "yin"
log = logging.getLogger(NAME)
_handler: RotatingFileHandler | None = None
_hooked = False  # setup() has set the crash hooks (shutdown() puts them back)
on_crash: Callable[[str], None] | None = None  # the window sets this to tell the user

_FILES = r"pdf|docx?|txt|eml|msg|html?|jpe?g|png|gif|bmp|tiff?|webp|heic|heif|csv|md|xlsx|xlsm|xls"
# In this order: a full path to a file keeps only its type, then other paths go, then a bare file name
# (which is often the case name: "Jane Roe v. Sam Poe.pdf" -> "<file.pdf>"), then e-mail addresses,
# index and other long numbers, and phone numbers.
_SCRUBS = [
    (re.compile(rf"[A-Za-z]:\\[^\"'<>|\n]*?\.({_FILES})\b", re.I), lambda m: f"<file.{m[1].lower()}>"),
    (re.compile(r"[A-Za-z]:\\[^\s\"'<>|]+"), "<path>"),
    (re.compile(rf"[\w .,'()&-]{{1,60}}\.({_FILES})\b", re.I), lambda m: f"<file.{m[1].lower()}>"),
    (re.compile(r"\S+@\S+\.\w+"), "<email>"),
    (re.compile(r"\d{5,}(?:[-/]\d{2,4})?"), "#"),
    (re.compile(r"\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}"), "<phone>"),
]


def scrub(text: object, limit: int = 300) -> str:
    """The text with anything that could be case or personal data taken out, and cut short."""
    s = str(text).replace("\r", " ")
    for pattern, repl in _SCRUBS:
        s = pattern.sub(repl, s)
    return s if len(s) <= limit else s[:limit] + "..."


def describe(exc: BaseException) -> str:
    """An error as 'ValueError: ...', scrubbed, for the log and for messages to the user."""
    return scrub(f"{type(exc).__name__}: {exc}")


class _Formatter(logging.Formatter):
    """Writes tracebacks short and private: file, line and function only, no folders (a folder can name
    the user or a case)."""
    def formatException(self, ei) -> str:
        """Where it happened (file, line, function: no source text, no folders), then the scrubbed message."""
        etype, exc, tb = ei
        frames = [f"  {Path(f.filename).name}:{f.lineno} in {f.name}" for f in traceback.extract_tb(tb)]
        return "Traceback:\n" + "\n".join(frames) + "\n" + describe(exc)


def log_dir() -> Path:
    """The logs folder in the settings folder, created when missing."""
    d = settings_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_path() -> Path:
    """The current log file (older copies sit next to it as app.log.1 and app.log.2)."""
    return log_dir() / "app.log"


def windows_version() -> str:
    """'Windows 10.0 build 26200, AMD64'; on another system, whatever platform.platform() says."""
    try:
        v = sys.getwindowsversion()
        return f"Windows {v.major}.{v.minor} build {v.build}, {platform.machine()}"
    except AttributeError:
        return platform.platform()


class _SharedFile(RotatingFileHandler):
    """The log file, which another copy of the app may have open: a launch that couldn't reach the copy open
    (hung) runs on its own, and Windows can't rename a file open elsewhere. RotatingFileHandler's rollover would
    then fail after moving app.log.1 over app.log.2 (the oldest copy lost), and drop the record, and every record
    after it, as long as both run. Here app.log is moved aside first, before anything else is touched: when that
    fails nothing has moved, the file is opened again and the record appended (it grows past maxBytes for a
    while), and the rollover is tried again RETRY_S later."""
    RETRY_S = 60.0
    _retry_at = 0.0  # (time.monotonic(): no rollover tried before then)

    def shouldRollover(self, record) -> bool:
        if time.monotonic() < self._retry_at:
            return False
        return bool(super().shouldRollover(record))

    def doRollover(self) -> None:
        """app.log -> app.log.1 -> app.log.2 (the oldest goes), or, when app.log can't be moved, on as it is."""
        if self.stream:
            self.stream.close()
            self.stream = None
        base = self.baseFilename
        aside = base + ".rotating"
        try:
            os.replace(base, aside)  # (the one step another copy's open file stops: first, so it loses nothing)
        except FileNotFoundError:
            aside = ""
        except OSError:
            self._retry_at = time.monotonic() + self.RETRY_S
            self.stream = self._open()
            return
        for i in range(self.backupCount - 1, 0, -1):
            try:
                if os.path.exists(f"{base}.{i}"):
                    os.replace(f"{base}.{i}", f"{base}.{i + 1}")
            except OSError:  # (an older copy held open: it stays, and so does the one it would have made way for)
                pass
        if aside:
            try:
                if os.path.exists(f"{base}.1"):  # (it couldn't make way: app.log goes back, rather than over it)
                    os.replace(aside, base)
                    self._retry_at = time.monotonic() + self.RETRY_S
                else:
                    os.replace(aside, f"{base}.1")
            except OSError:
                pass
        self.stream = self._open()


def setup(file: bool = True) -> None:
    """Records crashes that nothing else catches and, with `file`, starts the log file (each once). main() catches
    crashes from the start but opens the file only once it knows this launch runs (one that hands its files to
    the copy open never opens it)."""
    global _handler, _hooked
    log.setLevel(logging.INFO)
    log.propagate = False
    if not _hooked:
        # the hooks first: a crash is told to the user (on_crash) even when there is no log file to write it to
        sys.excepthook = _excepthook
        threading.excepthook = lambda a: _excepthook(a.exc_type, a.exc_value, a.exc_traceback)
        _hooked = True
    if not file or _handler is not None:
        return
    try:
        _handler = _SharedFile(log_path(), maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    except OSError:  # a read-only profile: run without a log rather than not at all
        _handler = None
        log.addHandler(logging.NullHandler())
        return
    _handler.setFormatter(_Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S"))
    log.addHandler(_handler)
    frozen = "installed app" if getattr(sys, "frozen", False) else "from source"
    log.info("started: version %s (%s), %s, Python %s", __version__, frozen, windows_version(),
             platform.python_version())


def shutdown() -> None:
    """Closes the file and puts things back (tests use this)."""
    global _handler, _hooked
    if _handler is not None:
        log.removeHandler(_handler)
        _handler.close()
        _handler = None
    _hooked = False
    sys.excepthook = sys.__excepthook__
    threading.excepthook = threading.__excepthook__


def _excepthook(etype, exc, tb) -> None:
    """Logs an error nothing caught (in any thread) and tells the window through on_crash. Ctrl+C and
    sys.exit() are not errors."""
    if issubclass(etype, (KeyboardInterrupt, SystemExit)):
        return
    log.error("unexpected error", exc_info=(etype, exc, tb))
    if on_crash:
        try:
            on_crash(describe(exc))
        except Exception:
            pass


def error(what: str, exc: BaseException) -> None:
    """Records a failure the program handled itself (a message box was shown, the job went on). `what` is
    scrubbed too: a message may name a file, and a file's name is often the case's."""
    log.error("%s", scrub(what), exc_info=(type(exc), exc, exc.__traceback__))


def recent(lines: int = 60) -> str:
    """The last `lines` lines of the log, or "(no log yet)"."""
    try:
        text = log_path().read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "(no log yet)"
    return "\n".join(text[-lines:])


def diagnostics(settings=None) -> str:
    """Text for a problem report: versions, the machine, a few settings and the recent log."""
    from .ingest import ocr_available
    out = [f"YinItAgreementForm {__version__} ({'installed app' if getattr(sys, 'frozen', False) else 'from source'})",
           windows_version(), f"Python {platform.python_version()}",
           f"Windows text recognition (photos, scans): {'available' if ocr_available() else 'NOT available'}"]
    if settings is not None:
        out.append(f"Form: {settings.form_choice}; AI helper: {'on' if settings.use_ai else 'off'}; "
                   f"instructions page: {settings.include_instructions}; flatten: {settings.flatten}")
    out += ["", f"--- recent log ({log_path()}) ---", recent()]
    return "\n".join(out)
