"""The list on the left of the window (off screen): a row per job (of a batch, or the job on screen alone) with
its case, date, day of the week, the transcript's own pages and the user's; under a job of several documents
a row per document; the tick of each job of a batch, a click on a document's row showing its job, a job's
documents folded away staying so, an unticked job greyed and the hover text of the ticks and Yours, and
right-click's Move to a job of its own, Remove from job and Remove this job. Also Job.your_pages (the Yours
column) without the window. Made-up documents only.
(The list's sorting and its Day column: tests/test_main_layout.py.)"""
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import Qt  # noqa: E402

from helpers import invoice_text, page_numbered_transcript, pat_settings, transcript_pdf  # noqa: E402
from minute_filler.gui.main_window import JOB_COLS, JOB_DATE, JOB_PAGES, JOB_YOURS  # noqa: E402

EMAIL = """From: Dana Smith <dsmith@smithlaw.example>
Sent: Wednesday, June 3, 2026 4:12 PM
To: Pat Reporter <preporter@example.com>
Subject: minutes - Roe v. X.Y. Holding

Please send the minutes for Jane Roe v. X.Y. Holding Corporation, Index 712345/2021, of 6/3/2026, daily copy.
"""


@pytest.fixture
def window(tmp_path, monkeypatch, make_window):
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", lambda self: 0)  # no dialogs waiting for a click
    s = pat_settings()
    s.use_ai = s.open_after = False
    s.output_dir = str(tmp_path / "out")
    s.save_math = "off"
    return make_window(s)


def wait(win, until, seconds=30):
    """Runs the Qt event loop until no background task is left and until() is true."""
    end = time.time() + seconds
    while time.time() < end:
        QtWidgets.QApplication.processEvents()
        if not win.runner._live and until():
            return
        time.sleep(0.01)
    raise AssertionError("timed out")


def cells(item) -> list[str]:
    """A row's text in every column: Case / file, Date, Day, Total pages, Your pages."""
    return [item.text(c) for c in range(len(JOB_COLS))]


def row_of(win, job):
    return win._job_item(job)


def test_two_days_are_a_row_each_with_their_pages(window, tmp_path):
    a = transcript_pdf(tmp_path / "day1.pdf", pages=30)
    b = transcript_pdf(tmp_path / "day2.pdf", pages=24, date="June 4, 2026")
    window.add_files([str(a), str(b)], batch=True)
    wait(window, lambda: len(window.jobs) == 2)
    lst = window.job_list
    first, second = (row_of(window, j) for j in window.jobs)
    assert lst.topLevelItemCount() == 2 and window.jobs_label.text().startswith("Jobs: 2")
    assert cells(first)[JOB_DATE:] == ["6/3/2026", "Wed", "30", "30"]  # (Pat Reporter's alone: every page is yours)
    assert cells(second)[JOB_DATE:] == ["6/4/2026", "Thu", "24", "24"]
    assert first.text(0).endswith("Jane Roe v. X.Y. Holding Corporation")
    assert "712345/2021" in first.toolTip(0) and "712345/2021" in first.toolTip(JOB_YOURS)  # (hover for the rest)
    assert first.childCount() == second.childCount() == 0 and not lst.rootIsDecorated()  # (one document each)
    assert not lst.isColumnHidden(JOB_PAGES) and not lst.isColumnHidden(JOB_YOURS)
    assert first.checkState(0) == Qt.Checked


def test_a_transcript_of_two_reporters_shows_the_pages_you_wrote(window, tmp_path):
    pdf = transcript_pdf(tmp_path / "shared.pdf", pages=30, initials=["pr"] * 18 + ["ds"] * 12)
    window.add_files([str(pdf)])
    wait(window, lambda: len(window.cur.docs) == 1)
    row = row_of(window, window.cur)
    assert cells(row)[JOB_PAGES:] == ["30", "18"] and window.jobs_label.text() == "This job"
    assert row.data(0, Qt.CheckStateRole) is None  # (a single job: no tick, Generate makes it)
    window.cur.own = ()  # the user's initials not known: whose are the pages?
    window._refresh_job_labels()
    assert row.text(JOB_YOURS) == "?"


def test_every_page_count_says_whose_pages(window, tmp_path):
    """The user, 2026-10-30: a transcript is often written by several reporters, so a count says whose pages: the
    job list's headings, Who ordered's and Who transcribed what's columns, the Invoice card's line (the pages it
    bills: the user's own) and each reporter's total under the takes, the user's marked."""
    from minute_filler.gui.main_window import ATT_COLS, ATT_PAGES, TAKE_COLS
    pdf = transcript_pdf(tmp_path / "shared.pdf", pages=30, initials=["pr"] * 18 + ["ds"] * 12)
    window.add_files([str(pdf)])
    wait(window, lambda: len(window.cur.docs) == 1)
    head = window.job_list.headerItem()
    assert [head.text(c) for c in (JOB_PAGES, JOB_YOURS)] == ["Total\npages", "Your\npages"]  # (a narrow list)
    assert ATT_COLS[ATT_PAGES] == "Your pages" and TAKE_COLS[3] == "Pages in take"
    window.output_boxes["invoice"].setChecked(True)
    window._refresh_outputs()
    assert window.inv_info.text().startswith("18 of your pages")
    window._update_status()
    assert window.takes_info.text() == "This day: Pat 18 pages (you) · DS 12 pages"


def test_pages_typed_in_are_yours(window, tmp_path):
    window.add_files([str(transcript_pdf(tmp_path / "t.pdf", pages=30))])
    wait(window, lambda: len(window.cur.docs) == 1)
    window.rows["est_pages"].choose("12")
    row = row_of(window, window.cur)
    assert cells(row)[JOB_PAGES:] == ["30", "12"]
    assert "Your pages: the 12 pages typed in Est. number of pages" in row.toolTip(0)


def test_a_job_of_two_documents_lists_them_and_moves_one_out(window, tmp_path):
    window.add_files([str(transcript_pdf(tmp_path / "Roe 6-3-2026.pdf", pages=30))])
    wait(window, lambda: len(window.cur.docs) == 1)
    window.add_text(EMAIL)
    wait(window, lambda: len(window.cur.docs) == 2)
    lst = window.job_list
    assert lst.topLevelItemCount() == 1 and window.jobs_label.text() == "This job"
    row = row_of(window, window.cur)
    assert row.childCount() == 2 and row.isExpanded() and lst.rootIsDecorated()
    assert cells(row.child(0)) == ["Roe 6-3-2026.pdf", "6/3/2026", "Wed", "30", "30"]
    assert cells(row.child(1)) == ["Pasted text 1", "e-mail", "", "", ""]
    assert row.child(1).toolTip(0).startswith("From: Dana Smith")  # (the text read from it)
    email = window.cur.docs[1]
    window._remove_doc(window.cur, email, own_job=True)  # right-click → Move to a job of its own
    assert len(window.jobs) == 2 and window.jobs[1].docs == [email]
    assert lst.topLevelItemCount() == 2 and all(lst.topLevelItem(i).childCount() == 0 for i in range(2))
    moved = row_of(window, window.jobs[1])  # (the list is sorted by date, then case: not in the order read)
    assert moved.text(JOB_DATE) == "6/3/2026" and moved.text(JOB_YOURS) == ""
    window._remove_job(window.jobs[1])  # right-click → Remove this job
    assert len(window.jobs) == 1 and lst.topLevelItemCount() == 1


def test_remove_from_job_takes_a_document_out(window, tmp_path):
    window.add_files([str(transcript_pdf(tmp_path / "t.pdf", pages=30))])
    wait(window, lambda: len(window.cur.docs) == 1)
    window.add_text(EMAIL)
    wait(window, lambda: len(window.cur.docs) == 2)
    window._remove_doc(window.cur, window.cur.docs[1])
    row = row_of(window, window.cur)
    assert [d.ing.name for d in window.cur.docs] == ["t.pdf"] and row.childCount() == 0
    window._remove_doc(window.cur, window.cur.docs[0])  # its last document: no row left
    assert window.job_list.topLevelItemCount() == 0


def test_an_unticked_job_is_greyed_and_the_list_says_what_ticks_and_yours_mean(window, tmp_path):
    """The user, 2026-10-23: unticked should look it, "subtle, but something" (the theme's muted text, its
    documents too, in the colour of the theme in use), and hovering says what a tick does and what Yours counts
    (the pages with your initials at the foot of the page)."""
    from PySide6.QtGui import QColor, QPalette
    from minute_filler.gui.main_window import JOB_TIPS, TICK_TIP, TICKED_ROW, UNTICKED_ROW, YOURS_TIP
    a = transcript_pdf(tmp_path / "day1.pdf", pages=30)
    b = transcript_pdf(tmp_path / "day2.pdf", pages=24, date="June 4, 2026")
    c = transcript_pdf(tmp_path / "day2 vol 2.pdf", pages=10, date="June 4, 2026")
    window.add_files([str(a), str(b), str(c)])
    wait(window, lambda: len(window.jobs) == 2 and sum(len(j.docs) for j in window.jobs) == 3)
    one, two = sorted(window.jobs, key=lambda j: len(j.docs))
    row = row_of(window, two)

    def greyed(item) -> list:
        return [item.data(c, Qt.ForegroundRole) for c in range(len(JOB_COLS))]

    assert greyed(row) == [None] * len(JOB_COLS) and row.childCount() == 2
    assert row.toolTip(0).startswith(TICKED_ROW) and row.toolTip(JOB_YOURS).startswith(YOURS_TIP)
    assert row.child(0).toolTip(JOB_YOURS).startswith(YOURS_TIP)
    row.setCheckState(0, Qt.Unchecked)
    row = row_of(window, two)
    muted = QtWidgets.QApplication.palette().color(QPalette.PlaceholderText)
    assert all(b is not None and b.color() == muted for b in greyed(row) + greyed(row.child(1)))
    assert greyed(row_of(window, one)) == [None] * len(JOB_COLS)
    assert row.toolTip(0).startswith(UNTICKED_ROW)
    assert "initials at the foot of the page" in JOB_TIPS["Your pages"] and TICK_TIP in JOB_TIPS["Case / file"]
    assert TICK_TIP in window.jobs_label.toolTip() and YOURS_TIP in window.jobs_label.toolTip()
    app = QtWidgets.QApplication.instance()
    was = app.palette()
    try:  # another theme: greyed in its colour
        pal = QPalette(was)
        pal.setColor(QPalette.PlaceholderText, QColor("#123456"))
        app.setPalette(pal)
        QtWidgets.QApplication.processEvents()
        assert greyed(row_of(window, two))[0].color() == QColor("#123456")
    finally:
        app.setPalette(was)
    row_of(window, two).setCheckState(0, Qt.Checked)
    assert greyed(row_of(window, two)) == [None] * len(JOB_COLS)


def test_a_batch_of_e_mails_ticks_switches_and_folds(window, tmp_path):
    def write(name, **kw):
        (tmp_path / name).write_text(invoice_text(**kw))
        return str(tmp_path / name)

    window.add_files([write("a.txt"), write("c.txt", title="Smith v. Jones", index="712222/2024", date="5/22/2026"),
                      write("b.txt", title="Roe v Doe", index="700001-2025", date="6-1-2026")], batch=True)
    wait(window, lambda: len(window.jobs) == 2)
    lst = window.job_list
    two, one = window.jobs  # (a.txt and c.txt are one job)
    assert lst.isColumnHidden(JOB_PAGES) and lst.isColumnHidden(JOB_YOURS)  # no transcript, no pages typed
    row = row_of(window, one)
    row.setCheckState(0, Qt.Unchecked)
    assert not one.include
    row.setCheckState(0, Qt.Checked)
    assert one.include
    lst.setCurrentItem(row_of(window, two).child(1))  # a document of the other job: that job is shown
    assert window.cur is two and window.rows["index_no"].text() == "712222/2024"
    lst.setCurrentItem(row)
    assert window.cur is one
    row_of(window, two).setExpanded(False)  # folded away by the user...
    window._refresh_jobs()
    assert not row_of(window, two).isExpanded() and row_of(window, two).childCount() == 2  # ...stays folded


def test_your_pages_without_the_window(tmp_path):
    from minute_filler.batch import Job, make_doc, remerge
    from minute_filler.extract_regex import RegexExtractor
    from minute_filler.ingest import ingest_file

    s = pat_settings()

    def job_of(make=transcript_pdf, **kw):
        ing = ingest_file(make(tmp_path / f"{len(list(tmp_path.iterdir()))}.pdf", **kw))
        job = Job(docs=[make_doc(ing, RegexExtractor(s.profile).extract(ing), s)])
        remerge(job, s)
        return job

    alone = job_of(pages=30)
    assert alone.your_pages() == alone.your_pages_of(alone.docs[0]) == 30
    shared = job_of(pages=30, initials=["pr"] * 18 + ["ds"] * 12)
    assert shared.your_pages() == 18
    shared.page_basis = {shared.docs[0].key(): "ds"}  # Whose pages... bills DS's: still 18 of them are yours
    assert shared.your_pages() == 18 and shared.own_pages() == 12
    shared.own = ()
    assert shared.your_pages() is None
    # (transcript_pdf's cover carries "pr": this one's first 4 pages carry no initials) whose are they?
    late = job_of(page_numbered_transcript, pages=20, initials=[""] * 4 + ["pr"] * 8 + ["ds"] * 8)
    assert late.docs[0].front_pages() == 4 and late.your_pages() is None
    late.front_owner = {late.docs[0].key(): "pr"}  # Whose pages... says: the user's
    assert late.your_pages() == 12
    other = job_of(pages=30, initials=["ds"] * 30)  # another reporter's alone
    assert other.your_pages() == 0
