"""Races between processes and threads: a launch that gave up waiting is not taken late too (single.py's "go"), a
launch while the window is closing opens its own window instead of handing its files to one about to go, a model
download is kept from the moment it starts, the log goes on while another copy holds app.log (and a launch that only
hands its files over opens no log), two saves of settings.json never share a .tmp file and a held file is tried
again, a PDF is never written under its final name, two saves under one name never take it both and a failed save
deletes only its own file, and Settings' warnings wait until every setting is in and saved. Socket names are made
up for each test (never the real one); all names are made up."""
import json
import os
import threading
import time
import uuid
from pathlib import Path

import pymupdf
import pytest

from helpers import pat_settings
from minute_filler.gui.single import SingleInstance, hand_over


def fresh_name() -> str:
    return f"YinItAgreementForm-test-{uuid.uuid4().hex}"


def run(qt, ms: int) -> None:
    """Runs the event loop for `ms` (the running copy's part, in this same process)."""
    from PySide6.QtCore import QElapsedTimer
    clock = QElapsedTimer()
    clock.start()
    while clock.elapsed() < ms:
        qt.QApplication.processEvents()
        time.sleep(0.005)


def raw_launch(qt, name: str, line: bytes):
    """A launch as single.send starts one: connected, its line written (and nothing else yet). The pipe takes
    it once the running copy reads (the copy's part: the event loop, run here until then)."""
    from PySide6.QtCore import QElapsedTimer
    from PySide6.QtNetwork import QLocalSocket
    sock = QLocalSocket()
    sock.connectToServer(name)
    assert sock.waitForConnected(2000)
    if line:
        sock.write(line)
        sock.flush()
        clock = QElapsedTimer()
        clock.start()
        while sock.bytesToWrite() and clock.elapsed() < 2000:
            qt.QApplication.processEvents()
        assert not sock.bytesToWrite()
    return sock


# ------------------------------------------------------------------ 1: a launch that gave up is not taken late
def test_a_launch_that_gave_up_waiting_is_not_taken_late(qt, monkeypatch):
    """The running copy was busy past WAIT_MS: the launch gave up, hung up and opened its own window, but its line
    was still in the pipe. When the copy comes back it must not open the same files too (before: it answered "ok"
    to nobody and took them, so they opened in two windows)."""
    import minute_filler.gui.single as single
    monkeypatch.setattr(single, "GO_MS", 300, raising=False)
    name = fresh_name()
    one = SingleInstance(name)
    got: list = []
    one.files_received.connect(got.append)
    try:
        assert one.claim()
        sock = raw_launch(qt, name, json.dumps({"files": ["C:/orders/roe.pdf"]}).encode() + b"\n")
        sock.disconnectFromServer()  # (gave up before the copy's loop ran again)
        run(qt, 1200)
        assert got == []
        assert hand_over(SingleInstance(name), ["C:/orders/poe.pdf"]) is True  # (the next launch still gets in)
        run(qt, 300)
        assert got == [["C:/orders/poe.pdf"]]
    finally:
        one.close()


def test_a_launch_that_never_says_go_is_dropped(qt, monkeypatch):
    """The launch read nothing back (it was giving up just then) and so never says "go": its files are not taken,
    and the copy hangs up on it after GO_MS (before: taken at the "ok")."""
    import minute_filler.gui.single as single
    monkeypatch.setattr(single, "GO_MS", 300, raising=False)
    name = fresh_name()
    one = SingleInstance(name)
    got: list = []
    one.files_received.connect(got.append)
    try:
        assert one.claim()
        sock = raw_launch(qt, name, json.dumps({"files": ["C:/orders/roe.pdf"]}).encode() + b"\n")
        run(qt, 1200)
        assert got == [] and one._launches == []
        assert sock.state() == sock.LocalSocketState.UnconnectedState  # (hung up on)
        sock.abort()
    finally:
        one.close()


def test_a_connection_that_says_nothing_is_dropped(qt):
    """A probe that gave up (connected, said nothing, hung up) is let go of, and the next launch is served."""
    name = fresh_name()
    one = SingleInstance(name)
    got: list = []
    one.files_received.connect(got.append)
    try:
        assert one.claim()
        raw_launch(qt, name, b"").disconnectFromServer()
        run(qt, 300)
        assert got == []
        assert hand_over(SingleInstance(name), []) is True
        run(qt, 300)
        assert got == [[]]
    finally:
        one.close()


# ------------------------------------------------------------------ 2: a launch while the window is closing
def closing_window(qt, name: str, close: bool):
    """A window whose close asks first (as "Still working... Close anyway?"), with a launch handing over a file
    while it asks; close: the answer. Returns the window (its .launch: what hand_over said)."""
    from PySide6.QtCore import Qt

    class Window(qt.QWidget):
        def __init__(self):
            super().__init__()
            self.drops, self.launch = [], None

        def add_files(self, paths):
            self.drops.append(paths)

        def closeEvent(self, e):
            box = qt.QDialog(self)
            box.setWindowModality(Qt.ApplicationModal)
            box.show()
            self.launch = hand_over(SingleInstance(name), ["C:/orders/poe.eml"])  # (a launch while it asks)
            box.close()
            if close:
                e.accept()
            else:
                e.ignore()
    return Window()


def test_a_launch_while_the_window_closes_opens_its_own(qt, monkeypatch):
    """A file handed over while "Close anyway?" is on screen, then Yes: the launch is not answered and opens a
    window of its own, and the copy closing stops listening (before: "ok", and the file went with the window)."""
    import minute_filler.gui.single as single
    from minute_filler.main import _take_launches
    monkeypatch.setattr(single, "WAIT_MS", 1000)
    name = fresh_name()
    one = SingleInstance(name)
    win = closing_window(qt, name, close=True)
    try:
        assert one.claim()
        _take_launches(qt.QApplication.instance(), win, one, [])
        win.show()
        win.close()
        run(qt, 800)
        assert win.launch is False and win.drops == []
        assert one.server is None  # (the next launch is a first copy: it doesn't wait for one going)
    finally:
        one.close()


def test_a_launch_while_a_close_is_called_off_is_taken(qt, monkeypatch):
    """The same with No: the window stays, and the launch waiting is answered and its file dropped as usual."""
    from PySide6.QtCore import QTimer
    import minute_filler.gui.single as single
    from minute_filler.main import _take_launches
    monkeypatch.setattr(single, "WAIT_MS", 3000)
    name = fresh_name()
    one = SingleInstance(name)
    win = closing_window(qt, name, close=False)
    try:
        assert one.claim()
        _take_launches(qt.QApplication.instance(), win, one, [])
        win.show()
        QTimer.singleShot(300, lambda: [w.close() for w in qt.QApplication.topLevelWidgets()
                                        if isinstance(w, qt.QDialog) and w.isVisible()])
        win.close()
        run(qt, 800)
        assert win.launch is True and win.isVisible()
        assert win.drops == [["C:/orders/poe.eml"]]
        assert one.server is not None
    finally:
        win.hide()
        one.close()


# ------------------------------------------------------------------ 3: a model download kept from its start
def test_a_model_download_is_kept_from_the_moment_it_starts(qt, monkeypatch):
    """The app can quit with the help dialog still open (Windows logging off): the download's thread must be kept
    already, not only once the dialog is closed (else Qt aborts, destroying a thread that runs); a finished one
    is let go of at the next download."""
    from minute_filler.gui import dialogs
    monkeypatch.setattr(dialogs, "_BACKGROUND", [])
    release = threading.Event()
    monkeypatch.setattr(dialogs._PullThread, "run", lambda self: release.wait(10))
    dlg = dialogs.OllamaHelpDialog("llama-test", "")
    dlg._pull()
    first = dlg.thread
    try:
        assert first in dialogs._BACKGROUND and first.isRunning()
    finally:
        release.set()
        assert first.wait(5000)
    dlg._pull()
    second = dlg.thread
    assert second.wait(5000)
    assert first not in dialogs._BACKGROUND and second in dialogs._BACKGROUND


# ------------------------------------------------------------------ 4: the log while another copy holds it
@pytest.mark.skipif(os.name != "nt", reason="only Windows refuses to rename a file open elsewhere")
def test_the_log_goes_on_while_another_copy_holds_it():
    """Another copy of the app has app.log open (Windows won't rename it): the records go on into it, and the older
    copies stay (before: app.log.1 moved over app.log.2, the oldest lost, and every record dropped). Once the other
    copy is gone the rollover works again."""
    from minute_filler import log
    log.shutdown()
    log.setup()
    try:
        path = log.log_path()
        older, oldest = path.with_name("app.log.1"), path.with_name("app.log.2")
        older.write_text("the older copy\n", encoding="utf-8")
        oldest.write_text("the oldest copy\n", encoding="utf-8")
        log._handler.maxBytes = 400
        with open(path, "a", encoding="utf-8"):  # (the other copy's)
            for i in range(20):
                log.log.info("record %d while both run", i)
            log._handler.flush()
            text = path.read_text(encoding="utf-8")
        assert all(f"record {i} while both run" in text for i in range(20))
        assert older.read_text(encoding="utf-8") == "the older copy\n"
        assert oldest.read_text(encoding="utf-8") == "the oldest copy\n"
        log._handler._retry_at = 0.0  # (tried again: RETRY_S later)
        log.log.info("the other copy has gone")
        log._handler.flush()
        assert "record 19 while both run" in older.read_text(encoding="utf-8")
        assert oldest.read_text(encoding="utf-8") == "the older copy\n"
        assert "the other copy has gone" in path.read_text(encoding="utf-8")
    finally:
        log.shutdown()


def test_a_launch_that_hands_its_files_over_opens_no_log(qt, monkeypatch, tmp_path):
    """main() with a copy running: the files are handed over and no log file is opened (it is the other copy's),
    while crashes are still caught."""
    import sys
    from minute_filler import log
    from minute_filler.main import main
    from minute_filler.settings import settings_dir
    name = fresh_name()
    monkeypatch.setattr("minute_filler.gui.single.socket_name", lambda app="YinItAgreementForm": name)
    order = tmp_path / "Roe v Poe.pdf"
    order.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(sys, "argv", ["YinItAgreementForm", str(order)])
    log.shutdown()
    one = SingleInstance(name)
    try:
        assert one.claim()
        assert main() == 0
        assert log._handler is None and not (settings_dir() / "logs" / "app.log").exists()
        assert sys.excepthook is log._excepthook
    finally:
        one.close()
        log.shutdown()


# ------------------------------------------------------------------ 5: settings.json saved by two at once
def test_a_save_leaves_another_copys_tmp_file_alone(monkeypatch):
    """Another copy is writing its settings.tmp (open): this save neither writes into it nor fails on it."""
    s = pat_settings()
    s.save()
    other = s.path.with_name("settings.tmp")
    with open(other, "w", encoding="utf-8") as f:
        f.write("the other copy's, half written")
        f.flush()
        s.profile.name = "Dana Steno"
        s.save()
    assert json.loads(s.path.read_text(encoding="utf-8"))["profile"]["name"] == "Dana Steno"
    assert other.read_text(encoding="utf-8") == "the other copy's, half written"
    assert [p.name for p in s.path.parent.glob("*.tmp")] == ["settings.tmp"]


def test_a_settings_file_held_a_moment_is_tried_again(monkeypatch):
    """Dropbox or an antivirus holds settings.json for a moment: the save is tried again and goes through."""
    s = pat_settings()
    real, tries = os.replace, []

    def held(src, dst):
        tries.append(1)
        if len(tries) < 3:
            raise PermissionError(13, "The process cannot access the file", str(dst))
        return real(src, dst)
    monkeypatch.setattr(os, "replace", held)
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    s.save()
    assert len(tries) == 3 and json.loads(s.path.read_text(encoding="utf-8"))["profile"]["name"] == "Pat Reporter"


def test_a_settings_save_that_fails_leaves_no_tmp_file(monkeypatch):
    s = pat_settings()

    def held(src, dst):
        raise PermissionError(13, "The process cannot access the file", str(dst))
    monkeypatch.setattr(os, "replace", held)
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    with pytest.raises(PermissionError):
        s.save()
    assert not list(s.path.parent.glob("*.tmp"))


# ------------------------------------------------------------------ 6: PDFs saved beside another copy
def blank(text: str) -> pymupdf.Document:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text)
    return doc


def test_a_pdf_is_never_written_under_its_final_name(tmp_path, monkeypatch):
    """The PDF is written to a file of its own in the same folder and then put in place: the app killed halfway
    leaves no half-written PDF under the name."""
    from minute_filler.pdfout import save_output
    real, written = pymupdf.Document.save, []

    def save(self, path, *a, **k):
        written.append(Path(path))
        return real(self, path, *a, **k)
    monkeypatch.setattr(pymupdf.Document, "save", save)
    out = save_output(blank("Jane Roe v. Sam Poe"), "agreement", tmp_path / "Roe v Poe.pdf")
    assert out == tmp_path / "Roe v Poe.pdf"
    assert len(written) == 1 and written[0] != out and written[0].parent == tmp_path
    with pymupdf.open(out) as doc:
        assert "Jane Roe" in doc[0].get_text()
    assert [p.name for p in tmp_path.iterdir()] == ["Roe v Poe.pdf"]


def test_two_saves_at_once_never_take_one_name(tmp_path, monkeypatch):
    """Two copies (here two threads) save under one name at the same moment: each gets a name of its own (before:
    both looked, both found it free, and one PDF was written over the other)."""
    from minute_filler.pdfout import save_output
    real = pymupdf.Document.save

    def slow(self, *a, **k):
        time.sleep(0.3)
        return real(self, *a, **k)
    monkeypatch.setattr(pymupdf.Document, "save", slow)
    docs = [blank("the first copy's"), blank("the second copy's")]
    made: list = []
    threads = [threading.Thread(target=lambda d=d: made.append(save_output(d, "agreement", tmp_path / "Roe.pdf")))
               for d in docs]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert sorted(p.name for p in made) == ["Roe (2).pdf", "Roe.pdf"]
    texts = set()
    for p in made:
        with pymupdf.open(p) as doc:
            texts.add(doc[0].get_text().strip())
    assert texts == {"the first copy's", "the second copy's"}


def test_a_failed_save_deletes_only_its_own_file(tmp_path, monkeypatch):
    """The disk fills while another copy saves an invoice under the same name: the half-written file goes, the
    other copy's invoice stays (before: this save deleted the file under the name, the other copy's)."""
    from minute_filler.pdfout import save_output
    target = tmp_path / "Invoice 2026-0001.pdf"

    def other_copy_then_full(self, path, *a, **k):
        for q in (target, target.with_name("Invoice 2026-0001 (2).pdf")):  # (the first name free, as it takes one)
            try:
                with open(q, "xb") as f:
                    f.write(b"%PDF-1.7 the other copy's invoice")
                break
            except FileExistsError:
                continue
        Path(path).write_bytes(b"%PDF-1.7 half of it")
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(pymupdf.Document, "save", other_copy_then_full)
    with pytest.raises(OSError, match="No space left"):
        save_output(blank("Invoice"), "invoice", target)
    assert [p.read_bytes() for p in tmp_path.iterdir()] == [b"%PDF-1.7 the other copy's invoice"]


def test_a_pdf_name_held_a_moment_is_tried_again(tmp_path, monkeypatch):
    """Dropbox or an antivirus holds the new file's name a moment: it is put in place on a later try."""
    from minute_filler.pdfout import save_output
    real, tries = os.replace, []

    def held(src, dst):
        tries.append(1)
        if len(tries) < 3:
            raise PermissionError(13, "The process cannot access the file", str(dst))
        return real(src, dst)
    monkeypatch.setattr(os, "replace", held)
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    out = save_output(blank("Jane Roe"), "agreement", tmp_path / "Roe.pdf")
    with pymupdf.open(out) as doc:
        assert "Jane Roe" in doc[0].get_text()
    assert [p.name for p in tmp_path.iterdir()] == ["Roe.pdf"]


# ------------------------------------------------------------------ 7: Settings' warnings after everything is in
def test_settings_warnings_wait_until_everything_is_saved(qt, monkeypatch, tmp_path):
    """A reporter line that can't be read and a signature that can't be stored: each is said, but only once every
    setting is in the Settings and on disk (before: the boxes came halfway, with the window's work going on
    meanwhile on settings half changed)."""
    from minute_filler.gui.dialogs import SettingsDialog
    s = pat_settings()
    dlg = SettingsDialog(s)
    dlg.r_names.setPlainText("ds = Dana\nnonsense\n")
    dlg._sig_new = str(tmp_path / "not there.png")  # (gone: it can't be stored)
    want = dlg.a_timeout.value() + 7
    dlg.a_timeout.setValue(want)  # (the last setting written)
    seen = []

    def warning(parent, title, text, *a, **k):
        disk = json.loads(s.path.read_text(encoding="utf-8")).get("ai_timeout") if s.path.exists() else None
        seen.append((title, s.ai_timeout, disk))
        return 0
    monkeypatch.setattr(qt.QMessageBox, "warning", warning)
    dlg.accept()
    assert [t for t, _, _ in seen] == ["Signature", "Reporters"]
    assert all(mem == want and disk == want for _, mem, disk in seen)
    assert s.reporter_names() == {"ds": "Dana"}
