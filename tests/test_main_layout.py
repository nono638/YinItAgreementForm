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
    """Who ordered first (Attorneys right under the case), then the speed, pages and dates; the invoice's cards
    with what was ordered before what it costs, and the trial's report last."""
    assert card_order(window) == ["case", "attorneys", "details", "invoice", "orders", "pays", "takes"]
    titles = {k: c.heading.text() for k, c in window.cards.items()}
    assert titles == {"case": "Case", "attorneys": "Attorneys: tick who ordered", "details": "Speed, pages and dates",
                      "invoice": "Invoice", "orders": "Who ordered what", "pays": "Who pays what",
                      "takes": "Who transcribed what"}
    assert window.orders_edit.text() == "Excerpts…"


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
    tooltips; a day unticked: "the 1 day ticked". Jobs of different cases: "this job" and "all 2 jobs"."""
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
    """Day 2 shown, ticked, and day 1 not: the case gets no invoice, which the pill said only on day 1 ("Ready to
    fill" on day 2); now day 2 says it too, and the link goes to day 1's attorneys."""
    from PySide6.QtCore import Qt
    from test_gui_batch import two_days
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
    """The invoice's choices for this job (Parties, Excerpts…, Whose pages…, Peripherals…, the prices) are a card
    of the form, above Who ordered what and Who pays what, which they change; hidden while Invoice is unticked.
    The speeds it offers are under the rate sheet, by the Speed the agreement names (the user, 2026-10-22: the speed
    was chosen in places apart). Folded, it sums itself up."""
    from test_sweep_270 import counsel, one_day, smith
    card = window.cards["invoice"]
    assert card.isHidden()  # (nothing loaded)
    one_day(window, qt, tmp_path, [counsel(), smith()])
    window._update_status()
    assert not card.isHidden()
    for w in (window.inv_parties, window.inv_who, window.inv_whose, window.inv_peripherals, window.inv_info,
              window.inv_detail):
        assert card.isAncestorOf(w) and not window.foot.isAncestorOf(w)
    assert all(window.cards["details"].isAncestorOf(cb) for cb in window.inv_speed_boxes.values())
    window._fold_card(card, True)
    assert window.cards["invoice"].summary.text().startswith("Parties 2")
    window._fold_card(card, False)
    window.output_boxes["invoice"].setChecked(False)
    assert card.isHidden() and window.orders_card.isHidden() and window.pays_card.isHidden()
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
