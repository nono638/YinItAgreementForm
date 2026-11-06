"""The math of the invoices in a folder of its own (the user, 2026-11-06): a "Math" folder in every way of saving
(a folder for each case, one Save to folder, invoices with a folder of their own, no folder at all), which the box
at the end never names or opens; invoices already made keep their math when a later one fails; the box says when the
math wasn't saved (Save the math says Don't save it) or couldn't be; a mouse wheel going by leaves the two lists of
Save the math alone; the PDFs are written as invoices are (a file of their own first, retries, paths over 260
characters); the command line's --math. All names are made up."""
import json
import os
from pathlib import Path

import pymupdf
import pytest

from helpers import ROE, make_case, pat_settings, transcript_pdf
from minute_filler.batch import expand_paths, fill_jobs, group, read_docs, saved_folders
from minute_filler.deliver import generate
from minute_filler.invoice import InvoiceOpts, firm_invoices
from minute_filler.invoice_math import is_math_file, math_note, math_pdfs, new_pdf, save_math, to_pdf
from minute_filler.models import Attorney
from minute_filler.settings import ReporterProfile, Settings
from test_show_the_math import math_window, settled

NAMES = [("Alex B. Counsel", "Counsel & Counsel"), ("Dana Smith", "Smith Law"), ("Kim Park", "Park Law"),
         ("Sam Poe", "Poe LLP")]
OFF_ONE = "The math of this invoice was not saved (Settings → Invoice → Save the math says Don't save it)."
OFF_MANY = "The math of these invoices was not saved (Settings → Invoice → Save the math says Don't save it)."
SOME = "Some of the math of these invoices could not be saved (the log says why)."


def lost(n: int) -> str:
    """The note for n invoices whose math couldn't be saved."""
    return f"The math of {n} invoice{'' if n == 1 else 's'} could not be saved (the log says why)."


@pytest.fixture
def s(tmp_path):
    s = pat_settings()
    s.output_dir = str(tmp_path / "out")
    s.records_dir = str(tmp_path / "records")
    s.invoice_speeds = ["Regular"]
    s.save_math = "both"
    return s


def attorneys(n: int) -> list[Attorney]:
    return [Attorney(name=a, firm=f, checked=True) for a, f in NAMES[:n]]


def firms(n: int = 2):
    """Jane Roe v. X.Y. Holding Corporation with n firms, and the options of a 60-page day shared by them."""
    case = make_case({**ROE, "case_name": "Jane Roe v. X.Y. Holding Corporation", "index_no": "712345/2021",
                      "dates": "6/3/2026"}, attorneys(n))
    return case, InvoiceOpts(60, n, days=[("6/3/2026", 60)])


def made_of(s, n: int = 2) -> list:
    """(FirmInvoice, number) of n invoices, as generate's `math` has them."""
    case, opts = firms(n)
    return [(f, f"2026-{i:04}") for i, f in enumerate(firm_invoices(case, s, opts), 1)]


def split(paths: list) -> tuple[list, list]:
    """The invoices among these files, and the math."""
    return [p for p in paths if not is_math_file(p)], [p for p in paths if is_math_file(p)]


def failing_at(monkeypatch, n: int) -> None:
    """The n-th invoice made can't be saved (the PDF open in another program), once."""
    from minute_filler import invoice
    real, calls = invoice.make_invoice, []

    def make(case, atty, *a, **k):
        calls.append(atty)
        if len(calls) == n:
            raise PermissionError("the PDF is open in another program")
        return real(case, atty, *a, **k)
    monkeypatch.setattr(invoice, "make_invoice", make)


# ------------------------------------------------------------------ where it goes
def test_the_math_has_a_folder_of_its_own_in_every_way_of_saving(tmp_path, monkeypatch):
    import minute_filler.settings as settings
    s = Settings()
    case = tmp_path / "712345-2021"
    assert s.case_folders and s.folder_for("math", case) == case / "Math"  # (as the invoices have case\Invoices)
    s.case_folders = False
    assert s.folder_for("invoice", tmp_path) == tmp_path and s.folder_for("math", tmp_path) == tmp_path / "Math"
    for on in (True, False):
        s.case_folders = on
        assert s.folder_for("math") == Path.home() / "Documents" / "Minute Agreements" / "Math"  # (nowhere to save)
    s.output_dirs["invoice"] = str(tmp_path / "Billing")  # (invoices with a folder of their own: inside it)
    for on in (True, False):
        s.case_folders = on
        assert s.folder_for("math", case) == s.folder_for("math") == tmp_path / "Billing" / "Math"
    del s.output_dirs["invoice"]
    monkeypatch.setitem(settings.OUTPUT_FOLDERS, "invoice", "Court Invoices")  # (a courthouse's built-in one)
    assert s.folder_for("math", case) == Path.home() / "Documents" / "Court Invoices" / "Math"


def test_a_courthouse_says_nothing_and_the_math_still_has_a_folder():
    from minute_filler.courthouses import Courthouse
    assert Courthouse("x", "X", ()).math_subfolder == "Math"


@pytest.mark.parametrize("case_folders, own", [(True, False), (False, False), (True, True), (False, True)])
def test_generate_saves_it_there_and_counts_it_in_the_invoices_folder(s, tmp_path, case_folders, own):
    s.case_folders = case_folders
    if own:
        s.output_dirs["invoice"] = str(tmp_path / "Billing")
    out = tmp_path / "out" / "712345-2021" if case_folders else tmp_path / "out"
    case, opts = firms()
    paths = generate(case, s, out, ["invoice"], opts)
    invoices, maths = split(paths)
    assert len(invoices) == 2 and len(maths) == 3
    home = tmp_path / "Billing" if own else out  # (the case's, Save to, or the invoices' own)
    assert {p.parent for p in invoices} == {home / "Invoices" if case_folders and not own else home}
    assert {p.parent for p in maths} == {home / "Math"}
    assert saved_folders(paths, s) == [home]
    assert not [p for p in home.glob("*.pdf") if is_math_file(p)]  # (none left among the invoices)
    assert expand_paths([str(home)]) == []  # (none of it read back as a document)


def test_only_a_math_pdf_in_its_folder_counts_as_in_the_folder_above(tmp_path):
    s = Settings()
    s.case_folders = False
    other = tmp_path / "Math" / "Transcript 6-3-2026.pdf"  # (Save to is a folder of the user's named Math)
    beside = tmp_path / "Invoice 2026-0001 - the math.pdf"  # (one an earlier version saved beside the invoices)
    assert saved_folders([other], s) == [tmp_path / "Math"] and saved_folders([beside], s) == [tmp_path]
    again = tmp_path / "math" / "Invoice 2026-0001 - the math (2).pdf"  # (a second one; the folder in any case)
    assert saved_folders([again], s) == [tmp_path]


@pytest.mark.parametrize("how", ["case", "flat", "own"])
@pytest.mark.parametrize("everything", [False, True])
def test_the_box_names_and_opens_the_invoices_folder_never_the_math(tmp_path, monkeypatch, make_window, qt, how,
                                                                    everything):
    """Generate and Generate all, each way of saving: the real box, answered Open folder."""
    from minute_filler.gui import main_window
    from test_extras import wait
    win = settled(math_window(tmp_path, monkeypatch, make_window, qt, preview=False, days=2 if everything else 1))
    win.s.outputs = ["invoice"]
    win.s.case_folders = how == "case"
    if how == "own":
        win.s.output_dirs["invoice"] = str(tmp_path / "Billing")
    opened, texts = [], []
    monkeypatch.setattr(main_window, "open_path", lambda p: opened.append(Path(p)))

    def answer(box):
        texts.append(box.text())
        next(b for b in box.buttons() if b.text() == "Open folder").click()
        return 0
    monkeypatch.setattr(qt.QMessageBox, "exec", answer)
    if everything:
        win.fill_all_jobs()
        wait(win, lambda: opened)
    else:
        win.fill()
    saved = {p for j in win.jobs for p in j.saved}
    assert any(p.parent.name == "Math" and is_math_file(p) for p in saved)
    want = {"case": tmp_path / "out" / win.jobs[0].folder, "flat": tmp_path / "out", "own": tmp_path / "Billing"}[how]
    assert opened == [want]
    assert str(want) in texts[0] and str(want / "Math") not in texts[0]


# ------------------------------------------------------------------ a later invoice fails
def test_invoices_already_made_keep_their_math_when_a_later_one_fails(s, tmp_path, monkeypatch):
    case, opts = firms(4)
    failing_at(monkeypatch, 3)
    math, keys = [], []
    with pytest.raises(PermissionError) as failed:  # (the error still comes out)
        generate(case, s, tmp_path, ["invoice"], opts, math=math, invoiced=keys)
    invoices, maths = split(failed.value.made)
    assert len(invoices) == len(math) == len(keys) == 2
    assert {p.name for p in maths} >= {f"{p.stem} - the math.pdf" for p in invoices}
    everyone = [p for p in maths if p.name.startswith("Invoices ")]
    assert len(maths) == 3 and len(everyone) == 1 and {p.parent for p in maths} == {tmp_path / "Math"}
    with pymupdf.open(everyone[0]) as doc:  # (of the invoices made: not of the two that weren't)
        text = "".join(page.get_text() for page in doc)
    assert "Alex B. Counsel" in text and "Dana Smith" in text and "Kim Park" not in text
    assert math_note("both", math, failed.value.made) == ""


def test_the_first_invoice_failing_leaves_nothing_to_save(s, tmp_path, monkeypatch):
    case, opts = firms(2)
    failing_at(monkeypatch, 1)
    math = []
    with pytest.raises(PermissionError) as failed:
        generate(case, s, tmp_path, ["invoice"], opts, math=math)
    assert failed.value.made == [] and math == [] and not (tmp_path / "Math").exists()


def test_a_retry_after_generate_all_stopped_has_the_math_of_every_invoice(s, tmp_path, monkeypatch):
    """Through fill_jobs: the day's error and files, then the next run, which bills only those left. Each invoice
    has its own math in the end; each run's "everyone's" PDF covers the invoices it made."""
    docs, errors = read_docs([str(transcript_pdf(tmp_path / "Roe 6-3-2026.pdf", 30))], s)
    assert not errors
    job, = group(docs, s)
    job.case.attorneys = attorneys(4)
    failing_at(monkeypatch, 3)
    math = []
    done = fill_jobs([job], s, outputs=["invoice"], math=math)
    invoices, maths = split(done)
    assert "PermissionError" in job.error and set(done) == set(job.saved)
    assert len(invoices) == len(math) == 2 and len(maths) == 3 and len(job.invoiced_keys) == 2
    assert math_note(s.save_math, math, done) == ""
    again = []
    later = fill_jobs([job], s, outputs=["invoice"], math=again)
    invoices2, maths2 = split(later)
    assert not job.error and len(invoices2) == len(again) == 2 and len(maths2) == 3
    assert {p.name for p in maths + maths2} >= {f"{p.stem} - the math.pdf" for p in invoices + invoices2}
    assert len({p.parent for p in maths + maths2}) == 1 and maths[0].parent.name == "Math"


@pytest.mark.parametrize("save", ["both", "off"])
def test_generate_says_what_was_saved_before_the_problem_and_of_the_math(tmp_path, monkeypatch, make_window, qt, save):
    """The one box Generate shows when a file fails: the math of the invoice made among what was saved; with Don't
    save it, that it wasn't."""
    from minute_filler.gui.widgets import QMessageBox
    win = settled(math_window(tmp_path, monkeypatch, make_window, qt, preview=False))
    win.s.outputs, win.s.save_math = ["invoice"], save
    win.cur.case.attorneys = attorneys(2)
    win.cur.att_touched = True
    win._show_job()
    said = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, what, text: said.append(text))
    failing_at(monkeypatch, 2)
    win.fill()
    assert "PermissionError" in win.cur.error and "the PDF is open" in said[0]
    if save == "both":
        assert " - the math.pdf" in said[0] and "not saved" not in said[0] and "could not be saved" not in said[0]
        assert [p for p in win.cur.saved if is_math_file(p) and p.parent.name == "Math"]
    else:
        assert " - the math.pdf" not in said[0] and OFF_ONE in said[0]


# ------------------------------------------------------------------ the note in the box at the end
def test_the_note_when_save_the_math_says_dont_save_it(s):
    assert math_note("off", made_of(s, 1), []) == OFF_ONE
    assert math_note("off", made_of(s, 2), []) == OFF_MANY
    assert math_note("off", [], []) == math_note("both", [], []) == ""  # (no invoice made: nothing to say of it)


@pytest.mark.parametrize("save, invoices, saved, note", [
    ("each", 2, 2, ""), ("each", 2, 1, lost(1)), ("each", 2, 0, lost(2)), ("each", 1, 0, lost(1)),
    ("both", 1, 1, ""),  # (one invoice alone gets its own only)
    ("both", 1, 0, lost(1)),
    ("both", 2, 3, ""), ("both", 2, 2, SOME), ("both", 2, 0, lost(2)),
    ("all", 3, 1, ""), ("all", 3, 0, lost(3)),
])
def test_the_note_when_a_pdf_of_it_couldnt_be_saved(s, save, invoices, saved, note):
    others = [Path("Invoice 2026-0001.pdf"), Path("Invoice 2026-0001 (detailed).pdf")]  # (not counted)
    files = [Path(f"Invoice 2026-000{i} - the math.pdf") for i in range(saved)]
    assert math_note(save, made_of(s, invoices), others + files) == note


def test_math_pdfs_is_what_save_math_makes(s, tmp_path):
    for save in ("both", "each", "all", "off"):
        for n in (1, 2, 3):
            s.save_math = save
            case, opts = firms(n)
            folder = tmp_path / f"{save} {n}"
            paths = generate(case, s, folder, ["invoice"], opts)
            assert len(split(paths)[1]) == math_pdfs(save, n), (save, n)
    assert math_pdfs("both", 0) == math_pdfs("all", 0) == 0


@pytest.mark.parametrize("save", ["both", "each", "all"])
def test_no_false_alarm_with_another_reporters_invoices_or_several_days(s, tmp_path, save):
    """The PDFs due go by each reporter's invoices of each Generate, not by the invoices made."""
    s.profile.initials = "pr"
    s.save_math, s.invoice_joint = save, False  # (each day an invoice of its own)
    s.reporters = {"ds": ReporterProfile(name="Dana", full_name="Dana Smith")}
    path = transcript_pdf(tmp_path / "Roe 6-3-2026.pdf", 10, initials=["pr"] * 6 + ["ds"] * 4)
    other = transcript_pdf(tmp_path / "Doe 6-4-2026.pdf", 8, date="June 4, 2026")
    docs, errors = read_docs([str(path), str(other)], s)
    assert not errors
    jobs = group(docs, s)
    assert len(jobs) == 2
    for job in jobs:
        job.case.attorneys = attorneys(2)
    jobs[0].page_basis = {jobs[0].docs[0].key(): ["me", "ds"]}
    math = []
    done = fill_jobs(jobs, s, outputs=["invoice"], math=math)
    assert len(math) == 6 and not [j.error for j in jobs if j.error]
    assert math_note(save, math, done) == ""
    # ... and one PDF of those missing is noticed, however few the invoices alone would call for
    last = next(p for p in reversed(done) if is_math_file(p))
    assert math_note(save, math, [p for p in done if p != last]) != ""


def box_texts(win, monkeypatch) -> list:
    """The text of each box that says what was saved, instead of showing it."""
    boxes = []
    monkeypatch.setattr(type(win), "_saved_box", lambda self, title, text, *a, **k: boxes.append(text))
    return boxes


def make_all(win, everything: bool, boxes: list) -> str:
    """Generate, or Generate all, to its box; its text."""
    from test_extras import wait
    if everything:
        win.fill_all_jobs()
        wait(win, lambda: boxes)
    else:
        win.fill()
    return boxes[-1]


def maths_window(tmp_path, monkeypatch, make_window, qt, everything, preview=False, save="both"):
    win = settled(math_window(tmp_path, monkeypatch, make_window, qt, preview=preview, days=2 if everything else 1))
    win.s.outputs, win.s.save_math = ["invoice"], save
    return win


@pytest.mark.parametrize("preview", [False, True])
@pytest.mark.parametrize("everything", [False, True])
def test_the_box_says_when_save_the_math_says_dont_save_it(tmp_path, monkeypatch, make_window, qt, everything, preview):
    win = maths_window(tmp_path, monkeypatch, make_window, qt, everything, preview, "off")
    boxes = box_texts(win, monkeypatch)
    assert OFF_ONE in make_all(win, everything, boxes)
    assert win.s.save_math == "off"  # (said, not changed: the setting is the user's)


@pytest.mark.parametrize("everything", [False, True])
def test_the_box_says_nothing_of_the_math_when_it_is_saved(tmp_path, monkeypatch, make_window, qt, everything):
    win = maths_window(tmp_path, monkeypatch, make_window, qt, everything)
    boxes = box_texts(win, monkeypatch)
    text = make_all(win, everything, boxes)
    assert "not saved" not in text and "could not be saved" not in text and "the log says why" not in text


@pytest.mark.parametrize("everything", [False, True])
def test_the_box_says_when_a_pdf_of_the_math_couldnt_be_saved(tmp_path, monkeypatch, make_window, qt, everything):
    from minute_filler import invoice_math

    def broken(*a, **k):
        raise OSError("disk full")
    win = maths_window(tmp_path, monkeypatch, make_window, qt, everything)
    monkeypatch.setattr(invoice_math, "new_pdf", broken)
    boxes = box_texts(win, monkeypatch)
    assert lost(1) in make_all(win, everything, boxes)
    assert all(j.invoiced or j.made for j in win.jobs)  # (it stops nothing: the invoice is made)


@pytest.mark.parametrize("everything", [False, True])
def test_the_box_tells_of_the_list_as_the_preview_left_it(tmp_path, monkeypatch, make_window, qt, everything):
    """Don't save it chosen under the math in the preview, then Save: none is saved, and the box says so."""
    from minute_filler.gui.preview import PreviewDialog
    win = maths_window(tmp_path, monkeypatch, make_window, qt, everything, preview=True)
    boxes = box_texts(win, monkeypatch)

    def look(dlg):
        dlg.math.saves.choice.setCurrentIndex(dlg.math.saves.choice.findData("off"))
        return PreviewDialog.Accepted
    monkeypatch.setattr(PreviewDialog, "exec", look)
    assert OFF_ONE in make_all(win, everything, boxes)
    assert not [p for j in win.jobs for p in j.saved if is_math_file(p)]


@pytest.mark.parametrize("everything", [False, True])
@pytest.mark.parametrize("was, now", [("off", "both"), ("both", "off")])
def test_the_list_changed_in_the_maths_window_after_saving(tmp_path, monkeypatch, make_window, qt, everything, was,
                                                           now):
    """The window showing the math comes before the box: Don't save it chosen there says nothing of these invoices,
    whose math was saved; turned on there, the box doesn't then say the list says Don't save it."""
    from minute_filler.gui.preview import MathDialog
    win = maths_window(tmp_path, monkeypatch, make_window, qt, everything, save=was)
    win.s.show_math = True
    boxes = box_texts(win, monkeypatch)
    monkeypatch.setattr(MathDialog, "exec",
                        lambda dlg: dlg.saves.choice.setCurrentIndex(dlg.saves.choice.findData(now)) or 0)
    text = make_all(win, everything, boxes)
    assert win.s.save_math == now and "Save the math says" not in text and "could not be saved" not in text


# ------------------------------------------------------------------ the two lists and the wheel
def wheel_down(qt, widget) -> None:
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    event = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120), Qt.NoButton,
                        Qt.NoModifier, Qt.NoScrollPhase, False)
    qt.QApplication.sendEvent(widget, event)


def clicked(qt, combo):
    """The list as after a click: it has the focus (StrongFocus: only a click or Tab gives it)."""
    from PySide6.QtCore import Qt
    assert combo.focusPolicy() == Qt.StrongFocus
    top = combo.window()
    top.show()
    top.activateWindow()
    combo.setFocus()
    qt.QApplication.processEvents()
    assert combo.hasFocus()
    return combo


def test_a_wheel_going_by_leaves_save_the_math_alone_in_settings(s, qt):
    from minute_filler.gui.dialogs import SettingsDialog
    s.save_math = "all"  # (the wheel down from here is Don't save it)
    s.save()
    dlg = SettingsDialog(s)
    box = dlg.i_save_math
    wheel_down(qt, box)
    assert box.currentData() == "all"
    dlg.accept()
    assert Settings.load().save_math == "all"
    dlg = SettingsDialog(s)
    dlg.tabs.setCurrentIndex(next(i for i in range(dlg.tabs.count()) if dlg.tabs.tabText(i) == "Invoice"))
    box = clicked(qt, dlg.i_save_math)
    wheel_down(qt, box)  # (clicked first: it means it)
    assert box.currentData() == "off"
    dlg.close()


def test_a_wheel_going_by_leaves_save_the_math_alone_under_the_math(s, qt):
    from minute_filler.gui.preview import MathDialog
    s.save_math = "all"
    s.save()
    dlg = MathDialog(made_of(s), s, None, live=True)
    box = dlg.saves.choice
    wheel_down(qt, box)
    assert box.currentData() == s.save_math == Settings.load().save_math == "all"
    box = clicked(qt, box)
    wheel_down(qt, box)
    assert box.currentData() == s.save_math == Settings.load().save_math == "off"
    dlg.close()


# ------------------------------------------------------------------ how the PDFs are written
def test_a_math_path_over_260_characters_saves(s, tmp_path):
    """Real invoices here have paths of 263 characters, and their math is longer still."""
    deep = tmp_path / ("A folder of a long case name " * 4).strip() / ("Another long folder name " * 4).strip()
    deep = deep / ("And one more for good measure " * 3).strip()
    try:
        deep.mkdir(parents=True)
    except OSError:
        pytest.skip("long paths are off on this machine")
    case, opts = firms()
    s.case_folders = False
    paths = generate(case, s, deep, ["invoice"], opts)
    maths = split(paths)[1]
    assert len(maths) == 3 and all(len(str(p)) > 260 and p.parent == deep / "Math" for p in maths)
    for p in maths:
        assert p.read_bytes().startswith(b"%PDF")
    manual = to_pdf("<p>The math</p>", deep / "Math" / ("Saved by hand as a long name " * 3 + ".pdf"))
    assert len(str(manual)) > 260 and manual.read_bytes().startswith(b"%PDF")
    assert not list(deep.rglob("~YinIt*"))  # (nothing being written left behind)


@pytest.mark.parametrize("save", [new_pdf, to_pdf])
def test_a_file_held_for_a_moment_is_tried_again(tmp_path, monkeypatch, save):
    """Dropbox, OneDrive or an antivirus holding the name for a moment, as for invoices; both ways of saving."""
    import time
    real, tries = os.replace, []

    def held(a, b):
        tries.append(b)
        if len(tries) == 1:
            raise PermissionError("Dropbox has it")
        return real(a, b)
    monkeypatch.setattr(os, "replace", held)
    monkeypatch.setattr(time, "sleep", lambda _: None)
    out = save("<p>The math</p>", tmp_path / "Math" / "Invoice 2026-0001 - the math.pdf")
    assert len(tries) == 2 and out == tmp_path / "Math" / "Invoice 2026-0001 - the math.pdf"
    assert out.read_bytes().startswith(b"%PDF") and [p.name for p in out.parent.iterdir()] == [out.name]


def test_generates_math_is_never_written_over_a_file_there(s, tmp_path):
    (f, number), = made_of(s, 1)
    there = tmp_path / "Math" / "Invoice 2026-0001 - the math.pdf"
    there.parent.mkdir()
    there.write_bytes(b"sent to a firm")
    saved = save_math([(f, number, tmp_path / "Invoice 2026-0001.pdf")], "each", "invoice", tmp_path / "Math")
    assert saved == [tmp_path / "Math" / "Invoice 2026-0001 - the math (2).pdf"]
    assert there.read_bytes() == b"sent to a firm"
    with pymupdf.open(saved[0]) as doc:
        assert doc.metadata["creator"] == "YinIt math" and doc.metadata["title"] == "The math"


def test_save_as_replaces_the_file_it_asked_about_and_only_once_it_is_written(tmp_path, monkeypatch):
    import time
    out = tmp_path / "The math.pdf"
    assert to_pdf("<p>First</p>", out) == out
    first = out.read_bytes()
    assert to_pdf("<p>Second</p>", out) == out and out.read_bytes() != first  # (the Save box asked)
    with pymupdf.open(out) as doc:
        assert doc.metadata["creator"] == "YinIt math" and "Second" in doc[0].get_text()
    kept = out.read_bytes()

    def held(a, b):
        raise PermissionError("open in a PDF viewer")
    monkeypatch.setattr(os, "replace", held)
    monkeypatch.setattr(time, "sleep", lambda _: None)
    with pytest.raises(PermissionError):
        to_pdf("<p>Third</p>", out)
    assert out.read_bytes() == kept and [p.name for p in tmp_path.iterdir()] == [out.name]  # (and no file left over)


def test_a_new_math_pdf_that_fails_leaves_no_name_taken(tmp_path, monkeypatch):
    import time

    def held(a, b):
        raise PermissionError("the disk went away")
    monkeypatch.setattr(os, "replace", held)
    monkeypatch.setattr(time, "sleep", lambda _: None)
    with pytest.raises(PermissionError):
        new_pdf("<p>The math</p>", tmp_path / "Math" / "Invoice 2026-0001 - the math.pdf")
    assert list((tmp_path / "Math").iterdir()) == []


def test_save_as_starts_in_the_nearest_folder_there_is(s, qt, tmp_path, monkeypatch):
    """Generate saved none, so its Math folder isn't made: the Save box starts in the folder it would be in, not
    wherever Windows last was."""
    from minute_filler.gui.preview import MathDialog
    dlg = MathDialog(made_of(s), s, None, tmp_path / "Math")
    asked = []
    monkeypatch.setattr(qt.QFileDialog, "getSaveFileName",
                        lambda parent, title, path, filt: (asked.append(Path(path)), ("", ""))[1])
    dlg._save()
    (tmp_path / "Math").mkdir()
    dlg._save()
    assert [p.parent for p in asked] == [tmp_path, tmp_path / "Math"]
    assert not list((tmp_path / "Math").iterdir())


def test_the_maths_window_says_where_in_every_way_of_saving():
    from minute_filler.gui.preview import _saved_math_text
    assert _saved_math_text([]) == "This time: not saved."
    assert _saved_math_text([Path("Math") / "a - the math.pdf"]) == "This time: 1 PDF in the Math folder."
    assert _saved_math_text([Path("x") / "a - the math.pdf"] * 3) == "This time: 3 PDFs in the Math folder."


# ------------------------------------------------------------------ the command line
def test_the_command_lines_math_goes_in_a_math_folder(tmp_path):
    from minute_filler import main
    folder = tmp_path / "in"
    folder.mkdir()
    transcript_pdf(folder / "Roe transcript.pdf")
    pat_settings().save()
    out = tmp_path / "cli"
    assert main.batch(str(out), [str(folder)], ["invoice"], math=True) in (0, 1)
    invoices = list(out.glob("*.pdf"))
    maths = list((out / "Math").glob("*.pdf"))
    assert [p.name for p in maths] == [f"{invoices[0].stem} - the math.pdf"] and not is_math_file(invoices[0])
    with pymupdf.open(maths[0]) as doc:
        assert doc.metadata["creator"] == "YinIt math"
    report = json.loads((out / "batch.json").read_text(encoding="utf-8"))
    assert maths[0].name in report["jobs"][0]["forms"]
    assert expand_paths([str(out / "Math")]) == []
