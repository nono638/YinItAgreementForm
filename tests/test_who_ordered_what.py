"""Who ordered what, spelled out: Job.order_lines gives a line per day and attorney with the pages it ordered
(every page, or which excerpt), who shares them and how many of the user's pages that bills; an attorney not
ticked on a day and a day still waiting for a choice say so. The window's Who ordered card says it per firm (its
row's What, Speed and Pages, and the line under the table: _show_orders), and Generate all warns before billing a
case with a day not decided. The invoices the days ticked come to (batch.bill_sets), and every card following the
job list's ticks, not the day shown. All names are made up."""
import os
import time

import pytest

from minute_filler.batch import group, read_docs
from minute_filler.models import Attorney

from helpers import pat_settings, transcript_pdf

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def alex():
    return Attorney(name="Alex B. Counsel", firm="Counsel & Counsel", checked=True)


def dana():
    return Attorney(name="Dana Smith", firm="Smith Law", checked=True)


A, B = alex().key(), dana().key()


@pytest.fixture
def s(tmp_path):
    s = pat_settings()
    s.output_dir = str(tmp_path / "out")
    s.records_dir = str(tmp_path / "records")
    return s


def job_of(tmp_path, s, pages=100, initials=None, attorneys=None):
    """The one job of a transcript of Roe v. X.Y. (6/3/2026), with Alex and Dana ticked unless `attorneys` says
    otherwise."""
    path = transcript_pdf(tmp_path / "Roe 6-3-2026.pdf", pages, initials=initials)
    docs, _ = read_docs([str(path)], s)
    job, = group(docs, s)
    job.case.attorneys = attorneys if attorneys is not None else [alex(), dana()]
    return job


def test_every_page_and_an_excerpt_are_spelled_out(tmp_path, s):
    job = job_of(tmp_path, s)
    a, d = job.order_lines()
    assert (a.name, a.whole, a.spans, a.billed) == ("Alex B. Counsel", True, [(1, 100)], 100)
    assert a.shared == {B: [(1, 100)]} and a.printed == ["pp. 101–200"]
    job.portions = [(19, [A]), (40, [A, B]), (100, [A])]  # Dana Smith ordered pages 20-40
    a, d = job.order_lines()
    assert a.whole and a.spans == [(1, 100)] and a.shared == {B: [(20, 40)]}
    assert not d.whole and d.spans == [(20, 40)] and d.shared == {A: [(20, 40)]} and d.billed == 21
    assert d.printed == ["pp. 120–140"]


def test_only_my_pages_are_counted_and_others_order_nothing(tmp_path, s):
    job = job_of(tmp_path, s, pages=10, initials=["pr"] * 6 + ["ds"] * 4, attorneys=[alex()])
    line, other = job.order_lines([alex(), dana()])
    assert line.whole and line.spans == [(1, 10)] and line.billed == 6 and line.shared == {}
    assert other.name == "Dana Smith" and other.note.startswith("not ticked on this day")


def test_a_day_waiting_for_a_choice_says_so(tmp_path, s):
    job = job_of(tmp_path, s, pages=8, initials=["ds"] * 8)  # none of the pages are Pat's
    lines = job.order_lines()
    assert len(lines) == 2 and all(l.note.startswith("⚠ Whose pages") for l in lines)
    job.page_basis[job.docs[0].key()] = "*"
    job.portions = [(3, [A, B]), (5, [A])]  # rows that no longer end on the day's pages
    assert all("Excerpts… needs checking" in l.note for l in job.order_lines())


def test_bill_sets_are_the_invoices_to_make_and_those_made(tmp_path, s):
    """batch.bill_sets, what the cards show of the days ticked: the invoice Generate all makes of a case's days
    not invoiced yet, and each invoice made already with the days it billed (Job.invoice_set); a day whose invoice
    is held, apart."""
    from minute_filler.batch import bill_sets, new_invoice_set
    paths = [transcript_pdf(tmp_path / f"d{n}.pdf", 10, date=f"June {n}, 2026") for n in (3, 4, 5, 8, 9)]
    docs, _ = read_docs([str(p) for p in paths], s)
    days = sorted(group(docs, s), key=lambda j: j.case.get("dates"))
    d3, d4, d5, d8, d9 = days
    for j in days:
        j.case.attorneys = [alex()]

    def ids(sets) -> list:
        return [[days.index(j) for j in g] for g in sets]

    d3.invoiced = d4.invoiced = True
    d3.invoice_set = d4.invoice_set = new_invoice_set()  # billed together
    d9.portions = [(5, [A])]  # rows that don't end on its pages: held until Excerpts... is checked
    sets, held = bill_sets(days, s)
    assert ids(sets) == [[0, 1], [2, 3]] and held == [d9]
    d4.invoice_set = new_invoice_set()  # billed alone after all
    assert ids(bill_sets(days, s)[0]) == [[0], [1], [2, 3]]
    assert ids(bill_sets([d4, d8], s)[0]) == [[1], [3]]  # (only the days given: d3 is not ticked)
    s.invoice_joint = False  # a day each
    assert ids(bill_sets(days, s)[0]) == [[0], [1], [2], [3]]


# ------------------------------------------------------------------ the window

@pytest.fixture
def window(tmp_path, monkeypatch, make_window):
    from PySide6 import QtWidgets
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", lambda self: 0)
    s = pat_settings()
    s.use_ai = s.open_after = False
    s.output_dir = str(tmp_path / "out")
    s.records_dir = str(tmp_path / "records")
    s.outputs = ["invoice"]
    return make_window(s)


def wait(win, until, seconds=20):
    """Runs the event loop until `until()` holds and the window has no work left, or `seconds` pass."""
    from PySide6 import QtWidgets
    end = time.time() + seconds
    while time.time() < end and not (until() and not win.work):
        QtWidgets.QApplication.processEvents()
        time.sleep(0.01)


def two_days(window, tmp_path):
    """Two days of Roe v. X.Y.: Alex on both, Dana on the first only (as Who ordered's What or Excerpts... say it:
    Job.not_ordered), with an excerpt."""
    window.add_files([str(transcript_pdf(tmp_path / "a.pdf", pages=30, date="June 3, 2026")),
                      str(transcript_pdf(tmp_path / "b.pdf", pages=20, date="June 4, 2026"))])
    wait(window, lambda: len(window.jobs) == 2 and all(j.docs for j in window.jobs))
    first, second = sorted(window.jobs, key=lambda j: j.case.get("dates"))
    first.case.attorneys, second.case.attorneys = [alex(), dana()], [alex()]
    first.portions = [(10, [A, B]), (30, [A])]
    second.not_ordered = {B}
    window.job_list.setCurrentItem(window.job_list.topLevelItem(window.jobs.index(first)))
    window._show_job()  # the editor shows these attorneys (else the next look at it takes them back)
    return first, second


def test_who_ordered_says_what_each_firm_orders_of_the_trial(window, tmp_path):
    """A row per firm of the trial, whichever day is shown: Alex orders the whole trial (ticked), Dana part of the
    first day (half ticked), both at the forms' speed (they share pages 1-10), and what each is billed; the line
    under the table says it in words. Shown on the second day, Dana (not named that day) is a row too."""
    from PySide6.QtCore import Qt
    from minute_filler.gui.main_window import _VISITOR
    first, second = two_days(window, tmp_path)
    rows = rows_of(window)
    assert rows["Alex B. Counsel"] == (Qt.Checked, "The whole trial (2 days)", "Expedite", "50")
    assert rows["Dana Smith"] == (Qt.PartiallyChecked, "Part of 6/3/2026", "Expedite", "10")
    info = window.orders_info.text()
    assert info.startswith("Alex B. Counsel: the whole trial (2 days), at Expedite.  Dana Smith: part of 6/3/2026, "
                           "at Expedite.  Generate all bills these 2 days")
    window.job_list.setCurrentItem(window._job_item(second))
    assert window.cur is second and rows_of(window) == rows
    dana_row = next(r for r in range(window.att.rowCount()) if window.att.item(r, 1).text() == "Dana Smith")
    assert window.att.item(dana_row, 0).data(_VISITOR) and window.att.item(dana_row, 1).font().italic()
    assert [a.name for a in window._read_attorneys()] == ["Alex B. Counsel"]  # (not a row of this day's)


def test_generate_all_warns_about_a_day_not_decided(window, tmp_path, monkeypatch):
    from PySide6 import QtWidgets
    first, second = two_days(window, tmp_path)
    first.portions = [(10, [A, B]), (25, [A])]  # no longer ends on the day's 30 pages: needs checking
    shown, started = [], []
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", lambda self: shown.append(self.text()))  # (Go back)
    monkeypatch.setattr("minute_filler.gui.main_window.MainWindow._batch_running", lambda self: False)
    import minute_filler.gui.main_window as mw
    monkeypatch.setattr(mw.Runner, "start", lambda self, *a, **k: started.append(a))
    window.fill_all_jobs()
    assert shown and "Excerpts… needs checking" in shown[0] and "6/3/2026" in shown[0]
    assert not started  # went back: nothing made


def test_generate_all_can_go_on_without_the_day(window, tmp_path, monkeypatch):
    from PySide6 import QtWidgets
    first, second = two_days(window, tmp_path)
    first.portions = [(10, [A, B]), (25, [A])]
    started = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(QtWidgets.QMessageBox, "clickedButton",
                        lambda self: next(b for b in self.buttons() if "Go on" in b.text()))
    import minute_filler.gui.main_window as mw
    monkeypatch.setattr(mw.Runner, "start", lambda self, *a, **k: started.append(a))
    window.fill_all_jobs()
    assert started  # made, the day not decided without its invoice (see batch.fill_jobs)


# ------------------------------------------------------------------ found in the sweep (each failed before)

def test_a_job_of_several_days_shares_by_the_parties_and_lists_the_others(tmp_path, s):
    """All days on one form (Settings): each day's lines carry the Parties number its invoice is shared by,
    and an attorney of the invoice not ticked says, for each day, that it orders nothing."""
    s.batch_combine_dates = True
    paths = [str(transcript_pdf(tmp_path / "a.pdf", 30)),
             str(transcript_pdf(tmp_path / "b.pdf", 20, date="June 4, 2026"))]
    docs, _ = read_docs(paths, s)
    job, = group(docs, s)
    job.case.attorneys = [alex()]
    job.parties = 3
    lines = job.order_lines([alex(), dana()])
    assert [(l.day, l.name, l.parties) for l in lines if not l.note] == [("6/3/2026", "Alex B. Counsel", 3),
                                                                         ("6/4/2026", "Alex B. Counsel", 3)]
    assert [(l.day, l.name) for l in lines if l.note.startswith("not ticked")] == [("6/3/2026", "Dana Smith"),
                                                                                   ("6/4/2026", "Dana Smith")]


def test_a_held_day_is_worded_as_the_invoice_panel_words_it(tmp_path, s):
    """A day whose invoice is held (every page another reporter's) says why in the hold's own words
    (Job.invoice_hold), after a ⚠, on each of its lines."""
    job = job_of(tmp_path, s, pages=8, initials=["ds"] * 8)
    assert {l.note for l in job.order_lines()} == {"⚠ " + job.invoice_hold()}


def test_a_typed_page_count_is_marked(tmp_path, s):
    from minute_filler.models import SRC_USER
    job = job_of(tmp_path, s)
    job.case.set("est_pages", "40", SRC_USER)
    a, d = job.order_lines()
    assert a.typed and a.pages == 40 and a.billed == 40


def rows_of(window):
    """Who ordered's rows by name: (its tick's state, What, Speed, Pages)."""
    from minute_filler.gui.main_window import ATT_PAGES, ATT_SPEED, ATT_WHAT
    t = window.att
    out = {}
    for r in range(t.rowCount()):
        what, speed, pages = t.cellWidget(r, ATT_WHAT), t.cellWidget(r, ATT_SPEED), t.item(r, ATT_PAGES)
        out[t.item(r, 1).text()] = (t.item(r, 0).checkState(), what.currentText() if what else "",
                                    speed.currentText() if speed else "", pages.text() if pages else "")
    return out


def one_day(window, tmp_path, pages=30, initials=None, attorneys=None, name="a.pdf"):
    """Drops one transcript on the window, ticks Alex and Dana (or `attorneys`) and returns its job."""
    window.add_files([str(transcript_pdf(tmp_path / name, pages=pages, initials=initials))])
    wait(window, lambda: window.cur.docs)
    window.cur.case.attorneys = [alex(), dana()] if attorneys is None else attorneys
    window._show_case()
    window._update_status()
    return window.cur


def test_the_line_says_a_day_nobody_ticked_holds_the_case(window, tmp_path):
    from PySide6.QtCore import Qt
    first, second = two_days(window, tmp_path)
    second.case.attorneys = [Attorney(name="Alex B. Counsel", firm="Counsel & Counsel", checked=False)]
    second.not_ordered = {A, B}  # (as Excerpts... says when every firm is unticked on the day)
    window._update_status()
    assert rows_of(window)["Alex B. Counsel"][:2] == (Qt.PartiallyChecked, "6/3/2026")  # (the first day only)
    assert "⚠ No invoice for these 2 days of the case yet: nobody is ticked on 6/4/2026" in window.orders_info.text()


def test_a_day_with_no_pages_to_bill_says_none(window, tmp_path):
    one_day(window, tmp_path)
    window.rows["est_pages"].choose("0")
    assert rows_of(window)["Alex B. Counsel"][3] == "0 (typed)"


def test_a_typed_page_count_says_it_is_what_is_billed(window, tmp_path):
    one_day(window, tmp_path, pages=100)
    window.rows["est_pages"].choose("40")
    assert rows_of(window)["Alex B. Counsel"][3] == "40 (typed)"


def test_an_excerpt_of_none_of_my_pages_says_it_gets_no_invoice(window, tmp_path):
    job = one_day(window, tmp_path, pages=10, initials=["ds"] * 4 + ["pr"] * 6)
    job.portions = [(4, [A, B]), (10, [A])]  # Dana Smith ordered pages 1-4: the other reporter's
    window._update_status()
    rows = rows_of(window)
    assert rows["Alex B. Counsel"][3] == "6 of 10" and rows["Dana Smith"][3] == "0 of 4: no invoice"


def test_a_day_waiting_for_whose_pages_opens_whose_pages(window, tmp_path, monkeypatch):
    """Who ordered's button opens Whose pages..., not the Excerpts window, while that holds the invoice."""
    import minute_filler.gui.main_window as mw
    one_day(window, tmp_path, pages=8, initials=["ds"] * 8, attorneys=[])  # nobody ticked, none of it Pat's
    assert window.orders_edit.text() == "⚠ Whose pages…"
    assert window.orders_info.text().startswith("⚠ No invoice yet for 6/3/2026:")
    opened = []
    monkeypatch.setattr(mw.MainWindow, "_whose_pages", lambda self, job, reason="": opened.append("whose"))
    monkeypatch.setattr(mw.MainWindow, "_who_ordered", lambda self: opened.append("excerpts"))
    window.orders_edit.click()
    assert opened == ["whose"]


def test_unticking_a_day_in_the_job_list_updates_the_card(window, tmp_path):
    from PySide6.QtCore import Qt
    first, second = two_days(window, tmp_path)
    assert rows_of(window)["Alex B. Counsel"][1] == "The whole trial (2 days)"
    window.job_list.topLevelItem(window.jobs.index(second)).setCheckState(0, Qt.Unchecked)
    assert not second.include and rows_of(window)["Alex B. Counsel"][1:] == ("The whole day", "Expedite", "30")
    assert window.orders_info.text().endswith("Unticked, so left out: 6/4/2026.")
    assert "Pages counts the pages billed" in window.orders_help.toolTip()  # (how they are billed: the ? beside it)


def run_now(self, fn, *args, on_done=None, on_error=None, on_progress=None, **kwargs):
    """Runner.start, done at once on this thread."""
    on_done(fn(*args, **kwargs))


def test_generate_all_warns_about_a_case_with_a_day_nobody_ticked(window, tmp_path, monkeypatch):
    from PySide6 import QtWidgets
    import minute_filler.gui.main_window as mw
    first, second = two_days(window, tmp_path)
    second.case.attorneys = [Attorney(name="Alex B. Counsel", firm="Counsel & Counsel", checked=False)]
    shown, started = [], []
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", lambda self: shown.append(self.text()))  # (Go back)
    monkeypatch.setattr(mw.MainWindow, "_batch_running", lambda self: False)
    monkeypatch.setattr(mw.Runner, "start", lambda self, *a, **k: started.append(a))
    window.fill_all_jobs()
    assert shown and "nobody is ticked on 6/4/2026" in shown[0] and "no invoice for this case" in shown[0]
    assert not started and window.cur is second  # went back, to the day to tick


def test_go_back_when_the_day_was_ticked_meanwhile(window, tmp_path, monkeypatch):
    """The day nobody was ticked on got its attorney while the box was open (a document read again): Go back
    raised StopIteration looking for it."""
    from PySide6 import QtWidgets
    import minute_filler.gui.main_window as mw
    first, second = two_days(window, tmp_path)
    second.case.attorneys = [Attorney(name="Alex B. Counsel", firm="Counsel & Counsel", checked=False)]

    def meanwhile(box):
        second.case.attorneys[0].checked = True
        return 0
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", meanwhile)  # (then Go back)
    monkeypatch.setattr(mw.MainWindow, "_batch_running", lambda self: False)
    started = []
    monkeypatch.setattr(mw.Runner, "start", lambda self, *a, **k: started.append(a))
    window.fill_all_jobs()
    assert not started and window.cur is first  # stayed where it was


def test_a_batch_preview_that_cant_be_shown_asks_to_save_without_it(window, tmp_path, monkeypatch):
    """A preview of Generate all that couldn't be drawn raised out of the slot: nothing said, nothing saved."""
    from PySide6 import QtWidgets
    import minute_filler.gui.main_window as mw
    from minute_filler.gui import preview
    first, second = two_days(window, tmp_path)
    window.s.preview_before_saving = True

    def broken(*a, **k):
        raise RuntimeError("a page that can't be drawn")
    monkeypatch.setattr(preview, "PreviewDialog", broken)
    asked = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "question",
                        lambda *a, **k: asked.append(a[2]) or QtWidgets.QMessageBox.No)
    monkeypatch.setattr(mw.Runner, "start", run_now)
    window._preview_batch([first, second], {id(first): first, id(second): second}, ["invoice"],
                          lambda shown: asked.append("saved"))
    assert asked and "Save the files without it?" in asked[0] and "saved" not in asked


def test_after_go_on_anyway_a_held_day_is_not_a_failure(window, tmp_path, monkeypatch):
    from PySide6 import QtWidgets
    import minute_filler.gui.main_window as mw
    first, second = two_days(window, tmp_path)
    first.portions = [(10, [A, B]), (25, [A])]  # needs checking
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(QtWidgets.QMessageBox, "clickedButton",
                        lambda self: next(b for b in self.buttons() if "Go on" in b.text()))
    monkeypatch.setattr(mw.Runner, "start", run_now)
    boxes = []
    monkeypatch.setattr(mw.MainWindow, "_saved_box",
                        lambda self, title, text, folders, details="", warn=False: boxes.append((text, warn)))
    window.fill_all_jobs()
    (text, warn), = boxes
    assert "1 day not invoiced, as you chose:" in text and "check Excerpts… for 6/3/2026" in text
    assert "could not be saved" not in text and not warn and "for 1 job" in text


def test_the_job_list_marks_a_day_whose_invoice_is_held(window, tmp_path):
    first, second = two_days(window, tmp_path)
    first.portions = [(10, [A, B]), (25, [A])]
    window._update_status()
    assert not first.problems() and first.invoice_hold()
    assert window.job_list.topLevelItem(window.jobs.index(first)).text(0).startswith("⚠")


def test_every_card_follows_the_ticks_not_the_day_shown(window, tmp_path):
    """The user, 2026-10-23: the ticks in the job list say which days count. Every card shows those, whichever day
    is shown, and leaves out a day unticked: Who transcribed what too (it showed every day of the trial), and the
    Excerpts window."""
    from PySide6.QtCore import Qt
    first, second = two_days(window, tmp_path)
    window.job_list.setCurrentItem(window._job_item(second))
    assert window.cur is second and rows_of(window)["Alex B. Counsel"][1] == "The whole trial (2 days)"
    assert "for these 2 days" in window.pays.text() and window.takes_info.text().startswith("These 2 days")
    assert window._excerpt_group() == [first, second]
    window._job_item(first).setCheckState(0, Qt.Unchecked)
    assert rows_of(window)["Alex B. Counsel"][1] == "The whole day"
    assert "for these 2 days" not in window.pays.text() and window.takes_info.text().startswith("This day")
    assert window._excerpt_group() == [second]
