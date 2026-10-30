"""Races around the rate sheet opened to be filled in, Records' right-click menu and the job list's: a save of the
sheet read in Excel's next save (the old file gone, the new one not yet in its place) prices nothing from another
sheet and stays watched, read again in a second, and only a second miss ends the watch, said so; Records read
again while the menu on Everything made is open keeps the rows selected, and its Delete deletes the rows chosen
when it opened, those still listed (never another); Remove this job, Remove from job and Move to a job of its own
on a day a read merged while the menu was open say so, and a document is taken out by identity, not an equal
twin (two pasted images). All names, numbers and prices are made up."""
import copy
import os

import pytest

from helpers import pat_settings, text_doc

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

COURT = ("Rate,Original,Copy,Email,Index\n"
         "Regular,$3.10,$0.90,$0.90,$0.90\n"
         "Hourly,$9.00,$2.00,$2.00,$2.00\n")  # (a speed the sample sheet doesn't have)
SAVED = COURT.replace("Hourly,$9.00", "Hourly,$9.50") + "Rates Last Updated:,5/2/2026\n"


# ------------------------------------------------------------------ the rate sheet opened to be filled in
@pytest.fixture
def sheet_window(tmp_path, make_window, monkeypatch, qt):
    """A window pricing from "Court Rates", watched as opened to be filled in, its one job at Hourly (chosen by
    the user: a speed the sample sheet lacks, so a job priced from that sheet even once loses it)."""
    from minute_filler.models import SRC_USER, FieldState
    monkeypatch.setattr(qt.QMessageBox, "exec", lambda self: 0)  # (no box waiting for a click)
    s = pat_settings()
    s.use_ai = False
    s.output_dir = str(tmp_path / "out")
    s.rate_sheets_dir = str(tmp_path / "sheets")
    s.invoice_speeds = ["Regular", "Hourly"]
    (tmp_path / "sheets").mkdir()
    path = tmp_path / "sheets" / "Court Rates.csv"
    path.write_text(COURT, encoding="utf-8")
    s.rate_sheet = "Court Rates"
    win = make_window(s)
    win.case.fields["delivery"] = FieldState("Hourly", SRC_USER, 1.0, ["Hourly"])
    win._apply_speed_rule()
    assert win.case.get("delivery") == "Hourly" and win.case.get("rate") == "9.00"
    win._watch_sheet(path)
    return win, path


def read_in_the_gap(monkeypatch, path, times=1):
    """The next `times` reads of the rate sheet folder (rates.list_sheets) are made while Excel saves: the sheet
    at `path` isn't there for that moment, though it was read whole just before (rates.load_sheet)."""
    from minute_filler import rates
    real, left = rates.list_sheets, [times]

    def listed(custom_dir=""):
        sheets, problems = real(custom_dir)
        if left[0] > 0:
            left[0] -= 1
            sheets = [sh for sh in sheets if sh.path != path]
        return sheets, problems
    monkeypatch.setattr(rates, "list_sheets", listed)


def test_a_save_read_in_excels_next_save_prices_nothing_and_is_read_again(sheet_window, monkeypatch):
    """Before: the read without the sheet put the sample sheet in its place, every job priced from it (Hourly lost,
    the rate the sample's), and the watch ended with no word: wrong prices until ⟳, later saves not read."""
    win, path = sheet_window
    path.write_text(SAVED, encoding="utf-8")
    read_in_the_gap(monkeypatch, path)
    win._sheet_saved()
    assert win._sheet_watched is not None and win._sheet_watched[0] == path and win._sheet_timer.isActive()
    assert win.s.rate_sheet == "Court Rates" and win.sheet_box.currentData() == "Court Rates"
    assert win.case.get("delivery") == "Hourly" and win.case.get("rate") == "9.00"  # (as before the save)
    win._sheet_saved()  # (a second later: read whole)
    assert win.case.get("delivery") == "Hourly" and win.case.get("rate") == "9.50"
    assert win.statusBar().currentMessage() == 'Read "Court Rates" again: its prices are all there and in order now.'
    assert win._sheet_watched is None  # (complete: no longer watched, as before)


def test_missed_twice_the_watch_ends_and_says_to_press_reload(sheet_window, monkeypatch):
    win, path = sheet_window
    path.write_text(SAVED, encoding="utf-8")
    read_in_the_gap(monkeypatch, path, times=2)
    win._sheet_saved()
    assert win._sheet_watched is not None and "Court Rates" not in win.statusBar().currentMessage()
    win._sheet_saved()
    assert win._sheet_watched is None and win._sheet_watch.files() == []
    assert win.statusBar().currentMessage() == ('"Court Rates" couldn\'t be read again after it was saved: press ⟳ '
                                                "next to the Rate sheet dropdown to read it.")
    assert win.s.rate_sheet == "Court Rates" and win.case.get("delivery") == "Hourly"  # (nothing priced from another)
    assert win.case.get("rate") == "9.00"


def test_another_sheet_picked_after_a_miss_ends_the_watch(sheet_window, monkeypatch):
    """(A guard of the read after a miss, which skips the check before it: the sheets read tell.)"""
    win, path = sheet_window
    path.write_text(SAVED, encoding="utf-8")
    read_in_the_gap(monkeypatch, path)
    win._sheet_saved()
    win.s.rate_sheet = "Sample Rates"  # (picked meanwhile: _sheet_changed)
    win._sheet_saved()
    assert win._sheet_watched is None and "Court Rates" not in win.statusBar().currentMessage()


# ------------------------------------------------------------------ Records: the menu on Everything made
@pytest.fixture
def records(qt, tmp_path, monkeypatch):
    """The Records window with three files made (made-up cases), shown off screen; its menus are replaced (shown,
    one would wait for a click): menu.picks is the text the menu picks (its start), menu.meanwhile what happens
    while it is open. Every question is answered Yes, and kept in asked."""
    from minute_filler.deliver import ledger_for
    from minute_filler.gui import records_window as rw
    s = pat_settings()
    s.records_dir = str(tmp_path / "records")
    lg = ledger_for(s)
    for name in ("Roe v. Poe", "Doe v. Moe", "Lee v. Kee"):
        lg.log_activity("agreement", case_name=name, file_path=rf"C:\out\Minute Agreement - {name}.pdf")

    class Menu(rw.QMenu):
        picks, meanwhile = "", []

        def exec(self, *a):
            for f in Menu.meanwhile:
                f()
            act = next(x for x in self.actions() if x.text().startswith(Menu.picks))
            act.trigger()
            return act

    asked = []
    monkeypatch.setattr(rw, "QMenu", Menu)
    monkeypatch.setattr(rw.QMessageBox, "question", lambda *a, **k: asked.append(a[2]) or rw.QMessageBox.Yes)
    monkeypatch.setattr(rw.QMessageBox, "information", lambda *a, **k: asked.append(a[2]))
    win = rw.RecordsWindow(s)
    win.reload()
    win.a_year.setCurrentIndex(0)
    win.show()
    yield win, lg, Menu, asked
    win.close()
    win.deleteLater()


def row_of(win, case):
    t = win.act_table
    return next(r for r in range(t.rowCount()) if win._act_at(r).case_name == case)


def choose(win, *cases):
    from PySide6.QtCore import QItemSelectionModel
    t = win.act_table
    t.clearSelection()
    for c in cases:
        t.selectionModel().select(t.model().index(row_of(win, c), 0),
                                  QItemSelectionModel.Select | QItemSelectionModel.Rows)


def right_click(win, case):
    t = win.act_table
    win._activity_menu(t.visualItemRect(t.item(row_of(win, case), 0)).center())


def listed(lg) -> set:
    return {a.case_name for a in lg.activity()}


def test_records_read_again_keep_the_rows_selected(records):
    """Before: every reload (the main window's win.reload() after each file made) cleared the selection."""
    win, lg, _, _ = records
    choose(win, "Roe v. Poe", "Lee v. Kee")
    win.reload()
    assert {a.case_name for a in win._selected("activity")} == {"Roe v. Poe", "Lee v. Kee"}


def test_delete_from_the_menu_after_a_reload_deletes_the_rows_chosen(records):
    """Before: a reload while the menu was open cleared the selection, and its Delete read the selection when
    clicked: "Delete 2 records…" did nothing, and said nothing."""
    win, lg, menu, asked = records
    choose(win, "Roe v. Poe", "Lee v. Kee")
    menu.picks, menu.meanwhile = "Delete 2 records", [win.reload]
    right_click(win, "Roe v. Poe")
    assert listed(lg) == {"Doe v. Moe"} and asked[-1].startswith("Move 2 records to the trash?")


def test_delete_from_the_menu_deletes_only_those_still_listed(records):
    """One of the two chosen was deleted elsewhere while the menu was open (another Records window): the other
    goes, the question says so, and nothing else is deleted; none left: said so, nothing deleted."""
    win, lg, menu, asked = records
    gone = next(a.id for a in lg.activity() if a.case_name == "Lee v. Kee")
    choose(win, "Roe v. Poe", "Lee v. Kee")
    menu.picks, menu.meanwhile = "Delete 2 records", [lambda: lg.delete(activity=[gone]), win.reload]
    right_click(win, "Roe v. Poe")
    assert listed(lg) == {"Doe v. Moe"}
    assert asked[-1].startswith("Move 1 record to the trash?")
    assert asked[-1].endswith("1 of the 2 chosen is no longer listed (the list was read again meanwhile): it stays "
                              "as it is.")
    doe = next(a.id for a in lg.activity() if a.case_name == "Doe v. Moe")
    choose(win, "Doe v. Moe")
    menu.picks, menu.meanwhile = "Delete 1 record", [lambda: lg.delete(activity=[doe]), win.reload]
    lg.restore(activity=[gone])  # (back in the list: the menu below is on Doe only)
    win.reload()
    right_click(win, "Doe v. Moe")
    assert listed(lg) == {"Lee v. Kee"}  # (Lee, listed again and not chosen, stays)
    assert asked[-1] == ("That record is no longer listed (the list was read again while the menu was open): "
                         "nothing was deleted.")


# ------------------------------------------------------------------ the job list's menu
@pytest.fixture
def list_window(tmp_path, make_window, monkeypatch, qt):
    monkeypatch.setattr(qt.QMessageBox, "exec", lambda self: 0)
    s = pat_settings()
    s.use_ai = s.open_after = False
    s.output_dir = str(tmp_path / "out")
    return make_window(s)


def put_jobs(win, *docs_of_each):
    """The window's jobs: one per list of documents (a batch when more than one)."""
    from minute_filler.batch import Job, remerge
    win.jobs = [Job(docs=list(docs), batch=len(docs_of_each) > 1) for docs in docs_of_each]
    for j in win.jobs:
        remerge(j, win.s)
    win.cur = win.jobs[0]
    win._refresh_jobs()
    win._show_job()


@pytest.fixture
def job_menu(list_window, monkeypatch):
    """The job list's right-click menu, replaced (shown, it would wait for a click): job_menu(row, picks,
    meanwhile) right-clicks the row (a QTreeWidgetItem) and picks the action whose text is `picks`, after
    meanwhile() (a read that ends while the menu is open)."""
    from minute_filler.gui import main_window as mw
    win = list_window

    def right_click(item, picks, meanwhile=lambda: None):
        class Menu(mw.QMenu):
            def exec(self, *a):
                meanwhile()
                return next(x for x in self.actions() if x.text() == picks)
        with monkeypatch.context() as m:
            m.setattr(mw, "QMenu", Menu)
            win._job_menu(win.job_list.visualItemRect(item).center())
    win.show()
    return right_click


def test_remove_this_job_after_a_read_merged_it_says_so(list_window, job_menu):
    """Before: nothing happened, and nothing was said."""
    win = list_window
    a, b = text_doc(win.s, "Please send the minutes of 6/3/2026", "a.txt"), text_doc(win.s, "and of 6/4", "b.txt")
    put_jobs(win, [a], [b])
    first, second = win.jobs

    def merged():  # (a read that ended found both one day)
        first.docs.append(b)
        win.jobs.remove(second)
        win._refresh_jobs()
    job_menu(win._job_item(second), "Remove this job", merged)
    assert win.jobs == [first] and first.docs == [a, b]
    assert win.statusBar().currentMessage() == ("That day changed while the menu was open (a read joined it with "
                                                "another): nothing was removed. Right-click it again to choose.")


def twins(win):
    """Two pasted images of one job, equal as Docs (both "Pasted image", no path), and a third document."""
    from minute_filler.batch import make_doc
    from minute_filler.extract_regex import RegexExtractor
    from minute_filler.ingest import Ingested
    ing = Ingested("Pasted image", "image", text="Minutes of 6/3/2026")
    one = make_doc(ing, RegexExtractor(win.s.profile).extract(ing), win.s)
    other = copy.deepcopy(one)
    assert other == one and other is not one
    return one, other, text_doc(win.s, "Please send the minutes", "order.txt")


def same(docs, want) -> bool:
    return len(docs) == len(want) and all(d is w for d, w in zip(docs, want))


def test_remove_from_job_takes_out_the_image_clicked_not_its_twin(list_window, job_menu):
    """Before: list.remove took out the first equal one; Move to a job of its own then left the image moved in
    both jobs."""
    win = list_window
    one, other, order = twins(win)
    put_jobs(win, [one, other, order])
    job = win.cur
    job_menu(win._job_item(job).child(1), "Move to a job of its own")
    assert same(job.docs, [one, order]) and same(win.jobs[1].docs, [other])
    job_menu(win._job_item(job).child(0), "Remove from job")
    assert same(job.docs, [order])


def test_remove_from_job_after_its_image_moved_leaves_the_twin_and_says_so(list_window, job_menu):
    """The image right-clicked went to another day while the menu was open: its twin, still in the job, stays.
    Before: the twin, equal to it, was taken out, and nothing was said."""
    win = list_window
    one, other, order = twins(win)
    put_jobs(win, [one, other, order], [text_doc(win.s, "Minutes of 6/4/2026", "d2.txt")])
    job, day2 = win.jobs

    def moved():  # (a read put the image with the other day)
        job.docs.pop(1)
        day2.docs.append(other)
        win._refresh_jobs()
    job_menu(win._job_item(job).child(1), "Remove from job", moved)
    assert same(job.docs, [one, order]) and same(day2.docs[1:], [other])
    assert win.statusBar().currentMessage() == ("That document's day changed while the menu was open (a read "
                                                "joined it with another): nothing was removed. Right-click it again "
                                                "to choose.")
