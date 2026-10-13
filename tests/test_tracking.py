"""The Records window's tick boxes, status and row colours (tracking.py, Settings -> Records; the user,
2026-10-10): Paid, Invoice sent, Transcribed and Transcript sent (Paid alone in use at first) and boxes of the
user's own; the Status column's words ("Paid, Transcribed, Not sent"); the colour rules, the first that matches
colouring the row, "Ready to send" only once every firm of the transcript has paid; Transcribed ticked on a
whole transcript at once; Undo; the ticks kept in the records (Invoice.checks) and their CSV columns; notes typed
into the table; and the Settings -> Records editor. All names and numbers are made up: four firms (Smith Law,
Counsel & Counsel, Roe & Co., Doe PC) ordered the 6/3/2026 transcript of Jane Roe v. X.Y. Holding Corporation,
712345/2021."""
import csv
import itertools
import json
import os
import sqlite3
from types import SimpleNamespace

import pytest

from helpers import pat_settings
from minute_filler.records import Invoice, Ledger
from minute_filler.settings import Settings
from minute_filler.tracking import (BLUE, EVERY_PAID, GREEN, ORANGE, PURPLE, TEAL, YELLOW, ColourRule, TrackBox,
                                    Transcripts, box_rows, default_boxes, default_rules, rule_for, rule_names,
                                    status_words)

FIRMS = ("Smith Law", "Counsel & Counsel", "Roe & Co.", "Doe PC")
CASE = "Jane Roe v. X.Y. Holding Corporation"


def inv(no, firm="Smith Law", dates="6/3/2026", index="712345/2021", case=CASE, **kw):
    """A made-up invoice of the 6/3/2026 transcript; kw: other Invoice fields."""
    return Invoice(invoice_no=no, created="2026-06-04", case_name=case, index_no=index, dates=dates, firm=firm,
                   pages=100, amounts={"Regular": "100.00"}, billed_speed="Regular", **kw)


def boxes_on(*keys):
    """The built-in boxes with these in use (and no others)."""
    out = default_boxes()
    for b in out:
        b.on = b.key in keys
    return out


# ------------------------------------------------------------------ the status

def test_the_status_says_each_box_in_use_ticked_or_not():
    i = inv("2026-0001")
    assert status_words(i, default_boxes()) == "Not paid"  # (Paid alone at first)
    i.status = "paid"
    assert status_words(i, default_boxes()) == "Paid"
    boxes = boxes_on("paid", "invoice_sent", "transcribed", "sent")
    i.checks = {"transcribed": "2026-06-10"}
    assert status_words(i, boxes) == "Paid, Invoice not sent, Transcribed, Not sent"
    boxes[1].no = ""  # a blank word says nothing
    assert status_words(i, boxes) == "Paid, Transcribed, Not sent"
    i.status = "void"
    assert status_words(i, boxes) == "Void"


# ------------------------------------------------------------------ the colours

def expected(boxes: set, paid, every, transcribed, sent):
    """The default rule's name for these boxes in use and this invoice (every: every firm paid)."""
    if "sent" in boxes and sent:
        return "Done" if paid else "Sent, not paid"
    if "transcribed" in boxes:
        if transcribed:
            return "Ready to send" if every else "Transcribed, waiting for payment"
        return "Paid, not transcribed" if paid else "Not paid, not transcribed"
    if "sent" in boxes and paid:
        return "Ready to send" if every else "Paid, waiting on other firms"
    return "Paid" if paid else "Not paid"


@pytest.mark.parametrize("keys", [("paid",), ("paid", "sent"), ("paid", "transcribed"),
                                  ("paid", "transcribed", "sent")])
def test_the_default_colours_whichever_boxes_are_in_use(keys):
    """Each set of boxes, every combination: the rule the user would expect (a rule naming a box not in use is
    skipped). Every firm paid only when this one has (it is one of them)."""
    boxes = boxes_on(*keys)
    for paid, every, transcribed, sent in itertools.product((False, True), repeat=4):
        if every and not paid:
            continue
        i = inv("2026-0001", status="paid" if paid else "open",
                checks={k: "2026-06-10" for k, on in (("transcribed", transcribed), ("sent", sent)) if on})
        rule = rule_for(i, boxes, default_rules(), SimpleNamespace(every_paid=lambda _, e=every: e))
        assert rule.name == expected(set(keys), paid, every, transcribed and "transcribed" in keys,
                                     sent and "sent" in keys), (keys, paid, every, transcribed, sent)
    colours = {r.name: r.colour for r in default_rules()}
    assert (colours["Done"], colours["Ready to send"], colours["Paid, not transcribed"],
            colours["Not paid, not transcribed"], colours["Transcribed, waiting for payment"],
            colours["Sent, not paid"]) == (GREEN, ORANGE, YELLOW, TEAL, BLUE, PURPLE)


def test_a_rule_naming_a_box_not_in_use_is_skipped_and_void_has_no_colour():
    rules = [ColourRule("Sent", "#000000", {"sent": True}), ColourRule("Any", "#111111", {})]
    i = inv("2026-0001", checks={"sent": "2026-06-12"})
    assert rule_for(i, boxes_on("paid"), rules).name == "Any"
    assert rule_for(i, boxes_on("paid", "sent"), rules).name == "Sent"
    i.status = "void"
    assert rule_for(i, boxes_on("paid", "sent"), rules) is None
    # the Status filter lists the rules that can colour a row, each name once
    assert rule_names(boxes_on("paid"), default_rules()) == ["Paid", "Not paid"]
    assert rule_names(boxes_on("paid", "transcribed", "sent"), default_rules()) == [  # (not "Paid, waiting on
        "Sent, not paid", "Done", "Ready to send", "Transcribed, waiting for payment",  # other firms": the ones
        "Paid, not transcribed", "Not paid, not transcribed"]                          # above catch it)
    assert rule_names(boxes_on("paid", "sent"), default_rules()) == [
        "Sent, not paid", "Done", "Ready to send", "Paid, waiting on other firms", "Not paid"]


# ------------------------------------------------------------------ the transcripts

def test_the_invoices_of_a_transcript_and_every_firm_paid():
    four = [inv(f"2026-000{n}", firm) for n, firm in enumerate(FIRMS, 1)]
    four[1].index_no = "712345-21"            # the same index number, written another way
    four[3].excerpt = "6/3/2026 pp. 20–40"    # an excerpt of the day is the same transcript
    joint = inv("2026-0005", "Poe LLP", dates="6/3/2026, 6/4/2026")  # shares 6/3/2026 only
    theirs = inv("DS-2026-0001", "Smith Law", reporter="ds")       # another reporter's pages
    void = inv("2026-0006", "Roe & Co.", status="void")
    gone = inv("2026-0007", "Doe PC", deleted="2026-06-05T10:00:00")
    nothing = inv("2026-0008", "Doe PC", dates="", index="", case="")
    by_name = [inv(f"2026-001{n}", firm, index="") for n, firm in enumerate(FIRMS[:2])]
    tr = Transcripts(four + [joint, theirs, void, gone, nothing] + by_name)
    assert sorted(tr.mates("2026-0001")) == ["2026-0001", "2026-0002", "2026-0003", "2026-0004"]
    assert tr.mates("2026-0005") == ["2026-0005"] and tr.mates("DS-2026-0001") == ["DS-2026-0001"]
    assert tr.mates("2026-0006") == [] and tr.mates("2026-0007") == []  # (void, deleted)
    assert tr.mates("2026-0008") == ["2026-0008"]
    assert sorted(tr.mates("2026-0010")) == ["2026-0010", "2026-0011"]  # (no index number: the case name)
    for i in four[:3]:
        i.status = "paid"
    assert not Transcripts(four + [joint]).every_paid(four[0])
    four[3].status = "paid"
    assert not Transcripts(four + [joint]).every_paid(four[0])  # Poe LLP ordered 6/3/2026 too, and owes
    joint.status = "paid"
    assert Transcripts(four + [joint, theirs, void]).every_paid(four[0])  # (theirs and the void don't count)


# ------------------------------------------------------------------ the settings

def test_settings_start_with_paid_alone_and_are_checked_when_read(tmp_path):
    s = Settings()
    assert [(b.key, b.on) for b in s.boxes()] == [("paid", True), ("invoice_sent", False),
                                                  ("transcribed", False), ("sent", False)]
    assert s.records_colours and len(s.rules()) == 10
    data = {"tracking_boxes": [
        5, {"key": "bogus", "name": "Bogus"}, {"key": "c1a", "name": "Proofread", "yes": "Proofread", "no": "",
                                               "on": True},
        {"key": "transcribed", "name": " ", "on": True, "whole": True}, {"key": "c1a", "name": "Twice"},
        {"key": "c2b", "name": "Notes", "on": True}, {"key": "c3c", "name": ""}],
        "tracking_rules": [{"name": "Proofread", "colour": "#123456", "when": {"c1a": True}},
                           {"name": "Gone", "colour": "#123456", "when": {"c9z": True}},
                           {"name": "Bad colour", "colour": "blue", "when": {}},
                           {"name": "Ready", "colour": "#ABCDEF", "when": {EVERY_PAID: True, "paid": "yes"}}]}
    s = Settings.from_dict(data)
    assert [(b.key, b.name, b.on) for b in s.boxes()] == [
        ("paid", "Paid", True), ("invoice_sent", "Invoice sent", False), ("c1a", "Proofread", True),
        ("transcribed", "Transcribed", True), ("sent", "Transcript sent", False), ("c2b", "Notes (2)", True)]
    assert [(r.name, r.colour) for r in s.rules()] == [("Proofread", "#123456")]
    assert s.tracking_rules == [{"name": "Proofread", "colour": "#123456", "when": {"c1a": True}}]  # (as saved)


def test_v13_shows_the_notes_column_once():
    old = Settings.from_dict({"settings_version": 12, "records_columns": {"invoices": ["no", "case"]}})
    assert old.records_columns["invoices"] == ["no", "case", "notes"]
    assert Settings.from_dict({"settings_version": 13, "records_columns": {"invoices": ["no"]}}
                              ).records_columns["invoices"] == ["no"]  # (taken off since: stays off)
    assert Settings.from_dict({"settings_version": 12}).records_columns == {}  # (the usual ones: Notes is one)


def test_the_boxes_travel_with_exported_settings(tmp_path):
    s = Settings()
    boxes = boxes_on("paid", "transcribed")
    s.tracking_boxes, s.tracking_rules, s.records_colours = box_rows(boxes), [], False
    path = s.export_to(tmp_path / "settings.yinit", personal=False)
    got = Settings.import_from(path, Settings())
    assert [b.on for b in got.boxes()] == [True, False, True, False] and got.rules() == []
    assert not got.records_colours


# ------------------------------------------------------------------ the records

def test_an_older_database_gets_the_checks_column(tmp_path):
    from test_records_trash import OLD_SCHEMA
    path = tmp_path / "records.db"
    with sqlite3.connect(path) as db:
        db.executescript(OLD_SCHEMA)
    lg = Ledger(path)
    assert lg.invoices()[0].checks == {}
    assert lg.set_checks(["2026-0007"], "sent", True, "2026-03-09")[0].checks == {}
    assert lg.invoices()[0].checks == {"sent": "2026-03-09"}


def test_boxes_ticked_kept_undone_and_copied(tmp_path):
    lg = Ledger(tmp_path / "r.db", mirror_dir=tmp_path / "mirror", boxes=[("transcribed", "Transcribed")])
    for n, firm in enumerate(FIRMS, 1):
        lg.add_invoice(inv(f"2026-000{n}", firm))
    lg.delete(invoices=["2026-0004"])
    before = lg.set_checks(["2026-0001", "2026-0002", "2026-0004"], "transcribed", True, "2026-06-10")
    assert [i.invoice_no for i in before] == ["2026-0001", "2026-0002"]  # (not the one in the trash)
    assert lg.set_checks(["2026-0001", "2026-0003"], "transcribed", True, "2026-06-11")[0].invoice_no == "2026-0003"
    got = {i.invoice_no: i.checks for i in lg.invoices()}
    assert got == {"2026-0001": {"transcribed": "2026-06-10"}, "2026-0002": {"transcribed": "2026-06-10"},
                   "2026-0003": {"transcribed": "2026-06-11"}}  # (ticked again: the first day kept)
    with open(tmp_path / "mirror" / "invoices.csv", encoding="utf-8-sig", newline="") as f:
        rows = {r["Invoice No."]: r for r in csv.DictReader(f)}
    assert rows["2026-0001"]["Transcribed"] == "6/10/2026" and rows["2026-0003"]["Status"] == "Open"
    lg.put_back_checks(before)
    assert {i.invoice_no: i.checks for i in lg.invoices()}["2026-0001"] == {}
    one = lg.invoice("2026-0003")
    lg.set_checks(["2026-0003"], "transcribed", False)
    lg.put_back(one)  # (the Undo of a change to one invoice puts its boxes back too)
    assert lg.invoice("2026-0003").checks == {"transcribed": "2026-06-11"}
    with sqlite3.connect(tmp_path / "r.db") as db:  # damaged rows read as nothing ticked
        db.execute("UPDATE invoices SET checks='{\"sent\": 5}' WHERE invoice_no='2026-0001'")
        db.execute("UPDATE invoices SET checks='[1, 2]' WHERE invoice_no='2026-0002'")
        db.execute("UPDATE invoices SET checks='not json' WHERE invoice_no='2026-0003'")
    assert all(i.checks == {} for i in lg.invoices())


def test_no_box_takes_a_records_column_name():
    from minute_filler.gui.records_window import INVOICE_COLS
    from minute_filler.tracking import _taken_headings
    assert {c.head.lower() for c in INVOICE_COLS} <= _taken_headings()


# ------------------------------------------------------------------ the window

@pytest.fixture
def records(qt, tmp_path):
    """The Records window with Paid, Transcribed and Transcript sent in use, and the four firms' invoices."""
    from minute_filler.deliver import ledger_for
    from minute_filler.gui.records_window import RecordsWindow
    s = pat_settings()
    s.records_dir = str(tmp_path / "records")
    s.tracking_boxes = box_rows(boxes_on("paid", "transcribed", "sent"))
    lg = ledger_for(s)
    for n, firm in enumerate(FIRMS, 1):
        lg.add_invoice(inv(f"2026-000{n}", firm))
    win = RecordsWindow(s)
    win.reload()
    win.i_year.setCurrentIndex(0)
    yield win, s, lg
    win.close()
    win.deleteLater()


def row_of(win, no):
    return next(r for r in range(win.inv_table.rowCount()) if win.inv_table.item(r, 0).data(256) == no)


def cell(win, no, key):
    from minute_filler.gui.records_window import col_index
    return win.inv_table.item(row_of(win, no), col_index(win.inv_cols, key))


def tint(win, no):
    """The colour of an invoice's row (None: none)."""
    from PySide6.QtCore import Qt
    it = cell(win, no, "no")
    return None if it.background().style() == Qt.NoBrush else it.background().color().name()


def test_transcribed_ticks_the_whole_transcript_and_undo_unticks_it(records, qt):
    from PySide6.QtCore import Qt
    win, _, lg = records
    t = win.inv_table
    assert not t.isColumnHidden(t.horizontalHeader().logicalIndex(1))  # (after Paid: Transcribed)
    assert t.horizontalHeaderItem(t.horizontalHeader().logicalIndex(1)).text() == "Transcribed"
    cell(win, "2026-0002", "box:transcribed").setCheckState(Qt.Checked)
    qt.QApplication.processEvents()
    assert all("transcribed" in i.checks for i in lg.invoices())
    assert all(cell(win, f"2026-000{n}", "box:transcribed").checkState() == Qt.Checked for n in range(1, 5))
    assert "Transcribed ticked on 4 invoices" in win.undo_btn.toolTip()
    cell(win, "2026-0001", "box:sent").setCheckState(Qt.Checked)  # (Transcript sent: this invoice alone)
    qt.QApplication.processEvents()
    assert [i.invoice_no for i in lg.invoices() if "sent" in i.checks] == ["2026-0001"]
    win.undo()
    win.undo()
    assert all(i.checks == {} for i in lg.invoices())


def test_the_rows_colours_follow_the_boxes(records):
    win, _, lg = records
    assert {tint(win, f"2026-000{n}") for n in range(1, 5)} == {TEAL}
    lg.mark_paid("2026-0001", "Regular", "100.00")
    win.show_invoices()
    assert tint(win, "2026-0001") == YELLOW and tint(win, "2026-0002") == TEAL
    assert cell(win, "2026-0001", "status").text() == "Paid, Not transcribed, Not sent"
    assert cell(win, "2026-0001", "no").background().color().alpha() == 80  # (see-through: light and dark)
    win._set_box(["2026-0001"], "transcribed", True)  # (the four: one transcript)
    assert {tint(win, f"2026-000{n}") for n in range(1, 5)} == {BLUE}  # the others haven't paid
    for n in range(2, 5):
        lg.mark_paid(f"2026-000{n}", "Regular", "100.00")
    win.show_invoices()
    assert {tint(win, f"2026-000{n}") for n in range(1, 5)} == {ORANGE}
    assert cell(win, "2026-0001", "status").toolTip().startswith("Ready to send\nPaid (Regular) on")
    win._set_box(["2026-0001"], "sent", True)
    assert tint(win, "2026-0001") == GREEN and tint(win, "2026-0002") == ORANGE
    lg.void("2026-0004")
    win.show_invoices()
    assert tint(win, "2026-0004") is None and cell(win, "2026-0004", "status").text() == "Void"
    from PySide6.QtCore import Qt
    assert not cell(win, "2026-0004", "box:sent").flags() & Qt.ItemIsEnabled  # (a void invoice can't be ticked)
    # the Status filter: the invoices of one colour, their totals, and the export's title
    i = win.i_status.findData("rule:Ready to send")
    assert win.i_status.itemText(1) == "Sent, not paid" and win.i_status.itemText(2) == "Done" and i > 0
    win.i_status.setCurrentIndex(i)
    assert sorted(x.invoice_no for x in win.shown) == ["2026-0002", "2026-0003"]
    assert win.kpi["count"].text() == "2" and win._filter_title().endswith("(ready to send)")
    win.s.records_colours = False  # no colours: the status text coloured as before
    win.i_status.setCurrentIndex(0)
    assert tint(win, "2026-0001") is None


def test_the_trash_has_no_boxes_colours_or_notes_to_type(records):
    from PySide6.QtCore import Qt
    win, _, lg = records
    lg.delete(invoices=["2026-0001"])
    win.i_trash.setChecked(True)
    assert win.inv_table.rowCount() == 1 and tint(win, "2026-0001") is None
    assert win.inv_table.isColumnHidden(0) and win.inv_table.isColumnHidden(len(win.inv_cols) - 1)
    assert not cell(win, "2026-0001", "notes").flags() & Qt.ItemIsEditable


def test_a_note_typed_in_the_table_is_kept_and_undone(records, qt, monkeypatch):
    from PySide6.QtCore import Qt
    from minute_filler.gui import records_window as rw
    win, _, lg = records
    note = cell(win, "2026-0003", "notes")
    assert note.flags() & Qt.ItemIsEditable and not cell(win, "2026-0003", "case").flags() & Qt.ItemIsEditable
    note.setText("Called Mon., will pay Fri.")
    qt.QApplication.processEvents()
    assert lg.invoice("2026-0003").notes == "Called Mon., will pay Fri."
    assert cell(win, "2026-0003", "notes").toolTip() == "Called Mon., will pay Fri."
    win.undo()
    assert lg.invoice("2026-0003").notes == ""
    # a database that can't be written says so, and the note shown is the one kept
    warned = []
    monkeypatch.setattr(rw.QMessageBox, "warning", lambda *a: warned.append(a[1]))
    monkeypatch.setattr(win.ledger, "set_notes", lambda *a: (_ for _ in ()).throw(sqlite3.OperationalError("locked")))
    cell(win, "2026-0003", "notes").setText("Lost")
    qt.QApplication.processEvents()
    assert warned == ["Could not save"] and cell(win, "2026-0003", "notes").text() == ""


def test_typing_a_note_doesnt_open_delete_or_close(records, qt, monkeypatch):
    """A double-click on Notes types (elsewhere it opens the PDF); Delete in the note deletes text, not the
    invoice; a refresh waits for the typing; Escape closes the note, not the window."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QAbstractItemView
    from minute_filler.gui import records_window as rw
    win, _, lg = records
    opened, asked = [], []
    monkeypatch.setattr(win, "_open_invoice", lambda i: opened.append(i.invoice_no))
    monkeypatch.setattr(rw.QMessageBox, "question", lambda *a: asked.append(a[1]) or rw.QMessageBox.No)
    win._double_clicked(cell(win, "2026-0001", "notes"))
    win._double_clicked(cell(win, "2026-0001", "case"))
    assert opened == ["2026-0001"]
    win.show()
    t = win.inv_table
    item = cell(win, "2026-0002", "notes")
    t.setCurrentItem(item)
    t.editItem(item)
    qt.QApplication.processEvents()
    assert t.state() == QAbstractItemView.EditingState
    win._delete_selected("invoices")
    QTest.keyClick(qt.QApplication.focusWidget(), Qt.Key_Delete)
    assert len(lg.invoices()) == 4 and asked == []  # (not even asked "Move 1 invoice to the trash?")
    win.show_invoices()  # (files made meanwhile, say): waits for the typing
    assert win._stale and t.state() == QAbstractItemView.EditingState
    QTest.keyClick(qt.QApplication.focusWidget(), Qt.Key_Escape)
    qt.QApplication.processEvents()
    assert win.isVisible() and t.state() != QAbstractItemView.EditingState and not win._stale


def test_ticking_keeps_the_place_and_the_menu_ticks_many(records, qt, monkeypatch):
    from PySide6.QtCore import QItemSelectionModel, Qt
    from minute_filler.gui import records_window as rw
    win, _, lg = records
    t = win.inv_table
    t.setCurrentCell(row_of(win, "2026-0003"), 2)
    cell(win, "2026-0001", "box:sent").setCheckState(Qt.Checked)
    qt.QApplication.processEvents()
    assert t.item(t.currentRow(), 0).data(Qt.UserRole) == "2026-0003"
    win.show_invoices()  # filled afresh (Paid ticked, files made): the same invoice still current
    assert t.currentRow() >= 0 and t.item(t.currentRow(), 0).data(Qt.UserRole) == "2026-0003"
    # the right-click menu: each box in use, on the invoices selected
    t.clearSelection()
    for no in ("2026-0001", "2026-0002"):
        t.selectionModel().select(t.model().index(row_of(win, no), 0),
                                  QItemSelectionModel.Select | QItemSelectionModel.Rows)
    seen = []

    class Menu(rw.QMenu):  # (shown, a menu would wait for a click)
        def exec(self, *a):
            seen.extend(self.actions())

    monkeypatch.setattr(rw, "QMenu", Menu)
    win.show()
    win._invoice_menu(t.visualItemRect(cell(win, "2026-0001", "no")).center())
    labels = [a.text() for a in seen]
    assert "Tick Transcribed (2 invoices)" in labels and "Tick Transcript sent (2 invoices)" in labels
    next(a for a in seen if a.text() == "Tick Transcript sent (2 invoices)").trigger()
    assert sorted(i.invoice_no for i in lg.invoices() if "sent" in i.checks) == ["2026-0001", "2026-0002"]
    assert "Transcript sent ticked on invoice 2026-0002" in win.undo_btn.toolTip()  # (0001 had it already)


def test_a_box_of_your_own_after_settings(records):
    from minute_filler.gui.records_window import INVOICE_COLS
    win, s, _ = records
    boxes = s.boxes() + [TrackBox("cabc123", "Proofread", "Proofread", "Not proofread", True)]
    s.tracking_boxes = box_rows(boxes)
    win.reload()
    t = win.inv_table
    col = len(win.inv_cols) - 1
    assert t.horizontalHeaderItem(col).text() == "Proofread" and not t.isColumnHidden(col)
    assert t.horizontalHeader().visualIndex(col) == 3  # (after Paid, Transcribed and Transcript sent)
    assert cell(win, "2026-0001", "status").text() == "Not paid, Not transcribed, Not sent, Not proofread"
    with open(os.path.join(s.records_dir, "invoices.csv"), encoding="utf-8-sig") as f:
        assert f.readline().strip().endswith("Transcribed,Transcript sent,Proofread")
    s.tracking_boxes = box_rows(boxes_on("paid"))  # back to Paid alone
    win.reload()
    assert win.inv_cols == INVOICE_COLS and t.columnCount() == len(INVOICE_COLS)
    assert cell(win, "2026-0001", "status").text() == "Not paid"


def test_tick_boxes_and_colours_open_settings_at_records(make_window, monkeypatch):
    from minute_filler.gui import main_window
    window = make_window(pat_settings())
    window.open_records()
    seen = []
    monkeypatch.setattr(main_window.SettingsDialog, "exec",
                        lambda self: seen.append(self.tabs.tabText(self.tabs.currentIndex())) or 0)
    window._records_win.on_settings("Records")
    assert seen == ["Records"]
    window._records_win.close()


# ------------------------------------------------------------------ the editor (Settings -> Records)

def test_the_editor_adds_moves_removes_and_restores(qt, monkeypatch):
    from minute_filler.gui import tracking_editor as te
    ed = te.TrackingEditor(default_boxes(), default_rules(), True)
    assert ed.rule_table.columnCount() == 5  # Colour, Name, Paid, Every firm paid, Note
    ed.box_table.setCurrentCell(3, te.NAME)
    ed._add_box()
    ed.box_table.item(4, te.NAME).setText("Proofread")
    ed.box_table.item(4, te.NO).setText("")
    assert [(b.name, b.on, b.no) for b in ed.boxes()][4] == ("Proofread", True, "")
    assert ed.rule_table.horizontalHeaderItem(3).text() == "Proofread"
    ed._move_box(-1)
    assert [b.name for b in ed.boxes()][3] == "Proofread"
    ed.box_table.setCurrentCell(0, te.NAME)
    assert not ed.remove_box.isEnabled()  # (Paid: switched off, never removed)
    ed.box_table.setCurrentCell(3, te.NAME)
    ed._remove_box()
    assert "Proofread" not in [b.name for b in ed.boxes()]
    # a colour's box cell: ticked -> not ticked -> either way -> ticked
    assert ed.rules()[8].name == "Paid" and ed.rule_table.item(8, 2).text() == "✓"
    ed._rule_clicked(8, 2)
    assert ed.rules()[8].when == {"paid": False} and ed.rule_table.item(8, 2).text() == "✗"
    ed._rule_clicked(8, 2)
    assert ed.rules()[8].when == {} and "Colours every row" in ed.rule_table.item(8, 4).text()
    ed._rule_clicked(8, 2)
    assert ed.rules()[8].when == {"paid": True} and ed.rule_table.item(8, 4).text() == ""
    assert "Not used: Transcript sent is not in use" == ed.rule_table.item(0, 4).text()
    monkeypatch.setattr(te.QMessageBox, "question", lambda *a: te.QMessageBox.Yes)
    ed._default_rules()
    assert ed.rules() == default_rules()
    # with Transcribed in use, the colours above "Paid, waiting on other firms" always come first
    ed = te.TrackingEditor(boxes_on("paid", "transcribed", "sent"), default_rules(), True)
    last = ed.rule_table.columnCount() - 1
    assert ed.rule_table.item(7, last).text() == "Not used with these boxes: the colours above it come first"
    assert ed.rule_table.item(2, last).text() == ""


def test_settings_records_tab_round_trip(qt, tmp_path):
    from PySide6.QtCore import Qt
    from minute_filler.gui.dialogs import SettingsDialog
    s = pat_settings()
    s.save()
    dlg = SettingsDialog(s)
    dlg.show_tab("Records")
    assert dlg.tabs.tabText(dlg.tabs.currentIndex()) == "Records"
    ed = dlg.k_track
    ed.box_table.item(2, 0).setCheckState(Qt.Checked)  # Transcribed: Use
    ed.colours.setChecked(False)
    assert ed.count.currentData() == "Ready to send"  # (the Records button's count, at first)
    ed.count.setCurrentIndex(ed.count.findData("Not paid"))
    dlg.accept()
    got = Settings.load()
    assert [b.on for b in got.boxes()] == [True, False, True, False] and not got.records_colours
    assert got.records_count == "Not paid"
    assert json.loads(got.path.read_text(encoding="utf-8"))["settings_version"] == Settings.settings_version
