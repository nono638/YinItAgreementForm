"""The main window's room and clarity (the user, 2026-10-11): the status and buttons in the menu bar, a divider
above the Outputs box and one above the paste box (kept for next time), the Outputs box and the cards folded to a
line, the drop zone one slim row once documents are read (and files dropped anywhere), the type of proceeding in
the Case card; the status counting the job's own checks (a click goes to the first), the badges in plain words,
"2 more ▾", the attorney table's details under it; a calendar for the dates, fields completing from the records,
a View menu, Undo for New job (no question), the Generate button's count, the jobs made lately on an empty window,
and the Records button's count (Settings -> Records, which can turn it off). All names and numbers are made up."""
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import QDate, QMimeData, QPointF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402

from helpers import pat_settings, transcript_pdf  # noqa: E402
from minute_filler.models import FieldState  # noqa: E402
from minute_filler.records import Invoice, Ledger, live_invoices, past_values, recent_jobs  # noqa: E402
from minute_filler.settings import Settings  # noqa: E402
from minute_filler.tracking import NOT_PAID, box_rows, count_names, count_of, default_boxes, default_rules  # noqa: E402

CASE = "Jane Roe v. X.Y. Holding Corporation"
EMAIL = ("From: Dana Smith <dsmith@smithlaw.example>\nTo: Pat Reporter <preporter@example.com>\n"
         "Subject: minutes\n\nPlease send the minutes for Jane Roe v. X.Y. Holding Corporation, Index 712345/2021, "
         "of 6/3/2026, expedited.\nDana Smith, Smith Law, 555-0100\n")


@pytest.fixture
def window(tmp_path, monkeypatch, make_window):
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", lambda self: 0)
    s = pat_settings(initials="pr")
    s.use_ai = s.open_after = False
    s.output_dir = str(tmp_path / "out")
    return make_window(s)


def wait(win, until, seconds=20):
    """Runs the event loop until no work is running and `until()` holds; fails after `seconds`."""
    end = time.time() + seconds
    while time.time() < end:
        QtWidgets.QApplication.processEvents()
        if not win.runner._live and until():
            return
        time.sleep(0.01)
    raise AssertionError("timed out")


def pump(seconds=0.2):
    end = time.time() + seconds
    while time.time() < end:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.01)


def read_transcript(win, tmp_path, name="Roe.pdf", **kw):
    """The job on screen: a made-up transcript of Jane Roe v. X.Y. Holding Corporation (its attorneys unticked)."""
    pdf = transcript_pdf(tmp_path / name, **kw)
    win.add_files([str(pdf)])
    wait(win, lambda: bool(win.cur.docs))
    return pdf


def files_dropped(*paths) -> tuple[QDropEvent, QMimeData]:
    """A drop of these files, and its data (kept by the caller: the event doesn't keep it alive)."""
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    return QDropEvent(QPointF(5, 5), Qt.CopyAction, md, Qt.LeftButton, Qt.NoModifier), md


# ------------------------------------------------------------------ room on the screen

def test_the_status_and_buttons_are_in_the_menu_bar_without_a_title_row(window):
    corner = window.menuBar().cornerWidget(Qt.TopRightCorner)
    assert all(corner.isAncestorOf(w) for w in (window.status, window.rec_btn, window.new_btn))
    assert not [w for w in window.findChildren(QtWidgets.QLabel) if w.objectName() in ("title", "subtitle")]


def test_the_dividers_hold_the_form_the_outputs_the_list_and_the_paste_box_and_are_kept(window, make_window):
    split = window.form_scroll.parentWidget()
    assert isinstance(split, QtWidgets.QSplitter) and split.orientation() == Qt.Horizontal
    assert window.vsplit.widget(0) is split and window.vsplit.widget(1) is window.foot
    assert window.left_split.widget(0).isAncestorOf(window.job_list)
    assert window.left_split.widget(1).isAncestorOf(window.paste)
    window.resize(1400, 900)
    window.show()
    pump()
    window.vsplit.setSizes([600, 300])
    kept = window.vsplit.sizes()
    window.close()
    saved = Settings.load()
    assert set(saved.window_splits) == {"outer", "left"}
    again = make_window(saved)
    again.resize(1400, 900)
    again.show()
    pump()
    # (made, the window was first fitted to the small screen offscreen, which moved the divider: put back, at the
    # same size, it is where it was)
    again._restore_splits()
    assert abs(again.vsplit.sizes()[1] - kept[1]) <= 20
    again.close()


def test_the_outputs_box_folds_to_a_line_of_boxes_that_tick_the_panels(window):
    window.resize(1366, 768)
    window.show()
    pump()
    form_before = window.vsplit.sizes()[0]
    window._fold_outputs(True)
    pump()
    assert window.outputs_body.isHidden() and not window.outputs_line.isHidden()
    assert window.vsplit.sizes()[0] > form_before + 150  # (the room goes to the form)
    assert Settings.load().outputs_folded and window.fold_outputs_action.isChecked()
    window.mini_outputs["invoice"].setChecked(True)
    assert window.output_boxes["invoice"].isChecked() and "invoice" in window.s.outputs
    speeds = ", ".join(n for n, cb in window.inv_speed_boxes.items() if cb.isChecked())
    assert window.mini_speeds.text() == f"({speeds})"
    window.output_boxes["invoice"].setChecked(False)
    assert not window.mini_outputs["invoice"].isChecked() and window.mini_speeds.isHidden()
    window._fold_outputs(False)
    assert not window.outputs_body.isHidden() and not Settings.load().outputs_folded
    window.close()


def test_the_drop_zone_is_a_slim_row_once_documents_are_read(window, tmp_path):
    from minute_filler.gui.main_window import DROP_MORE_TEXT, DROP_TEXT
    assert not window.drop.slim and window.drop.text.text() == DROP_TEXT
    read_transcript(window, tmp_path)
    assert window.drop.slim and window.drop.text.text() == DROP_MORE_TEXT
    window.new_job()
    assert not window.drop.slim and window.drop.text.text() == DROP_TEXT


def test_a_file_dropped_on_a_field_is_read_not_typed_into_it(window, tmp_path):
    pdf = transcript_pdf(tmp_path / "Roe.pdf")
    edit = window.rows["part"].edit
    drop, _md = files_dropped(pdf)
    # (what the window's event filter is given for a drop on the field: a drop made up offscreen isn't delivered)
    assert window.eventFilter(edit, drop) is True
    wait(window, lambda: bool(window.cur.docs))
    assert str(pdf) not in edit.text() and "Roe.pdf" not in edit.text()
    text = QMimeData()
    text.setText("Part 14")
    plain = QDropEvent(QPointF(5, 5), Qt.CopyAction, text, Qt.LeftButton, Qt.NoModifier)
    assert not window._drag_filter(edit, plain)  # (text dropped on a field is the field's)


def test_a_file_dropped_on_the_window_itself_is_read(window, tmp_path):
    pdf = transcript_pdf(tmp_path / "Roe.pdf")
    drop, _md = files_dropped(pdf)
    window.dropEvent(drop)
    wait(window, lambda: bool(window.cur.docs))
    assert window.cur.docs[0].ing.name == "Roe.pdf"


def test_the_left_divider_gives_one_job_the_paste_box_and_a_batch_the_list(window, tmp_path):
    window.resize(1400, 900)
    window.show()
    pump()
    top, bottom = window.left_split.sizes()
    assert top < bottom  # (one job: a short list)
    window.left_split.setSizes([60, 400])  # (dragged: the paste box given still more)
    a = transcript_pdf(tmp_path / "Roe 6-3.pdf")
    b = transcript_pdf(tmp_path / "Roe 6-4.pdf", date="June 4, 2026")
    window.add_files([str(a), str(b)], batch=True)
    wait(window, lambda: len(window.jobs) == 2)
    pump()
    top, bottom = window.left_split.sizes()
    least = window.left_split.widget(1).minimumSizeHint().height()
    assert top > bottom and bottom <= least + 30  # (a batch: the list; the paste box a few lines)
    window.close()


def test_the_type_of_proceeding_is_in_the_case_card(window):
    assert window.cards["case"].isAncestorOf(window.proc_boxes["Trial"])
    headings = [w.text() for w in window.findChildren(QtWidgets.QLabel) if w.objectName() == "section"]
    assert "Type of proceeding" not in headings and "Case" in headings


# ------------------------------------------------------------------ clarity

def test_the_status_counts_the_jobs_checks_and_a_click_goes_to_the_first(window, tmp_path):
    read_transcript(window, tmp_path)  # (a transcript lists who appeared, not who ordered: nobody is ticked)
    assert window.cur.no_attorney_chosen()
    assert window.status.text() == "⚠  1 to check" and window.status.property("state") == "warn"
    assert "⚠ no attorney is ticked" in window.status.toolTip()
    window._fold_card(window.cards["attorneys"], True)
    window.status.clicked.emit()
    assert not window.cards["attorneys"].body.isHidden() and window.att.currentRow() == 0
    # a required field blank comes first: its card unfolds and the field lights up
    window._fold_card(window.cards["case"], True)
    window.rows["index_no"].choose("")
    assert "1 missing" in window.status.text() and "Missing: Index Number" in window.status.toolTip()
    window.status.clicked.emit()
    assert not window.cards["case"].body.isHidden() and window.rows["index_no"].edit.property("flash") is True


def test_the_status_is_ready_when_nothing_needs_a_look(window, tmp_path):
    read_transcript(window, tmp_path)
    window.att.item(0, 0).setCheckState(Qt.Checked)
    assert window._job_checks() == []
    assert window.status.text() in ("✓  Ready to fill",) or window.status.text().startswith("Ready to fill  ·")


def test_the_badges_say_where_a_value_came_from_in_plain_words(window, tmp_path):
    read_transcript(window, tmp_path)
    court = window.rows["court"]
    assert court.state.source == "regex" and court.badge.text() == "found" and court.badge.property("src") == "regex"
    derived = [r for r in window.rows.values() if r.state.source == "derived" and r.state.value]
    assert derived and all(r.badge.text() == "worked out" for r in derived)


def test_other_readings_of_a_field_say_how_many(window):
    row = window.rows["judge"]
    row.set_state(FieldState("Maria T. Alvarez", "regex", 0.9, ["Maria T. Alvarez", "M. Alvarez", "Alvarez"]))
    assert row.alts.text() == "2 more ▾" and not row.alts.isHidden()
    assert "2 other readings" in row.alts.toolTip()
    row.set_state(FieldState("Maria T. Alvarez", "regex", 0.9, ["Maria T. Alvarez"]))
    assert row.alts.isHidden()


def test_the_attorney_table_shows_who_and_the_details_under_it(window, tmp_path, monkeypatch):
    from minute_filler.gui import main_window as mw
    read_transcript(window, tmp_path)
    assert [window.att.isColumnHidden(c) for c in range(9)] == [c in mw.ATT_DETAIL_COLS for c in range(9)]
    window.att.setCurrentCell(1, 1)
    assert window.att_edits[1].text() == window.att.item(1, 1).text()
    assert "Details of row 2" in window.att_which.text()
    window.att_edits[2].setText("Counsel & Counsel LLP")
    window.att_edits[2].editingFinished.emit()
    assert window.att.item(1, 2).text() == "Counsel & Counsel LLP" and window.case.attorneys[1].firm == \
        "Counsel & Counsel LLP"
    window.att_edits[3].setPlainText("1 Main Street\n\nKew Gardens, NY 11415")
    window._att_detail_edited(3)
    assert window.att.item(1, 3).text() == "1 Main Street / Kew Gardens, NY 11415"
    assert window.case.attorneys[1].address == "1 Main Street\nKew Gardens, NY 11415"
    # Ctrl+Enter while a detail is still being typed: it is taken as typed (_commit_edit)
    phone = window.att_edits[4]
    phone.setText("555-0100")
    monkeypatch.setattr(mw.QApplication, "focusWidget", staticmethod(lambda: phone))
    window._commit_edit()
    assert window.att.item(1, 4).text() == "555-0100" and window.case.attorneys[1].phone == "555-0100"


def test_a_folded_card_sums_itself_up_with_a_warning_and_is_kept(window, tmp_path):
    read_transcript(window, tmp_path)
    window._fold_card(window.cards["case"], True)
    summary = window.cards["case"].summary
    assert window.cards["case"].body.isHidden() and not window.cards["case"].isHidden()
    assert summary.full().startswith("Jane Roe") and "712345" in summary.full()
    assert Settings.load().folded_cards == ["case"]
    window.rows["index_no"].choose("")
    assert summary.full().startswith("⚠ ")
    window._fold_card(window.cards["case"], False)
    assert Settings.load().folded_cards == []


# ------------------------------------------------------------------ new pieces

def test_the_calendar_picks_a_day_as_typed(window, tmp_path):
    read_transcript(window, tmp_path)
    row = window.rows["delivery_date"]
    row.month.clicked.emit(QDate(2026, 10, 20))
    assert row.text() == "10/20/2026" and window.case.fields["delivery_date"].source == "you"
    assert window.rows["agreement_date"].calendar is not None and window.rows["dates"].calendar is None


def test_the_fields_complete_from_the_records(window):
    led = Ledger()
    for firm in ("Smith Law", "smith  law", "Counsel & Counsel"):
        led.log_activity("agreement", case_name=CASE, judge="Maria T. Alvarez", part="14", firm=firm,
                         attorney="Dana Smith")
    values = past_values()
    assert values["firm"] == ["Smith Law", "Counsel & Counsel"] and values["judge"] == ["Maria T. Alvarez"]
    window._read_records_side()
    wait(window, lambda: "judge" in window._completions)
    assert window.rows["judge"].edit.completer().model().stringList() == ["Maria T. Alvarez"]
    assert window.att_edits[2].completer().model().stringList() == ["Smith Law", "Counsel & Counsel"]
    assert window.att_edits[1].completer().model().stringList() == ["Dana Smith"]


def test_the_view_menu_zooms_changes_the_theme_and_folds(window):
    texts = [a.text().split("\t")[0] for a in window.view_menu.actions()]
    assert texts[:3] == ["Zoom &in", "Zoom &out", "&Actual size"]
    dark = next(a for a in window.theme_actions.actions() if a.data() == "dark")
    dark.trigger()
    assert window.s.theme == "dark" and Settings.load().theme == "dark"
    window._fold_all(True)
    assert all(fr.body.isHidden() for fr in window.cards.values())
    assert set(Settings.load().folded_cards) == set(window.cards)
    window._fold_all(False)
    assert not any(fr.body.isHidden() for fr in window.cards.values())


def test_new_job_asks_nothing_and_undo_brings_the_batch_back(window, tmp_path, monkeypatch):
    def asked(*_a, **_k):
        raise AssertionError("New job asked")
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", asked)
    a = transcript_pdf(tmp_path / "Roe 6-3.pdf")
    b = transcript_pdf(tmp_path / "Roe 6-4.pdf", date="June 4, 2026")
    window.add_files([str(a), str(b)], batch=True)
    wait(window, lambda: len(window.jobs) == 2)
    window._select_job(window.jobs[1])  # (the second day on screen: Undo shows it again)
    window.paste.setPlainText("notes")
    jobs, shown = list(window.jobs), window.cur
    assert shown is window.jobs[1]
    window.new_job()
    assert window.cur.is_empty() and len(window.jobs) == 1
    assert not window.undo_box.isHidden() and not window.undo_btn.isHidden() and "2 jobs" in window.undo_text.text()
    window.undo_btn.click()
    assert window.jobs == jobs and window.cur is shown and window.paste.toPlainText() == "notes"
    assert window.undo_box.isHidden() and window.job_list.topLevelItemCount() == 2


def test_no_undo_while_documents_are_being_read_and_none_after_new_input(window, tmp_path):
    read_transcript(window, tmp_path)
    window.work += 1  # (a folder still being read: what it reads is dropped by New job)
    window.new_job()
    assert window._undo is None and window.undo_btn.isHidden() and window.undo_text.text() == "Cleared."
    read_transcript(window, tmp_path, "Roe 2.pdf")
    window.new_job()
    assert window._undo is not None
    window.paste.setPlainText("Please send the minutes")  # something new: the Undo would throw it away
    assert window._undo is None and window.undo_box.isHidden()


def test_generate_says_how_many_files_it_makes(window, tmp_path):
    assert window.fill_btn.text() == "Generate"
    read_transcript(window, tmp_path)
    window.att.item(0, 0).setCheckState(Qt.Checked)
    assert window.fill_btn.text().startswith("Generate  (") and window.fill_btn.text().endswith(("file)", "files)"))


def test_an_empty_window_lists_the_jobs_made_lately_and_marks_nothing_missing(window, tmp_path, monkeypatch):
    led = Ledger()
    led.log_activity("agreement", case_name=CASE, dates="6/3/2026", origin='{"case": {}}', ts="2026-10-09T10:00:00")
    led.log_activity("invoice", case_name=CASE, dates="6/3/2026", origin='{"case": {}}', ts="2026-10-09T10:00:01")
    led.log_activity("agreement", case_name="John Smith v. Jones Trucking Corp.", dates="5/22/2026",
                     origin='{"x": 1}', ts="2026-10-08T15:30:00")
    led.log_activity("agreement", case_name="No origin v. Kept", dates="5/1/2026", ts="2026-10-10T09:00:00")
    assert [(c, d) for c, d, _, _ in recent_jobs()] == [(CASE, "6/3/2026"),
                                                        ("John Smith v. Jones Trucking Corp.", "5/22/2026")]
    window._read_records_side()
    wait(window, lambda: len(window._recent_jobs) == 2)
    assert not window.start_card.isHidden() and window.start_card.heading.text() == "Recent jobs"
    links = [window.start_list.itemAt(i).widget() for i in range(window.start_list.count())]
    assert links[0].text() == f"{CASE}  ·  6/3/2026  ·  made 10/9/2026"
    opened = []
    monkeypatch.setattr(window, "open_past_job", lambda o: opened.append(o) or True)
    links[1].clicked.emit()
    assert opened == ['{"x": 1}']
    assert window.rows["index_no"].edit.property("missing") is False
    window.paste.setPlainText("Please send the minutes")
    assert window.start_card.isHidden() and window.rows["index_no"].edit.property("missing") is True


# ------------------------------------------------------------------ the Records button's count

def invoices_of_one_transcript():
    """Two firms of the 6/3/2026 transcript, both paid, transcribed: Ready to send. Two of the 6/4/2026 one,
    transcribed: Doe PC paid, waiting on Roe & Co., which hasn't paid (so neither is Ready to send)."""
    def inv(no, firm, dates="6/3/2026", **kw):
        return Invoice(invoice_no=no, created="2026-06-04", case_name=CASE, index_no="712345/2021", dates=dates,
                       firm=firm, pages=100, amounts={"Regular": "100.00"}, billed_speed="Regular",
                       checks={"transcribed": "2026-06-10"}, **kw)
    return [inv("2026-0001", "Smith Law", status="paid"), inv("2026-0002", "Counsel & Counsel", status="paid"),
            inv("2026-0003", "Doe PC", dates="6/4/2026", status="paid"), inv("2026-0004", "Roe & Co.", dates="6/4/2026")]


def boxes_with(*keys):
    out = default_boxes()
    for b in out:
        b.on = b.kind == "paid" or b.key in keys
    return out


def test_the_count_of_a_status():
    invoices, rules = invoices_of_one_transcript(), default_rules()
    boxes = boxes_with("transcribed", "sent")
    assert count_of("Ready to send", invoices, boxes, rules) == 2
    assert count_of(NOT_PAID, invoices, boxes, rules) == 1
    assert count_of("", invoices, boxes, rules) == 0
    assert count_of("Ready to send", invoices, boxes_with(), rules) == 0  # (Paid alone: it can't happen)
    assert count_names(boxes_with(), rules) == [NOT_PAID]
    assert "Ready to send" in count_names(boxes, rules) and "Paid" not in count_names(boxes, rules)


def test_the_records_button_counts_and_can_be_turned_off(window):
    led = Ledger()
    for i in invoices_of_one_transcript():
        led.add_invoice(i)
    assert len(live_invoices()) == 4
    window.s.tracking_boxes = box_rows(boxes_with("transcribed", "sent"))
    window.s.records_count = "Ready to send"
    window._count_records()
    wait(window, lambda: window.rec_btn.text() != "Records")
    assert window.rec_btn.text() == "Records · Ready to send: 2" and "2 invoices are Ready to send" in \
        window.rec_btn.toolTip()
    window.s.records_count = NOT_PAID
    window._count_records()
    wait(window, lambda: window.rec_btn.text() == "Records · Not paid: 1")
    window.s.records_count = ""  # Nothing
    window._count_records()
    assert window.rec_btn.text() == "Records"


def test_settings_records_chooses_the_count(qt):
    from minute_filler.gui.tracking_editor import TrackingEditor
    ed = TrackingEditor(boxes_with(), default_rules(), True, "Ready to send")
    labels = [ed.count.itemText(i) for i in range(ed.count.count())]
    assert labels == ["Nothing", NOT_PAID, "Ready to send (with these boxes: Not paid)"]
    assert ed.count_name() == "Ready to send"
    ed.count.setCurrentIndex(ed.count.findData(""))
    assert ed.count_name() == ""
    ed = TrackingEditor(boxes_with("transcribed", "sent"), default_rules(), True, "Ready to send")
    assert ed.count.currentText() == "Ready to send"
    s = Settings()
    s.records_count = "Paid, not transcribed"
    s.save()
    assert Settings.load().records_count == "Paid, not transcribed"
