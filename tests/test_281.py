"""The user's answers of 2026-10-13 to the questions left after 2.8.0 (2.8.1): a rate sheet still with the old
template's Days, 7 and 21 (calendar days then, business days now), is offered 5 and 15 once; the Records button
counts Not paid when its colour can't come up (Ready to send with Paid alone), and Not paid leaves out the invoices
made in another reporter's name; a transcript sent before it is paid has a colour of its own (Sent, not paid,
purple); with each price a page rounded to the cent, an even split's small print says what each pays and the
Excerpts window's prices are rounded as the invoice's are; the CSV copies keep text Excel would take for a formula
as text; and on a short screen the Outputs box starts folded until the user folds or unfolds it. All names and
numbers are made up."""
import csv
import os
import time
from decimal import Decimal

import pytest

from helpers import pat_settings
from minute_filler.rates import FALLBACK, load_sheet, old_days, set_new_days, sheet_fingerprint
from minute_filler.records import Invoice, Ledger, csv_text
from minute_filler.settings import LOCAL, Settings
from minute_filler.tracking import (NOT_PAID, PURPLE, count_of, counted, default_boxes, default_rules, rule_for,
                                    rule_rows, rules_280)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

CASE = "Jane Roe v. X.Y. Holding Corporation"
OLD_SHEET = ("Rate,Original,Copy,Email,Index,Days\r\n"
             "Immediate,\"$1,007.60\",$1.45,$1.45,$1.45,0\r\n"
             "Daily,$6.50,$1.25,$1.25,$1.25,1\r\n"
             "Expedite,$5.40,$1.10,$1.10,$1.10, 7\r\n"
             "Regular,$4.30,$1.00,$1.00,$1.00,21\r\n"
             ",,,,,\r\n"
             "Rates Last Updated:,5/2/2024,,,,\r\n")


def invoice(no, firm="Smith Law", **kw):
    return Invoice(invoice_no=no, created="2026-06-04", case_name=CASE, index_no="712345/2021", dates="6/3/2026",
                   firm=firm, pages=100, amounts={"Regular": "100.00"}, billed_speed="Regular", **kw)


def boxes_with(*keys):
    """The built-in boxes, Paid and these in use."""
    out = default_boxes()
    for b in out:
        b.on = b.kind == "paid" or b.key in keys
    return out


def pump(seconds=0.2):
    from PySide6.QtWidgets import QApplication
    end = time.time() + seconds
    while time.time() < end:
        QApplication.processEvents()
        time.sleep(0.01)


def sheet_file(folder, text, name="Pat Rates"):
    folder.mkdir(exist_ok=True)
    p = folder / f"{name}.csv"
    p.write_bytes(text.encode("utf-8"))
    return p


# ------------------------------------------------------------------ the old Days of a rate sheet
def test_a_sheet_with_the_old_days_is_found_and_only_its_days_change(tmp_path):
    """Expedite 7 and Regular 21 become 5 and 15; everything else in the file stays as it was: the BOM, the CRLF
    line endings, a price quoted for its comma, the empty row."""
    p = tmp_path / "Pat Rates.csv"
    p.write_bytes(b"\xef\xbb\xbf" + OLD_SHEET.encode())
    assert old_days(load_sheet(p))
    set_new_days(p)
    want = OLD_SHEET.replace(", 7\r\n", ",5\r\n").replace(",21\r\n", ",15\r\n")
    assert p.read_bytes() == b"\xef\xbb\xbf" + want.encode()
    sheet = load_sheet(p)
    assert [(sp.name, sp.days) for sp in sheet.speeds if sp.name in ("Expedite", "Regular")] == [
        ("Regular", 15), ("Expedite", 5)] and not old_days(sheet)
    assert not list(tmp_path.glob("*.new"))


def test_which_days_count_as_the_old_ones(tmp_path):
    def days(text):
        return old_days(load_sheet(sheet_file(tmp_path, "Rate,Original,Days\n" + text)))
    assert days("Regular,$4.30,21\n")                        # (the one of them it has)
    assert days("Regular,$4.30,21\nExpedite,$5.40,\n")       # (Expedite without a Days)
    assert not days("Regular,$4.30,21\nExpedite,$5.40,10\n")  # (the user's own choice)
    assert not days("Regular,$4.30,15\nExpedite,$5.40,5\n")
    assert not days("Daily,$6.50,1\n")
    assert not old_days(load_sheet(sheet_file(tmp_path, "Rate,Original\nRegular,$4.30\n")))
    assert not old_days(FALLBACK)
    p = sheet_file(tmp_path, "Rate,Original,Days\nRegular,$4.30,21")  # (LF, no line ending at the end)
    set_new_days(p)
    assert p.read_bytes() == b"Rate,Original,Days\nRegular,$4.30,15"
    with pytest.raises(ValueError):
        set_new_days(sheet_file(tmp_path, "Rate,Original\nRegular,$4.30\n"))


@pytest.fixture
def old_sheet_window(tmp_path, make_window):
    """make(business_days=True) -> a window using a sheet with the old Days, once its start has run (which asks
    about them, with business days on), and the sheet's path."""
    def make(business_days=True):
        sheets = tmp_path / "sheets"
        path = sheet_file(sheets, OLD_SHEET)
        s = pat_settings(initials="pr")
        s.use_ai = s.open_after = s.check_updates = False
        s.rate_sheets_dir, s.rate_sheet = str(sheets), "Pat Rates"
        s.turnaround_business_days = business_days
        win = make_window(s)
        pump(0.3)  # (the window's start: _startup)
        return win, path
    return make


def answer(win, text):
    box = win._days_box
    assert box is not None
    next(b for b in box.buttons() if b.text() == text).click()
    pump(0.05)
    assert win._days_box is None


def test_the_app_offers_5_and_15_once_and_changes_the_sheet(old_sheet_window):
    win, path = old_sheet_window()
    s = win.s
    box = win._days_box  # (asked at the start)
    assert box is not None and box.isVisible() and box.windowModality() != 0
    text = box.text()
    assert '"Pat Rates" gives Expedite 7 days and Regular 21 days' in text and "business days" in text
    win._check_old_days()  # (asked once at a time)
    assert win._days_box is box
    s.rate_sheets_ok = [sheet_fingerprint(s.sheet())]  # (an incomplete sheet used anyway stays so as changed)
    assert s.days_for("Regular") == 21
    answer(win, "Change to 5 and 15")
    assert s.days_for("Expedite") == 5 and s.days_for("Regular") == 15  # (read again, every job priced again)
    assert b",$1.10,5\r\n" in path.read_bytes() and win.statusBar().currentMessage() == \
        '"Pat Rates" says Expedite 5, Regular 15 business days now.'
    assert s.rate_sheets_ok == [sheet_fingerprint(s.sheet())] != [""]
    win._check_old_days()
    assert win._days_box is None  # (5 and 15: nothing to ask)


def test_keep_is_remembered_for_that_sheet(old_sheet_window):
    win, path = old_sheet_window()
    before = path.read_bytes()
    answer(win, "Keep 7 and 21")
    assert path.read_bytes() == before and win.s.sheet_days_kept == ["Pat Rates"]
    assert Settings.load().sheet_days_kept == ["Pat Rates"]
    win._check_old_days()
    assert win._days_box is None


def test_not_asked_with_calendar_days_or_while_generate_all_runs(old_sheet_window):
    win, _ = old_sheet_window(business_days=False)  # (7 and 21 are calendar days again)
    assert win._days_box is None
    win._check_old_days()
    assert win._days_box is None
    win.s.turnaround_business_days = True
    win.filling = True
    win._check_old_days()
    assert win._days_box is None
    win.filling = False
    win._check_old_days()
    assert win._days_box is not None
    answer(win, "Keep 7 and 21")


def test_a_sheet_being_filled_in_is_asked_about_once_it_has_its_prices(old_sheet_window):
    """Opened from the warning of an incomplete sheet, it is asked about once saved with all its prices: one
    question at a time, and the prices first."""
    win, path = old_sheet_window(business_days=False)  # (nothing asked at the start)
    win.s.turnaround_business_days = True
    win._watch_sheet(path)
    win._check_old_days()
    assert win._days_box is None
    path.write_bytes(OLD_SHEET.replace("Rates Last", ",,,,,\r\nRates Last").encode())  # (saved: another size)
    win._sheet_saved()
    assert win._sheet_watched is None and win._days_box is not None
    answer(win, "Keep 7 and 21")


def test_a_lower_price_alone_doesnt_hold_the_question(old_sheet_window):
    """Watched while being fixed, a sheet with all its prices whose only problem is a price lower at a faster
    speed (the user may mean it) is asked about its Days all the same (the review of the 2026-10-21 sweep)."""
    win, path = old_sheet_window(business_days=False)  # (nothing asked at the start)
    path.write_bytes(OLD_SHEET.replace("Daily,$6.50,$1.25", "Daily,$6.50,$1.05").encode())  # (Copy below Expedite's)
    win.s.reload_rates()
    win.s.turnaround_business_days = True
    win._watch_sheet(path)
    win._check_old_days()
    assert win._days_box is not None
    answer(win, "Keep 7 and 21")


def test_a_sheet_that_cant_be_written_is_said_so_and_asked_again(old_sheet_window, monkeypatch, qt):
    from minute_filler import rates
    win, path = old_sheet_window()

    def locked(p):
        raise PermissionError("open in Excel")
    monkeypatch.setattr(rates, "set_new_days", locked)
    answer(win, "Change to 5 and 15")
    shown = [w for w in qt.QApplication.topLevelWidgets()
             if isinstance(w, qt.QMessageBox) and w.isVisible() and "couldn't be changed" in w.text()]
    assert shown and win.s.sheet_days_kept == []
    shown[0].close()
    win._check_old_days()
    assert win._days_box is not None
    answer(win, "Keep 7 and 21")


def test_not_now_and_the_x_ask_again_at_the_next_start_not_this_session(old_sheet_window):
    win, _ = old_sheet_window()
    answer(win, "Not now")
    assert win.s.sheet_days_kept == [] and Settings.load().sheet_days_kept == []
    win._check_old_days()  # (⟳, Settings: not this session)
    assert win._days_box is None
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    for close in (lambda box: QTest.keyClick(box, Qt.Key_Escape), lambda box: box.close()):  # (Esc, the box's X)
        win._days_later.clear()  # (the next start)
        win._check_old_days()
        close(win._days_box)
        pump(0.05)
        assert win._days_box is None and win.s.sheet_days_kept == [] and "Pat Rates" in win._days_later


def test_an_answer_for_a_sheet_no_longer_in_use_does_nothing(old_sheet_window, tmp_path):
    """Hardening: the window-modal box blocks picking another sheet, but should the sheet in use change before the
    answer, Change mustn't rewrite the sheet asked about, nor Keep remember it."""
    win, path = old_sheet_window()
    before = path.read_bytes()
    sheet_file(tmp_path / "sheets", "Rate,Original,Copy,Email,Index\nRegular,$4.30,$1.00,$1.00,$1.00\n", "Other")
    win.s.reload_rates()
    win.s.rate_sheet = "Other"
    answer(win, "Change to 5 and 15")
    assert path.read_bytes() == before and win.s.sheet_days_kept == []


def test_the_question_names_only_the_days_the_sheet_has_each_speed_once(old_sheet_window, tmp_path):
    """A sheet with Regular 21 alone says nothing of 7; two rows of one speed (Expedite and Rush) ask once."""
    win, path = old_sheet_window(business_days=False)
    win.s.turnaround_business_days = True
    path.write_text("Rate,Original,Copy,Email,Index,Days\nRegular,$4.30,$1.00,$1.00,$1.00,21\n", encoding="utf-8")
    win._read_sheets_again()
    win._check_old_days()
    text = win._days_box.text()
    assert "gives Regular 21 days" in text and "21 business days come out about 30 calendar days" in text
    assert " 7 " not in text and "about 9" not in text
    assert [b.text() for b in win._days_box.buttons()].count("Change to 15") == 1
    answer(win, "Not now")
    win._days_later.clear()
    path.write_text("Rate,Original,Copy,Email,Index,Days\nExpedite,$5.40,$1.10,$1.10,$1.10,7\n"
                    "Rush,$5.50,$1.10,$1.10,$1.10,7\nRegular,$4.30,$1.00,$1.00,$1.00,21\n", encoding="utf-8")
    win._read_sheets_again()
    win._check_old_days()
    assert {b.text() for b in win._days_box.buttons()} == {"Change to 5 and 15", "Keep 7 and 21", "Not now"}
    answer(win, "Change to 5 and 15")
    assert [sp.days for sp in load_sheet(path).speeds] == [15, 5, 5]


def test_days_written_07_are_changed_too(tmp_path):
    """load_sheet reads "07" as 7, so the question comes; Change must change it (it was left, and the question came
    back every time)."""
    p = sheet_file(tmp_path, "Rate,Original,Days\rExpedite,$5.40,07\rRegular,$4.30,021\r")  # (CR alone: an old Mac's)
    assert old_days(load_sheet(p)) and set_new_days(p) == 2
    assert p.read_bytes() == b"Rate,Original,Days\rExpedite,$5.40,5\rRegular,$4.30,15\r"
    before = p.read_bytes()
    assert set_new_days(p) == 0 and p.read_bytes() == before  # (nothing to change: the file left as it is)


def test_change_keeps_not_now_of_the_incomplete_sheet_warning(tmp_path, make_window, monkeypatch, qt):
    """An incomplete sheet answered Not now at the start isn't warned about again this session because the app
    changed its Days (its prices are as they were)."""
    from minute_filler.gui import main_window
    shown = []

    def not_now(box):
        shown.append(box.windowTitle())
        next(b for b in box.buttons() if b.text() == "Not now").click()
        return 0
    monkeypatch.setattr(main_window.QMessageBox, "exec", not_now)
    sheets = tmp_path / "sheets"
    sheet_file(sheets, "Rate,Original,Copy,Email,Index,Days\r\nExpedite,$5.40,$1.10,$1.10,,7\r\n"
                       "Regular,$4.30,$1.00,$1.00,$1.00,21\r\n")  # (no Index for Expedite)
    s = pat_settings(initials="pr")
    s.use_ai = s.open_after = s.check_updates = False
    s.rate_sheets_dir, s.rate_sheet = str(sheets), "Pat Rates"
    win = make_window(s)
    pump(0.3)
    assert shown == ["Your rate sheet is incomplete"]
    answer(win, "Change to 5 and 15")
    win._settings_changed()  # (Settings -> OK)
    assert shown == ["Your rate sheet is incomplete"] and s.days_for("Regular") == 15


def test_a_change_that_changed_nothing_is_said_so(old_sheet_window, monkeypatch, qt):
    from minute_filler import rates
    win, path = old_sheet_window()
    monkeypatch.setattr(rates, "set_new_days", lambda p: 0)  # (edited in between: nothing was 7 or 21 any more)
    answer(win, "Change to 5 and 15")
    shown = [w for w in qt.QApplication.topLevelWidgets()
             if isinstance(w, qt.QMessageBox) and w.isVisible() and "couldn't be changed" in w.text()]
    assert shown and "says Expedite" not in win.statusBar().currentMessage()
    shown[0].close()


# ------------------------------------------------------------------ the settings saved by 2.8.0
def test_the_colours_of_280_get_sent_not_paid_and_changed_ones_stay():
    s = Settings.from_dict({"settings_version": 14, "tracking_rules": rule_rows(rules_280())})
    assert s.rules()[0].name == "Sent, not paid" and s.tracking_rules == rule_rows(default_rules())
    mine = rule_rows(rules_280())
    mine[0]["colour"] = "#000000"
    assert Settings.from_dict({"settings_version": 14, "tracking_rules": mine}).tracking_rules == mine
    # (saved since: the user's list, whatever it is)
    assert Settings.from_dict({"settings_version": 15, "tracking_rules": rule_rows(rules_280())}).tracking_rules \
        == rule_rows(rules_280())


def test_a_box_folded_by_hand_in_280_stays_folded():
    assert Settings.from_dict({"settings_version": 14, "outputs_folded": True}).outputs_fold_chosen
    assert not Settings.from_dict({"settings_version": 14, "outputs_folded": False}).outputs_fold_chosen
    assert not Settings.from_dict({"outputs_folded": True, "outputs_fold_chosen": False}).outputs_fold_chosen
    assert {"outputs_fold_chosen", "sheet_days_kept"} <= set(LOCAL)


# ------------------------------------------------------------------ Records: the colours and the count
def test_a_transcript_sent_before_it_is_paid_is_purple_not_done():
    boxes, rules = boxes_with("transcribed", "sent"), default_rules()
    sent = {"sent": "2026-06-12", "transcribed": "2026-06-10"}
    unpaid = rule_for(invoice("2026-0001", checks=dict(sent)), boxes, rules)
    paid = rule_for(invoice("2026-0002", status="paid", checks=dict(sent)), boxes, rules)
    assert (unpaid.name, unpaid.colour) == ("Sent, not paid", PURPLE) and paid.name == "Done"
    assert rule_for(invoice("2026-0003"), boxes_with(), rules).name == "Not paid"  # (Paid alone: as before)


def test_ready_to_send_with_paid_alone_counts_not_paid():
    rules = default_rules()
    assert counted("Ready to send", boxes_with(), rules) == NOT_PAID
    assert counted("Ready to send", boxes_with("transcribed"), rules) == "Ready to send"
    assert counted(NOT_PAID, boxes_with(), rules) == NOT_PAID and counted("", boxes_with(), rules) == ""
    no_paid = boxes_with()
    no_paid[0].on = False
    assert counted("Ready to send", no_paid, rules) == ""


def test_the_counts_leave_out_another_reporters_invoices():
    """Not paid and the colours alike, as Records' totals do (the button and a Status filter's count agree); every
    firm paid still looks at them all."""
    invoices = [invoice("2026-0001"), invoice("2026-0002", firm="Counsel & Counsel", status="paid"),
                invoice("DS-2026-0001", reporter="ds")]
    assert count_of(NOT_PAID, invoices, boxes_with(), default_rules()) == 1
    sent = {"sent": "2026-06-12"}
    invoices = [invoice("2026-0003", checks=dict(sent)), invoice("DS-2026-0002", reporter="ds", checks=dict(sent))]
    assert count_of("Sent, not paid", invoices, boxes_with("sent"), default_rules()) == 1


def test_a_new_colour_isnt_one_of_the_colours_given():
    from minute_filler.gui.tracking_editor import NEW_COLOUR
    assert NEW_COLOUR not in {r.colour for r in default_rules()}


def test_the_records_button_counts_not_paid_with_paid_alone(make_window):
    s = pat_settings(initials="pr")
    s.use_ai = False
    led = Ledger()
    for i in (invoice("2026-0001"), invoice("2026-0002", firm="Counsel & Counsel"),
              invoice("DS-2026-0001", reporter="ds")):
        led.add_invoice(i)
    assert s.records_count == "Ready to send" and not any(b.on for b in s.boxes() if b.kind != "paid")
    win = make_window(s)
    win._count_records()
    end = time.time() + 20
    while time.time() < end and win.rec_btn.text() == "Records":
        pump(0.05)
    assert win.rec_btn.text() == "Records · Not paid: 2"


# ------------------------------------------------------------------ the CSV copies
def test_text_excel_would_take_for_a_formula_stays_text_in_the_csv_copies(tmp_path):
    assert [csv_text(v) for v in ("=> sent 10/3", "- left a message", "+1 555 0100", "@home", "-12.50", "+5",
                                  "Smith Law", "", 12, "\t=1+1", "\r=1")] == \
        ["'=> sent 10/3", "'- left a message", "'+1 555 0100", "'@home", "-12.50", "+5", "Smith Law", "", 12,
         "'\t=1+1", "'\r=1"]
    led = Ledger(tmp_path / "r.db", boxes=[("c1234abcd", "=Judge copy")])
    led.add_invoice(invoice("2026-0001", notes="=> sent 10/3"))
    led.export_csv(tmp_path / "csv")
    with open(tmp_path / "csv" / "invoices.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    assert "'=Judge copy" in rows[0] and "'=> sent 10/3" in rows[1] and "Smith Law" in rows[1]


# ------------------------------------------------------------------ rounding: the small print and Excerpts
@pytest.mark.usefixtures("split_orders_choose")
def test_excerpts_round_each_price_a_page_as_the_invoice_does(tmp_path):
    """Three firms sharing 10 pages at Regular, no index: $4.30 / 3 + $1 + $1 = $3.4333 a page; exactly
    $34.33..., by the page $3.43 x 10 = $34.30, as each firm's invoice has it."""
    from test_excerpts import trial
    from minute_filler.excerpts import Run, case_days, firms_of, prices, runs_of, store
    s = pat_settings()
    s.output_dir, s.records_dir = str(tmp_path / "out"), str(tmp_path / "records")
    s.invoice_speeds, s.invoice_include_index = ["Regular"], False
    jobs = trial(tmp_path, s)
    d1, d2 = days = case_days(jobs)
    firms = firms_of(jobs)
    a, b, c = (x.key() for x in firms)
    store(d1, [Run(d1, 1, 30, [a]), Run(d1, 31, 40, [a, b, c])], firms)
    store(d2, [Run(d2, 1, 20, [a])], firms)

    def shared():
        p = prices(days, [r for d in days for r in runs_of(d)], s)
        return next(each["Regular"] for keys, _, each in p.groups if keys == (a, b, c)), dict(
            (k, v["Regular"]) for k, v in p.firms)
    each, _ = shared()
    assert abs(each - Decimal("34.3333")) < Decimal("0.001")  # (exact: the default)
    s.invoice_rounding = "page"
    each, invoices = shared()
    assert each == Decimal("34.30") and invoices[b] == invoices[c] == Decimal("34.30")


# ------------------------------------------------------------------ the status while nothing is loaded
def test_the_status_while_nothing_is_loaded_is_plain_text(make_window):
    """It looked like a button (the user, 2026-10-13): plain text with an ellipsis; reading, ready and the
    problems keep their coloured pill."""
    from minute_filler.gui.main_window import IDLE_STATUS
    from minute_filler.gui.theme import QSS
    s = pat_settings(initials="pr")
    s.use_ai = False
    win = make_window(s)
    assert win.status.text() == IDLE_STATUS == "Drop a document to begin…" and win.status.property("state") == ""
    rules = {line.split("{")[0].strip(): line for line in QSS.splitlines() if line.startswith("QLabel#status")}
    assert "background" not in rules["QLabel#status"] and "font-weight" not in rules["QLabel#status"]
    assert all("background" in rules[f'QLabel#status[state="{st}"]'] for st in ("ok", "warn", "busy"))


# ------------------------------------------------------------------ the Outputs box on a short screen
def test_a_short_screen_folds_the_outputs_box_until_the_user_chooses(make_window, monkeypatch):
    from minute_filler.gui import main_window
    monkeypatch.setattr(main_window, "SHORT_SCREEN", 100_000)  # (every screen is short)
    s = pat_settings(initials="pr")
    s.use_ai = False
    win = make_window(s)
    win.show()
    pump()
    assert s.outputs_folded and win.outputs_body.isHidden() and not s.outputs_fold_chosen
    win._fold_outputs_by_hand(False)  # (its arrow, its title, View → Fold the Outputs box)
    assert not win.outputs_body.isHidden() and s.outputs_fold_chosen and Settings.load().outputs_fold_chosen
    win.hide()
    win.show()
    pump()
    assert not win.outputs_body.isHidden()  # (as the user left it)
    win.close()


def test_the_arrow_the_title_and_the_view_menu_count_as_the_users_choice(make_window, monkeypatch):
    from minute_filler.gui import main_window
    monkeypatch.setattr(main_window, "SHORT_SCREEN", 100_000)
    s = pat_settings(initials="pr")
    s.use_ai = False
    win = make_window(s)
    win.show()
    pump()
    for click in (win.outputs_fold.click, win.fold_outputs_action.trigger):
        s.outputs_fold_chosen = False
        folded = s.outputs_folded
        click()
        assert s.outputs_fold_chosen and s.outputs_folded != folded
    win.close()


def test_unfolded_by_the_app_it_stays_so_back_from_minimized(make_window, monkeypatch, qt):
    """Unfolded to show a problem (_go_to_problem: Whose pages…, the run sheet box), the box isn't folded again when
    the window comes back from minimized; a zoom decides again (the room changed)."""
    from PySide6.QtCore import Qt
    from minute_filler.gui import main_window
    monkeypatch.setattr(main_window, "SHORT_SCREEN", 100_000)
    s = pat_settings(initials="pr")
    s.use_ai = False
    win = make_window(s)
    win.show()
    pump()
    win._fold_outputs(False)  # (what _go_to_problem does)
    win.setWindowState(Qt.WindowMinimized)
    pump(0.1)
    win.setWindowState(Qt.WindowNoState)
    pump(0.3)
    assert not win.outputs_body.isHidden() and not s.outputs_fold_chosen
    win.set_zoom(1.1)
    assert win.outputs_body.isHidden()
    win.close()


def test_the_built_program_gives_windows_its_own_icon_and_nothing_breaks_without_it(make_window, monkeypatch):
    """_exe_icon_for_windows: run from source it does nothing; frozen, a window Windows can't take the icon for (off
    screen here) changes nothing and raises nothing."""
    import sys
    from minute_filler import main
    s = pat_settings(initials="pr")
    s.use_ai = False
    win = make_window(s)
    main._exe_icon_for_windows(win)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    main._exe_icon_for_windows(win)


def test_a_tall_screen_unfolds_a_box_the_app_folded(make_window):
    s = pat_settings(initials="pr")
    s.use_ai = False
    s.outputs_folded = True  # (folded on a short screen, never chosen: SHORT_SCREEN is 0 in the tests)
    win = make_window(s)
    win.show()
    pump()
    assert not win.outputs_body.isHidden() and not s.outputs_folded
    win.close()
    s.outputs_folded = s.outputs_fold_chosen = True  # (folded by hand: stays so)
    win = make_window(s)
    win.show()
    pump()
    assert win.outputs_body.isHidden()
    win.close()
