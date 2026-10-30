"""The sweep of the case folders named for their days (2026-10-29): a folder renamed for a later day keeps the
case's one run sheet (Generate and Generate all), the records' "Open this job again" finds the documents in it,
and Whose pages... follows them; a rename the window couldn't make isn't made behind its back by Generate all,
nor while documents are still being read, and the Saved box says so; Records not told is said too. A folder of
the user's own that starts with the index number is left alone; a day deleted since leaves the name, a day the
records don't know (made on another computer) stays in it; a case with no index number keeps one folder; a long
caption is cut before the days. The Recent jobs list isn't overwritten by an older read; the folder name box
takes accented letters and a pattern saved before; a document anywhere in the case's folder isn't copied to
Inputs. All names and numbers are made up."""
import json
import threading
import time
from pathlib import Path

import pytest

from minute_filler.batch import (Job, expand_paths, fill_jobs, follow_moves, group, move_case_folders, read_docs)
from minute_filler.records import Ledger

from helpers import invoice_text, pat_settings

OLD = "234567-2026 10-13-2026 Jones v USA Hauling"
BOTH = "234567-2026 10-13,14-2026 Jones v USA Hauling"


def settings(tmp_path, **kw):
    s = pat_settings()
    s.use_ai = s.open_after = False
    s.output_dir = str(tmp_path / "out")
    s.records_dir = str(tmp_path / "records")
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def order(folder: Path, day: int, index="234567-2026") -> str:
    """A made-up order e-mail of Jones v. USA Hauling for 10/<day>/2026."""
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / f"{day}-{index or 'x'}.txt"
    p.write_text(invoice_text(title="Jones v. USA Hauling", index=index, date=f"10-{day}-2026"))
    return str(p)


def made(tmp_path, s, day, ledger, folder=None, index="234567-2026", **kw) -> Job:
    """Day `day` made alone, as from the command line (fill_jobs, its folder chosen there)."""
    docs, _ = read_docs(expand_paths([order(folder or tmp_path / "in", day, index)]), s)
    jobs = group(docs, s)
    fill_jobs(jobs, s, outputs=["agreement"], ledger=ledger, **kw)
    return jobs[0]


def ledger(tmp_path):
    return Ledger(tmp_path / "records.db", mirror_dir=tmp_path / "mirror")


# ------------------------------------------------------------------ the records and Whose pages follow a rename

def test_the_records_origins_follow_a_renamed_folder(tmp_path):
    """The documents kept in the case's folder: Open this job again still finds them after a later day renamed it
    (Ledger.move_folder rewrites the origins' "sources" too, the same way for every row of one origin)."""
    s, led = settings(tmp_path), ledger(tmp_path)
    out = tmp_path / "out"
    made(tmp_path, s, 13, led, folder=out / OLD)
    made(tmp_path, s, 14, led)
    assert [p.name for p in out.iterdir()] == [BOTH]
    for a in led.activity():
        sources = json.loads(a.origin)["sources"]
        assert sources and all(Path(p).exists() for p in sources), (a.dates, sources)


def test_what_is_kept_by_a_documents_path_follows_it(tmp_path):
    """Whose pages... (page_basis), the front pages' owner and the run sheet chosen are kept by path: a rename
    that moved the document would otherwise lose them, and the pages be billed otherwise."""
    from minute_filler.records import moved_origin
    old, new = tmp_path / OLD, tmp_path / BOTH
    doc = str(old / "Roe 6-3.pdf")
    job = Job(docs=[], page_basis={doc: "ds", "elsewhere.pdf": "*"}, front_owner={doc: "pr"},
              runsheet_to=str(old / "Trial Runs" / "Run Sheet.xlsx"), index_numbers_ok=[doc])
    follow_moves([job], [(old, new)])
    assert job.page_basis == {str(new / "Roe 6-3.pdf"): "ds", "elsewhere.pdf": "*"}
    assert job.index_numbers_ok == [str(new / "Roe 6-3.pdf")]  # (Generate anyway: not asked again)
    assert job.front_owner == {str(new / "Roe 6-3.pdf"): "pr"}
    assert job.runsheet_to == str(new / "Trial Runs" / "Run Sheet.xlsx")
    origin = {"sources": [doc], "job": {"page_basis": {doc: "ds"}, "front_owner": {}}}
    assert moved_origin(origin, old, new) and origin["sources"] == [str(new / "Roe 6-3.pdf")]
    assert origin["job"]["page_basis"] == {str(new / "Roe 6-3.pdf"): "ds"}
    assert not moved_origin({"sources": ["elsewhere.pdf"]}, old, new)


def test_records_not_told_of_a_rename_is_said(tmp_path):
    class Locked:
        def move_folder(self, old, new):
            raise OSError("database is locked")
    s = settings(tmp_path)
    out = tmp_path / "out"
    (out / OLD).mkdir(parents=True)
    job = Job(docs=[], folder=BOTH, folder_named=BOTH, folder_from=OLD)
    problems = move_case_folders([job], s, Locked())
    assert (out / BOTH).is_dir() and len(problems) == 1 and "Records couldn't be told" in problems[0]


# ------------------------------------------------------------------ which folder is the case's

def test_a_folder_of_the_users_own_starting_with_the_index_number_is_left_alone(tmp_path):
    s, led = settings(tmp_path), ledger(tmp_path)
    mine = tmp_path / "out" / "234567-2026 Transcripts from the clerk"
    mine.mkdir(parents=True)
    (mine / "notes.txt").write_text("the user's own notes")
    job = made(tmp_path, s, 13, led)
    assert job.folder == OLD and sorted(p.name for p in mine.iterdir()) == ["notes.txt"]


def test_a_day_deleted_since_leaves_the_folders_name_a_day_the_records_dont_know_stays(tmp_path):
    s, led = settings(tmp_path), ledger(tmp_path)
    out = tmp_path / "out"
    made(tmp_path, s, 13, led)
    made(tmp_path, s, 31, led)  # (meant the 14th)
    assert [p.name for p in out.iterdir()] == ["234567-2026 10-13,31-2026 Jones v USA Hauling"]
    wrong = [a for a in led.activity() if "10/31" in a.dates]
    led.delete(activity=[a.id for a in wrong])  # (in the trash, its file still there: the day is still in it)
    made(tmp_path, s, 14, led)
    assert [p.name for p in out.iterdir()] == ["234567-2026 10-13,14,31-2026 Jones v USA Hauling"]
    # (the file deleted too, where it is now, its record in the trash: the next day made leaves the 31st out)
    for r in led._rows("SELECT file_path FROM activity WHERE dates LIKE '%10/31%'"):
        Path(r["file_path"]).unlink()
    made(tmp_path, s, 14, led)
    assert [p.name for p in out.iterdir()] == [BOTH]
    # the 15th made on another computer (these records don't know it): it stays in the name
    (out / BOTH).rename(out / "234567-2026 10-13,14,15-2026 Jones v USA Hauling")
    made(tmp_path, s, 16, ledger(tmp_path / "other"))
    assert [p.name for p in out.iterdir()] == ["234567-2026 10-13,14,15,16-2026 Jones v USA Hauling"]


def test_a_folder_of_the_users_own_with_the_index_number_and_a_date_is_left_alone(tmp_path):
    """Named by the index number and a day, but not by the case (nor known to the records): the user's."""
    s, led = settings(tmp_path), ledger(tmp_path)
    mine = tmp_path / "out" / "234567-2026 10-13-2026 transcripts from the clerk"
    mine.mkdir(parents=True)
    job = made(tmp_path, s, 14, led)
    assert job.folder == "234567-2026 10-14-2026 Jones v USA Hauling" and mine.is_dir()


def test_a_new_folder_beside_the_case_s_is_named_for_its_own_days(tmp_path):
    """If it's already there: Make a new one beside it. The later day's folder isn't named for the days it doesn't
    hold."""
    s, led = settings(tmp_path, case_folder_existing="new"), ledger(tmp_path)
    made(tmp_path, s, 13, led)
    job = made(tmp_path, s, 14, led)
    assert job.folder == "234567-2026 10-14-2026 Jones v USA Hauling"
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == [OLD, job.folder]


def test_a_case_with_no_index_number_keeps_one_folder(tmp_path):
    s, led = settings(tmp_path), ledger(tmp_path)
    made(tmp_path, s, 13, led, index="")
    made(tmp_path, s, 14, led, index="")
    assert [p.name for p in (tmp_path / "out").iterdir()] == ["10-13,14-2026 Jones v USA Hauling"]


def test_days_over_new_year_are_taken_out_of_a_folder_s_name_whole():
    from minute_filler.pdfout import name_without_days
    assert name_without_days("12-30,31-2026 and 1-2-2027 Jones v USA Hauling") == "jones v usa hauling"
    assert name_without_days("234567-2026 9-29,30 and 10-1-2026 Jones v USA Hauling") == \
        "234567-2026 jones v usa hauling"


def test_a_long_caption_is_cut_before_the_days():
    from minute_filler.models import CaseInfo
    from minute_filler.pdfout import CASE_FOLDER_MAX, case_folder_name, days_in_name
    case = CaseInfo()
    case.set("case_name", "Jane Roe, as Administrator of the Estate of John Roe v. Sam Poe Holding Corporation "
                          "and Example Trucking Company")
    case.set("court", "Supreme Court of the State of New York")
    case.set("judge", "Hon. Alexandra Example-Justice")
    days = ["10/13/2026", "10/14/2026", "11/2/2026"]
    name = case_folder_name(case, "{case} {court} {judge} {days}", days)
    assert len(name) <= CASE_FOLDER_MAX and name.endswith("10-13,14 and 11-2-2026")
    assert days_in_name(name) == set(days)


# ------------------------------------------------------------------ copying the documents read

def test_a_document_anywhere_in_the_case_s_folder_is_not_copied_to_inputs(tmp_path):
    from minute_filler.batch import copy_inputs
    s = settings(tmp_path, save_inputs=True)
    out = tmp_path / "out"
    docs, _ = read_docs(expand_paths([order(out / OLD / "Transcripts", 13)]), s)
    job = group(docs, s)[0]
    job.folder = job.folder_named = OLD
    assert copy_inputs(job, s, out / OLD) == []
    assert not (out / OLD / "Inputs").exists()


def test_without_a_case_folder_a_document_elsewhere_in_save_to_is_copied(tmp_path):
    """Every output with a folder of its own: no case folder, the files' folder is Save to itself, and a document
    in a folder of Save to is copied (only one right in it is beside the files)."""
    from minute_filler.batch import copy_inputs
    s = settings(tmp_path, save_inputs=True, outputs=["agreement"])
    s.output_dirs = {"agreement": str(tmp_path / "Agreements")}
    out = tmp_path / "out"
    docs, _ = read_docs(expand_paths([order(out / "Clerk" / "June", 13)]), s)
    job = group(docs, s)[0]
    assert job.folder == "" and [p.name for p in copy_inputs(job, s, out)] == ["13-234567-2026.txt"]


# ------------------------------------------------------------------ the window

@pytest.fixture
def window(tmp_path, make_window, qt, monkeypatch):
    from minute_filler.gui.dialogs import ClarifyDialog
    monkeypatch.setattr(ClarifyDialog, "exec", lambda self: qt.QDialog.Accepted)
    monkeypatch.setattr(qt.QMessageBox, "exec", lambda self: 0)
    return make_window(settings(tmp_path, outputs=["agreement"]))


def wait(win, qt, until, seconds=60):
    end = time.time() + seconds
    while time.time() < end:
        qt.QApplication.processEvents()
        if not win.runner._live and until():
            return
        time.sleep(0.01)
    raise AssertionError("timed out")


def saved_texts(window, monkeypatch) -> list:
    """The text of each Saved / Batch finished box."""
    texts = []
    monkeypatch.setattr(window, "_saved_box", lambda title, text, *a, **k: texts.append(text))
    return texts


def two_days(window, qt, tmp_path, inp=None):
    """Day 13 made (Generate), then day 14 dropped in beside it."""
    inp = inp or tmp_path / "in"
    window.add_files([order(inp, 13)])
    wait(window, qt, lambda: window.cur.docs)
    window.fill()
    window.add_files([order(inp, 14)], batch=True)
    wait(window, qt, lambda: len(window.jobs) == 2)


def run_sheet_days(window, qt, tmp_path, monkeypatch):
    """Two days of a trial of two reporters, the run sheet added to (Settings: add): day 3 made, day 4 read."""
    from test_runsheet import TALK, TITLE_1, transcript
    window.s.runsheet_existing, window.s.outputs, window.s.runsheet_dir = "add", ["runsheet"], ""
    window._runsheet_touched = True
    inp = tmp_path / "in"
    inp.mkdir()
    window.add_files([str(transcript(inp / "Transcript 6-3-2026 Roe v Poe.pdf"))])
    wait(window, qt, lambda: window.cur.docs)
    window.fill()
    window.add_files([str(transcript(inp / "Transcript 6-4-2026 Roe v Poe.pdf",
                                     [(320, "ds", "", TITLE_1), (321, "pr", "", TALK)], day="June 4, 2026"))],
                     batch=True)
    wait(window, qt, lambda: len(window.jobs) == 2)


def test_the_case_s_run_sheet_follows_its_renamed_folder(window, qt, tmp_path, monkeypatch):
    """Generate on the later day: the run sheet chosen in the folder (before it was renamed) is added to, not a
    second one started beside it."""
    run_sheet_days(window, qt, tmp_path, monkeypatch)
    window.cur = next(j for j in window.jobs if "6/4" in j.case.get("dates"))
    window._show_job()
    window.fill()
    sheets = list((tmp_path / "out").rglob("*.xlsx"))
    assert len(sheets) == 1 and "6-3,4-2026" in str(sheets[0]), sheets


def test_generate_all_keeps_one_run_sheet_after_a_rename(window, qt, tmp_path, monkeypatch):
    run_sheet_days(window, qt, tmp_path, monkeypatch)
    window.fill_all_jobs()
    wait(window, qt, lambda: not window.filling)
    sheets = list((tmp_path / "out").rglob("*.xlsx"))
    assert len(sheets) == 1 and "6-3,4-2026" in str(sheets[0]), sheets


def test_generate_records_the_documents_where_they_are_after_the_rename(window, qt, tmp_path, monkeypatch):
    """Generate (one day) with the documents kept in the case's folder: the day's own record names them in the
    renamed folder (its origin was taken before the rename)."""
    out = tmp_path / "out"
    two_days(window, qt, tmp_path, inp=out / OLD)
    window.cur = next(j for j in window.jobs if "10/14" in j.case.get("dates"))
    window._show_job()
    window.fill()
    assert [p.name for p in out.iterdir()] == [BOTH]
    for a in Ledger().activity():
        sources = json.loads(a.origin)["sources"]
        assert sources and all(Path(p).exists() for p in sources), (a.dates, sources)


def test_a_rename_the_window_could_not_make_is_not_made_behind_its_back(window, qt, tmp_path, monkeypatch):
    """Generate all: the folder locked while the window renames it, free a moment later on the batch's thread.
    The files go into it as it is (as the Batch finished box says), and the window's jobs name a folder that is
    there."""
    out = tmp_path / "out"
    texts = saved_texts(window, monkeypatch)
    two_days(window, qt, tmp_path)
    monkeypatch.setattr("time.sleep", lambda _: None)
    real = Path.rename

    def rename(self, target):
        if threading.current_thread() is threading.main_thread():
            raise PermissionError("in use")
        return real(self, target)
    monkeypatch.setattr(Path, "rename", rename)
    window.fill_all_jobs()
    wait(window, qt, lambda: not window.filling)
    assert [p.name for p in out.iterdir()] == [OLD]
    assert all((out / j.folder).is_dir() for j in window.jobs)
    assert "could not be renamed" in texts[-1]


def test_no_folder_is_renamed_while_documents_are_being_read(window, qt, tmp_path, monkeypatch):
    out = tmp_path / "out"
    texts = saved_texts(window, monkeypatch)
    two_days(window, qt, tmp_path)
    window.cur = next(j for j in window.jobs if "10/14" in j.case.get("dates"))
    window._show_job()
    # (a document still being read: it would come in by the folder's old path. Generate waits for reads to end
    # (MainWindow._still_reading), so this is a read begun once Generate went ahead: a file dropped during
    # Generate all)
    monkeypatch.setattr(window, "_still_reading", lambda *a: False)
    window.work += 1
    try:
        window.fill()
    finally:
        window.work -= 1
    assert [p.name for p in out.iterdir()] == [OLD] and window.cur.folder == OLD and not window.cur.folder_from
    assert "wasn't renamed for this day while documents were still being read" in texts[-1]
    window.s.recent_files = [str(out / OLD / "Roe.pdf"), str(tmp_path / "elsewhere.pdf")]
    window.fill()  # (renamed the next time; File -> Open recent follows)
    assert [p.name for p in out.iterdir()] == [BOTH]
    assert window.s.recent_files == [str(out / BOTH / "Roe.pdf"), str(tmp_path / "elsewhere.pdf")]


def test_an_older_recent_jobs_read_does_not_undo_the_setting(window, qt, tmp_path):
    two_days(window, qt, tmp_path)
    window._clear_jobs()
    wait(window, qt, lambda: True)
    window._read_records_side()  # (a read in flight...)
    window.s.recent_jobs_show = False  # (...when Settings turn the list off)
    window._read_records_side()
    wait(window, qt, lambda: True)
    assert window._recent_jobs == [] and window.start_list.count() == 0


def test_the_folder_name_box_takes_accents_and_a_pattern_saved_before(qt):
    from PySide6.QtGui import QValidator
    from minute_filler.gui.dialogs import SettingsDialog
    s = pat_settings()
    s.case_folder_pattern = "{index}.{case}"  # (saved by hand or by an earlier version: the dot is no longer kept)
    d = SettingsDialog(s)
    box = d.o_case_pattern
    assert box.text() == "{index} {case}"
    assert box.validator().validate("{index} Café Ñoño", 0)[0] == QValidator.Acceptable
    assert box.validator().validate("{index} v. Poe", 0)[0] == QValidator.Invalid
