"""A rate sheet that leaves out prices (the user, 2026-10-09): not every speed has to be on it (not every agency
does Immediate, some courts offer Realtime), "but every peripheral should be spelled out": each speed on the sheet
needs its Original, Copy, Email and Index price. The Email and Index prices are also read from a column headed
close to the name ("E-mail", "Index Price"), unless that would be a guess (two close ones, a judge's index). The
window warns when the sheet in use is incomplete (picked, read again, after Settings, at start) and asks whether
to use it anyway (kept until the file changes), to go back to the sheet before, to open the sheet to fill it in
(read again each time it is saved), or not now. It also warns when a price is lower at a faster speed, which
can't be right (the user, 2026-10-20), comparing only the four speeds known by name. All names and prices are
made up."""
import os
from decimal import Decimal
from pathlib import Path

import pytest

from minute_filler.invoice_calc import extra_rate
from minute_filler.rates import (BUNDLED_DIR, FALLBACK, cheaper_faster, load_sheet, missing_prices,
                                 sheet_fingerprint)
from minute_filler.settings import LOCAL, Settings

from helpers import pat_settings

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

GAPS = ("Rate,Original,Copy,Email,Index Price,Days\n"  # ("Index Price": read as the Index price)
        "Regular,$4.30,$1.00,,,21\n"
        "Daily,$6.50,$1.25,$0.00,n/a,1\n"
        "Immediate,,,,,0\n"            # a speed not offered: fine
        "Realtime,,$2.00,$2.00,$2.00,0\n"  # prices but no Original: not read at all
        "Note:,prices include tax\n"
        "Rates Last Updated:,5/2/2026\n")
COMPLETE = "Rate,Original,Copy,Email,Index\nRegular,$4.30,$1.00,$1.00,$1.00\n"
WRONG = ("Rate,Original,Copy,Email,Index\n"
         "Regular,$4.30,$1.00,$1.00,$1.00\n"
         "Expedite,$5.40,$1.10,$1.10,$1.00\n"    # (an Index the same as Regular's: fine)
         "Daily,$5.00,$1.25,$1.05,$1.25\n"       # an Original and an Email lower than Expedite's
         "Immediate,$7.60,$1.45,$1.45,\n"        # (no Index: missing, not compared)
         "Realtime,$3.00,$0.50,$0.50,$0.50\n")   # a speed of another name: not compared
WRONG_SAID = ["Daily's Original, $5.00, is less than Expedite's, $5.40",
              "Daily's Email, $1.05, is less than Expedite's, $1.10"]


def sheet(tmp_path, text, name="Court Rates"):
    p = tmp_path / f"{name}.csv"
    p.write_text(text, encoding="utf-8")
    return load_sheet(p)


def test_the_bundled_sheet_is_complete():
    assert missing_prices(load_sheet(BUNDLED_DIR / "Sample Rates.csv")) == []
    assert missing_prices(FALLBACK) == [] and sheet_fingerprint(FALLBACK) == ""


def test_the_bundled_sheet_costs_more_at_each_faster_speed():
    assert cheaper_faster(load_sheet(BUNDLED_DIR / "Sample Rates.csv")) == [] and cheaper_faster(FALLBACK) == []


def test_what_counts_as_lower_at_a_faster_speed(tmp_path):
    """Each known speed against the next slower one on the sheet, whatever order the file has them in (Daily's
    Original is below Expedite's, so the sheet itself lists Daily first); equal prices, a price left out and a
    speed of another name aren't said."""
    sh = sheet(tmp_path, WRONG)
    assert [sp.name for sp in sh.speeds] == ["Realtime", "Regular", "Daily", "Expedite", "Immediate"]
    assert cheaper_faster(sh) == WRONG_SAID
    named = sheet(tmp_path, "Rate,Original,Copy\nRush,$5.40,$1.10\nNext day,$6.50,$1.00\n", "Named")
    assert cheaper_faster(named) == ["Next day's Copy, $1.00, is less than Rush's, $1.10"]
    # $0.00: not charged at that speed (an index only at Daily), not a lower price
    free = sheet(tmp_path, "Rate,Original,Copy,Email,Index\nDaily,$6.50,$1.25,$1.25,$1.25\n"
                           "Immediate,$7.60,$1.45,$1.45,$0.00\n", "Free")
    assert cheaper_faster(free) == []
    # a speed between that doesn't charge it (or has no price) is skipped: Daily against Regular
    for between in ("$0.00", ""):
        gap = sheet(tmp_path, "Rate,Original,Copy,Email,Index\nRegular,$4.30,$1.00,$1.00,$1.00\n"
                              f"Expedite,$5.40,$1.10,$1.10,{between}\nDaily,$6.50,$1.25,$1.25,$0.90\n", "Gap")
        assert cheaper_faster(gap) == ["Daily's Index, $0.90, is less than Regular's, $1.00"]


def test_what_counts_as_missing(tmp_path):
    """$0.00 is a price, "n/a" and a blank aren't (the "Index Price" column is read as the Index). Immediate, left
    blank, is a speed not offered; Realtime has prices but no Original, so it isn't read at all; the note row is
    no speed."""
    sh = sheet(tmp_path, GAPS)
    assert [sp.name for sp in sh.speeds] == ["Regular", "Daily"] and sh.skipped == ["Realtime"]
    assert sh.read_as == {"Index Price": "Index"}
    assert missing_prices(sh) == [("Regular", ["Email", "Index"]), ("Daily", ["Index"]), ("Realtime", ["Original"])]
    assert missing_prices(sheet(tmp_path, "Rate,Original,Email\nRegular,$4.30,$1.00\n", "Short")) == \
        [("Regular", ["Copy", "Index"])]
    assert missing_prices(sheet(tmp_path, COMPLETE, "Fine")) == []


@pytest.mark.parametrize("email, index", [
    ("Email", "Index"), ("EMAIL", "INDEX"), ("E-Mail", "index"),          # the names, in any capitals
    ("E mail", "Index Price"), ("Emailed copy", "Index (per page)"),      # close to them
    ("e_mail price", "Indices"), ("Emial", "Idnex"),                       # ... and slips
])
def test_headings_close_to_email_or_index_are_read(tmp_path, email, index):
    """The user, 2026-10-09: the headings as named first, then ones close to them, so "the reading would still
    work". The invoice prices them, nothing is missing, and those not named so are listed (for the tooltip)."""
    sh = sheet(tmp_path, f"Rate,Original,Copy,{email},{index},Days\nRegular,$4.30,$1.00,$1.05,$1.10,21\n")
    sp, = sh.speeds
    assert (extra_rate(sp, "email", "e-mail"), extra_rate(sp, "index")) == (Decimal("1.05"), Decimal("1.10"))
    assert missing_prices(sh) == []
    assert sh.read_as == {h: label for h, label in ((email, "Email"), (index, "Index"))
                          if h.lower() not in ("email", "e-mail", "index")}


def test_the_name_comes_first_and_nothing_is_guessed(tmp_path):
    """A heading that is the name wins over one close to it. Two close ones, one close to both, a judge's index
    and other columns are left alone: the price is then missing, and the window says so. Original and Copy keep
    their own columns."""
    def read(headings):
        sh = sheet(tmp_path, f"Rate,Original,Copy,{headings}\nRegular,$4.30,$1.00,$1.01,$1.02,$1.03\n", "Odd")
        sp, = sh.speeds
        return extra_rate(sp, "email", "e-mail"), extra_rate(sp, "index"), missing_prices(sh)

    assert read("Email,Index Price,Index") == (Decimal("1.01"), Decimal("1.03"), [])
    assert read("Email,Index,Index Price") == (Decimal("1.01"), Decimal("1.02"), [])
    assert read("Email,Index Price,Index Fee") == (Decimal("1.01"), 0, [("Regular", ["Index"])])
    assert read("Email/Index,Judge's Index,Notes") == (0, 0, [("Regular", ["Email", "Index"])])
    assert read("Realtime,Media,Indemnity") == (0, 0, [("Regular", ["Email", "Index"])])
    sh = sheet(tmp_path, "Rate,Price,Copy Price,Email Price,Index Price\nRegular,$4.30,$1.00,$1.05,$1.10\n", "Words")
    sp, = sh.speeds
    assert (sp.original, sp.copy, sp.extras) == ("4.30", "1.00", {"Email": "$1.05", "Index": "$1.10"})


def test_the_fingerprint_follows_the_file(tmp_path):
    first = sheet_fingerprint(sheet(tmp_path, GAPS))
    assert first.startswith("Court Rates:") and first == sheet_fingerprint(sheet(tmp_path, GAPS))
    assert sheet_fingerprint(sheet(tmp_path, GAPS + "Hourly,$9.00,$2.00,$2.00,$2.00,0\n")) != first


def test_the_answers_are_this_computers_own():
    """Kept in the settings file, left out of an exported one; only text is read back."""
    assert "rate_sheets_ok" in LOCAL
    assert Settings.from_dict({"rate_sheets_ok": ["Court Rates:abc", 3, None, "Fine:def"]}).rate_sheets_ok == \
        ["Court Rates:abc", "Fine:def"]


# ------------------------------------------------------------------ the window

@pytest.fixture
def window(tmp_path, make_window):
    s = pat_settings()
    s.use_ai = False
    s.output_dir = str(tmp_path / "out")
    s.rate_sheets_dir = str(tmp_path / "sheets")
    (tmp_path / "sheets").mkdir()
    (tmp_path / "sheets" / "Court Rates.csv").write_text(GAPS, encoding="utf-8")
    return make_window(s)


@pytest.fixture
def boxes(monkeypatch):
    """The message boxes shown, and the button each is answered with (boxes.answer: its text; None: closed)."""
    from PySide6 import QtWidgets

    class Boxes(list):
        answer = None

    shown = Boxes()

    def exec_(box):
        shown.append((box.windowTitle(), box.text(), [b.text() for b in box.buttons()]))
        shown.escape = box.escapeButton().text() if box.escapeButton() else None  # (Esc and the window's X)
        for b in box.buttons():
            if b.text() == shown.answer:
                b.click()
                return

    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", exec_)
    return shown


def pick(window, name):
    window.sheet_box.setCurrentIndex(window.sheet_box.findData(name))


def test_picking_an_incomplete_sheet_warns_and_can_go_back(window, boxes):
    assert window.s.rate_sheet == "Sample Rates" and boxes == []  # (complete: nothing said at start)
    boxes.answer = "Go back to Sample Rates"
    pick(window, "Court Rates")
    (title, text, buttons), = boxes
    assert title == "Your rate sheet is incomplete"
    assert text.startswith('The rate sheet "Court Rates" is missing some prices:\n\n'
                           "•  Regular: no Email or Index price\n•  Daily: no Index price\n"
                           "•  Realtime: no Original price (so it isn't offered at all)\n\n"
                           "Leaving off a speed you don't offer is fine, but every speed on the sheet needs all four "
                           "prices: Original, Copy, Email and Index.")
    assert ' The Email and Index prices are read from the columns headed so, or close to it ("E-mail", "Index ' \
           'Price") when only one column is.\n\nUse this rate sheet anyway?' in text
    assert buttons == ["Use it anyway", "Go back to Sample Rates", "Open the sheet to fill it in"]
    assert boxes.escape == "Go back to Sample Rates"
    assert window.s.rate_sheet == "Sample Rates" and window.sheet_box.currentData() == "Sample Rates"
    assert window.s.rate_sheets_ok == []
    assert '\nThe "Index Price" column is read as the Index price\n⚠ Missing: Regular: Email, Index; Daily: Index; ' \
           'Realtime: Original' in window.sheet_box.itemData(window.sheet_box.findData("Court Rates"), 3)  # (tooltip)


def test_use_it_anyway_until_the_file_changes(window, boxes, tmp_path):
    boxes.answer = "Use it anyway"
    pick(window, "Court Rates")
    assert window.s.rate_sheet == "Court Rates" and len(boxes) == 1
    assert window.s.rate_sheets_ok == [sheet_fingerprint(window.s.sheet())]
    assert Settings.load().rate_sheets_ok == window.s.rate_sheets_ok  # (saved)
    window._reload_sheets()  # read again, unchanged: not asked again
    window._check_rate_sheet()
    assert len(boxes) == 1
    (tmp_path / "sheets" / "Court Rates.csv").write_text(GAPS + "Hourly,$9.00,,,,0\n", encoding="utf-8")
    window._reload_sheets()  # edited in Excel, still incomplete: asked again
    assert len(boxes) == 2 and "•  Hourly: no Copy, Email or Index price" in boxes[-1][1]
    assert "Go back to" not in " ".join(boxes[-1][2])  # (the same sheet: nothing to go back to)


def test_not_now_when_there_is_nothing_to_go_back_to(window, boxes):
    """At start (or ⟳) there is no sheet to go back to: Not now, also Esc and the window's X, keeps it in use as it
    is, not asked again this session unless read again (the user, 2026-10-10)."""
    window.s.rate_sheet = "Court Rates"
    boxes.answer = "Not now"
    window._check_rate_sheet()  # (at start)
    (_, _, buttons), = boxes
    assert buttons == ["Use it anyway", "Not now", "Open the sheet to fill it in"] and boxes.escape == "Not now"
    assert window.s.rate_sheet == "Court Rates" and window.s.rate_sheets_ok == []
    window._check_rate_sheet()
    assert len(boxes) == 1
    boxes.answer = None  # (closed)
    window._reload_sheets()
    assert len(boxes) == 2 and window.s.rate_sheet == "Court Rates" and window.s.rate_sheets_ok == []


def test_open_the_sheet_and_it_is_read_again_when_saved(window, boxes, monkeypatch, tmp_path, qt):
    """The sheet itself opens (not the folder) and nothing is kept; each time it is saved it is read again, the
    jobs priced from it, and the note at the bottom says what it still misses, with no box; once it has every
    price, it is no longer watched (the user, 2026-10-10)."""
    opened = []
    monkeypatch.setattr("minute_filler.gui.main_window.open_path", opened.append)
    path = tmp_path / "sheets" / "Court Rates.csv"
    boxes.answer = "Open the sheet to fill it in"
    pick(window, "Court Rates")
    assert opened == [path] and window.s.rate_sheet == "Court Rates" and window.s.rate_sheets_ok == []
    watch = window._sheet_watch
    assert [Path(p) for p in watch.files()] == [path] and [Path(p) for p in watch.directories()] == [path.parent]
    window._check_rate_sheet()  # (at start, after Settings: once a session)
    assert len(boxes) == 1
    note = window.statusBar().currentMessage
    window._sheet_saved()  # (something else in the folder changed: the sheet wasn't saved)
    assert "Read" not in note()
    path.write_text(GAPS.replace("Regular,$4.30,$1.00,,,21", "Regular,$4.30,$1.00,$1.05,$1.10,21"), encoding="utf-8")
    with monkeypatch.context() as m:
        m.setattr(qt.QApplication, "activeModalWidget", lambda: object())
        window._sheet_saved()  # (a question on screen: not now, in a second)
        assert window._sheet_timer.isActive() and not window.s.sheet().find("Regular").extras.get("Email")
    window._sheet_saved()
    assert note() == 'Read "Court Rates" again. Still missing: Daily: Index; Realtime: Original'
    assert window.s.sheet().find("Regular").extras["Email"] == "$1.05" and len(boxes) == 1
    assert window._sheet_watched is not None
    path.write_text(COMPLETE, encoding="utf-8")
    window._sheet_saved()
    assert note() == 'Read "Court Rates" again: its prices are all there and in order now.' and len(boxes) == 1
    assert window._sheet_watched is None and window._sheet_watch.files() == []


def test_the_watch_sees_the_sheet_saved(window, boxes, monkeypatch, tmp_path, qt):
    """The same through the file watcher itself, as Excel saves: a new file in place of the old one."""
    import time
    monkeypatch.setattr("minute_filler.gui.main_window.open_path", lambda p: None)
    path = tmp_path / "sheets" / "Court Rates.csv"
    boxes.answer = "Open the sheet to fill it in"
    pick(window, "Court Rates")
    window._sheet_timer.setInterval(50)
    (tmp_path / "sheets" / "~new.tmp").write_text(COMPLETE, encoding="utf-8")
    for _ in range(40):  # (a virus scanner may hold the new file a moment, as Excel's saves meet too: retried)
        try:
            os.replace(tmp_path / "sheets" / "~new.tmp", path)
            break
        except PermissionError:
            time.sleep(0.05)
    end = time.time() + 15
    while time.time() < end and window._sheet_watched is not None:
        qt.QApplication.processEvents()
        time.sleep(0.02)
    assert window.statusBar().currentMessage() == 'Read "Court Rates" again: its prices are all there and in order now.'


def test_after_settings_the_sheet_in_use_is_checked(window, boxes):
    """Settings → Defaults picked the incomplete sheet: asked, with the one before to go back to."""
    boxes.answer = "Go back to Sample Rates"
    window.s.rate_sheet = "Court Rates"
    window._settings_changed(sheet="Sample Rates")
    assert len(boxes) == 1 and window.s.rate_sheet == "Sample Rates"


def test_the_headings_hint_only_when_email_or_index_is_missing(window, boxes, tmp_path):
    (tmp_path / "sheets" / "No Copy.csv").write_text("Rate,Original,Copy,Email,Index\nRegular,$4.30,,$1.00,$1.00\n",
                                                     encoding="utf-8")
    window._reload_sheets()
    boxes.answer = "Go back to Sample Rates"
    pick(window, "No Copy")
    (_, text, _), = boxes
    assert "•  Regular: no Copy price\n" in text and "headed" not in text


def test_a_sheet_lower_at_a_faster_speed_warns(window, boxes, tmp_path):
    (tmp_path / "sheets" / "Wrong.csv").write_text(WRONG.replace("$1.45,\n", "$1.45,$1.45\n"), encoding="utf-8")
    window._reload_sheets()
    boxes.answer = "Go back to Sample Rates"
    pick(window, "Wrong")
    (title, text, buttons), = boxes
    assert title == "Your rate sheet's prices look wrong"
    assert text == ('The rate sheet "Wrong" has prices that are lower at a faster speed:\n\n'
                    + "\n".join(f"•  {c}" for c in WRONG_SAID) + "\n\nA faster speed shouldn't cost less: please "
                    "check these against your own rates.\n\nUse this rate sheet anyway?")
    assert buttons == ["Use it anyway", "Go back to Sample Rates", "Open the sheet to fix it"]
    assert "\n⚠ Lower at a faster speed: " + "; ".join(WRONG_SAID) in \
        window.sheet_box.itemData(window.sheet_box.findData("Wrong"), 3)  # (tooltip)


def test_missing_prices_and_lower_ones_in_one_box(window, boxes, tmp_path):
    (tmp_path / "sheets" / "Both.csv").write_text("Rate,Original,Copy,Email,Index\nRegular,$4.30,$1.00,$1.00,$1.00\n"
                                                  "Daily,$6.50,$0.90,,$1.25\n", encoding="utf-8")
    window._reload_sheets()
    boxes.answer = "Go back to Sample Rates"
    pick(window, "Both")
    (title, text, buttons), = boxes
    assert title == "Your rate sheet is incomplete" and "•  Daily: no Email price\n" in text
    assert text.endswith("\n\nIt also has prices that are lower at a faster speed:\n\n"
                         "•  Daily's Copy, $0.90, is less than Regular's, $1.00\n\nA faster speed shouldn't cost less: "
                         "please check these against your own rates.\n\nUse this rate sheet anyway?")
    assert "Open the sheet to fill it in" in buttons


def test_a_sheet_opened_to_fix_says_what_is_still_lower(window, boxes, monkeypatch, tmp_path):
    monkeypatch.setattr("minute_filler.gui.main_window.open_path", lambda p: None)
    path = tmp_path / "sheets" / "Wrong.csv"
    wrong = WRONG.replace("$1.45,\n", "$1.45,$1.45\n")  # (every price there: only the order is wrong)
    path.write_text(wrong, encoding="utf-8")
    window._reload_sheets()
    boxes.answer = "Open the sheet to fix it"
    pick(window, "Wrong")
    assert window.s.rate_sheet == "Wrong" and window._sheet_watched is not None
    path.write_text(wrong.replace("Daily,$5.00", "Daily,$6.50"), encoding="utf-8")
    window._sheet_saved()
    assert window.statusBar().currentMessage() == ('Read "Wrong" again. Still lower at a faster speed: Daily\'s Email, '
                                                   "$1.05, is less than Expedite's, $1.10")
    path.write_text(COMPLETE, encoding="utf-8")
    window._sheet_saved()
    assert window.statusBar().currentMessage() == 'Read "Wrong" again: its prices are all there and in order now.'
    assert window._sheet_watched is None and len(boxes) == 1


def test_a_lower_price_kept_as_it_is_ends_the_watch(window, boxes, monkeypatch, tmp_path):
    """Opened to be fixed, then kept with Use it anyway (the user may mean that price): no longer watched, so no
    note at each save; and a lower price alone doesn't hold the old Days question (the sweep of 2026-10-21: it
    was watched all session, and the question never came)."""
    monkeypatch.setattr("minute_filler.gui.main_window.open_path", lambda p: None)
    path = tmp_path / "sheets" / "Wrong.csv"
    wrong = WRONG.replace("$1.45,\n", "$1.45,$1.45\n")
    path.write_text(wrong, encoding="utf-8")
    window._reload_sheets()
    boxes.answer = "Open the sheet to fix it"
    pick(window, "Wrong")
    assert window._sheet_watched is not None
    asked = []
    monkeypatch.setattr(type(window), "_check_old_days", lambda self: asked.append(self.s.rate_sheet))
    path.write_text(wrong + "Rates Last Updated:,5/2/2026\n", encoding="utf-8")  # (saved, still lower)
    window._sheet_saved()
    assert window._sheet_watched is not None and asked == ["Wrong"]
    boxes.answer = "Use it anyway"
    window._reload_sheets()  # (⟳: asked again, kept as it is)
    assert boxes[-1][0] == "Your rate sheet's prices look wrong" and window._sheet_watched is None


def test_no_box_while_generate_all_runs(window, boxes, qt, monkeypatch):
    """A sheet picked (or read again) while Generate all runs isn't asked about then, nor under the batch's own
    windows when it ends (Batch finished, The math); it is asked about once they are closed, with Go back to the
    sheet in use before the batch's picks (the sweep of 2026-10-21, and the review of its fixes)."""
    import time
    from PySide6.QtWidgets import QApplication
    end = time.time() + 0.3
    while time.time() < end:  # (the window's start, with its own check of the sheet: Sample Rates, complete)
        qt.QApplication.processEvents()
    window.filling = True
    window.s.rate_sheet = "Court Rates"
    boxes.answer = "Not now"
    assert window._check_rate_sheet("Sample Rates", sheet=window.s.sheet()) is True and boxes == []
    window._check_rate_sheet("Court Rates", again=True)  # (another pick: Go back is still to the first)
    window.filling = False
    open_box = object()
    monkeypatch.setattr(QApplication, "activeModalWidget", staticmethod(lambda: open_box))  # "Batch finished"
    window._batch_ended()
    end = time.time() + 1.5
    while time.time() < end:
        qt.QApplication.processEvents()
    assert boxes == []  # (still open: asked again in half a second)
    monkeypatch.setattr(QApplication, "activeModalWidget", staticmethod(lambda: None))  # (closed)
    end = time.time() + 1.5
    while time.time() < end and not boxes:
        qt.QApplication.processEvents()
    (title, _, buttons), = boxes
    assert title == "Your rate sheet is incomplete" and "Go back to Sample Rates" in buttons
    window._batch_ended()  # (once only)
    qt.QApplication.processEvents()
    assert len(boxes) == 1
