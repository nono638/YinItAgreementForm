"""A document of a job opened again (Records -> Open this job again) that comes back after the job was opened gets
what the record kept by its path: Whose pages... (Job.page_basis, Job.front_owner) and the takes the user corrected
(Doc.fixes), dropped back from another folder (known by its name, as the rows and the count know it) or in its own
place later on (batch.back_from_record, Job.old_fixes). They were lost, and the bill changed with no word: the whole
transcript chosen on Pat's 10 pages and DS's 20, 30 total pages billed, became 10 dropped back from another folder;
DS's pages chosen, 20 became 10; a take corrected, 11 of Pat's pages billed became 10. Two documents of one name that
nothing tells apart get nothing, as before, and so does a trial's document back from another folder (its record doesn't
say which day a document is of: known by its name, another day's own volume took it). The real window. All names and
numbers are made up."""
import json
from pathlib import Path

import pytest

from minute_filler.batch import (Job, back_from_record, fill_jobs, follow_moves, group, job_origin, joint_origin,
                                 read_docs)
from minute_filler.deliver import case_snapshot, ledger_for
from minute_filler.models import Attorney

from helpers import CAPTION_DPM, MIN_U_SCRIPT_COVER as COVER, page_numbered_transcript, pat_settings

PR, DS = "pr", "ds"
ALEX = dict(name="Alex B. Counsel", firm="Counsel & Counsel", party="Defendant")
DANA = dict(name="Dana Smith", firm="Smith Law", party="Plaintiff")
A, D = Attorney(**ALEX).key(), Attorney(**DANA).key()


@pytest.fixture
def s(tmp_path):
    s = pat_settings()
    s.profile.initials = "P.R."
    s.output_dir, s.records_dir = str(tmp_path / "out"), str(tmp_path / "records")
    s.save_math = "off"
    s.use_ai = s.open_after = False
    return s


@pytest.fixture
def window(monkeypatch, make_window, qt, s):
    monkeypatch.setattr(qt.QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(qt.QMessageBox, "question", lambda *a, **k: qt.QMessageBox.Yes)
    s.outputs = ["invoice"]
    return make_window(s)


def wait(win, until=lambda: True, seconds=30):
    import time

    from PySide6.QtWidgets import QApplication
    end = time.time() + seconds
    while time.time() < end:
        QApplication.processEvents()
        if not win.runner._live and win.work == 0 and until():
            return
        time.sleep(0.01)
    raise AssertionError("timed out")


def shared(path: Path, pages: int = 30, mine: int = 10, **k) -> Path:
    """Jane Roe's day, June 3: Pat Reporter's first `mine` pages, then another reporter's, DS (printed from 100)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return page_numbered_transcript(path, pages, first=100, initials=[PR] * mine + [DS] * (pages - mine), **k)


def job_of(s, *paths) -> Job:
    """The one job these PDFs make, read as the window reads them, both firms ticked."""
    docs, errors = read_docs([str(p) for p in paths], s)
    assert not errors
    job, = group(docs, s)
    job.case.attorneys = [Attorney(**ALEX, checked=True), Attorney(**DANA, checked=True)]
    job.att_touched = True
    return job


def record_of(job: Job) -> dict:
    """What a Generate would keep of this job now."""
    return json.loads(json.dumps({**job_origin(job), "case": case_snapshot(job.case)}))


def away(path: Path, folder: Path) -> Path:
    """The document moved into `folder` (another folder, or one the record doesn't know): its path there."""
    folder.mkdir(parents=True, exist_ok=True)
    return path.rename(folder / path.name)


def open_again(window, origin) -> Job:
    assert window.open_past_job(json.dumps(origin)) is True
    wait(window)
    return window.cur


def drop(window, path: Path, count: int) -> None:
    window.add_files([str(path)], same_job=True)
    wait(window, lambda: len(window.cur.docs) == count)


def sets(job: Job) -> list:
    """The invoices the job makes: whose (the user's: ""), and how many pages each bills."""
    return [(o.reporter, o.pages) for o in job.invoice_sets()]


# ------------------------------------------------------------------ Whose pages...
@pytest.mark.parametrize("basis, billed", [
    ("*", [("", 30)]),  # (the whole transcript, on Pat's invoices)
    (DS, [(DS, 20)]),  # (DS's pages, on invoices in that reporter's name)
    (["me", DS], [("", 10), (DS, 20)]),  # (each reporter's on their own)
])
def test_whose_pages_follow_a_document_dropped_back_from_another_folder(window, tmp_path, s, basis, billed):
    path = shared(tmp_path / "in" / "Roe.pdf")
    job = job_of(s, path)
    job.page_basis = {job.docs[0].key(): basis}
    assert sets(job) == billed
    origin = record_of(job)
    moved = away(path, tmp_path / "elsewhere")
    cur = open_again(window, origin)
    assert not cur.docs
    drop(window, moved, 1)
    assert cur.page_basis == {str(moved): basis}
    assert sets(cur) == billed and not cur.invoice_hold()
    assert record_of(cur)["job"]["page_basis"] == {str(moved): basis}  # (made again now, by the path it has now)


def test_whose_first_pages_are_follows_a_document_dropped_back_from_another_folder(window, tmp_path, s):
    """Its first 2 pages carry no initials, and Whose pages... said they are Pat's: lost, the invoice was held to ask
    again whose they are."""
    (tmp_path / "in").mkdir()
    who = [""] * 2 + [PR] * 8 + [DS] * 20
    path = page_numbered_transcript(tmp_path / "in" / "Roe.pdf", 30, first=100, initials=who)
    job = job_of(s, path)
    job.front_owner = {job.docs[0].key(): PR}
    assert job.invoice_pages() == job.your_pages() == 10 and not job.invoice_hold()
    origin = record_of(job)
    moved = away(path, tmp_path / "elsewhere")
    cur = open_again(window, origin)
    drop(window, moved, 1)
    assert cur.front_owner == {str(moved): PR}
    assert cur.invoice_pages() == cur.your_pages() == 10 and not cur.invoice_hold()


# ------------------------------------------------------------------ the takes corrected
@pytest.mark.parametrize("from_elsewhere", [True, False])
def test_the_takes_corrected_follow_a_document_dropped_back(window, tmp_path, s, from_elsewhere):
    """Page 110 (place 10) corrected to Pat's: 11 of Pat's pages billed. Dropped back from another folder, or in its
    own place once the job was opened without it, it got none: 10 of Pat's pages billed."""
    path = shared(tmp_path / "in" / "Roe.pdf")
    job = job_of(s, path)
    job.docs[0].correct({10: PR})
    assert job.invoice_pages() == job.your_pages() == 11
    origin = record_of(job)
    assert origin["job"]["page_fixes"] == {str(path): {"10": PR}}
    moved = away(path, tmp_path / "elsewhere")
    cur = open_again(window, origin)
    assert not cur.docs
    if not from_elsewhere:
        moved = moved.rename(path)
    drop(window, moved, 1)
    assert cur.docs[0].fixes == {10: PR} and cur.docs[0].owners()[10] == PR
    assert cur.invoice_pages() == cur.your_pages() == 11 and not cur.old_fixes
    assert record_of(cur)["job"]["page_fixes"] == {str(moved): {"10": PR}}


@pytest.mark.parametrize("older", [True, False])
def test_a_record_that_counted_the_cover_gives_the_takes_without_it(window, tmp_path, s, older):
    """A record made before the Min-U-Script cover stopped counting kept page 110 at place 11, the cover at place 0:
    without it, place 10 (fixes_without_cover). A record of now kept place 10 already: as it is."""
    path = shared(tmp_path / "in" / "Roe.pdf", cover=COVER)
    job = job_of(s, path)
    job.docs[0].correct({10: PR})
    origin = record_of(job)
    assert origin["job"]["cover_out"] is True and origin["job"]["page_fixes"] == {str(path): {"10": PR}}
    if older:  # (no mark, the cover among the pages: 31 total pages, the place one on)
        del origin["job"]["cover_out"]
        origin["job"]["page_fixes"] = {str(path): {"11": PR}}
        origin["case"]["fields"]["est_pages"][0] = "31"
    moved = away(path, tmp_path / "elsewhere")
    cur = open_again(window, origin)
    drop(window, moved, 1)
    assert cur.docs[0].fixes == {10: PR} and cur.docs[0].owners()[10] == PR and cur.docs[0].owners()[11] == DS
    assert cur.transcript_pages() == 30 and cur.invoice_pages() == cur.your_pages() == 11 and not cur.old_places


JUNE_4 = CAPTION_DPM.replace("June 3, 2026", "June 4, 2026")


@pytest.mark.parametrize("from_elsewhere", [False, True])
def test_a_trial_s_day_gives_a_volume_dropped_back_its_takes(window, tmp_path, s, from_elsewhere):
    """June 3 in two volumes (the second, Roe PM.pdf, 10 total pages: Pat's 5, then DS's, place 5 corrected to Pat's),
    June 4 in one, all on one invoice. Opened again with Roe PM.pdf away, then dropped back in its own place: it gets
    its corrected take. From another folder it gets none, as before: a trial's record doesn't say which day a document
    is of, and known by its name, another day's own volume of that name took it (the test below)."""
    am = shared(tmp_path / "in" / "Roe AM.pdf", 20)
    pm = shared(tmp_path / "in" / "Roe PM.pdf", 10, mine=5)
    day2 = page_numbered_transcript(tmp_path / "in" / "Roe 6-4.pdf", 20, first=200,
                                    caption=CAPTION_DPM.replace("June 3, 2026", "June 4, 2026"))
    docs, errors = read_docs([str(am), str(pm), str(day2)], s)
    assert not errors
    days = sorted(group(docs, s), key=lambda j: j.case.get("dates"))
    assert [len(j.docs) for j in days] == [2, 1]
    for j in days:
        j.case.attorneys = [Attorney(**ALEX, checked=True), Attorney(**DANA, checked=True)]
        j.att_touched = True
    next(d for d in days[0].docs if d.path == str(pm)).correct({5: PR})
    origin = json.loads(json.dumps(joint_origin(days, split_rule="")))
    assert origin["page_fixes"] == {str(pm): {"5": PR}}
    moved = away(pm, tmp_path / "elsewhere")
    assert window.open_past_job(json.dumps(origin)) is True
    wait(window, lambda: len([j for j in window.jobs if j.docs]) == 2)
    if not from_elsewhere:
        moved = moved.rename(pm)
    window.add_files([str(moved)])
    wait(window, lambda: sum(len(j.docs) for j in window.jobs) == 3)
    june3 = next(j for j in window.jobs if j.case.get("dates") == "6/3/2026")
    back = next(d for d in june3.docs if d.path == str(moved))
    assert back.fixes == ({} if from_elsewhere else {5: PR})
    assert june3.your_pages() == 10 + (5 if from_elsewhere else 6)


def test_a_trial_day_takes_no_corrected_take_of_another_day_by_its_name(window, tmp_path, s):
    """Each volume a "Transcript.pdf" in a folder of its own: June 3's AM and PM (place 5 of the PM one corrected to
    Pat's), June 4's AM, on one invoice. Opened again with June 3's PM away, then June 4's own PM volume dropped in (DS's
    6 pages, then Pat's 4). Known by its name as June 3's, it took that corrected take: a page of DS's billed as Pat's,
    25 of your pages for 24, with no word said."""
    am3 = shared(tmp_path / "6-3 AM" / "Transcript.pdf", 20)
    pm3 = shared(tmp_path / "6-3 PM" / "Transcript.pdf", 10, mine=5)
    (tmp_path / "6-4 AM").mkdir()
    am4 = page_numbered_transcript(tmp_path / "6-4 AM" / "Transcript.pdf", 20, first=200, caption=JUNE_4)
    docs, errors = read_docs([str(am3), str(pm3), str(am4)], s)
    assert not errors
    days = sorted(group(docs, s), key=lambda j: j.case.get("dates"))
    assert [len(j.docs) for j in days] == [2, 1]
    for j in days:
        j.case.attorneys = [Attorney(**ALEX, checked=True), Attorney(**DANA, checked=True)]
        j.att_touched = True
    next(d for d in days[0].docs if d.path == str(pm3)).correct({5: PR})
    origin = json.loads(json.dumps(joint_origin(days, split_rule="")))
    away(pm3, tmp_path / "elsewhere")
    assert window.open_past_job(json.dumps(origin)) is True
    wait(window, lambda: len([j for j in window.jobs if j.docs]) == 2)
    (tmp_path / "6-4 PM").mkdir()
    pm4 = page_numbered_transcript(tmp_path / "6-4 PM" / "Transcript.pdf", 10, first=220, caption=JUNE_4,
                                   initials=[DS] * 6 + [PR] * 4)
    window.add_files([str(pm4)])
    wait(window, lambda: sum(len(j.docs) for j in window.jobs) == 3)  # (June 3's PM still away)
    june4 = next(j for j in window.jobs if j.case.get("dates") == "6/4/2026")
    new = next(d for d in june4.docs if d.path == str(pm4))
    assert new.fixes == {} and june4.your_pages() == 20 + 4


def trial_record(s, *paths, fix=None) -> dict:
    """The record of one invoice for the days these PDFs make, both firms ticked on each. fix: (a PDF, {place:
    initials}), the take corrected in it first."""
    docs, errors = read_docs([str(p) for p in paths], s)
    assert not errors
    days = sorted(group(docs, s), key=lambda j: j.case.get("dates"))
    for j in days:
        j.case.attorneys = [Attorney(**ALEX, checked=True), Attorney(**DANA, checked=True)]
        j.att_touched = True
    if fix:
        next(d for j in days for d in j.docs if d.path == str(fix[0])).correct(fix[1])
    return json.loads(json.dumps(joint_origin(days, split_rule="")))


def test_a_trial_day_s_own_record_reads_back_no_other_day_s_transcript(window, tmp_path, s, monkeypatch):
    """June 3 in two volumes and June 4 in one, on one invoice. Opened again with June 3's PM volume away, which is then
    dropped back in its own place (it goes to June 3). June 4's own record, made then, named June 3's PM volume among
    the trial's documents (nothing says which day's each is), and opened again it read it into June 4's job: 25 of your
    pages billed on June 4 (30 total pages) for its 20 (20 total pages), with no word said. Now it is left out, as
    it is dated June 3, and a toast says so."""
    am3 = shared(tmp_path / "in" / "Roe 6-3 AM.pdf", 20)
    pm3 = shared(tmp_path / "in" / "Roe 6-3 PM.pdf", 10, mine=5)
    am4 = page_numbered_transcript(tmp_path / "in" / "Roe 6-4.pdf", 20, first=200, caption=JUNE_4)
    origin = trial_record(s, am3, pm3, am4)
    moved = away(pm3, tmp_path / "elsewhere")
    assert window.open_past_job(json.dumps(origin)) is True
    wait(window, lambda: len([j for j in window.jobs if j.docs]) == 2)
    window.add_files([str(moved.rename(pm3))])
    wait(window, lambda: sum(len(j.docs) for j in window.jobs) == 3)
    june4 = next(j for j in window.jobs if j.case.get("dates") == "6/4/2026")
    rec4 = record_of(june4)
    assert rec4["job"].get("trial_day") is True and str(pm3) in rec4["job"]["old_sources"]
    toasts = []
    monkeypatch.setattr(window, "_toast", toasts.append)
    cur = open_again(window, rec4)
    assert [d.path for d in cur.docs] == [str(am4)] and cur.case.get("dates") == "6/4/2026"
    assert cur.your_pages() == cur.invoice_pages() == cur.transcript_pages() == 20
    assert any(t.startswith("Roe 6-3 PM.pdf, of this trial, isn't dated this day: left out") for t in toasts)


def test_a_trial_day_s_own_record_reads_back_its_own_volume_that_was_away(window, tmp_path, s):
    """June 3 in two volumes (the PM one: Pat's 5 pages, then DS's 5, place 5 corrected to Pat's) and June 4 in one, on
    one invoice. Opened again with June 3's own PM volume away, June 3's own record is made then. That record kept
    the PM's corrected take (left out, it came back uncorrected: 15 of your pages billed for 16), and opened again
    with the PM back in its place, it reads it: 16 of your pages billed (30 total pages), not 10 (20 total pages)."""
    am3 = shared(tmp_path / "in" / "Roe 6-3 AM.pdf", 20)
    pm3 = shared(tmp_path / "in" / "Roe 6-3 PM.pdf", 10, mine=5)
    am4 = page_numbered_transcript(tmp_path / "in" / "Roe 6-4.pdf", 20, first=200, caption=JUNE_4)
    origin = trial_record(s, am3, pm3, am4, fix=(pm3, {5: PR}))
    moved = away(pm3, tmp_path / "elsewhere")
    assert window.open_past_job(json.dumps(origin)) is True
    wait(window, lambda: len([j for j in window.jobs if j.docs]) == 2)
    june3 = next(j for j in window.jobs if j.case.get("dates") == "6/3/2026")
    rec3 = record_of(june3)
    assert rec3["job"].get("trial_day") is True and rec3["job"]["page_fixes"] == {str(pm3): {"5": PR}}
    moved.rename(pm3)
    cur = open_again(window, rec3)
    assert sorted(d.path for d in cur.docs) == sorted([str(am3), str(pm3)])
    assert next(d for d in cur.docs if d.path == str(pm3)).fixes == {5: PR}
    assert cur.transcript_pages() == 30 and cur.your_pages() == cur.invoice_pages() == 10 + 6


def test_a_trial_day_s_own_record_gives_its_own_document_its_takes_by_name(window, tmp_path, s):
    """June 3 in two volumes, June 4 in one (Roe 6-4.pdf: Pat's 10 pages, then DS's 10, place 11 corrected to Pat's),
    on one invoice; opened again with June 3's PM away, June 4's own record made then. Roe 6-4.pdf, which that record
    read, is then moved to another folder and dropped back from there: it is this day's, no doubt, and gets its
    corrected take, 11 of your pages billed, not 10."""
    am3 = shared(tmp_path / "in" / "Roe 6-3 AM.pdf", 20)
    pm3 = shared(tmp_path / "in" / "Roe 6-3 PM.pdf", 10, mine=5)
    am4 = page_numbered_transcript(tmp_path / "in" / "Roe 6-4.pdf", 20, first=200, caption=JUNE_4,
                                   initials=[PR] * 10 + [DS] * 10)
    origin = trial_record(s, am3, pm3, am4, fix=(am4, {11: PR}))
    away(pm3, tmp_path / "elsewhere")
    assert window.open_past_job(json.dumps(origin)) is True
    wait(window, lambda: len([j for j in window.jobs if j.docs]) == 2)
    rec4 = record_of(next(j for j in window.jobs if j.case.get("dates") == "6/4/2026"))
    assert rec4["job"].get("trial_day") is True
    moved4 = away(am4, tmp_path / "archive")
    cur = open_again(window, rec4)
    assert cur.docs == []
    drop(window, moved4, 1)
    assert window.cur.docs[0].fixes == {11: PR} and window.cur.your_pages() == window.cur.invoice_pages() == 11


def test_a_trial_day_s_own_record_gives_no_other_day_s_corrected_take_by_its_name(window, tmp_path, s):
    """Each volume a "Transcript.pdf" in a folder of its own: June 3's AM (a Min-U-Script cover first) and PM (place 5
    corrected to Pat's), June 4's AM, on one invoice. Opened again with June 3's PM away, June 4's own record keeps
    that corrected take for when it comes back. Opened again, that record was a single day's, and June 4's own PM
    volume dropped in (DS's 6 pages, then Pat's 4) took June 3's take by its name: a page of DS's billed as Pat's, 25
    of your pages for 24, with no word said."""
    am3 = shared(tmp_path / "6-3 AM" / "Transcript.pdf", 20, cover=COVER)
    pm3 = shared(tmp_path / "6-3 PM" / "Transcript.pdf", 10, mine=5)
    (tmp_path / "6-4 AM").mkdir()
    am4 = page_numbered_transcript(tmp_path / "6-4 AM" / "Transcript.pdf", 20, first=200, caption=JUNE_4)
    origin = trial_record(s, am3, pm3, am4, fix=(pm3, {5: PR}))
    away(pm3, tmp_path / "elsewhere")
    assert window.open_past_job(json.dumps(origin)) is True
    wait(window, lambda: len([j for j in window.jobs if j.docs]) == 2)
    june4 = next(j for j in window.jobs if j.case.get("dates") == "6/4/2026")
    rec4 = record_of(june4)
    assert rec4["job"]["page_fixes"] == {str(pm3): {"5": PR}}
    cur = open_again(window, rec4)
    assert cur.old_fixes_exact and [d.path for d in cur.docs] == [str(am4)]
    (tmp_path / "6-4 PM").mkdir()
    pm4 = page_numbered_transcript(tmp_path / "6-4 PM" / "Transcript.pdf", 10, first=220, caption=JUNE_4,
                                   initials=[DS] * 6 + [PR] * 4)
    drop(window, pm4, 2)
    new = next(d for d in window.cur.docs if d.path == str(pm4))
    assert new.fixes == {} and window.cur.your_pages() == 20 + 4


# ------------------------------------------------------------------ not a guess
def test_two_documents_of_one_name_get_theirs_only_when_a_path_tells_them_apart(window, tmp_path, s):
    """AM\\Transcript.pdf (the whole transcript chosen; place 10 corrected) and PM\\Transcript.pdf (place 5 corrected).
    Both back from other folders, nothing says which is which: neither gets anything, as before. AM back in its own
    place says the other is PM: each gets its own."""
    am = shared(tmp_path / "AM" / "Transcript.pdf", 20)
    pm = shared(tmp_path / "PM" / "Transcript.pdf", 10, mine=5)
    job = job_of(s, am, pm)
    first, second = sorted(job.docs, key=lambda d: d.path != str(am))
    first.correct({10: PR})
    second.correct({5: PR})
    job.page_basis = {str(am): "*"}
    origin = record_of(job)
    x, y = away(am, tmp_path / "X"), away(pm, tmp_path / "Y")

    cur = open_again(window, origin)
    drop(window, x, 1)
    drop(window, y, 2)
    assert [d.fixes for d in cur.docs] == [{}, {}] and cur.page_basis == {str(am): "*"}
    assert cur.invoice_pages() == 10 + 5  # (Pat's own pages of each)

    cur = open_again(window, origin)
    assert not cur.docs
    drop(window, x.rename(am), 1)
    drop(window, y, 2)
    fixes = {d.path: d.fixes for d in cur.docs}
    assert fixes == {str(am): {10: PR}, str(y): {5: PR}} and cur.page_basis == {str(am): "*"}
    assert cur.invoice_pages() == 20 + 6


def test_a_document_taken_out_of_the_job_brings_nothing_to_another_of_its_name(window, tmp_path, s):
    """a.pdf (the whole transcript chosen, place 10 corrected) is read when the job is opened and then taken out by
    the user: another a.pdf dropped in gets neither. b.pdf, away, dropped back from another folder, gets its own."""
    a = shared(tmp_path / "in" / "a.pdf")
    b = shared(tmp_path / "in" / "b.pdf", 10, mine=5)
    job = job_of(s, a, b)
    job.docs[0].correct({10: PR})
    job.docs[1].correct({5: PR})
    job.page_basis = {str(a): "*"}
    origin = record_of(job)
    moved = away(b, tmp_path / "elsewhere")
    cur = open_again(window, origin)
    assert [d.fixes for d in cur.docs] == [{10: PR}]
    window._remove_doc(cur, cur.docs[0])
    other = shared(tmp_path / "other" / "a.pdf", 30, mine=10)
    drop(window, other, 1)
    # (Pat's own 10 of its pages: the Pages field still holds the record's 40 total pages, b.pdf being away)
    assert cur.docs[0].fixes == {} and str(other) not in cur.page_basis and cur.own_pages() == 10
    drop(window, moved, 2)
    assert {d.path: d.fixes for d in cur.docs} == {str(other): {}, str(moved): {5: PR}}


def test_two_documents_dropped_in_of_the_name_of_one_of_the_record_s_get_nothing(tmp_path, s):
    """Either may be the record's: neither is taken for it. One of them alone is."""
    path = tmp_path / "in" / "Roe.pdf"
    x, y = shared(tmp_path / "X" / "Roe.pdf"), shared(tmp_path / "Y" / "Roe.pdf")

    def job_with(*paths) -> Job:
        job = Job(old_sources=[str(path)], page_basis={str(path): "*"}, old_fixes={str(path): ({10: PR}, False)})
        job.docs = read_docs([str(p) for p in paths], s)[0]
        back_from_record(job)
        return job
    both = job_with(x, y)
    assert [d.fixes for d in both.docs] == [{}, {}] and both.page_basis == {str(path): "*"}
    one = job_with(y)
    assert one.docs[0].fixes == {10: PR} and one.page_basis == {str(y): "*"}


# ------------------------------------------------------------------ kept meanwhile
def test_a_choice_or_a_take_corrected_since_on_the_document_itself_stays(tmp_path, s):
    path = shared(tmp_path / "in" / "Roe.pdf")
    moved = away(path, tmp_path / "elsewhere")
    job = Job(old_sources=[str(path)], page_basis={str(path): "*"}, front_owner={str(path): PR},
              old_fixes={str(path): ({10: PR}, False)})
    job.docs = read_docs([str(moved)], s)[0]
    job.docs[0].fixes = {12: PR}
    job.page_basis[str(moved)] = DS
    back_from_record(job)
    assert job.docs[0].fixes == {12: PR} and job.page_basis == {str(moved): DS}
    assert job.front_owner == {str(moved): PR} and not job.old_fixes


def test_the_takes_still_to_come_back_follow_a_folder_renamed(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    job = Job(old_sources=[str(old / "a.pdf")], old_fixes={str(old / "a.pdf"): ({5: DS}, True)})
    follow_moves([job], [(old, new)])
    assert job.old_fixes == {str(new / "a.pdf"): ({5: DS}, True)}


# ------------------------------------------------------------------ a record made while a document is away
def billed(job: Job, s, led) -> dict:
    """Generate (fill_jobs, into the test's own records): the record its invoice keeps."""
    before = {i.invoice_no for i in led.invoices()}
    fill_jobs([job], s, outputs=["invoice"], ledger=led)
    assert not job.error
    made = [i for i in led.invoices() if i.invoice_no not in before]
    return json.loads(led.origin_of(made[0].invoice_no))


def test_a_record_made_while_a_document_is_away_keeps_its_takes(window, tmp_path, s):
    """b.pdf (Pat's 5 of its 10 total pages, place 5 corrected to Pat's) away when the job opened again was billed: the
    record made then kept a.pdf's takes alone. Opened again from it with b.pdf back, 16 of Pat's pages were billed for
    17, with no word said."""
    a = shared(tmp_path / "in" / "a.pdf", 20)
    b = shared(tmp_path / "in" / "b.pdf", 10, mine=5)
    job = job_of(s, a, b)
    for d in job.docs:
        d.correct({10: PR} if d.path == str(a) else {5: PR})
    assert job.your_pages() == 11 + 6
    led = ledger_for(s)
    first = billed(job, s, led)
    gone = away(b, tmp_path / "elsewhere")
    cur = open_again(window, first)
    assert [d.path for d in cur.docs] == [str(a)]
    made = billed(cur, s, led)
    assert made["sources"] == [str(a)] and made["job"]["page_fixes"] == {str(a): {"10": PR}, str(b): {"5": PR}}
    gone.rename(b)
    cur = open_again(window, made)
    assert {d.path: d.fixes for d in cur.docs} == {str(a): {10: PR}, str(b): {5: PR}} and not cur.old_fixes
    assert cur.invoice_pages() == cur.your_pages() == 17
    assert record_of(cur)["job"]["page_fixes"] == {str(a): {"10": PR}, str(b): {"5": PR}}  # (all here: as always)


def test_so_on_an_older_record_that_counted_the_cover(window, tmp_path, s):
    """The job still waits for b.pdf, so the record made meanwhile counts the covers as its record did: b.pdf's place 6
    (its cover at place 0), place 5 once it is back."""
    a = shared(tmp_path / "in" / "a.pdf", 20)
    b = shared(tmp_path / "in" / "b.pdf", 10, mine=5, cover=COVER)
    job = job_of(s, a, b)
    next(d for d in job.docs if d.path == str(b)).correct({5: PR})
    origin = record_of(job)
    assert origin["job"]["cover_out"] is True
    del origin["job"]["cover_out"]  # (made before the cover stopped counting: the cover among the places)
    origin["job"]["page_fixes"] = {str(b): {"6": PR}}
    origin["case"]["fields"]["est_pages"][0] = "31"
    gone = away(b, tmp_path / "elsewhere")
    made = record_of(open_again(window, origin))
    assert "cover_out" not in made["job"] and made["job"]["page_fixes"] == {str(b): {"6": PR}}
    gone.rename(b)
    cur = open_again(window, made)
    back = next(d for d in cur.docs if d.path == str(b))
    assert back.fixes == {5: PR} and back.owners()[5] == PR and back.owners()[6] == DS
    assert cur.invoice_pages() == cur.your_pages() == 10 + 6 and not cur.old_places


def test_a_record_made_meanwhile_keeps_the_takes_away_only_at_places_it_counts_alike(tmp_path, s):
    """b.pdf's takes, kept without the covers, go in a record of a day settled while it is away. c.pdf's, kept with
    them, would need c.pdf's cover to be put right: left out, never at the wrong place."""
    a = shared(tmp_path / "in" / "a.pdf", 20)
    b, c = tmp_path / "in" / "b.pdf", tmp_path / "in" / "c.pdf"
    job = job_of(s, a)
    job.old_sources = [str(a), str(b), str(c)]
    job.old_fixes = {str(b): ({5: PR}, False), str(c): ({6: PR}, True)}
    made = record_of(job)
    assert made["job"]["cover_out"] is True and made["job"]["page_fixes"] == {str(b): {"5": PR}}


def trial_with_a_volume_corrected(tmp_path, s, cover: bool):
    """June 3 in two volumes (Roe PM.pdf: Pat's 5 of its 10 total pages, place 5 corrected to Pat's), June 4 (20 total
    pages, after a Min-U-Script cover when `cover` says), both firms ticked: the days and the volume's path."""
    am = shared(tmp_path / "in" / "Roe AM.pdf", 20)
    pm = shared(tmp_path / "in" / "Roe PM.pdf", 10, mine=5)
    day2 = page_numbered_transcript(tmp_path / "in" / "Roe 6-4.pdf", 20, first=200,
                                    cover=COVER.replace("June 3, 2026", "June 4, 2026") if cover else "",
                                    caption=CAPTION_DPM.replace("June 3, 2026", "June 4, 2026"))
    docs, errors = read_docs([str(am), str(pm), str(day2)], s)
    assert not errors
    days = sorted(group(docs, s), key=lambda j: j.case.get("dates"))
    assert [len(j.docs) for j in days] == [2, 1]
    for j in days:
        j.case.attorneys = [Attorney(**ALEX, checked=True), Attorney(**DANA, checked=True)]
        j.att_touched = True
    next(d for d in days[0].docs if d.path == str(pm)).correct({5: PR})
    return days, pm


def trial_again(window, origin) -> list[Job]:
    """The trial opened again from this record (a record of the days, as their invoice keeps it): its days, once read."""
    assert window.open_past_job(json.dumps(origin)) is True
    wait(window, lambda: len([j for j in window.jobs if j.docs]) == 2)
    return sorted(window.jobs, key=lambda j: j.case.get("dates"))


@pytest.mark.parametrize("cover", [True, False])
def test_a_trial_s_record_made_while_a_volume_is_away_keeps_its_takes(window, tmp_path, s, cover):
    """All on one invoice, billed again with Roe PM.pdf away, then opened from that record with it back: Pat's 15 pages
    of June 3 billed for 16. Without a cover anywhere, the record that kept the take counts the covers among the places
    (it has no "cover_out"), so the record made meanwhile waits for the volume, and counts them too."""
    days, pm = trial_with_a_volume_corrected(tmp_path, s, cover)
    origin = json.loads(json.dumps(joint_origin(days, split_rule="")))
    assert ("cover_out" in origin) is cover and origin["page_fixes"] == {str(pm): {"5": PR}}
    gone = away(pm, tmp_path / "elsewhere")
    made = json.loads(json.dumps(joint_origin(trial_again(window, origin), split_rule="")))
    assert ("cover_out" in made) is cover and made["page_fixes"] == {str(pm): {"5": PR}}
    gone.rename(pm)
    assert window.open_past_job(json.dumps(made)) is True
    wait(window, lambda: sum(len(j.docs) for j in window.jobs) == 3)
    june3 = next(j for j in window.jobs if j.case.get("dates") == "6/3/2026")
    back = next(d for d in june3.docs if d.path == str(pm))
    assert back.fixes == {5: PR} and june3.your_pages() == 10 + 6


def test_a_day_s_rows_come_back_where_they_were_in_a_record_that_waits_for_a_volume(window, tmp_path, s):
    """An older record of the trial (the cover among June 4's places: Alex B. Counsel's rows ending on places 6 and
    21, page 203 corrected to DS's at place 4). June 4 settles by its own pages, its rows on 5 and 20, the take on 3;
    the record made while Roe PM.pdf is away counts the covers for the volume's take, so it gives June 4's rows and
    take their cover back, and they are moved once, not twice."""
    days, pm = trial_with_a_volume_corrected(tmp_path, s, cover=True)
    days[1].portions = [(5, [A]), (20, [A, D])]
    day2 = days[1].docs[0]
    day2.correct({3: DS})
    origin = json.loads(json.dumps(joint_origin(days, split_rule="")))
    del origin["cover_out"]  # (made before the cover stopped counting)
    origin["orders"][1]["portions"] = [[6, [A]], [21, [A, D]]]
    origin["page_fixes"][day2.key()] = {"4": DS}
    gone = away(pm, tmp_path / "elsewhere")
    june3, june4 = trial_again(window, origin)
    assert not june4.old_places and june4.portions == [(5, [A]), (20, [A, D])] and june4.docs[0].fixes == {3: DS}
    made = json.loads(json.dumps(joint_origin([june3, june4], split_rule="")))
    assert "cover_out" not in made and made["orders"][1]["portions"] == [[6, [A]], [21, [A, D]]]
    assert made["page_fixes"] == {day2.key(): {"4": DS}, str(pm): {"5": PR}}
    gone.rename(pm)
    assert window.open_past_job(json.dumps(made)) is True
    wait(window, lambda: sum(len(j.docs) for j in window.jobs) == 3)
    june3, june4 = sorted(window.jobs, key=lambda j: j.case.get("dates"))
    assert june4.portions == [(5, [A]), (20, [A, D])] and not june4.portions_problem()
    assert june4.docs[0].fixes == {3: DS} and june4.your_pages() == 19
    assert next(d for d in june3.docs if d.path == str(pm)).fixes == {5: PR} and june3.your_pages() == 10 + 6
