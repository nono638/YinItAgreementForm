"""The Who ordered card (the user, 2026-10-24: "It should be in one place, and it should be intuitive who's
ordering"): a row per firm of the trial, whichever day is shown; a tick is the whole trial (Settings.trial_orders),
a half tick a firm ordering some days only, which a click makes the whole trial, then none, then puts back as it
was; What makes a firm the whole trial or the day shown, or opens Excerpts…; Speed names the speed billed and sets
it for every day; the Speed of the forms is every day's. A firm another day names is a row of the day shown too,
and ticked it orders that day. Day by day, a tick is the day shown's, as before. All names are made up."""
import os
import time

import pytest

from minute_filler.models import Attorney

from helpers import pat_settings, transcript_pdf

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def window(tmp_path, monkeypatch, make_window):
    from PySide6 import QtWidgets
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", lambda self: 0)
    s = pat_settings()
    s.use_ai = s.open_after = False
    s.output_dir = str(tmp_path / "out")
    s.records_dir = str(tmp_path / "records")
    s.outputs = ["agreement"]
    return make_window(s)


def pump(seconds: float = 0.0):
    from PySide6 import QtWidgets
    end = time.time() + seconds
    QtWidgets.QApplication.processEvents()
    while time.time() < end:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.01)


def wait(win, until, seconds=20):
    end = time.time() + seconds
    while time.time() < end and not (until() and not win.work):
        pump()
        time.sleep(0.01)


def three_days(window, tmp_path):
    """Jane Roe's trial, 6/3 to 6/5/2026, a transcript a day (each lists Advocate & Partners and Counsel & Counsel,
    neither ticked), the second day shown."""
    files = [transcript_pdf(tmp_path / f"Roe {d}.pdf", n, date=f"June {d}, 2026") for d, n in ((3, 30), (4, 20), (5, 10))]
    window.add_files([str(f) for f in files], batch=True)
    wait(window, lambda: len(window.jobs) == 3 and all(j.docs for j in window.jobs))
    days = sorted(window.jobs, key=lambda j: j.case.get("dates"))
    window._select_job(days[1])
    pump()
    return days


def row_of(window, firm: str) -> int:
    return next(r for r in range(window.att.rowCount()) if window.att.item(r, 2).text().startswith(firm))


def click(window, firm: str):
    """A click on a firm's tick (Qt flips the box; the window works out what it means)."""
    from PySide6.QtCore import Qt
    item = window.att.item(row_of(window, firm), 0)
    item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)
    pump()


def state(window, firm: str):
    return window.att.item(row_of(window, firm), 0).checkState()


def ordering(days, firm: str) -> list[bool]:
    return [any(a.firm.startswith(firm) and a.checked for a in j.case.attorneys) for j in days]


def choose(box, data):
    box.setCurrentIndex(box.findData(data))
    box.activated.emit(box.currentIndex())
    pump()


def test_a_tick_is_the_whole_trial(window, tmp_path):
    from PySide6.QtCore import Qt
    days = three_days(window, tmp_path)
    click(window, "Counsel")
    assert ordering(days, "Counsel") == [True, True, True] and state(window, "Counsel") == Qt.Checked
    assert window.orders_info.text().startswith("Alex B. Counsel: the whole trial (3 days)")
    click(window, "Counsel")
    assert ordering(days, "Counsel") == [False, False, False] and state(window, "Counsel") == Qt.Unchecked


def test_a_half_tick_goes_whole_then_none_then_back_as_it_was(window, tmp_path):
    from PySide6.QtCore import Qt
    from minute_filler.gui.main_window import ATT_WHAT
    days = three_days(window, tmp_path)
    click(window, "Counsel")
    choose(window.att.cellWidget(row_of(window, "Counsel"), ATT_WHAT), "only")  # only 6/4/2026, the day shown
    assert ordering(days, "Counsel") == [False, True, False] and state(window, "Counsel") == Qt.PartiallyChecked
    key = days[1].ticked_keys()[0]
    assert key in days[0].not_ordered and key in days[2].not_ordered
    assert window.att.cellWidget(row_of(window, "Counsel"), ATT_WHAT).currentText() == "6/4/2026"
    click(window, "Counsel")
    assert ordering(days, "Counsel") == [True, True, True] and not any(key in j.not_ordered for j in days)
    click(window, "Counsel")
    assert ordering(days, "Counsel") == [False, False, False]
    click(window, "Counsel")  # (back as it was: the second day only)
    assert ordering(days, "Counsel") == [False, True, False] and key in days[0].not_ordered


def test_what_and_speed_are_for_every_day(window, tmp_path):
    from minute_filler.gui.main_window import ATT_SPEED, ATT_WHAT
    days = three_days(window, tmp_path)
    click(window, "Counsel")
    click(window, "Advocate")
    box = window.att.cellWidget(row_of(window, "Counsel"), ATT_SPEED)
    assert box.currentText() == "Expedite" and box.findData("") == -1  # (ordered with another firm: it commits)
    choose(box, "Daily")
    key = days[0].ticked_keys()
    counsel = next(a.key() for a in days[0].case.attorneys if a.firm.startswith("Counsel"))
    assert [j.speeds.get(counsel) for j in days] == ["Daily"] * 3 and key
    assert window.att.cellWidget(row_of(window, "Counsel"), ATT_SPEED).currentText() == "Daily"
    choose(window.att.cellWidget(row_of(window, "Advocate"), ATT_WHAT), "only")
    # alone on the other days now: Counsel & Counsel still Daily (chosen); Advocate & Partners at the forms' speed
    assert window.att.cellWidget(row_of(window, "Advocate"), ATT_SPEED).currentText() == "Expedite"
    assert "at Daily" in window.orders_info.text() and "Advocate & Partners, LLP: 6/4/2026, at Expedite" in \
        window.orders_info.text()


def test_a_firm_ordering_alone_chooses_from_its_invoice(window, tmp_path):
    from minute_filler.gui.main_window import ATT_SPEED
    three_days(window, tmp_path)
    click(window, "Counsel")
    box = window.att.cellWidget(row_of(window, "Counsel"), ATT_SPEED)
    assert box.currentText() == "They choose: Regular or Expedite" and box.currentData() == ""


def test_the_forms_speed_is_every_days(window, tmp_path):
    days = three_days(window, tmp_path)
    window.delivery.setCurrentIndex(window.delivery.findData("Regular"))
    assert [j.case.get("delivery") for j in days] == ["Regular"] * 3
    assert all(j.case.fields["delivery"].source == "you" for j in days)


def test_a_firm_another_day_names_is_a_row_and_ticked_orders_this_day(window, tmp_path):
    from PySide6.QtCore import Qt
    from minute_filler.gui.main_window import _VISITOR
    days = three_days(window, tmp_path)
    days[0].case.attorneys.append(Attorney(name="Dana Smith", firm="Smith Law", checked=False))
    window._show_attorneys()
    r = row_of(window, "Smith Law")
    assert window.att.item(r, 0).data(_VISITOR) and state(window, "Smith Law") == Qt.Unchecked
    click(window, "Smith Law")
    assert ordering(days, "Smith Law") == [True, True, True]
    assert not window.att.item(row_of(window, "Smith Law"), 0).data(_VISITOR)  # (a row of this day's now)


def test_a_firm_typed_in_orders_the_whole_trial_and_is_removed_from_it(window, tmp_path):
    from PySide6.QtCore import QItemSelectionModel
    days = three_days(window, tmp_path)
    window._add_att_row()
    r = window._att_own - 1
    window.att.item(r, 1).setText("Dana Smith")
    window.att.item(r, 2).setText("Smith Law")
    pump()
    assert ordering(days, "Smith Law") == [True, True, True]
    window.att.clearSelection()
    window.att.selectionModel().select(window.att.model().index(row_of(window, "Smith Law"), 1),
                                       QItemSelectionModel.Select | QItemSelectionModel.Rows)
    window._remove_att_rows()
    assert not any(a.firm == "Smith Law" for j in days for a in j.case.attorneys)


def test_some_days_or_pages_opens_excerpts_whatever_is_ticked(window, tmp_path):
    from minute_filler.gui.main_window import ATT_WHAT
    three_days(window, tmp_path)
    assert not window.output_boxes["invoice"].isChecked()
    click(window, "Counsel")
    choose(window.att.cellWidget(row_of(window, "Counsel"), ATT_WHAT), "some")
    assert window.excerpts is not None and window.excerpts.isVisible() and len(window.excerpts.days) == 3
    window.excerpts.close()


def test_day_by_day_a_tick_is_the_day_shown(window, tmp_path):
    from PySide6.QtCore import Qt
    window.s.trial_orders = "day"
    days = three_days(window, tmp_path)
    click(window, "Counsel")
    assert ordering(days, "Counsel") == [False, True, False] and state(window, "Counsel") == Qt.Checked
    window.delivery.setCurrentIndex(window.delivery.findData("Regular"))
    assert days[1].case.get("delivery") == "Regular" and days[0].case.get("delivery") != "Regular"


def test_a_trial_opened_again_comes_back_with_who_ordered(window, tmp_path):
    """Open this job again of a trial (its agreement, made for the three days): read again a job per day, each
    day comes back with who ordered it, the firms that order some days only and the speeds, as its record kept
    them (batch.trial_orders, put_back_orders); before, the ticks of a trial were lost."""
    import json
    from minute_filler.deliver import ledger_for
    from minute_filler.gui.main_window import ATT_SPEED, ATT_WHAT
    days = three_days(window, tmp_path)
    click(window, "Counsel")
    click(window, "Advocate")
    choose(window.att.cellWidget(row_of(window, "Advocate"), ATT_WHAT), "only")  # 6/4/2026 only
    choose(window.att.cellWidget(row_of(window, "Counsel"), ATT_SPEED), "Daily")
    before = [(sorted(j.ticked_keys()), sorted(j.not_ordered), j.speeds) for j in days]
    window.fill_all_jobs()
    wait(window, lambda: not window.filling)
    rows = [a for a in ledger_for(window.s).activity("agreement") if json.loads(a.origin).get("joint")]
    assert rows
    window._clear_jobs()
    assert window.open_past_job(rows[0].origin) is True
    wait(window, lambda: len(window.jobs) == 3 and all(j.docs for j in window.jobs))
    again = sorted(window.jobs, key=lambda j: j.case.get("dates"))
    assert [(sorted(j.ticked_keys()), sorted(j.not_ordered), j.speeds) for j in again] == before


def test_asked_at_generate_a_firm_is_one_line_for_the_trial(window, tmp_path, monkeypatch):
    """Settings -> Invoice -> Firms ordering the same pages: ask. Two firms ordering three days: Generate all asked
    six lines (a firm and a day each); now one per firm, "All 3 days", the answer every day's."""
    from minute_filler.gui.dialogs import SplitSpeedsDialog
    window.s.split_speeds = "ask"
    window.output_boxes["invoice"].setChecked(True)
    days = three_days(window, tmp_path)
    click(window, "Counsel")
    click(window, "Advocate")
    seen, asked = [], []
    real = SplitSpeedsDialog.__init__

    def keep(self, asks, *a, **k):  # (the lines the question is made of)
        asked[:] = asks
        real(self, asks, *a, **k)

    def daily(dlg):
        seen.append([a.days for a in asked])
        for cb in dlg.combos:
            cb.setCurrentIndex(cb.findData("Daily"))
        return SplitSpeedsDialog.Accepted

    monkeypatch.setattr(SplitSpeedsDialog, "__init__", keep)
    monkeypatch.setattr(SplitSpeedsDialog, "exec", daily)
    assert window._ask_split_speeds(days, "Generate all")
    assert seen == [["All 3 days", "All 3 days"]]
    assert all(set(j.speeds.values()) == {"Daily"} and len(j.speeds) == 2 for j in days)


def test_the_boxes_stay_while_nothing_they_show_changes(window, tmp_path):
    """The cards are refreshed at each key typed: a box made again each time flickered and lost its focus."""
    from minute_filler.gui.main_window import ATT_SPEED
    three_days(window, tmp_path)
    click(window, "Counsel")
    box = window.att.cellWidget(row_of(window, "Counsel"), ATT_SPEED)
    window._update_status()
    window.rows["part"].choose("15")
    assert window.att.cellWidget(row_of(window, "Counsel"), ATT_SPEED) is box


def test_a_firms_details_are_its_details_on_every_day(window, tmp_path):
    from minute_filler.gui.main_window import ATT_FIELDS
    days = three_days(window, tmp_path)
    r = row_of(window, "Counsel")
    window.att.item(r, ATT_FIELDS.index("phone")).setText("(555) 010-0199")
    assert all(a.phone == "(555) 010-0199" for j in days for a in j.case.attorneys if a.firm.startswith("Counsel"))
    window.s.trial_orders = "day"  # (day by day: the day shown's alone)
    window.att.item(r, ATT_FIELDS.index("phone")).setText("(555) 010-0123")
    assert [a.phone for j in days for a in j.case.attorneys if a.firm.startswith("Counsel")] == \
        ["(555) 010-0199", "(555) 010-0123", "(555) 010-0199"]


def test_a_box_half_ticked_is_drawn_so():
    from minute_filler.gui.theme import QSS
    assert "QTableView::indicator:indeterminate" in QSS and "DASH_ICON" in QSS
