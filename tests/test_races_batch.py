"""What the user does while Generate all works on its copies of the jobs, and what the window is told when it ends
(MainWindow._run_batch): a tick changed after a run that stopped part way, a firm renamed, the case's details
typed, a read that puts one day's documents with another (also while the batch's preview is open), the window
closed while the preview is made, and a batch that stops with an error after invoices were made. The background
work is held (Held): it runs when the test says, so what happens "meanwhile" is not left to the clock."""
import os
from collections import Counter

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")
from PySide6 import QtCore, QtGui  # noqa: E402

from helpers import pat_settings, transcript_pdf  # noqa: E402


class Held:
    """The window's background work, held: Generate all's fill_jobs (the batch or its preview) is run when the
    test calls run(), so what the test does before then happens while the batch "runs". Other work (a records
    copy...) is left waiting."""

    def __init__(self, window, monkeypatch):
        self.calls: list = []
        monkeypatch.setattr(window.runner, "start", self.start)

    def start(self, fn, *args, on_done=None, on_error=None, on_progress=None, **kw):
        self.calls.append((fn, args, kw, on_done, on_error))

    def batches(self) -> int:
        return sum(1 for c in self.calls if c[0].__name__ == "fill_jobs")

    def run(self, then_fail: bool = False):
        """Runs the first fill_jobs waiting and calls its on_done; then_fail: as if fill_jobs raised once its
        files and invoices were made (on_error)."""
        call = next(c for c in self.calls if c[0].__name__ == "fill_jobs")
        self.calls.remove(call)
        fn, args, kw, on_done, on_error = call
        paths = fn(*args, **kw)
        if then_fail:
            on_error("RuntimeError: something went wrong after the invoices")
        else:
            on_done(paths)


@pytest.fixture
def window(tmp_path, monkeypatch, make_window):
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", lambda self: 0)  # no dialogs waiting for a click
    s = pat_settings()
    s.use_ai = s.open_after = False
    s.output_dir = str(tmp_path / "out")
    s.save_math = "off"
    s.invoice_joint = False  # (each day its own invoices: what each one billed is plain to see)
    return make_window(s)


def wait(win, until, seconds=20):
    import time
    end = time.time() + seconds
    while time.time() < end:
        QtWidgets.QApplication.processEvents()
        if not win.runner._live and until():
            return
        time.sleep(0.01)
    raise AssertionError("timed out")


def counsel(checked=True):
    from minute_filler.models import Attorney
    return Attorney(name="Alex B. Counsel", firm="Counsel & Counsel", checked=checked)


def smith(checked=True):
    from minute_filler.models import Attorney
    return Attorney(name="Dana Smith", firm="Smith Law", checked=checked)


def poe(checked=True):
    from minute_filler.models import Attorney
    return Attorney(name="Sam Poe", firm="Poe Law", checked=checked)


def two_days(window, tmp_path, attorneys=lambda: [counsel(), smith()]):
    """Two days of Roe v. X.Y. (30 and 60 pages), invoices only, each day's attorneys these; the first shown."""
    window.output_boxes["agreement"].setChecked(False)
    window.output_boxes["invoice"].setChecked(True)
    window.add_files([str(transcript_pdf(tmp_path / "a.pdf", pages=30, date="June 3, 2026")),
                      str(transcript_pdf(tmp_path / "b.pdf", pages=60, date="June 4, 2026"))])
    wait(window, lambda: len(window.jobs) == 2 and all(j.docs for j in window.jobs))
    for i in (1, 0):
        window.job_list.setCurrentItem(window.job_list.topLevelItem(i))
        window.case.attorneys = attorneys()
        window._show_attorneys()
    window._refresh_outputs()
    assert window.cur.invoice_pages() == 30
    return window.cur, next(j for j in window.jobs if j is not window.cur)


def told(window, monkeypatch) -> list[str]:
    """The texts of the Batch finished boxes."""
    said: list[str] = []
    monkeypatch.setattr(type(window), "_saved_box", lambda self, title, text, *a, **k: said.append(text))
    return said


def billed(window) -> Counter:
    from minute_filler.deliver import ledger_for
    return Counter(i.bill_to for i in ledger_for(window.s).invoices())


@pytest.mark.usefixtures("split_orders_choose")
def test_a_tick_changed_after_a_run_that_stopped_part_way_doesnt_bill_its_invoices_again(window, tmp_path,
                                                                                         monkeypatch):
    """A day's second invoice couldn't be saved (its first one was), and an attorney was ticked while the batch
    ran: the attorney whose invoice was made went back to the day only when every invoice was, so the next
    Generate all billed it twice."""
    from minute_filler import invoice
    two_days(window, tmp_path, lambda: [counsel(), smith(), poe(checked=False)])
    real, calls = invoice.make_invoice, []

    def flaky(case, atty, *a, **k):
        calls.append(atty.name)
        if len(calls) == 2:  # (the first day's second invoice, once)
            raise PermissionError("the PDF is open in another program")
        return real(case, atty, *a, **k)

    monkeypatch.setattr(invoice, "make_invoice", flaky)
    held = Held(window, monkeypatch)
    window.fill_all_jobs()
    assert window.filling and held.batches() == 1
    window.att.item(2, 0).setCheckState(QtCore.Qt.Checked)  # Sam Poe ticked meanwhile
    assert all("poe law" in j.ticked_keys() for j in window.jobs)
    held.run()
    assert sum(billed(window).values()) == 3  # (one of the four couldn't be saved)
    stopped = next(j for j in window.jobs if j.error)
    assert not stopped.invoiced and not stopped.made and len(stopped.invoiced_keys) == 1
    window.fill_all_jobs()
    held.run()
    assert billed(window) == {"Alex B. Counsel": 2, "Dana Smith": 2, "Sam Poe": 2}


@pytest.mark.usefixtures("split_orders_choose")
def test_a_firm_renamed_while_generate_all_runs_isnt_billed_again_under_its_new_name(window, tmp_path, monkeypatch):
    """The firm typed in Who ordered while the batch ran: the copy's attorneys went back to the day under the old
    name ("smith law"), so the next Generate all billed "smith law group" again."""
    day1, day2 = two_days(window, tmp_path)
    said = told(window, monkeypatch)
    held = Held(window, monkeypatch)
    window.fill_all_jobs()
    window.att.item(1, 2).setText("Smith Law Group")
    assert "smith law group" in day1.ticked_keys()
    held.run()
    assert billed(window) == {"Alex B. Counsel": 2, "Dana Smith": 2}
    # (its files say "Smith Law": made again, its invoices kept as billed)
    assert not day1.made and "Roe" in said[0].split("changed while the files were made")[1]
    window.fill_all_jobs()
    if held.batches():
        held.run()
    assert billed(window) == {"Alex B. Counsel": 2, "Dana Smith": 2}


def test_the_case_typed_while_generate_all_runs_is_made_again(window, tmp_path, monkeypatch):
    """The judge typed while the batch ran: the day was marked made, its files saying the judge as it was, and
    nothing said so."""
    day1, day2 = two_days(window, tmp_path)
    said = told(window, monkeypatch)
    held = Held(window, monkeypatch)
    window.fill_all_jobs()
    window.rows["judge"].choose("Maria T. Lopez")  # (the day shown: the first)
    held.run()
    assert day2.made and day2.invoiced
    assert not day1.made and day1.invoiced  # (its invoice is kept: not billed again)
    note = said[0].split("changed while the files were made")
    assert len(note) == 2 and "Roe" in note[1] and "1 job(s)" in note[0][-12:]


def joined(window, into, other):
    """A read that ends with a document of both days (an e-mail naming them, no pages of its own): batch.group
    puts `other`'s documents with `into`'s, as the window's read does (MainWindow.add_files: self.jobs =
    group(...))."""
    from dataclasses import replace

    from helpers import invoice_text, text_doc
    from minute_filler.batch import Ident, group
    a, b = into.docs[0], other.docs[0]
    mail = text_doc(window.s, invoice_text("Roe v X.Y. Holding", "712345-2021", "6-3-2026"), "e-mail.txt")
    both = replace(mail, ident=Ident(a.ident.index, a.ident.dates | b.ident.dates, a.ident.sides))
    window.jobs = group([both], window.s, window.jobs)
    window._refresh_jobs()
    assert other not in window.jobs and any(d is b for d in into.docs)


def test_a_day_joined_to_another_while_generate_all_runs_is_said(window, tmp_path, monkeypatch):
    """The second day was invoiced by the batch while a read put its documents with the first day (not being
    made): the first day bills them again with its own, and nothing said so."""
    day1, day2 = two_days(window, tmp_path)
    day1.include = False  # (the second day alone is made)
    said = told(window, monkeypatch)
    held = Held(window, monkeypatch)
    window.fill_all_jobs()
    joined(window, day1, day2)
    held.run()
    assert billed(window) == {"Alex B. Counsel": 1, "Dana Smith": 1}
    assert not day1.made and not day1.invoiced
    assert "changed while the files were made" in said[0]
    line = said[0].split("changed while the files were made")[1]
    assert "now has the documents of" in line and "invoiced just now" in line


def test_a_day_joined_to_another_while_the_preview_is_open_is_not_saved(tmp_path, monkeypatch, make_window):
    """Save in Generate all's preview after a read put the second day's documents with the first: the second
    day's copy was still billed (60 pages), and the first day, now with them, billed them again later."""
    from minute_filler.deliver import ledger_for
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", lambda self: 0)
    s = pat_settings()
    s.use_ai = s.open_after = False
    s.output_dir = str(tmp_path / "out")
    s.save_math = "off"
    s.invoice_joint = False
    window = make_window(s, preview=True)
    day1, day2 = two_days(window, tmp_path, lambda: [counsel()])
    held = Held(window, monkeypatch)
    window.fill_all_jobs()  # (the preview)
    joined(window, day1, day2)
    held.run()  # the preview shown, Save (conftest's PreviewDialog.exec): the batch starts
    assert held.batches() == 1
    held.run()
    assert [i.pages for i in ledger_for(window.s).invoices()] == [30]  # the first day as it was copied
    assert not day1.made and not day1.invoiced and day1.invoice_pages() == 90


def test_closing_while_the_preview_is_made_doesnt_start_the_batch(tmp_path, monkeypatch, make_window):
    """The preview ended while "Close anyway?" was on screen: it opened, its Save started the batch, and Yes then
    ended the app with the batch half made. It goes back now; No leaves the window as it was."""
    from minute_filler.gui.preview import PreviewDialog
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", lambda self: 0)
    s = pat_settings()
    s.use_ai = s.open_after = False
    s.output_dir = str(tmp_path / "out")
    s.save_math = "off"
    window = make_window(s, preview=True)
    two_days(window, tmp_path)
    held = Held(window, monkeypatch)
    shown = []
    monkeypatch.setattr(PreviewDialog, "exec", lambda self: shown.append(1) or QtWidgets.QDialog.Accepted)
    window.fill_all_jobs()
    assert window.filling and held.batches() == 1

    def asked(*a):
        held.run()  # the preview ends while the question is open
        return QtWidgets.QMessageBox.No

    monkeypatch.setattr(QtWidgets.QMessageBox, "question", asked)
    e = QtGui.QCloseEvent()
    window.closeEvent(e)
    assert not e.isAccepted() and not shown and held.batches() == 0 and not window.filling
    assert not window._closing  # (No: a preview made later opens)
    window.fill_all_jobs()
    held.run()
    assert shown == [1] and held.batches() == 1


@pytest.mark.usefixtures("split_orders_choose")
def test_a_batch_that_stops_with_an_error_keeps_what_it_invoiced(window, tmp_path, monkeypatch):
    """fill_jobs raised once its invoices were made: nothing was copied back, so the next Generate all billed
    every day again."""
    day1, day2 = two_days(window, tmp_path)
    errors = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", lambda parent, title, text, *a: errors.append(text))
    held = Held(window, monkeypatch)
    window.fill_all_jobs()
    held.run(then_fail=True)
    assert len(errors) == 1 and "went wrong" in errors[0]
    assert billed(window) == {"Alex B. Counsel": 2, "Dana Smith": 2}
    assert day1.invoiced and day2.invoiced and not day1.made and not day2.made
    window.fill_all_jobs()
    held.run()
    assert billed(window) == {"Alex B. Counsel": 2, "Dana Smith": 2}
    assert day1.made and day2.made  # (nothing left to make: done)
