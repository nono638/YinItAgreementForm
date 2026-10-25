"""Regressions found by the bug sweep before 2.11.0, each failing on the code before its fix: the list of what to
check after New job and after the changes that fix a problem (Parties set right, Invoice unticked, a day
unticked, a speed kept), a note naming the Generate button as it reads, the reason an invoice is held said the
same everywhere, the attorney table's firm tags after an edit and a zoom, the Excerpts window's tags, the speeds
question's tags of two trials, the way a trial was billed read again after a delete in the Records window, Save
a copy of Who transcribed what, F1 in Options ▾ and a click on its button while it is open, the paste box (its
divider saved, and the window losing the focus), and the job list's Case column zoomed in. All names and numbers
are made up."""
import time

import pytest
from PySide6.QtCore import QEvent, QObject, QPoint, QSize, Qt
from PySide6.QtGui import QKeySequence, QShortcut

from helpers import ROE, make_case, transcript_pdf
from minute_filler.models import Attorney

from test_job_list import EMAIL, wait as wait_for
from test_sweep_270 import A, B, C, counsel, one_day, poe, smith, window  # noqa: F401 (window: a fixture)


def pump(qt, n=8):
    for _ in range(n):
        qt.QApplication.processEvents()


def todo(win) -> list[str]:
    """The texts of the Before you generate list."""
    return [p.text for p in win._todo]


# ------------------------------------------------------------ the list of what to check


def test_new_job_takes_the_list_of_what_to_check_away(window, qt):
    """New job: the Before you generate box of the job before it goes (it stayed, its links dead, until the next
    document was read)."""
    window.add_text(EMAIL)  # (an e-mail: no pages to bill)
    wait_for(window, lambda: window.cur.docs)
    window._update_status()
    assert todo(window) and not window.todo.isHidden()
    window._clear_jobs()
    assert window._todo == [] and window.todo.isHidden()


def test_the_list_of_what_to_check_follows_parties_and_the_outputs(window, qt, tmp_path):
    """Parties set right as the list says takes its hold off the list (and the pill); Invoice unticked takes the
    invoice's problem off. Both stayed listed until something else refreshed it."""
    from minute_filler.invoice import NO_INVOICE
    job = one_day(window, qt, tmp_path, [counsel(), smith()])
    job.speeds = {A: "Daily", B: "Immediate"}
    job.parties = 3
    window._update_status()
    assert [t for t in todo(window) if t.startswith("Parties says 3")]
    window.inv_parties.setValue(2)  # (_invoice_parties_changed)
    assert not [t for t in todo(window) if t.startswith("Parties says")]
    assert "Parties says" not in window.status.text()
    window._clear_jobs()
    window.add_text(EMAIL)
    wait_for(window, lambda: window.cur.docs)
    window._update_status()
    assert NO_INVOICE in todo(window)
    window.output_boxes["invoice"].setChecked(False)  # (_outputs_changed)
    assert NO_INVOICE not in todo(window)


def test_the_list_of_what_to_check_follows_a_day_unticked_and_a_speed_kept(window, qt, tmp_path):
    """Day 2 of a case with nobody ticked holds the case's invoice: unticking day 2 (not billed now) takes that off
    day 1's list. An e-mail naming another speed: Keep (the speed chosen) takes the question off the list."""
    from test_speed_rule import DAILY
    window.add_files([str(transcript_pdf(tmp_path / "d1.pdf", pages=30)),
                      str(transcript_pdf(tmp_path / "d2.pdf", pages=24, date="June 4, 2026"))], batch=True)
    wait_for(window, lambda: len(window.jobs) == 2 and all(j.docs for j in window.jobs))
    d1, d2 = sorted(window.jobs, key=lambda j: j.case.get("dates"))
    d1.case.attorneys = [Attorney(name="Dana Smith", firm="Smith Law", party="Plaintiff", checked=True)]
    d2.case.attorneys = [Attorney(name="Dana Smith", firm="Smith Law", party="Plaintiff", checked=False)]
    window._select_job(d1)
    window._show_job()
    held = lambda: [t for t in todo(window) if t.startswith("No invoice for the case yet")]  # noqa: E731
    assert held()
    window._job_item(d2).setCheckState(0, Qt.Unchecked)  # (_job_ticked)
    assert d2.include is False and not held()
    window._clear_jobs()
    window.add_text(DAILY)
    wait_for(window, lambda: window.cur.docs)
    window._update_status()
    asked = lambda: [t for t in todo(window) if '"daily copy"' in t]  # noqa: E731
    assert asked()
    window.speed_keep.click()  # (_keep_speed -> _apply_speed)
    assert not asked()


def test_texts_name_the_generate_button_as_it_reads(window, qt, tmp_path):
    """A day invoiced already, among jobs of two cases: Who ordered's note names the button as it reads,
    "Generate this job" (it said "Generate 6/3/2026 only", the button's words only when one case is loaded)."""
    from test_speed_rule import DAILY
    job = one_day(window, qt, tmp_path, [counsel(), smith()])
    window.output_boxes["invoice"].setChecked(True)
    other = tmp_path / "lee.txt"  # (another case, read as a document of its own)
    other.write_text(DAILY.replace("Jane Roe v. Sam Poe", "Lee v. Park").replace("712345/2021", "733333/2024"),
                     encoding="utf-8")
    window.add_files([str(other)], batch=True)
    wait_for(window, lambda: len(window.jobs) == 2 and all(j.docs for j in window.jobs))
    job.invoiced = True
    window._select_job(job)
    window._show_job()
    assert window.fill_btn.text().startswith("Generate this job")
    assert "(Generate this job does)" in window.orders_info.text()


def test_the_reason_an_invoice_is_held_is_the_same_everywhere(window, qt):
    """Three firms at three speeds and Parties 4: the hold is the speeds (Job.invoice_hold checks them first), so
    the count's tooltip says so and the list's link goes to Who ordered, not to the Parties box."""
    atts = [counsel(), smith(), poe()]
    job = window.cur
    job.case = make_case({**ROE, "est_pages": "40"}, atts)
    job.speeds = {A: "Daily", B: "Immediate", C: "Regular"}
    job.parties = 4
    window._show_job()
    window._update_status()
    assert job.invoice_hold().startswith("The speeds need checking") and job.hold_kind() == "speeds"
    assert "the speeds are checked" in window.output_counts["invoice"].toolTip()
    went = []
    window._go_to = lambda w, key="": went.append(w)
    next(p for p in window._problems() if p.text == job.invoice_hold()).go()
    assert went == [window.inv_who]


# ------------------------------------------------------------ the firms' tags


def test_the_attorney_tables_tags_follow_an_edit(window, qt, tmp_path):
    """Smith Law's party typed as Defendant: its tag in the attorney table turns to the defense's, as the trial's
    marks say (it kept the plaintiff's until the job was shown again); a row that names nobody loses its tag."""
    from minute_filler.gui.badges import STRIPE_ROLE, tag_color
    from minute_filler.gui.main_window import ATT_FIELDS
    pl = dict(party="Plaintiff", checked=True)
    one_day(window, qt, tmp_path, [Attorney(name="Alex B. Counsel", firm="Counsel & Counsel", **pl),
                                   Attorney(name="Dana Smith", firm="Smith Law", **pl)])
    window._update_status()
    row = next(r for r in range(window.att.rowCount()) if window.att.item(r, 2).text() == "Smith Law")
    before = window.att.item(row, 1).data(STRIPE_ROLE)
    window.att.item(row, ATT_FIELDS.index("party")).setText("Defendant")
    now = window.att.item(row, 1).data(STRIPE_ROLE)
    assert now != before and now == tag_color(window._marks(window.cur)[B]).name()
    window.att.item(row, ATT_FIELDS.index("firm")).setText("")
    window.att.item(row, ATT_FIELDS.index("name")).setText("")
    assert window.att.item(row, 1).data(STRIPE_ROLE) is None and window.att.item(row, 1).icon().isNull()


def test_the_firm_tags_follow_the_zoom(window, qt, tmp_path):
    """At 140 % the firms' tags in Who ordered's table are drawn at the zoomed size, and it makes room for them."""
    from minute_filler.gui.badges import TAG_HEIGHT, badge_size
    from minute_filler.gui.zoom import z
    one_day(window, qt, tmp_path, [counsel(), smith()])
    try:
        window.set_zoom(1.4)
        want = QSize(*badge_size(z(TAG_HEIGHT)))
        assert window.att.iconSize() == want
        assert window.att.item(0, 1).icon().availableSizes() == [want]
    finally:
        window.set_zoom(1.0)


def test_the_excerpts_window_tags_firms_as_the_main_window_does(window, qt, tmp_path, monkeypatch):
    """Day 1 lists Counsel & Counsel first, day 2 Smith Law first; day 1 unticked (not on day 2's invoice): the
    Excerpts window of day 2 tags the firms as the main window does, by the whole trial (it went by day 2 alone,
    the tags swapped)."""
    import minute_filler.gui.badges as badges
    window.add_files([str(transcript_pdf(tmp_path / "d1.pdf", pages=30)),
                      str(transcript_pdf(tmp_path / "d2.pdf", pages=24, date="June 4, 2026"))], batch=True)
    wait_for(window, lambda: len(window.jobs) == 2 and all(j.docs for j in window.jobs))
    d1, d2 = sorted(window.jobs, key=lambda j: j.case.get("dates"))
    pl = dict(party="Plaintiff", checked=True)
    d1.case.attorneys = [Attorney(name="Alex B. Counsel", firm="Counsel & Counsel", **pl),
                         Attorney(name="Dana Smith", firm="Smith Law", **pl)]
    d2.case.attorneys = [Attorney(name="Dana Smith", firm="Smith Law", **pl),
                         Attorney(name="Alex B. Counsel", firm="Counsel & Counsel", **pl)]
    window._select_job(d1)
    window._show_job()
    d1.include = False
    window._select_job(d2)
    window._show_job()
    main = {k: m.badge for k, m in window._marks(d2).items()}
    assert main == {counsel().key(): "1", smith().key(): "2"}
    drawn = []
    real = badges.badge_icon
    monkeypatch.setattr(badges, "badge_icon", lambda mark, *a: drawn.append(mark.badge) or real(mark, *a))
    window._who_ordered(d2)
    ex = window.excerpts
    assert drawn == [main[a.key()] for a in ex.firms]
    ex.close()


def test_the_speeds_question_tags_each_trials_firms_as_that_trial_does(window, qt, monkeypatch):
    """Generate all over two trials, Smith Law a plaintiff ('1') in one and the defense ('A') in the other: the
    question about the firms' speeds tags it '1' on the first trial's rows (both were 'A')."""
    import minute_filler.batch as batch
    import minute_filler.gui.dialogs as dialogs
    from minute_filler.batch import Job, SpeedAsk
    j1, j2 = Job(), Job()
    j1.case = make_case({**ROE}, [Attorney(name="Dana Smith", firm="Smith Law", party="Plaintiff", checked=True)])
    j2.case = make_case({**ROE, "case_name": "Sam Poe v. Lee Jones", "index_no": "799999/2022"},
                        [Attorney(name="Kim Park", firm="Park PLLC", party="Plaintiff", checked=True),
                         Attorney(name="Dana Smith", firm="Smith Law", party="Defendant", checked=True)])
    window.jobs = [j1, j2]
    window.s.split_speeds = "ask"  # (Settings -> Invoice: ask me each firm's speed at Generate)
    asks = [SpeedAsk(j1, B, "Dana Smith", "", "Daily"), SpeedAsk(j2, B, "Dana Smith", "", "Daily")]
    monkeypatch.setattr(batch, "speeds_to_ask", lambda jobs, s: asks)
    seen = {}
    real = dialogs.SplitSpeedsDialog

    class Asked:
        Accepted = 1

        def __init__(self, asks_, speeds, button, parent, marks):
            seen.update(marks)

        def exec(self):
            return 0
    monkeypatch.setattr(dialogs, "SplitSpeedsDialog", Asked)
    assert window._ask_split_speeds([j1, j2]) is False
    assert seen[id(j1)][B].badge == "1" and seen[id(j2)][B].badge == "A"
    dlg = real(  # (the dialog itself shows each row's own: by its job)
        asks, [("Daily", "Daily")], "Generate all", None, seen)
    tags = [lab.text() for lab in dlg.findChildren(qt.QLabel) if "Dana Smith" in lab.text()]
    assert len(tags) == 2 and "&nbsp;1&nbsp;" in tags[0] and "&nbsp;A&nbsp;" in tags[1]


# ------------------------------------------------------------ the records, Who transcribed what


def test_a_delete_in_the_records_window_is_read_again(window, qt, tmp_path):
    """Day 1 of a trial invoiced one way, Settings now the other: day 2 is priced the first way. That invoice moved
    to the trash in the Records window: day 2 is priced as Settings say, as Generate would bill it (the window
    kept the way it had read until something else was made)."""
    from minute_filler.batch import fill_jobs
    from minute_filler.deliver import ledger_for
    from test_mixed_speeds import excerpt_example
    fill_jobs([excerpt_example()], window.s, outputs=["invoice"])
    window.s.invoice_split_rule = "same_speed"
    window._records_changed()
    job = one_day(window, qt, tmp_path, [counsel(), smith()])
    window._update_status()
    assert job.trial_rule == "make_whole"
    window.open_records()
    rw = window._records_win
    rw.delete("invoices", ledger_for(window.s).invoices(), ask=False)
    assert job.trial_rule == ""
    rw.close()


def test_save_a_copy_of_who_transcribed_what_says_when_it_fails(window, qt, monkeypatch, tmp_path):
    """Any error saving the copy is said and logged (only a file's was: a name with a character a workbook can't
    hold ended the click with nothing said), and the rows saved are those shown when it was clicked."""
    import minute_filler.gui.main_window as mw
    window._take_rows = ["the rows shown"]
    saved, said = [], []

    def choose(*a, **k):
        window._take_rows = ["a read ended meanwhile"]
        return str(tmp_path / "takes.xlsx"), "Excel workbook (*.xlsx)"
    monkeypatch.setattr(qt.QFileDialog, "getSaveFileName", choose)
    monkeypatch.setattr(qt.QMessageBox, "warning", lambda *a: said.append(a[1]))

    def fail(rows, path, csv_file=False):
        saved.append(rows)
        raise ValueError("a character a workbook can't hold")
    monkeypatch.setattr(mw, "save_takes", fail)
    window._save_takes()
    assert saved == [["the rows shown"]] and said == ["Not saved"]


# ------------------------------------------------------------ Options ▾


def test_f1_in_options_opens_the_topic_of_the_part_in_use(window, qt):
    """The box open is a window of its own: the main window's F1 never reached it. Its own F1 opens the topic of
    the panel in use; an output's tick box names its output's topic."""
    from minute_filler.gui.help_window import help_topic_of
    from minute_filler.gui.main_window import OUTPUT_TOPICS
    keys = [s for s in window.options_pop.findChildren(QShortcut) if s.key() == QKeySequence("F1")]
    assert len(keys) == 1
    asked = []
    window.show_help = asked.append
    window.resize(1400, 900)
    window.show()
    window._show_output_options()
    pump(qt)
    box = next(w for w in window.option_panels["agreement"].findChildren(qt.QWidget)
               if w.focusPolicy() != Qt.NoFocus and w.isEnabled())
    box.setFocus()
    pump(qt)
    keys[0].activated.emit()
    window.options_pop.hide()
    assert asked == [OUTPUT_TOPICS["agreement"]]
    assert help_topic_of(window.output_boxes["runsheet"]) == OUTPUT_TOPICS["runsheet"]
    assert "Outputs" in [w.text() for w in window.findChildren(qt.QLabel, "section")]  # (as the help calls it)


def test_a_click_on_options_while_its_box_is_open_only_closes_it(window, qt):
    """The click that closes a popup is passed on to what is under it: on Options ▾ it opened the box again. A
    press on the button reaching the open box is marked not to be passed on (as QComboBox does)."""
    window.resize(1400, 900)
    window.show()
    pump(qt)
    window._show_output_options()
    pump(qt)
    pop, btn = window.options_pop, window.options_btn
    centre = btn.mapToGlobal(QPoint(btn.width() // 2, btn.height() // 2))
    seen = []

    class Watch(QObject):
        def eventFilter(self, obj, e):
            if obj is pop and e.type() == QEvent.MouseButtonPress:
                seen.append(pop.testAttribute(Qt.WA_NoMouseReplay))
            return False
    watch = Watch()
    pop.installEventFilter(watch)  # (after the window's own filter: it sees the attribute the window set)
    from PySide6.QtTest import QTest
    QTest.mousePress(pop, Qt.LeftButton, Qt.NoModifier, pop.mapFromGlobal(centre))
    pump(qt)
    pop.removeEventFilter(watch)
    assert seen == [True]
    pop.hide()


# ------------------------------------------------------------ the paste box and the job list


def test_the_paste_boxs_divider_is_saved_as_it_was_before_the_box_went_to_one_line(window, qt, tmp_path):
    """Closed with a job loaded (the paste box one line), the divider saved is where it was before: the next start
    opened with the paste box squeezed."""
    from minute_filler.gui.main_window import QByteArray
    window.resize(1400, 900)
    window.show()
    pump(qt)
    before = bytes(window.left_split.saveState())
    one_day(window, qt, tmp_path, [counsel()])
    window._size_drop()
    pump(qt)
    assert window._paste_slim is True and bytes(window.left_split.saveState()) != before
    window._save_splits()
    assert bytes(QByteArray.fromBase64(window.s.window_splits["left"].encode())) == before
    try:  # a zoom while it is one line sizes the line again, and keeps the divider from before (it took the squeezed)
        window.set_zoom(1.2)
        window._save_splits()  # (closed at once: the line not sized again yet)
        assert bytes(QByteArray.fromBase64(window.s.window_splits["left"].encode())) == before
        pump(qt, 10)
        assert window._paste_slim is True
        window._save_splits()
        assert bytes(QByteArray.fromBase64(window.s.window_splits["left"].encode())) == before
    finally:
        window.set_zoom(1.0)


def test_a_zoom_while_the_paste_box_is_open_keeps_its_divider_for_later(window, qt, tmp_path):
    """Zoomed in before anything is loaded (the box open), then a job: the divider kept is the one before the box
    went to one line, as without the zoom."""
    window.resize(1400, 900)
    window.show()
    pump(qt)
    try:
        window.set_zoom(1.2)
        pump(qt, 10)
        assert window._paste_slim is False
        before = bytes(window.left_split.saveState())
        one_day(window, qt, tmp_path, [counsel()])
        window._size_drop()
        pump(qt)
        assert window._paste_slim is True and bytes(window._split_unslim) == before
    finally:
        window.set_zoom(1.0)


def test_the_paste_box_stays_open_when_the_window_loses_the_focus(window, qt, tmp_path):
    """Clicked into, then the user goes to Outlook to copy the e-mail: the empty box stays open (it went to one line
    as the window lost the focus, and the divider moved back and forth)."""
    window.add_files([str(transcript_pdf(tmp_path / "d1.pdf", pages=30))])
    wait_for(window, lambda: window.cur.docs)
    window.show()
    window.activateWindow()
    pump(qt)
    window.paste.setFocus()
    pump(qt, 5)
    assert window._paste_slim is False
    other = qt.QWidget()
    other.show()
    other.activateWindow()
    end = time.time() + 1
    while time.time() < end:
        qt.QApplication.processEvents()
        time.sleep(0.01)
    assert window._paste_slim is False
    other.close()


def test_the_case_column_keeps_room_for_the_case_zoomed_in(window, qt, tmp_path):
    """At 140 % in a 1400-wide window the Date, Day, Pages and Yours columns left the case 42 pixels (the tick box
    and "⚠ J…"): it keeps CASE_MIN, and the list scrolls sideways instead."""
    from minute_filler.gui.main_window import CASE_MIN
    from minute_filler.gui.zoom import z
    from test_main_layout import days_read_newest_first
    window.resize(1400, 900)
    window.show()
    try:
        window.set_zoom(1.4)
        pump(qt)
        days_read_newest_first(window, tmp_path)
        window._update_status()
        pump(qt, 10)
        assert window.job_list.columnWidth(0) >= z(CASE_MIN)
    finally:
        window.set_zoom(1.0)
    pump(qt, 10)
    assert window.job_list.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff  # (room again: no bar)
