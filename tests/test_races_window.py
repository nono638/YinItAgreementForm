"""Races in the window: background work (an AI answer, a read ending) that finishes while a box is open, and
the window's answer that must then go to the day as it is now. Generate's preview: a firm ticked meanwhile is
billed later (the day is not marked invoiced for it). Peripherals..., Customize... and Whose pages...: a read that
put the day's documents with another day gives that day the answer (or a note says it was dropped). Open this job
again asks while a document is still being read. Correct where this take ends...: the "Are you sure?" box is the
day's that holds the transcript now. An older read of the records ending last doesn't put back older
completions. A tick spread from another day of the trial keeps a name being typed in Who ordered. Pat Reporter
("pr") is the user, Dana Smith ("ds") another reporter; all names are made up."""
import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from minute_filler.batch import Job  # noqa: E402

from helpers import pat_settings, transcript_pdf  # noqa: E402
from test_gui_batch import wait  # noqa: E402

PR, DS = "pr", "ds"


def settings(tmp_path):
    s = pat_settings(initials=PR)
    s.use_ai = s.open_after = False
    s.welcomed = True
    s.output_dir, s.records_dir = str(tmp_path / "out"), str(tmp_path / "records")
    return s


@pytest.fixture
def previewing(tmp_path, monkeypatch, make_window, qt):
    """A window with the preview on and a 12-page transcript of Jane Roe v. X.Y. Holding Corporation read, its
    first firm ticked; the Saved box's text is kept in win.said."""
    monkeypatch.setattr(qt.QMessageBox, "exec", lambda self: 0)
    s = settings(tmp_path)
    s.outputs = ["agreement", "invoice"]
    win = make_window(s, preview=True)
    win.add_files([str(transcript_pdf(tmp_path / "Transcript.pdf", 12))])
    wait(win, lambda: win.cur.docs)
    first = win.cur.case.attorneys[0]
    for a in win.cur.case.attorneys:
        a.checked = a is first
    win.cur.att_touched = True
    win._show_case()
    win.said = []
    monkeypatch.setattr(win, "_saved_box", lambda title, text, *a, **k: win.said.append(text))
    return win


def other_firm(job):
    """An attorney of the job of another firm than the one ticked (another Attorney.key(): another invoice)."""
    first = job.case.attorneys[0]
    return next(a for a in job.case.attorneys if a.key() and a.key() != first.key() and not a.is_placeholder())


# ------------------------------------------------------------------ Generate: what changed while the preview was up
def test_a_firm_ticked_while_the_preview_is_open_is_billed_later(previewing, monkeypatch):
    """An AI answer ticks another firm while the preview is open: the files made bill only the first firm, so the
    day is not marked invoiced (Generate all would never bill the second); the first firm's invoice is kept as made
    (not billed again), and the Saved box says the day changed."""
    from minute_filler.gui.preview import PreviewDialog
    job = previewing.cur
    first, second = job.case.attorneys[0].key(), other_firm(job).key()

    def ticked_meanwhile(dlg):  # (by key: Generate read the table back into new Attorney rows first)
        next(a for a in job.case.attorneys if a.key() == second).checked = True
        return PreviewDialog.Accepted
    monkeypatch.setattr(PreviewDialog, "exec", ticked_meanwhile)
    previewing.fill()
    assert job.saved and not job.invoiced and not job.made
    assert job.billed_keys() == [first]  # (the second firm's is still to make)
    assert "This day changed while the files were made" in previewing.said[-1]


def test_another_speed_chosen_while_the_preview_is_open_is_billed_later(previewing, monkeypatch):
    """The speed of the forms chosen again while the preview is open (case "delivery"): the invoice made is at the
    old speed, so the day isn't marked invoiced either."""
    from minute_filler.gui.preview import PreviewDialog
    job = previewing.cur
    was = job.case.get("delivery")
    other = next(sp.name for sp in previewing.s.offered_speeds() if sp.name != was)

    def faster_meanwhile(dlg):
        job.case.set("delivery", other)
        return PreviewDialog.Accepted
    monkeypatch.setattr(PreviewDialog, "exec", faster_meanwhile)
    previewing.fill()
    assert job.saved and not job.invoiced and not job.made
    assert "This day changed while the files were made" in previewing.said[-1]


def test_a_preview_with_nothing_changed_marks_the_day_made_and_invoiced(previewing):
    previewing.fill()
    job = previewing.cur
    assert job.saved and job.invoiced and job.made and job.invoice_set
    assert "changed while" not in previewing.said[-1]


# ------------------------------------------------------------------ boxes whose day was merged into another meanwhile
@pytest.fixture
def two_days(tmp_path, monkeypatch, make_window, qt):
    """Two days of Roe read as two jobs, each a transcript of Pat's and Dana's pages."""
    monkeypatch.setattr(qt.QMessageBox, "exec", lambda self: 0)
    win = make_window(settings(tmp_path))
    win.add_files([str(transcript_pdf(tmp_path / "Roe 6-3-2026.pdf", 6, initials=[PR, PR, DS, DS, DS, PR])),
                   str(transcript_pdf(tmp_path / "Roe 6-4-2026.pdf", 4, date="June 4, 2026",
                                      initials=[PR, DS, PR, PR]))])
    wait(win, lambda: len(win.jobs) == 2 and all(j.docs for j in win.jobs))
    return win


def merged_into_the_other(win, job):
    """What batch.group does when a read that ends puts a day's documents with another day: the day leaves the
    list, its documents in the other one's."""
    other = next(j for j in win.jobs if j is not job)
    other.docs = other.docs + list(job.docs)
    win.jobs.remove(job)
    if win.cur is job:
        win.cur = other
    return other


def gone(win, job):
    win.jobs.remove(job)
    if win.cur is job:
        win.cur = win.jobs[0]


def test_peripherals_answered_after_a_merge_go_to_the_day_now_holding_its_documents(two_days, monkeypatch):
    from minute_filler.gui.dialogs import InvoicePeripheralsDialog
    win = two_days
    job = win.cur
    held = []
    monkeypatch.setattr(InvoicePeripheralsDialog, "exec", lambda dlg: held.append(merged_into_the_other(win, job)) or 1)
    monkeypatch.setattr(InvoicePeripheralsDialog, "values", lambda dlg: (False, "on"))
    win._invoice_peripherals()
    other, = held
    assert (other.invoice_email, other.invoice_index) == (False, "on")


def test_customize_answered_after_a_merge_goes_to_the_day_now_holding_its_documents(two_days, monkeypatch):
    from minute_filler.gui.dialogs import InvoiceShowDialog
    win = two_days
    job = win.cur
    held = []
    monkeypatch.setattr(InvoiceShowDialog, "exec", lambda dlg: held.append(merged_into_the_other(win, job)) or 1)
    monkeypatch.setattr(InvoiceShowDialog, "values", lambda dlg: ["pages"])
    win._invoice_show()
    other, = held
    assert other.invoice_show == ["pages"]


def test_peripherals_answered_for_a_day_removed_meanwhile_say_so(two_days, monkeypatch):
    from minute_filler.gui.dialogs import InvoicePeripheralsDialog
    win = two_days
    job = win.cur
    monkeypatch.setattr(InvoicePeripheralsDialog, "exec", lambda dlg: gone(win, job) or 1)
    monkeypatch.setattr(InvoicePeripheralsDialog, "values", lambda dlg: (False, "on"))
    win._invoice_peripherals()
    assert "removed while the box was open" in win.statusBar().currentMessage()
    assert all(j.invoice_email is None for j in win.jobs)


def test_whose_pages_answered_after_a_merge_go_to_the_day_now_holding_the_transcript(two_days, monkeypatch):
    """Whose pages... dropped its answer without a word when a read merged the day meanwhile."""
    from minute_filler.gui.dialogs import PagesOwnerDialog
    win = two_days
    job = win.cur
    doc = job.transcripts()[0]
    held = []
    monkeypatch.setattr(PagesOwnerDialog, "exec", lambda dlg: held.append(merged_into_the_other(win, job)) or 1)
    monkeypatch.setattr(PagesOwnerDialog, "values", lambda dlg: ({doc.key(): DS}, {}))
    assert win._whose_pages(job)
    other, = held
    assert other.page_basis[doc.key()] == DS


def test_whose_pages_answered_for_a_day_removed_meanwhile_says_so(two_days, monkeypatch):
    from minute_filler.gui.dialogs import PagesOwnerDialog
    win = two_days
    job = win.cur
    doc = job.transcripts()[0]
    monkeypatch.setattr(PagesOwnerDialog, "exec", lambda dlg: gone(win, job) or 1)
    monkeypatch.setattr(PagesOwnerDialog, "values", lambda dlg: ({doc.key(): DS}, {}))
    assert not win._whose_pages(job)
    assert "removed while the box was open" in win.statusBar().currentMessage()


# ------------------------------------------------------------------ Open this job again while a read goes on
def test_open_this_job_again_asks_while_a_document_is_still_being_read(make_window, tmp_path, monkeypatch, qt):
    """The window is empty but a file dropped is still being read (self.work): opening a past job cleared the
    window, and dropped that file, without asking."""
    monkeypatch.setattr(qt.QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(qt.QMessageBox, "information", lambda *a, **k: 0)
    asked = []
    monkeypatch.setattr(qt.QMessageBox, "question", lambda *a, **k: asked.append(a[2]) or qt.QMessageBox.No)
    win = make_window(settings(tmp_path))
    origin = json.dumps({"sources": [], "job": {}})
    assert all(j.is_empty() for j in win.jobs)
    win.work = 1  # (a read going on)
    try:
        assert win.open_past_job(origin) is False
    finally:
        win.work = 0
    assert len(asked) == 1 and "still being read" in asked[0]


def test_open_this_job_again_into_an_empty_window_asks_nothing(make_window, tmp_path, monkeypatch, qt):
    monkeypatch.setattr(qt.QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(qt.QMessageBox, "information", lambda *a, **k: 0)
    asked = []
    monkeypatch.setattr(qt.QMessageBox, "question", lambda *a, **k: asked.append(a[2]) or qt.QMessageBox.No)
    win = make_window(settings(tmp_path))
    win.open_past_job(json.dumps({"sources": [], "job": {}}))
    assert asked == []


# ------------------------------------------------------------------ Correct where this take ends: the day now
def test_the_take_box_is_about_the_day_holding_the_transcript_now(make_window, tmp_path, monkeypatch, qt):
    """While the page question is open a read puts the transcript with another day, one made already: the "Are
    you sure?" box says that day's files aren't changed (it described the day the transcript had left)."""
    from test_runsheet import transcript
    asked = []
    monkeypatch.setattr(qt.QMessageBox, "exec", lambda self: asked.append(self.text()) or 0)  # (Cancel)
    monkeypatch.setattr(qt.QMessageBox, "information", lambda *a: asked.append(a[2]))
    s = settings(tmp_path)
    s.outputs = ["runsheet"]
    win = make_window(s)
    win.add_files([str(transcript(tmp_path / "Transcript 6-3-2026 Roe v Poe.pdf"))])
    wait(win, lambda: len(win.cur.docs) == 1 and bool(win._take_rows))
    job = win.cur
    doc = job.docs[0]
    assert not job.made
    made = Job(made=True)

    def moved_meanwhile(*a, **k):
        made.docs = [doc]
        job.docs = []
        win.jobs.append(made)
        return 315, True
    monkeypatch.setattr(qt.QInputDialog, "getInt", moved_meanwhile)
    win._fix_take(win._take_rows[1])  # Dana's first take, pages 312-314
    assert "will end on page 315" in asked[-1] and "Files made already aren't changed" in asked[-1]
    assert not doc.fixes  # (Cancel)


# ------------------------------------------------------------------ what the fields complete from
def test_an_older_read_of_the_records_ending_last_keeps_the_newer_completions(make_window, tmp_path, monkeypatch):
    from minute_filler.records import past_values
    win = make_window(settings(tmp_path))
    started = []
    monkeypatch.setattr(win.runner, "start", lambda fn, *a, **k: started.append((fn, k.get("on_done"))))
    win._read_records_side()
    win._read_records_side()
    older, newer = [done for fn, done in started if fn is past_values]
    newer({"judge": ["Hon. Newer"]})
    older({"judge": ["Hon. Older"]})
    assert win._completions["judge"].stringList() == ["Hon. Newer"]


# ------------------------------------------------------------------ a tick spread from another day of the trial
def typing_in(win, text: str):
    """Opens the editor of the first Name cell of Who ordered and types `text` in it (not committed)."""
    win.activateWindow()
    win.att.setCurrentCell(0, 1)
    win.att.editItem(win.att.item(0, 1))
    viewport = win.att.viewport()
    editor = next(w for w in viewport.findChildren(QtWidgets.QLineEdit) if w.isVisibleTo(viewport))
    editor.setFocus()
    editor.setText(text)
    return editor


def open_editor(win):
    viewport = win.att.viewport()
    return next((w for w in viewport.findChildren(QtWidgets.QLineEdit) if w.parent() == viewport
                 and w.isVisibleTo(viewport)), None)


def test_a_tick_spread_from_another_day_keeps_a_name_being_typed(two_days):
    """An AI answer for the trial's other day ticks a firm, which spreads to the day shown (Settings.trial_orders
    "trial"): Who ordered's table was drawn again and the name half typed in it was lost. It is kept, and its
    editor opens again with the cursor after it; the firm is ticked on the day shown too."""
    win = two_days
    shown = win.cur
    other = next(j for j in win.jobs if j is not shown)
    assert win.s.trial_orders == "trial"
    firm = next(a for a in other.case.attorneys if a.key() and a.key() != shown.case.attorneys[0].key()
                and not a.is_placeholder())
    assert not any(a.checked for a in shown.case.attorneys if a.key() == firm.key())
    typing_in(win, "Dana Smi")
    firm.checked = True
    other.att_touched = True  # (the answer's tick is kept by the merge)
    win._remerge(other)
    assert any(a.checked for a in shown.case.attorneys if a.key() == firm.key())  # (spread to the day shown)
    assert any(a.name == "Dana Smi" for a in shown.case.attorneys)
    editor = open_editor(win)
    assert win.att.state() == QtWidgets.QAbstractItemView.EditingState and editor is not None
    assert editor.text().startswith("Dana Smi") and editor.cursorPosition() == len("Dana Smi")


# ------------------------------------------------------------------ Generate waits for the reading to finish
@pytest.fixture
def boxes(monkeypatch, qt):
    """The titles and texts of the information boxes shown (answered at once)."""
    shown = []
    monkeypatch.setattr(qt.QMessageBox, "information", lambda parent, title, text, *a: shown.append((title, text)))
    return shown


def test_generate_waits_while_a_document_is_still_being_read(previewing, boxes):
    """A read still going (the user, 2026-10-29: "you can't generate as things are still being read"): a box says
    to wait, nothing is made; the read over, Generate makes the files."""
    job = previewing.cur
    previewing.work = 1
    previewing.fill()
    assert boxes and boxes[-1][0] == "Please wait for the reading to finish"
    assert "Some documents are still being read" in boxes[-1][1] and "Press Generate again" in boxes[-1][1]
    assert not job.saved and not job.made
    previewing.work = 0
    previewing.fill()
    assert job.saved and job.made


def test_generate_waits_while_the_ai_is_still_asked(previewing, boxes):
    """An AI answer still to come can tick a firm or set the speed: Generate waits for it too."""
    previewing.s.use_ai = True  # (asked while the AI is on: an answer to a question sent before it was off is dropped)
    previewing.ai_pending = 1
    previewing.fill()
    assert "The AI is still reading the documents" in boxes[-1][1] and not previewing.cur.saved
    previewing.ai_pending = 0


def test_generate_all_waits_while_a_document_is_still_being_read(tmp_path, monkeypatch, make_window, qt, boxes):
    """Two days: Generate all waits while a read goes on (a read ending during the batch could put one day with
    the other), then makes them both."""
    from minute_filler.gui import dialogs
    from test_gui_batch import two_days
    monkeypatch.setattr(qt.QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(dialogs.ClarifyDialog, "exec", lambda self: 0)  # (not expected; never waits)
    s = settings(tmp_path)
    s.save_math = "off"
    win = make_window(s)
    win.output_boxes["agreement"].setChecked(False)
    win.output_boxes["invoice"].setChecked(True)
    two_days(win, tmp_path)
    win.work = 1
    win.fill_all_jobs()
    # (the button named as it reads)
    assert "Press Generate all 2 days again" in boxes[-1][1] and not win.filling and not any(j.saved for j in win.jobs)
    win.work = 0
    win.fill_all_jobs()
    wait(win, lambda: not win.filling)
    assert all(j.saved and j.made for j in win.jobs)
