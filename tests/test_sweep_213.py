"""Regressions found by the 2.13.0 sweep of the Who ordered card (a tick is the whole trial): speeds carried to the
days a firm is added to, Excerpts' runs kept in step with an untick, invoiced days that still order a firm, the
records keeping the runs, the half tick's cycle, day-by-day mode, Generate's speeds as the rows show them and put
back on Go back, and the words of the Invoice card and the Excerpts window. All names and numbers are made up."""
import pytest

from minute_filler.batch import (_date_key, group, joint_origin, order_firm,
                                 put_back_orders, set_firm_speed, spread_orders, tick_firm)
from minute_filler.excerpts import Run, case_days, firms_of, store
from minute_filler.models import SRC_USER, FieldState

from test_trial_orders import key_of, read_days, settings
from test_who_ordered_card import choose, click, ordering, pump, row_of, state, three_days, wait

POE = """From: Alex B. Counsel <acounsel@counsel.example>
Sent: Monday, June {d}, 2026 9:30 AM
To: Pat Reporter <preporter@example.com>
Subject: minutes - Poe v. Roe

Please send the minutes of 6/{d}/2026 in Sam Poe v. Jane Roe, Index No. 799999/2022, Part 14.

Alex B. Counsel
"""


@pytest.fixture
def s(tmp_path):
    return settings(tmp_path, "a")


@pytest.fixture
def trial(tmp_path, s):
    return sorted(group(read_days(tmp_path, s), s), key=lambda j: _date_key(j.case.get("dates")))


def keys(trial):
    return key_of(trial[0], "Counsel"), key_of(trial[0], "Advocate")


# ------------------------------------------------------------ the model (batch.py)

def test_the_whole_trial_carries_the_firms_speed_to_the_days_it_adds(s, trial):
    """A firm made "Only" a day, its speed chosen there, then the whole trial: every day at that speed (the row
    said Daily, Generate of another day billed "they choose")."""
    counsel, _ = keys(trial)
    order_firm(trial, counsel, False, shown=trial[0])
    set_firm_speed(trial, counsel, "Daily")
    order_firm(trial, counsel, True, shown=trial[0])
    assert [j.speeds.get(counsel) for j in trial] == ["Daily"] * 4


def test_a_day_its_document_ticks_gets_the_firms_speed(s, trial):
    """A day already ticking a standing firm (its document does) gets the firm's speed from the other days."""
    counsel, _ = keys(trial)
    tick_firm(trial, counsel, True, s, shown=trial[0])
    set_firm_speed(trial, counsel, "Daily")
    trial[3].speeds.pop(counsel)
    assert spread_orders(trial, s) and trial[3].speeds[counsel] == "Daily"


def test_the_forms_speed_of_an_invoiced_day_isnt_spread(s, trial):
    """The forms' speed the user chose on an invoiced day (since changed, or put back with ↺ on the others) isn't
    made every day's again."""
    counsel, _ = keys(trial)
    tick_firm(trial, counsel, True, s, shown=trial[0])
    trial[0].case.fields["delivery"] = FieldState("Daily", SRC_USER, 1.0, ["Daily"])
    trial[0].invoiced = True
    spread_orders(trial, s)
    assert all(j.case.fields["delivery"].source != SRC_USER for j in trial[1:])


def test_only_a_day_takes_the_firm_out_of_the_other_days_runs(s, trial):
    """A firm made "Only" one day is taken out of the other days' Excerpts runs, so their invoices aren't held
    ("it names an attorney no longer ticked")."""
    counsel, advocate = keys(trial)
    tick_firm(trial, counsel, True, s, shown=trial[0])
    tick_firm(trial, advocate, True, s, shown=trial[0])
    day = next(d for d in case_days(trial) if d.job is trial[1])
    store(day, [Run(day, 1, 10, [counsel, advocate]), Run(day, 11, day.pages, [counsel])], firms_of(trial), s)
    order_firm(trial, advocate, False, shown=trial[0])
    assert not trial[1].portions_problem() and advocate not in trial[1].ticked_keys()
    tick_firm(trial, counsel, False, s, shown=trial[0])
    assert not any(counsel in keys for _, keys, *_ in trial[1].portions)


def test_an_untick_leaves_an_invoiced_day_ordering_it_alone(s, trial):
    """A firm unticked while an invoiced day still orders it isn't spread back to the other days by that day."""
    counsel, _ = keys(trial)
    tick_firm(trial, counsel, True, s, shown=trial[0])
    trial[0].invoiced = True
    tick_firm(trial, counsel, False, s, shown=trial[1])
    spread_orders(trial, s)
    assert [counsel in j.ticked_keys() for j in trial] == [True, False, False, False]


def test_day_by_day_picks_stay_when_the_setting_turns_to_the_trial(s, trial):
    """Ticked day by day ("day"), a firm's days are kept when the setting turns to the whole trial."""
    counsel, _ = keys(trial)
    s.trial_orders = "day"
    tick_firm(trial, counsel, True, s, shown=trial[1])
    s.trial_orders = "trial"
    spread_orders(trial, s)
    assert [counsel in j.ticked_keys() for j in trial] == [False, True, False, False]


def test_a_trial_opened_again_keeps_its_excerpts_runs(s, trial, tmp_path):
    """The record of a trial keeps each day's runs, so a day split between firms comes back split, not ordered
    whole by both."""
    counsel, advocate = keys(trial)
    tick_firm(trial, counsel, True, s, shown=trial[0])
    tick_firm(trial, advocate, True, s, shown=trial[0])
    day = next(d for d in case_days(trial) if d.job is trial[1])
    store(day, [Run(day, 1, 10, [counsel]), Run(day, 11, day.pages, [advocate])], firms_of(trial), s)
    origin = joint_origin(trial)
    again = sorted(group(read_days(tmp_path, s, name="again"), s), key=lambda j: _date_key(j.case.get("dates")))
    put_back_orders(again, origin, s)
    assert again[1].portions == trial[1].portions and not again[1].portions_problem()


# ------------------------------------------------------------ the window

@pytest.fixture
def window(tmp_path, monkeypatch, make_window):
    from PySide6 import QtWidgets
    from helpers import pat_settings
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", lambda self: 0)
    s = pat_settings()
    s.use_ai = s.open_after = False
    s.output_dir = str(tmp_path / "out")
    s.records_dir = str(tmp_path / "records")
    s.outputs = ["agreement"]
    return make_window(s)


def test_excerpts_of_one_day_pins_the_trials_other_days(window, tmp_path):
    """Excerpts showing one day (invoices day by day): a firm given pages of it alone doesn't order the trial's
    other days, which it isn't shown on (they would be spread to it)."""
    from minute_filler.batch import spread_orders
    window.s.invoice_joint = False
    days = three_days(window, tmp_path)
    click(window, "Counsel")
    window._who_ordered(days[1])
    ex = window.excerpts
    assert [d.job for d in ex.days] == [days[1]]
    counsel, advocate = key_of(days[1], "Counsel"), key_of(days[1], "Advocate")
    day = ex.days[0]
    ex._keep(day, [Run(day, 1, 5, [counsel, advocate]), Run(day, 6, day.pages, [counsel])])
    spread_orders(days, window.s)
    assert ordering(days, "Advocate") == [False, True, False]
    ex.close()


def test_generate_puts_back_the_speeds_it_set_when_nothing_is_made(window, tmp_path, monkeypatch):
    """Generate sets each firm's speed as its row shows it ("shown"), and takes it off again on Go back: the
    rows still follow the forms' Speed."""
    window.output_boxes["invoice"].setChecked(True)
    days = three_days(window, tmp_path)
    click(window, "Counsel")
    click(window, "Advocate")
    window.s.preview_before_saving = True
    monkeypatch.setattr(type(window), "_preview", lambda *a, **k: False)
    window.fill()
    assert not any(j.speeds for j in days)


def test_generate_all_puts_back_the_speeds_on_the_previews_go_back(window, tmp_path, monkeypatch):
    """Generate all's preview Go back: the speeds it set are taken off again."""
    window.output_boxes["invoice"].setChecked(True)
    days = three_days(window, tmp_path)
    click(window, "Counsel")
    click(window, "Advocate")
    window.s.preview_before_saving = True
    backs = []

    def preview(self, chosen, copies, outputs, then, day=None, back=None):
        backs.append(back)
    monkeypatch.setattr(type(window), "_preview_batch", preview)
    window.fill_all_jobs()
    assert backs and all(j.speeds for j in days)  # (the preview made from them)
    backs[0]()
    assert not any(j.speeds for j in days)


def test_generate_of_one_day_bills_the_speed_the_row_shows(window, tmp_path):
    """A firm alone on the day generated, sharing pages on another day, commits to the speed its row names, as
    Generate all bills it (not "they choose" on its invoice)."""
    from minute_filler.gui.main_window import ATT_SPEED
    window.output_boxes["invoice"].setChecked(True)
    days = three_days(window, tmp_path)
    click(window, "Counsel")
    click(window, "Advocate")
    from minute_filler.gui.main_window import ATT_WHAT
    choose(window.att.cellWidget(row_of(window, "Advocate"), ATT_WHAT), "only")  # (What: only 6/4/2026)
    window._select_job(days[0])
    pump()
    counsel = key_of(days[0], "Counsel")
    assert window.att.cellWidget(row_of(window, "Counsel"), ATT_SPEED).currentText() == "Expedite"
    assert window._ask_split_speeds([days[0]])
    assert days[0].speeds.get(counsel) == "Expedite"


def test_copies_for_generate_all_have_their_own_not_ordered(window, tmp_path, monkeypatch):
    """Generate all's copies don't share the days' not_ordered sets: an edit while it runs doesn't reach them."""
    days = three_days(window, tmp_path)
    click(window, "Counsel")
    got = {}
    monkeypatch.setattr(type(window), "_run_batch", lambda self, chosen, copies, *a, **k: got.update(copies))
    window.fill_all_jobs()
    assert got and all(got[id(j)].not_ordered is not j.not_ordered for j in days)


def test_a_half_tick_of_another_case_isnt_put_back(window, tmp_path):
    """The days a half tick had are kept for its trial alone: the same firm clicked in another case orders that
    case, and the first is left as it is."""
    from minute_filler.gui.main_window import ATT_WHAT
    days = three_days(window, tmp_path)
    click(window, "Counsel")
    choose(window.att.cellWidget(row_of(window, "Counsel"), ATT_WHAT), "only")
    click(window, "Counsel")  # whole
    click(window, "Counsel")  # none
    from minute_filler.models import Attorney
    for d in (8, 9):  # (Sam Poe's trial, two days: a tick there is its whole trial, as in Jane Roe's)
        window.add_text(POE.format(d=d))
        wait(window, lambda: all(j.docs for j in window.jobs))
    poe = [j for j in window.jobs if all(j is not d for d in days)]
    assert len(poe) == 2
    for j in poe:
        j.case.attorneys = [Attorney(name="Alex B. Counsel", firm="Counsel & Counsel", checked=False)]
    window._select_job(poe[0])
    pump()
    click(window, "Counsel")
    assert all(j.ticked_keys() == ["counsel and counsel"] for j in poe)
    assert ordering(days, "Counsel") == [False, False, False]


def test_a_half_tick_can_be_unticked_beside_an_invoiced_day(window, tmp_path):
    """An invoiced day without the firm doesn't keep its box half ticked for good: a click unticks the days still
    to bill."""
    from PySide6.QtCore import Qt
    days = three_days(window, tmp_path)
    days[0].invoiced = True
    click(window, "Counsel")
    assert ordering(days, "Counsel") == [False, True, True] and state(window, "Counsel") == Qt.Checked
    click(window, "Counsel")
    assert ordering(days, "Counsel") == [False, False, False] and state(window, "Counsel") == Qt.Unchecked


def test_the_third_click_puts_back_this_firms_runs_alone(window, tmp_path):
    """A half tick's third click puts back the firm's own runs: another firm's change meanwhile stays."""
    from minute_filler.gui.main_window import ATT_WHAT
    days = three_days(window, tmp_path)
    click(window, "Counsel")
    click(window, "Advocate")
    counsel, advocate = key_of(days[2], "Counsel"), key_of(days[2], "Advocate")
    day = next(d for d in case_days(days) if d.job is days[2])
    store(day, [Run(day, 1, 4, [counsel, advocate]), Run(day, 5, day.pages, [counsel])], firms_of(days), window.s)
    window._show_attorneys()
    click(window, "Advocate")  # whole
    click(window, "Advocate")  # none
    choose(window.att.cellWidget(row_of(window, "Counsel"), ATT_WHAT), "only")  # Counsel: 6/4 only
    pump()
    click(window, "Advocate")  # back as it was
    assert not days[2].portions_problem() and counsel not in days[2].ticked_keys()


def test_day_by_day_a_firms_speed_is_the_day_shown(window, tmp_path):
    """Day by day, a firm's Speed is the day shown's alone."""
    from minute_filler.gui.main_window import ATT_SPEED
    window.s.trial_orders = "day"
    days = three_days(window, tmp_path)
    for j in days:
        window._select_job(j)
        pump()
        click(window, "Counsel")
    window._select_job(days[1])
    pump()
    choose(window.att.cellWidget(row_of(window, "Counsel"), ATT_SPEED), "Regular")
    counsel = key_of(days[1], "Counsel")
    assert [j.speeds.get(counsel) for j in days] == [None, "Regular", None]


def test_a_row_the_spread_adds_to_the_day_shown_stays(window, tmp_path):
    """A firm ordering the trial that the day shown doesn't name is added to it by the spread after an edit, and
    the table, read back before it is shown again, doesn't drop it."""
    from minute_filler.models import Attorney
    days = three_days(window, tmp_path)
    for j in (days[0], days[2]):
        j.case.attorneys.append(Attorney(name="Dana Smith", firm="Smith Law", checked=True))
    window._attorneys_edited()
    window._update_status()
    pump(0.2)
    assert ordering(days, "Smith Law") == [True, True, True]


def test_a_name_corrected_is_that_attorneys_alone(window, tmp_path):
    """A name corrected in Who ordered goes to the firm's rows of the other days that name that attorney, not
    to another attorney of the firm."""
    from minute_filler.models import Attorney
    days = three_days(window, tmp_path)
    days[0].case.attorneys.append(Attorney(name="Dana Smith", firm="Smith Law"))
    days[1].case.attorneys.append(Attorney(name="Alex B. Smyth", firm="Smith Law"))
    window._show_attorneys()
    r = row_of(window, "Smith Law")
    window.att.item(r, 1).setText("Alex B. Smith")
    pump()
    assert [a.name for a in days[0].case.attorneys if a.firm == "Smith Law"] == ["Dana Smith"]


def test_the_folded_card_says_who_ordered(window, tmp_path):
    """Folded, Who ordered's line says who ordered, not "No attorneys yet"."""
    three_days(window, tmp_path)
    click(window, "Counsel")
    window._fold_card(window.cards["attorneys"], True)
    window._update_status()
    pump()
    assert window.cards["attorneys"].summary.text().startswith("Alex B. Counsel")


def test_the_invoice_card_names_the_speed_billed_without_a_question_mark(window, tmp_path):
    """With Generate billing the speeds shown, the Invoice card prices firms sharing pages at that speed, with
    no "?" (Generate doesn't ask); set to ask, it marks them."""
    window.output_boxes["invoice"].setChecked(True)
    three_days(window, tmp_path)
    click(window, "Counsel")
    click(window, "Advocate")
    window._update_status()
    pump()
    assert "?" not in window.inv_info.text() and "Expedite" in window.inv_info.text()
    window.s.split_speeds = "ask"
    window._refresh_outputs()
    pump()
    assert "Expedite?" in window.inv_info.text()


def test_a_firm_removed_stays_off_the_days_an_invoiced_day_doesnt_order(window, tmp_path):
    """Remove selected with an invoiced day still ordering the firm: the other days stay without it after the
    next edit (its tick there would spread back)."""
    days = three_days(window, tmp_path)
    click(window, "Counsel")
    days[0].invoiced = True
    window.att.selectRow(row_of(window, "Counsel"))
    window._remove_att_rows()
    pump(0.2)
    window._attorneys_edited()
    pump(0.2)
    assert ordering(days, "Counsel") == [True, False, False]


def test_a_firm_alone_on_the_days_to_bill_chooses_on_its_invoice(window, tmp_path):
    """A firm that shared pages only on an invoiced day, alone on the days still to bill, reads "They choose":
    not a speed it isn't billed."""
    from minute_filler.gui.main_window import ATT_SPEED, ATT_WHAT
    days = three_days(window, tmp_path)
    window._select_job(days[0])
    pump()
    click(window, "Counsel")
    click(window, "Advocate")
    choose(window.att.cellWidget(row_of(window, "Advocate"), ATT_WHAT), "only")  # (6/3/2026 only)
    days[0].invoiced = True
    window._select_job(days[1])
    pump()
    assert window.att.cellWidget(row_of(window, "Counsel"), ATT_SPEED).currentText().startswith("They choose")


def test_excerpts_names_the_speed_billed_without_a_question_mark(window, tmp_path):
    """With Generate billing the speeds shown, Excerpts prices a firm sharing pages at the speed it is billed,
    without the "?" of a speed Generate would ask."""
    days = three_days(window, tmp_path)
    click(window, "Counsel")
    click(window, "Advocate")
    window._who_ordered(days[1])
    ex = window.excerpts
    t = ex.table
    texts = [t.item(r, c).text() for r in range(t.rowCount()) for c in range(t.columnCount()) if t.item(r, c)]
    assert any("Expedite" in x for x in texts) and not any("?" in x for x in texts)
    ex.close()


def test_the_firms_names_keep_their_room_in_a_narrow_window(window, tmp_path):
    """In a narrow window Who ordered's Name and Firm keep ATT_NAME_MIN each (they held three letters beside What
    and Speed), and the table scrolls sideways instead."""
    from minute_filler.gui.main_window import ATT_NAME_MIN
    from minute_filler.gui.zoom import z
    three_days(window, tmp_path)
    window.resize(1080, 900)
    window.show()
    pump(0.3)
    assert min(window.att.columnWidth(1), window.att.columnWidth(2)) >= z(ATT_NAME_MIN)


# ------------------------------------------------------------ found reviewing the fixes

def test_they_choose_stays_beside_an_invoiced_day(window, tmp_path):
    """"They choose" chosen after a day was invoiced at Daily stays so after an edit: the invoiced day's speed
    isn't carried back to the days still to bill."""
    from minute_filler.gui.main_window import ATT_SPEED
    days = three_days(window, tmp_path)
    click(window, "Counsel")
    choose(window.att.cellWidget(row_of(window, "Counsel"), ATT_SPEED), "Daily")
    days[0].invoiced = True
    window._show_attorneys()
    pump()
    choose(window.att.cellWidget(row_of(window, "Counsel"), ATT_SPEED), "")  # They choose
    window._attorneys_edited()  # (any edit in the table: a phone number typed)
    pump(0.2)
    c = key_of(days[1], "Counsel")
    assert [j.speeds.get(c) for j in days] == ["Daily", None, None]


def test_they_choose_is_the_days_not_ordered_too(s, trial):
    """"They choose" clears the firm's speed on the days it doesn't order now too: made the whole trial again,
    no day comes back at the old speed."""
    counsel, _ = keys(trial)
    tick_firm(trial, counsel, True, s, shown=trial[0])
    set_firm_speed(trial, counsel, "Daily")
    order_firm(trial, counsel, False, shown=trial[1])
    set_firm_speed(trial, counsel, "")
    order_firm(trial, counsel, True, shown=trial[1])
    assert not any(j.speeds.get(counsel) for j in trial)


def test_a_firmless_name_corrected_isnt_billed_twice(window, tmp_path):
    """An attorney without a firm is keyed by the name: corrected on one day, the other days' rows follow, so no
    day has the attorney twice."""
    from minute_filler.models import Attorney
    days = three_days(window, tmp_path)
    days[0].case.attorneys.append(Attorney(name="Dana Smith", checked=True))
    days[1].case.attorneys.append(Attorney(name="DANA SMITH", checked=True))
    days[2].case.attorneys.append(Attorney(name="Dana Smith", checked=True))
    window._show_attorneys()
    pump()
    r = next(r for r in range(window.att.rowCount()) if window.att.item(r, 1).text().lower() == "dana smith")
    window.att.item(r, 1).setText("Dana Smith, Esq.")
    pump(0.3)
    assert all(len([a for a in j.case.attorneys if a.checked and not a.firm]) == 1 for j in days)


def test_the_third_click_puts_back_the_days_speeds(window, tmp_path):
    """The half tick's third click puts back each day's speed of the firm, as it was before the first (the whole
    trial gave the days without one the firm's)."""
    days = three_days(window, tmp_path)
    click(window, "Counsel")
    c = key_of(days[1], "Counsel")
    for a in days[2].case.attorneys:
        if a.key() == c:
            a.checked = False
    days[2].not_ordered.add(c)
    days[0].speeds[c] = "Daily"
    window._show_attorneys()
    pump()
    for _ in range(3):
        click(window, "Counsel")
    assert [j.speeds.get(c) for j in days] == ["Daily", None, None]


def test_the_invoice_card_prices_as_generate_bills(window, tmp_path):
    """Billing the speeds shown, the Invoice card prices a firm sharing pages at the speed Generate sets it to
    (its speed on another day of the invoice), not the agreement form's."""
    window.output_boxes["invoice"].setChecked(True)
    days = three_days(window, tmp_path)
    click(window, "Counsel")
    click(window, "Advocate")
    days[1].speeds[key_of(days[1], "Counsel")] = "Daily"
    window._refresh_outputs()
    pump()
    line = next(x for x in window.inv_info.text().splitlines() if x.startswith("Alex B. Counsel"))
    assert "Daily" in line and "Expedite" not in line


def test_a_firm_removed_with_the_day_shown_invoiced_orders_nothing(window, tmp_path):
    """Removed while the day shown is invoiced, the firm's row goes from it too: no day keeps saying it doesn't
    order it (typed again, it orders the whole trial)."""
    days = three_days(window, tmp_path)
    click(window, "Counsel")
    c = key_of(days[1], "Counsel")
    days[1].invoiced = True
    window.att.selectRow(row_of(window, "Counsel"))
    window._remove_att_rows()
    pump(0.2)
    assert not any(c in j.not_ordered for j in days)
