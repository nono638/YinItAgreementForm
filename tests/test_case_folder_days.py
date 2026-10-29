"""A case's folder named for its days (the user, 2026-10-28): "712345-2021 10-13,14,15-2026 Jones v USA Hauling" by
default (Settings.case_folder_pattern "{index} {days} {case}"), with only what every file system takes in it
(pdfout.folder_safe: "v." is "v"). The days of a trial Generated together share one folder named for all of them;
a day Generated later renames the case's folder (named for fewer days, or "712345-2021" by an older version) to
name it too, and the records' files follow (Ledger.move_folder); a folder that can't be renamed keeps its name
and takes the new files. Settings v17 saves the math again for those who had turned it off, and gives the old
default pattern the new one. With Settings.save_inputs on (off by default), the documents read are copied into
an "Inputs" folder beside the files (batch.copy_inputs). All names are made up."""
from pathlib import Path

import pytest

from minute_filler.batch import (case_dir_for, case_folders, copy_inputs, expand_paths, fill_jobs, group,
                                 move_case_folders, read_docs, settle_case_folders)
from minute_filler.pdfout import case_folder_name, compact_days, folder_safe
from minute_filler.records import Ledger
from minute_filler.settings import Settings

from helpers import ROE, invoice_text, make_case, pat_settings


def write(folder: Path, name: str, **kw) -> str:
    """A made-up e-mailed order (helpers.invoice_text) in `folder`; its path."""
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / name
    p.write_text(invoice_text(**kw))
    return str(p)


def jobs_of(s, *paths):
    docs, _ = read_docs(expand_paths(list(paths)), s)
    return group(docs, s)


def settings(tmp_path) -> Settings:
    s = pat_settings()
    s.output_dir = str(tmp_path / "out")
    return s


# ------------------------------------------------------------------ the name
def test_the_days_are_written_short_a_month_s_together_and_each_year_once():
    assert compact_days(["10/13/2026"]) == "10-13-2026"
    assert compact_days(["10/15/2026", "10/13/2026", "10/14/2026", "10/14/2026"]) == "10-13,14,15-2026"
    assert compact_days(["10/1/2026", "9/29/2026", "9/30/2026", "10/2/2026"]) == "9-29,30 and 10-1,2-2026"
    assert compact_days(["1/2/2027", "12/30/2026", "12/31/2026"]) == "12-30,31-2026 and 1-2-2027"
    assert compact_days([]) == ""
    many = [f"10/{d}/2026" for d in range(1, 29)]  # (too long for a folder's name: first to last)
    assert compact_days(many) == "10-1-2026 to 10-28-2026"


def test_only_what_every_file_system_takes_is_kept():
    assert folder_safe("Jones v. USA Hauling, Inc.") == "Jones v USA Hauling, Inc"
    assert folder_safe("O'Brien & Sons: <Part 2>? \"x\" | y * z / w \\ v.") == "OBrien and Sons Part 2 x y z w v"
    assert folder_safe("  Café   Ñoño\tLLC ") == "Café Ñoño LLC"  # (letters of any language are kept)
    jones = make_case({"case_name": "Jones v. U.S.A. Hauling, Inc.", "index_no": "234567/2026",
                       "dates": "10/13/2026, 10/14/2026, 10/15/2026"})
    assert case_folder_name(jones, Settings().case_folder_pattern) == \
        "234567-2026 10-13,14,15-2026 Jones v USA Hauling, Inc"
    # (the days given: a trial's, not only the case's own)
    assert case_folder_name(jones, "{index} {days}", ["10/16/2026", "10/13/2026"]) == "234567-2026 10-13,16-2026"


def test_the_days_are_read_back_from_a_folder_s_name():
    from minute_filler.pdfout import days_in_name
    assert days_in_name("234567-2026 10-13,14,15-2026 Jones v USA Hauling") == {"10/13/2026", "10/14/2026",
                                                                              "10/15/2026"}
    assert days_in_name("234567-2026 9-29,30 and 10-1-2026 X") == {"9/29/2026", "9/30/2026", "10/1/2026"}
    assert days_in_name("234567-2026 12-31-2026 and 1-2-2027 X") == {"12/31/2026", "1/2/2027"}
    assert days_in_name("234567-2026") == set() and days_in_name("234567-2026 Jones v USA Hauling") == set()
    assert days_in_name("Part 13-99-2026") == set()  # (no such day)


def test_settings_v17_saves_the_math_again_and_names_the_folders_anew():
    old = Settings.from_dict({"settings_version": 16, "save_math": "off", "case_folder_pattern": "{index}"})
    assert (old.save_math, old.case_folder_pattern) == ("both", "{index} {days} {case}")
    own = Settings.from_dict({"settings_version": 16, "save_math": "each", "case_folder_pattern": "{case} {index}"})
    assert (own.save_math, own.case_folder_pattern) == ("each", "{case} {index}")  # (chosen: kept)
    now = Settings.from_dict({"settings_version": 17, "save_math": "off"})
    assert now.save_math == "off"  # (turned off again since: kept)
    assert (Settings().save_math, Settings().save_inputs) == ("both", False)


# ------------------------------------------------------------------ one folder for the days of a trial
def test_the_days_of_a_trial_made_together_share_one_folder(tmp_path):
    s = settings(tmp_path)
    jobs = jobs_of(s, *(write(tmp_path / "in", f"{d}.txt", title="Jones v. USA Hauling", index="234567-2026",
                              date=f"10-{d}-2026") for d in (13, 14, 15)))
    assert len(jobs) == 3
    [f] = case_folders(jobs, s, ["agreement"])
    assert f.name == "234567-2026 10-13,14,15-2026 Jones v USA Hauling" and len(f.jobs) == 3
    made = fill_jobs(jobs, s, outputs=["agreement"])
    assert {p.parent.parent.name for p in made} == {"234567-2026 10-13,14,15-2026 Jones v USA Hauling"}


def made_day(tmp_path, s, day: int, ledger=None, loaded=()):
    """Day `day` of Jones v. USA Hauling, made into its case's folder; the job."""
    jobs = jobs_of(s, write(tmp_path / "in", f"{day}.txt", title="Jones v. USA Hauling", index="234567-2026",
                            date=f"10-{day}-2026"))
    fill_jobs(jobs, s, outputs=["agreement"], ledger=ledger, batch=[*loaded, *jobs])
    return jobs[0]


def test_a_day_made_later_renames_the_folder_and_the_records_follow(tmp_path):
    s = settings(tmp_path)
    ledger = Ledger(tmp_path / "records.db", mirror_dir=tmp_path / "mirror")
    out = tmp_path / "out"
    first = made_day(tmp_path, s, 13, ledger)
    assert first.folder == "234567-2026 10-13-2026 Jones v USA Hauling"
    [row] = ledger.activity()
    assert Path(row.file_path).parent.parent == out / first.folder
    # a later session: the day 13 not loaded, the folder found by its name (the index number and days)
    second = made_day(tmp_path, s, 14, ledger)
    assert second.folder == "234567-2026 10-13,14-2026 Jones v USA Hauling"
    assert sorted(p.name for p in out.iterdir()) == [second.folder]  # (renamed: no second folder)
    assert all(Path(a.file_path).parent.parent == out / second.folder and Path(a.file_path).exists()
               for a in ledger.activity())
    # with the day 14 loaded in the window, no records: its folder says the days it holds
    third = made_day(tmp_path, s, 15, None, loaded=[second])
    assert third.folder == second.folder == "234567-2026 10-13,14,15-2026 Jones v USA Hauling"
    assert sorted(p.name for p in out.iterdir()) == [third.folder]


def test_a_folder_an_older_version_named_is_renamed_too(tmp_path):
    s = settings(tmp_path)
    ledger = Ledger(tmp_path / "records.db", mirror_dir=tmp_path / "mirror")
    old = tmp_path / "out" / "234567-2026"
    (old / "Minute Agreements").mkdir(parents=True)
    (old / "Minute Agreements" / "Minute Agreement - Jones.pdf").write_bytes(b"%PDF")
    ledger.log_activity("agreement", case_name="Jones v. USA Hauling", index_no="234567-2026", dates="10/13/2026",
                        file_path=str(old / "Minute Agreements" / "Minute Agreement - Jones.pdf"))
    day = made_day(tmp_path, s, 14, ledger)
    assert day.folder == "234567-2026 10-13,14-2026 Jones v USA Hauling"
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == [day.folder]
    assert (tmp_path / "out" / day.folder / "Minute Agreements" / "Minute Agreement - Jones.pdf").exists()


def test_a_folder_that_can_t_be_renamed_takes_the_files_as_it_is(tmp_path, monkeypatch):
    s = settings(tmp_path)
    first = made_day(tmp_path, s, 13)
    jobs = jobs_of(s, write(tmp_path / "in", "14.txt", title="Jones v. USA Hauling", index="234567-2026",
                            date="10-14-2026"))

    def locked(self, target):
        raise PermissionError("in use")
    with monkeypatch.context() as m:  # (a file in the folder open in another program)
        m.setattr("time.sleep", lambda _: None)  # (the tries a moment apart, as for Dropbox)
        m.setattr(Path, "rename", locked)
        settle_case_folders(jobs, s, ["agreement"], [first, *jobs])
        assert jobs[0].folder_from == first.folder
        problems = move_case_folders(jobs, s, None, [first, *jobs])
    assert problems and "could not be renamed" in problems[0]
    assert jobs[0].folder == first.folder and not jobs[0].folder_from
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == [first.folder]
    # tried again at the next Generate, the folder free now (its name says the day 13 it holds)
    settle_case_folders(jobs, s, ["agreement"], [first, *jobs])
    move_case_folders(jobs, s, None, [first, *jobs])
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["234567-2026 10-13,14-2026 Jones v USA Hauling"]
    assert first.folder == jobs[0].folder == "234567-2026 10-13,14-2026 Jones v USA Hauling"


def test_new_folders_beside_it_rename_nothing(tmp_path):
    s = settings(tmp_path)
    s.case_folder_existing = "new"
    first = made_day(tmp_path, s, 13)
    second = made_day(tmp_path, s, 14, loaded=[first])
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == sorted({first.folder, second.folder})
    assert first.folder == "234567-2026 10-13-2026 Jones v USA Hauling"


def test_the_run_sheet_is_looked_for_in_the_case_s_folder_named_for_other_days(tmp_path):
    s = settings(tmp_path)
    first = made_day(tmp_path, s, 13)
    later = jobs_of(s, write(tmp_path / "in", "14.txt", title="Jones v. USA Hauling", index="234567-2026",
                             date="10-14-2026"))[0]
    assert case_dir_for(later, s) == tmp_path / "out" / first.folder
    assert case_dir_for(later, s, [first]) == tmp_path / "out" / first.folder


def test_documents_in_a_folder_named_by_the_index_number_are_in_the_case_s_folder(tmp_path):
    s = pat_settings()  # (Save to blank: next to the documents)
    case = tmp_path / "234567-2026 Jones"
    jobs = jobs_of(s, write(case, "13.txt", title="Jones v. USA Hauling", index="234567-2026", date="10-13-2026"))
    assert case_folders(jobs, s) == []
    made = fill_jobs(jobs, s, outputs=["agreement"])
    assert [p.parent for p in made] == [case / "Minute Agreements"]


# ------------------------------------------------------------------ the documents read
def test_the_documents_read_are_copied_only_when_settings_say_so(tmp_path):
    s = settings(tmp_path)
    jobs = jobs_of(s, write(tmp_path / "in", "13.txt", title="Jones v. USA Hauling", index="234567-2026",
                            date="10-13-2026"))
    fill_jobs(jobs, s, outputs=["agreement"])
    case = tmp_path / "out" / jobs[0].folder
    assert not (case / "Inputs").exists()  # (off by default)
    s.save_inputs = True
    fill_jobs(jobs, s, outputs=["agreement"])
    assert [p.name for p in (case / "Inputs").iterdir()] == ["13.txt"]
    assert (case / "Inputs" / "13.txt").read_text() == (tmp_path / "in" / "13.txt").read_text()
    assert copy_inputs(jobs[0], s) == []  # (the same file there already: never twice)
    (tmp_path / "in" / "13.txt").write_text(invoice_text(title="Jones v. USA Hauling", index="234567-2026",
                                                         date="10-13-2026") + "\nchanged")
    assert [p.name for p in copy_inputs(jobs[0], s)] == ["13 (2).txt"]  # (another of that name: beside it)


def test_pasted_text_is_copied_as_a_text_file_and_a_document_in_the_case_s_folder_isn_t(tmp_path):
    from helpers import text_doc
    s = settings(tmp_path)
    s.save_inputs = True
    jobs = group([text_doc(s, invoice_text(title="Jones v. USA Hauling", index="234567-2026", date="10-13-2026"))], s)
    fill_jobs(jobs, s, outputs=["agreement"])
    inputs = tmp_path / "out" / jobs[0].folder / "Inputs"
    assert [p.name for p in inputs.iterdir()] == ["Pasted text.txt"]
    # a document read from the case's folder: there already
    s.output_dir = ""
    case = tmp_path / "234567-2026 Jones"
    there = jobs_of(s, write(case, "14.txt", title="Jones v. USA Hauling", index="234567-2026", date="10-14-2026"))
    fill_jobs(there, s, outputs=["agreement"])
    assert not (case / "Inputs").exists()


def test_the_inputs_folder_is_the_case_s(tmp_path):
    s = settings(tmp_path)
    s.save_inputs = True
    jobs = jobs_of(s, write(tmp_path / "in", "13.txt", title="Jones v. USA Hauling", index="234567-2026",
                            date="10-13-2026"))
    made = fill_jobs(jobs, s, outputs=["agreement"])
    from minute_filler.batch import saved_folders
    assert saved_folders([tmp_path / "out" / jobs[0].folder / "Inputs" / "13.txt", *made], s) == \
        [tmp_path / "out" / jobs[0].folder]
    s.case_folders = False
    assert s.folder_for("inputs", tmp_path / "out") == tmp_path / "out" / "Inputs"


def test_a_failed_copy_is_logged_and_the_others_still_copied(tmp_path, monkeypatch):
    import shutil
    s = settings(tmp_path)
    s.save_inputs = True
    jobs = jobs_of(s, write(tmp_path / "in", "13.txt", title="Jones v. USA Hauling", index="234567-2026",
                            date="10-13-2026"),
                   write(tmp_path / "in", "13b.txt", title="Jones v. USA Hauling", index="234567-2026",
                         date="10-13-2026"))
    assert len(jobs) == 1 and len(jobs[0].docs) == 2
    settle_case_folders(jobs, s, ["agreement"])
    real = shutil.copy2

    def copy2(src, dst, **kw):
        if Path(src).name == "13.txt":
            raise OSError("disk full")
        return real(src, dst, **kw)
    monkeypatch.setattr(shutil, "copy2", copy2)
    assert [p.name for p in copy_inputs(jobs[0], s)] == ["13b.txt"]


@pytest.fixture
def window(tmp_path, make_window, monkeypatch, qt):
    s = settings(tmp_path)
    s.use_ai = s.open_after = False
    s.outputs = ["agreement"]
    s.records_dir = str(tmp_path / "records")
    win = make_window(s)
    from minute_filler.gui.dialogs import ClarifyDialog
    monkeypatch.setattr(ClarifyDialog, "exec", lambda self: qt.QDialog.Accepted)
    monkeypatch.setattr(qt.QMessageBox, "exec", lambda self: 0)
    return win


def test_the_window_renames_the_case_s_folder_for_a_day_made_later(window, qt, tmp_path):
    import time

    def wait(until, seconds=30):
        end = time.time() + seconds
        while time.time() < end:
            qt.QApplication.processEvents()
            if not window.runner._live and until():
                return
            time.sleep(0.01)
        raise AssertionError("timed out")
    window.add_files([write(tmp_path / "in", "13.txt", title="Jones v. USA Hauling", index="234567-2026",
                            date="10-13-2026")])
    wait(lambda: window.cur.docs)
    window.fill()
    assert window.cur.folder == "234567-2026 10-13-2026 Jones v USA Hauling"
    window.add_files([write(tmp_path / "in", "14.txt", title="Jones v. USA Hauling", index="234567-2026",
                            date="10-14-2026")], batch=True)
    wait(lambda: len(window.jobs) == 2)
    window.cur = next(j for j in window.jobs if "10/14" in j.case.get("dates"))
    window._show_job()
    window.fill()
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["234567-2026 10-13,14-2026 Jones v USA Hauling"]
    assert {j.folder for j in window.jobs} == {"234567-2026 10-13,14-2026 Jones v USA Hauling"}
