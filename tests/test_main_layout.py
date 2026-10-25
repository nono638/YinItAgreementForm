"""The main window laid out as the job goes (the user, 2026-10-22: the cards felt unintuitive): the cards in the
order the work is done, named for what is in them, the field badges quiet unless something needs a look, each
firm marked by its tag and a stripe (not a shade that reads as "check this"), short texts, Generate buttons that
say what they make, the things to check listed where they can be clicked, the invoice's choices in a card of the
form and the Outputs box one row. All names are made up."""
import pytest

from helpers import pat_settings


@pytest.fixture
def window(make_window, tmp_path, monkeypatch, qt):
    """A window styled as the app styles it at start, making agreements and invoices; message boxes and the
    questions before Generate answered at once."""
    from minute_filler.gui.dialogs import ClarifyDialog
    from minute_filler.gui.theme import apply_theme
    monkeypatch.setattr(qt.QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(ClarifyDialog, "exec", lambda self: qt.QDialog.Accepted)
    apply_theme(qt.QApplication.instance(), "light")
    s = pat_settings()
    s.use_ai = s.open_after = False
    s.output_dir, s.records_dir = str(tmp_path / "out"), str(tmp_path / "records")
    s.outputs = ["agreement", "invoice"]
    return make_window(s)


def card_order(win) -> list[str]:
    """The keys of the form's folding cards, top to bottom."""
    lay = win.form_scroll.widget().layout()
    return sorted(win.cards, key=lambda k: lay.indexOf(win.cards[k]))


def test_the_cards_follow_the_job_and_say_what_is_in_them(window):
    """Who ordered first (right under the case: who, what and at what speed, in one card, the user, 2026-10-24),
    then the pages and dates; the invoice's choices before what it costs, and the trial's report last."""
    assert card_order(window) == ["case", "attorneys", "details", "invoice", "pays", "takes"]
    titles = {k: c.heading.text() for k, c in window.cards.items()}
    assert titles == {"case": "Case", "attorneys": "Who ordered", "details": "Pages and dates", "invoice": "Invoice",
                      "pays": "Who pays what", "takes": "Who transcribed what"}
    assert window.orders_edit.text() == "Excerpts…" and window.cards["attorneys"].isAncestorOf(window.orders_edit)


def test_a_badge_is_a_pill_only_for_a_value_to_look_at(window):
    """Where a value came from is said quietly ("found", "PDF", "default"...: grey, no pill); a value the AI or the
    records gave, or one the reader wasn't sure of, keeps a coloured pill, as its field is marked to look at."""
    from minute_filler.gui.theme import QSS
    from minute_filler.models import FieldState
    court = window.rows["court"]
    for st, loud in [(FieldState("Supreme", "regex", 0.9), False), (FieldState("Supreme", "default", 1.0), False),
                     (FieldState("Supreme", "you", 1.0), False), (FieldState("Supreme", "regex", 0.5), True),
                     (FieldState("Supreme", "AI", 0.9), True), (FieldState("Supreme", "records", 0.9), True)]:
        court.set_state(st)
        assert court.badge.property("loud") is loud, st
        assert court.badge.text()
    base = next(line for line in QSS.splitlines() if line.startswith("QLabel#badge {"))
    assert "border: 1px solid transparent" in base and "font-weight" not in base
    assert 'QLabel#badge[src="regex"]' not in QSS  # (a source's colour is the loud pill's only)


def test_a_folded_who_pays_what_shows_its_warning(window, qt, tmp_path):
    """Nothing to bill because something needs fixing (three speeds on the same pages): folded, Who pays what's
    line starts with the ⚠ its card shows, as the other cards' lines do."""
    from test_sweep_270 import A, B, C, counsel, one_day, poe, smith
    job = one_day(window, qt, tmp_path, [counsel(), smith(), poe()])
    job.speeds = {A: "Daily", B: "Immediate", C: "Regular"}
    window._update_status()
    assert "⚠" in window.pays.text()
    window._fold_card(window.cards["pays"], True)
    assert window.cards["pays"].summary.text().startswith("⚠ Nothing to bill yet")
    job.speeds = {A: "Daily", B: "Daily", C: "Daily"}
    window._update_status()
    window._card_summaries()
    assert window.cards["pays"].summary.text().startswith("3 invoices: ")


def test_the_generate_buttons_say_what_they_make(window, tmp_path):
    """The days of one case: "Generate 6/3/2026 only" and "Generate all 2 days" (the user, 2026-10-22: in a trial
    "Generate this job (14 files)" beside "Generate all (10 files)" was a puzzle), the files they make in their
    tooltips; a day unticked: "the 1 day ticked". A job of another case added: "this job" and "all 3 jobs"."""
    from minute_filler.batch import Job
    from helpers import ROE, make_case
    from test_gui_batch import two_days
    two_days(window, tmp_path)
    window._update_status()
    assert window.fill_btn.text().startswith("Generate 6/3/2026 only  (")
    assert window.fill_all_btn.text().startswith("Generate all 2 days  (")
    assert window.fill_btn.toolTip().startswith("Makes ") and "minute agreement form" in window.fill_btn.toolTip()
    assert "for the day shown alone" in window.fill_btn.toolTip()
    assert window.fill_all_btn.toolTip().endswith("for all 2 days (Ctrl+Shift+Enter)")
    window.jobs[1].include = False
    window._update_status()
    assert window.fill_all_btn.text().startswith("Generate the 1 day ticked  (")
    other = Job()
    other.case = make_case({**ROE, "case_name": "Smith v. Jones", "index_no": "700123/2025"})
    window.jobs[1].include = True
    window.jobs.append(other)
    window._generate_labels({"agreement": 3, "mofr": 0, "math": 2})
    assert window.fill_btn.text().startswith("Generate this job")
    assert window.fill_all_btn.text() == "Generate all 3 jobs  (5 files)"
    assert window.fill_all_btn.toolTip().startswith("Makes 5 files: 3 minute agreement forms, 2 PDFs of the math")


def att(name="", firm="", party=""):
    """An attorney row, ticked as ordering."""
    from minute_filler.models import Attorney
    return Attorney(name=name, firm=firm, party=party, checked=True)


def test_the_status_names_the_first_thing_to_check_and_reaches_what_it_missed(window, qt, tmp_path):
    """The pill names the first thing to look at and its click goes there, now also to what it never reached:
    two rows that may be one firm (the Attorneys card's question), the page count to check and a date on a court
    holiday (the warnings under those fields)."""
    from test_sweep_270 import one_day
    one_day(window, qt, tmp_path, [att("Dana Smith", "Smith Law", "Plaintiff"),
                                   att("Lee Jones", "Smith Law Group", "Plaintiff")])
    window._update_status()
    assert window._firm_q is not None
    assert window.status.text().endswith(": Are these one firm? ›") and "1 to check" in window.status.text()
    window._fold_card(window.cards["attorneys"], True)
    window.status.clicked.emit()
    assert not window.cards["attorneys"].body.isHidden() and window.firm_same.property("flash") is True
    window._answer_firm(False)
    window.pages_warn.setText("⚠ The PDF's pages may be 28, not 30: check the count")
    window._job_status()
    assert window.status.text().endswith(": Check the page count ›")
    window.status.clicked.emit()
    assert window.rows["est_pages"].edit.property("flash") is True
    window.pages_warn.setText("")
    note = window.date_notes["delivery_date"]
    note.setText("⚠ 11/11/2026 is Veterans Day, a court holiday")
    window._job_status()
    assert window.status.text().endswith(": 11/11/2026 is Veterans Day, a court… ›")
    assert "⚠ 11/11/2026 is Veterans Day, a court holiday" in window.status.toolTip()
    window.status.clicked.emit()
    assert window.rows["delivery_date"].edit.property("flash") is True


def test_the_guesses_are_one_line_and_the_pill_says_ready_with_them(window, qt, tmp_path):
    """Two fields the reader wasn't sure of are one thing to check, "2 guesses to look at: Part No., Judge /
    Justice", and the pill still says "Ready to fill", with them to review after it."""
    from minute_filler.models import FieldState
    from test_sweep_270 import counsel, one_day
    one_day(window, qt, tmp_path, [counsel()])
    for key in ("judge", "part"):
        window.rows[key].set_state(FieldState(window.rows[key].text() or "14", "regex", 0.5))
    window._job_status()
    problems = window._problems()
    assert [p.kind for p in problems] == ["review"] and problems[0].text == \
        "2 guesses to look at: Part No., Judge / Justice"
    assert window.status.text() == "Ready to fill  ·  2 to review: Part No. ›"


def test_before_you_generate_lists_everything_to_look_at_each_a_link_to_its_place(window, qt, tmp_path):
    """At the top of the form, only while something needs a look (after GOV.UK's error summary): every problem
    the status pill counts, each a link that goes to its place and lights it up; nothing while reading or before
    anything is read."""
    from test_sweep_270 import one_day
    assert window.todo.isHidden()
    one_day(window, qt, tmp_path, [att("Dana Smith", "Smith Law", "Plaintiff"),
                                   att("Lee Jones", "Smith Law Group", "Plaintiff")])
    window.rows["index_no"].choose("")
    window._update_status()
    lay = window.form_scroll.widget().layout()
    assert not window.todo.isHidden() and lay.indexOf(window.todo) < lay.indexOf(window.cards["case"])
    text = window.todo_text.text()
    assert "Before you generate" in text and "Index Number is missing" in text and "Are these one firm" in text
    assert text.count("<a href=") == len(window._problems())
    window._fold_card(window.cards["attorneys"], True)
    window._todo_clicked("1")  # (the firm question, after the field missing)
    assert not window.cards["attorneys"].body.isHidden() and window.firm_same.property("flash") is True
    window._todo_clicked("0")
    assert window.rows["index_no"].edit.property("flash") is True
    window.rows["index_no"].choose("712345/2021")
    window._answer_firm(False)
    assert window.todo.isHidden() == (not window._problems())


def test_another_day_nobody_is_ticked_on_is_said_on_the_day_shown(window, tmp_path):
    """Day by day (Settings -> Options -> Trials): day 2 shown, ticked, and day 1 not: the case gets no invoice,
    which the pill said only on day 1 ("Ready to fill" on day 2); now day 2 says it too, and the link goes to day
    1's attorneys. (A tick of the whole trial ticks day 1 too: test_trial_orders.)"""
    from PySide6.QtCore import Qt
    from test_gui_batch import two_days
    window.s.trial_orders = "day"
    window.output_boxes["invoice"].setChecked(True)
    two_days(window, tmp_path)
    day1, day2 = window.jobs
    window._select_job(day2)
    window.att.item(0, 0).setCheckState(Qt.Checked)
    window._update_status()
    first = window._problems()[0]
    assert first.text.startswith("No invoice for the case yet: nobody is ticked on 6/3/2026")
    assert "No invoice for the case yet ›" in window.status.text()
    first.go()
    assert window.cur is day1 and window.att.property("flash") is True


def test_the_invoice_is_a_card_of_the_form_and_its_speeds_are_by_the_rate_sheet(window, qt, tmp_path):
    """The invoice's choices for this job (Parties, Whose pages…, Peripherals…, the prices) are a card of the
    form, above Who pays what, which they change; hidden while Invoice is unticked. The speeds it offers are in Who
    ordered, by the Speed the agreement names (the user, 2026-10-22: the speed was chosen in places apart).
    Folded, it sums itself up."""
    from test_sweep_270 import counsel, one_day, smith
    card = window.cards["invoice"]
    assert card.isHidden()  # (nothing loaded)
    one_day(window, qt, tmp_path, [counsel(), smith()])
    window._update_status()
    assert not card.isHidden()
    assert window.inv_who is window.orders_edit and window.cards["attorneys"].isAncestorOf(window.inv_who)
    for w in (window.inv_parties, window.inv_whose, window.inv_peripherals, window.inv_info,
              window.inv_detail):
        assert card.isAncestorOf(w) and not window.foot.isAncestorOf(w)
    assert all(window.cards["attorneys"].isAncestorOf(cb) for cb in window.inv_speed_boxes.values())
    window._fold_card(card, True)
    assert window.cards["invoice"].summary.text().startswith("Parties 2")
    window._fold_card(card, False)
    window.output_boxes["invoice"].setChecked(False)
    assert card.isHidden() and window.pays_card.isHidden()
    window.output_boxes["invoice"].setChecked(True)
    assert not card.isHidden()


def test_the_outputs_box_is_one_row_and_options_open_under_it(window, qt):
    """What to make, how many files of each, Options ▾ and the Generate buttons, in one row at the bottom (the
    form gets the room the four panels took); each output's standing choices in Options ▾."""
    foot = window.foot
    assert all(foot.isAncestorOf(b) for b in window.output_boxes.values())
    assert foot.isAncestorOf(window.fill_btn) and foot.isAncestorOf(window.options_btn)
    window.resize(1400, 900)
    window.show()
    qt.QApplication.processEvents()
    assert foot.height() <= window.fill_btn.height() * 2.5
    pop = window.options_pop
    for w in (window.form_choice, window.per_email, window.sign_rep, window.mofr_division, window.rs_existing,
              window.rs_folder):
        assert pop.isAncestorOf(w)
    window._show_output_options()
    assert pop.isVisible()
    pop.hide()
    assert not hasattr(window, "vsplit") and not hasattr(window, "outputs_body")


def test_the_attorneys_show_without_scrolling_at_1400_by_900(window, qt, tmp_path):
    """Who ordered (the attorney table) is the second card and the Outputs box one row: at 1400 x 900 the table is
    in sight with a day loaded, without scrolling the form (before, the details card and four panels of options
    pushed it out of sight)."""
    from test_sweep_270 import counsel, one_day, smith
    window.resize(1400, 900)
    window.show()
    one_day(window, qt, tmp_path, [counsel(), smith()])
    window._update_status()
    for _ in range(5):
        qt.QApplication.processEvents()
    form = window.form_scroll
    assert form.verticalScrollBar().value() == 0
    bottom = window.att.mapTo(form.widget(), window.att.rect().bottomLeft()).y()
    assert bottom <= form.viewport().height()


@pytest.mark.parametrize("zoom", [1.0, 1.4])
def test_the_outputs_row_fits_the_smallest_window(window, qt, tmp_path, zoom):
    """At the window's least width (1080 at 100 %, as zoomed), the Outputs row with every output ticked and both
    Generate buttons of two days of a case is no wider: the buttons go on a row of their own under it, and back at
    the end of it in a wide window. The page never scrolls sideways for it."""
    from minute_filler.gui.zoom import z
    from test_gui_batch import two_days
    for key in window.output_boxes:
        window.output_boxes[key].setChecked(True)
    two_days(window, tmp_path)
    window.show()
    window.set_zoom(zoom)
    for width, below in ((z(1080), True), (z(2400), False)):
        window.resize(width, 800)
        for _ in range(5):
            qt.QApplication.processEvents()
        window._place_foot()
        page = window.page_scroll
        assert page.widget().minimumSizeHint().width() <= page.viewport().width(), width
        assert (window.foot_row2.indexOf(window.gen_box) >= 0) is below, width


def test_the_result_cards_look_like_results_and_the_report_starts_folded(window):
    """Who pays what and Who transcribed what show results to read, not fields to fill: a look of their own (a
    tint, in both themes); Who transcribed what (a report, its totals on its folded line) starts folded, also for
    a settings file from before v16 (one of v16 keeps it unfolded if the user unfolded it)."""
    from minute_filler.gui.theme import DARK, LIGHT, QSS
    from minute_filler.settings import Settings
    assert window.pays_card.property("result") is True and window.takes_card.property("result") is True
    assert not window.cards["case"].property("result")
    assert 'QFrame#card[result="true"]' in QSS and all("result_bg" in t for t in (LIGHT, DARK))
    assert window.cards["takes"].body.isHidden()
    assert Settings().folded_cards == ["takes"]
    assert "takes" in Settings.from_dict({"settings_version": 15, "folded_cards": ["case"]}).folded_cards
    assert Settings.from_dict({"settings_version": 16, "folded_cards": []}).folded_cards == []  # (unfolded since)


def test_the_paste_box_is_one_line_once_a_job_is_loaded(window, qt, tmp_path):
    """Once a job is loaded the paste box is one line, "Paste an e-mail or notes…", without its label and Extract
    from text, so the job list has the room (the user, 2026-10-22); text in it opens it again, and New job too."""
    from minute_filler.gui.main_window import PASTE_SLIM
    from test_sweep_270 import counsel, one_day
    assert not window.paste_label.isHidden() and not window.extract_btn.isHidden()
    one_day(window, qt, tmp_path, [counsel()])
    window._size_drop()
    assert window.paste_label.isHidden() and window.extract_btn.isHidden()
    assert window.paste.placeholderText() == PASTE_SLIM and window.paste.maximumHeight() < 60
    window.paste.setPlainText("Please send the minutes of 6/4/2026.")
    assert not window.paste_label.isHidden() and not window.extract_btn.isHidden()
    window.paste.setPlainText("")
    assert window.paste_label.isHidden()
    window.new_job()
    window._size_drop()
    assert not window.paste_label.isHidden() and window.paste.maximumHeight() > 1000


# ------------------------------------------------------------------ the job list: sorted, and its Day column

def days_read_newest_first(window, tmp_path):
    """Four days of a case read 10/21, 10/20, 10/19, 10/14 (a folder can come in that way), with pages 87, 109,
    145, 120: the jobs in that order."""
    from helpers import transcript_pdf
    from test_job_list import wait
    files = [transcript_pdf(tmp_path / f"d{i}.pdf", pages=n, date=d) for i, (n, d) in enumerate(
        [(8, "October 21, 2026"), (10, "October 20, 2026"), (14, "October 19, 2026"), (12, "October 14, 2026")])]
    window.add_files([str(f) for f in files], batch=True)
    wait(window, lambda: len(window.jobs) == 4 and all(j.docs for j in window.jobs))


def shown(window, col=1) -> list[str]:
    """The job list's rows top to bottom, as the text of one column (1: the Date)."""
    lst = window.job_list
    return [lst.topLevelItem(i).text(col) for i in range(lst.topLevelItemCount())]


def test_the_job_list_is_by_date_oldest_first_and_sorts_by_any_heading(window, tmp_path, make_window):
    """The days in the order of the calendar, whatever order they were read in, and the earliest shown first (the
    user, 2026-10-22: newest first was the wrong way round, and the headings couldn't be clicked); a heading sorts
    by it, as dates and numbers (10 before 8 the other way round as text), and the choice is kept."""
    from PySide6.QtCore import Qt
    from minute_filler.gui.main_window import JOB_DATE, JOB_PAGES
    from minute_filler.settings import Settings
    days_read_newest_first(window, tmp_path)
    assert [j.case.get("dates") for j in window.jobs][0] == "10/21/2026"  # (read newest first)
    assert shown(window) == ["10/14/2026", "10/19/2026", "10/20/2026", "10/21/2026"]
    assert window.cur.case.get("dates") == "10/14/2026"
    assert window.job_list.header().sectionsClickable()
    window.job_list.sortByColumn(JOB_DATE, Qt.DescendingOrder)
    assert shown(window) == ["10/21/2026", "10/20/2026", "10/19/2026", "10/14/2026"]
    window.job_list.sortByColumn(JOB_PAGES, Qt.AscendingOrder)
    assert shown(window, JOB_PAGES) == ["8", "10", "12", "14"]  # (as numbers: "10" < "8" as text)
    assert Settings.load().job_sort == ["Pages", "ascending"]
    window._refresh_jobs()  # (rebuilt: sorted as chosen)
    assert shown(window, JOB_PAGES) == ["8", "10", "12", "14"]
    again = make_window(Settings.load())
    assert again._job_sort() == (JOB_PAGES, Qt.AscendingOrder)


def test_the_day_column_says_the_weekday_and_can_be_hidden(window, tmp_path, make_window):
    """The Day column says each date's weekday ("Wed" for 10/14/2026) and is narrow; View → Show the day of the
    week in the job list hides it, and the choice is kept for the next start."""
    from minute_filler.gui.main_window import JOB_DAY
    from minute_filler.settings import Settings
    days_read_newest_first(window, tmp_path)
    assert shown(window, JOB_DAY) == ["Wed", "Mon", "Tue", "Wed"]  # (10/14, 10/19, 10/20, 10/21/2026)
    assert not window.job_list.isColumnHidden(JOB_DAY)
    # (as wide as "Wed": sized by Qt, each column kept room for the sort arrow and the case name got 2 letters)
    assert window.job_list.columnWidth(JOB_DAY) < 60
    window._show_weekday(False)
    assert window.job_list.isColumnHidden(JOB_DAY) and not window.weekday_action.isChecked()
    assert Settings.load().job_weekday is False
    assert make_window(Settings.load()).s.job_weekday is False


def test_a_jobs_documents_stay_in_the_order_read_however_the_list_is_sorted(window, tmp_path):
    """A job's documents (the rows under it) stay in the order they were read, the PDF before the pasted text,
    whichever way the list is sorted by date."""
    from PySide6.QtCore import Qt
    from minute_filler.gui.main_window import JOB_DATE
    from test_job_list import EMAIL, wait
    from helpers import transcript_pdf
    window.add_files([str(transcript_pdf(tmp_path / "Roe 6-3-2026.pdf", pages=30))])
    wait(window, lambda: len(window.cur.docs) == 1)
    window.add_text(EMAIL)
    wait(window, lambda: len(window.cur.docs) == 2)
    row = window._job_item(window.cur)
    for order in (Qt.AscendingOrder, Qt.DescendingOrder):
        window.job_list.sortByColumn(JOB_DATE, order)
        assert [row.child(i).text(0) for i in range(2)] == ["Roe 6-3-2026.pdf", "Pasted text 1"]


def test_rows_without_a_sort_key_sort_by_their_text(qt):
    """A row compared before its keys are set (one added while the list is sorted) sorts by its text: Qt's own
    comparison, called from the subclass's, crashed the app (PySide: found by the revert proof, 2026-10-22)."""
    from PySide6.QtCore import Qt
    from minute_filler.gui.main_window import DocItem, JobItem
    t = qt.QTreeWidget()
    t.setColumnCount(2)
    for x in "bca":
        JobItem(t, [x, x])
    t.setSortingEnabled(True)
    t.sortByColumn(0, Qt.AscendingOrder)
    assert [t.topLevelItem(i).text(0) for i in range(3)] == ["a", "b", "c"]
    top = t.topLevelItem(0)
    for x in "yx":
        DocItem(top, [x, ""])
    t.sortByColumn(0, Qt.AscendingOrder)
    assert [top.child(i).text(0) for i in range(2)] == ["x", "y"]
