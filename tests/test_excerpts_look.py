"""How Who ordered which pages looks and clicks (gui/firm_columns.py, gui/excerpts.py): a band of each firm's colour
over its name, a stripe of it down its column, the speed list in its heading, a click anywhere in a cell ticking
it, how wide the columns are, what the cells and the lines under the table say (prices, held invoices, pages typed),
the row and column chosen after a change, Split run…, and one rebuild of the table for one change. What the table's
prices are made of: tests/test_excerpts.py, tests/test_mixed_speeds.py; that they are what Generate bills:
tests/test_excerpts_money.py. Prices are from the bundled "Sample Rates" sheet: at Expedite, an original of $5.40, a
copy and an e-mailed copy of $1.10 a page, so $7.60 a page alone and $4.90 a page shared by two. A day of 30 pages
(helpers.transcript_pdf) shows the page numbers "101–130". All names are made up."""
import os
from decimal import Decimal

import pytest

from helpers import pat_settings, transcript_pdf
from minute_filler.batch import group, read_docs
from minute_filler.excerpts import Run, case_days, firms_of, prices, runs_of, store
from minute_filler.models import Attorney

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

DANA = dict(name="Dana Smith", firm="Smith Law", party="Plaintiff")
ALEX = dict(name="Alex B. Counsel", firm="Counsel & Counsel", party="Defendant")
KIM = dict(name="Kim Park", firm="Park PC", party="Defendant")
D, A, K = (Attorney(**x).key() for x in (DANA, ALEX, KIM))


@pytest.fixture
def s(tmp_path):
    s = pat_settings()
    s.output_dir, s.records_dir = str(tmp_path / "out"), str(tmp_path / "records")
    s.invoice_speeds = ["Regular", "Expedite"]
    s.invoice_include_index = False
    return s


@pytest.fixture
def themed(qt):
    """The app in the light theme (a window without it measures narrower than on screen); the zoom and the style sheet
    left as they were."""
    from minute_filler.gui import zoom
    from minute_filler.gui.theme import apply_theme
    app = qt.QApplication.instance()
    style, palette = app.styleSheet(), app.palette()
    apply_theme(app, "light")
    yield apply_theme
    zoom.set_zoom(1.0)
    app.setStyleSheet(style)
    app.setPalette(palette)


def days_of(tmp_path, s, pages=(30,), firms=(DANA, ALEX, KIM), ticked=(D, A), initials=None):
    """Jobs of a transcript per number in `pages`, one day each (at Expedite, as on the agreement form), with these
    firms, those in `ticked` ordering every page."""
    when = ("June 3, 2026", "June 4, 2026", "June 5, 2026")
    docs, errors = read_docs([str(transcript_pdf(tmp_path / f"Day {i}.pdf", n, date=when[i], initials=initials))
                              for i, n in enumerate(pages)], s)
    assert not errors
    jobs = group(docs, s)
    for j in jobs:
        j.case.attorneys = [Attorney(**x, checked=Attorney(**x).key() in ticked) for x in firms]
        j.case.set("delivery", "Expedite")
        j.att_touched = True
    return jobs


def pump(qt, times=8):
    for _ in range(times):
        qt.QApplication.processEvents()


def open_window(qt, jobs, s, told=None):
    """The window on these days, shown off screen."""
    from minute_filler.gui.excerpts import ExcerptsWindow
    w = ExcerptsWindow(s, (lambda: told.append(1)) if told is not None else (lambda: None))
    w.load(jobs)
    w.show()
    pump(qt)
    return w


def split(w, day, *rows):
    """A day's runs from (first place, last place, firms) rows, kept and shown."""
    d = next(x for x in w.days if x is day)
    store(d, [Run(d, a, b, list(keys)) for a, b, keys in rows], w.firms, w.s)
    w.load(w.group)


def cell(w, r, key):
    """The cell of firm `key` in row r."""
    from minute_filler.gui.excerpts import FIRST_FIRM
    return w.table.item(r, FIRST_FIRM + [a.key() for a in w.firms].index(key))


def section_of(w, key):
    """The heading's section of firm `key`."""
    from minute_filler.gui.excerpts import FIRST_FIRM
    return FIRST_FIRM + [a.key() for a in w.firms].index(key)


def colour_of(w, key):
    from minute_filler.gui.badges import tag_color
    return tag_color(w._marks[key]).name()


# ------------------------------------------------------------------ the band and the stripe
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_each_firm_has_its_colour_in_a_band_with_no_shade_behind_its_name(qt, themed, tmp_path, s, theme):
    """Over the firm's name, drawn in the heading (a firm's name on a pale shade read as a field to check: the user,
    2026-10-22, so only the band is coloured), and the other headings none. Past the last column, the strip goes on."""
    from minute_filler.gui.firm_columns import BAND, GAP
    from minute_filler.gui.theme import DARK, LIGHT
    from minute_filler.gui.zoom import z
    themed(qt.QApplication.instance(), theme)
    tokens = LIGHT if theme == "light" else DARK
    w = open_window(qt, days_of(tmp_path, s), s)
    head = w.table.horizontalHeader()
    picture = head.grab().toImage()
    seen = set()
    for key in (D, A, K):
        logical = section_of(w, key)
        x = head.sectionViewportPosition(logical)
        middle = x + head.sectionSize(logical) // 2
        assert picture.pixelColor(middle, z(BAND) // 2).name() == colour_of(w, key)
        # (no shade on the name's row)
        assert picture.pixelColor(x + 2, z(BAND) + z(GAP) + 2).name() == tokens["header_bg"]
        seen.add(colour_of(w, key))
    assert len(seen) == 3
    assert picture.pixelColor(head.sectionViewportPosition(0) + 2, 2).name() == tokens["header_bg"]  # Date: no band
    assert picture.pixelColor(head.length() + 5, 10).name() == tokens["header_bg"]
    w.close()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_stripe_keeps_its_colour_on_a_selected_row(qt, themed, tmp_path, s, theme):
    """Down each firm's column, ticked or not; on a selected row Qt tints what a style draws (the square went brown
    that way in 2.14.1), and this is drawn over it."""
    themed(qt.QApplication.instance(), theme)
    jobs = days_of(tmp_path, s)
    w = open_window(qt, jobs, s)
    split(w, w.days[0], (1, 10, [D, A]), (11, 30, [A]))
    w.table.selectRow(0)
    pump(qt)
    picture = w.table.viewport().grab().toImage()
    for r in (0, 1):  # (row 0 selected, Dana ticked; row 1 not, Dana unticked)
        for key in (D, A, K):
            rect = w.table.visualItemRect(cell(w, r, key))
            assert picture.pixelColor(rect.left() + 1, rect.center().y()).name() == colour_of(w, key), (r, key)
    w.close()


def test_a_firm_without_a_mark_has_no_band_or_stripe_and_still_works(qt, themed, tmp_path, s):
    """The colour is a help: with no marks the columns work as ever, with nothing painted."""
    from minute_filler.gui.badges import STRIPE_ROLE
    from minute_filler.gui.excerpts import ExcerptsWindow, FIRST_FIRM
    jobs = days_of(tmp_path, s)
    w = ExcerptsWindow(s, lambda: None, marks=lambda job: {})
    w.load(jobs)
    w.show()
    pump(qt)
    assert w.table.horizontalHeaderItem(FIRST_FIRM).data(STRIPE_ROLE) is None
    assert w.table.item(0, FIRST_FIRM).data(STRIPE_ROLE) is None
    assert w.table.horizontalHeader().grab().toImage().pixelColor(
        w.table.horizontalHeader().sectionViewportPosition(FIRST_FIRM) + 40, 2).name() != "#ea580c"
    assert "Dana Smith" in w.summary.text() and "&#9632;" not in w.summary.text()
    w.close()


def test_a_price_to_commit_to_stays_amber_on_a_selected_row(qt, themed, tmp_path, s):
    """The style sheet's item:selected sets one colour for the text of a selected row: the amber went."""
    from PySide6.QtGui import QColor
    from minute_filler.gui.excerpts import AMBER
    s.split_speeds = "ask"
    w = open_window(qt, days_of(tmp_path, s), s)
    assert cell(w, 0, D).text() == "Expedite? · $147.00 (÷2)"
    w.table.selectRow(0)
    pump(qt)
    picture = w.table.viewport().grab().toImage()
    rect = w.table.visualItemRect(cell(w, 0, D))
    amber = QColor(AMBER)
    pixels = [picture.pixelColor(x, y) for x in range(rect.left(), rect.right())
              for y in range(rect.top(), rect.bottom())]
    assert any(abs(c.red() - amber.red()) + abs(c.green() - amber.green()) + abs(c.blue() - amber.blue()) < 12
               for c in pixels)
    w.close()


@pytest.mark.parametrize("level", [1.0, 1.6])
def test_a_cells_text_clears_its_box_selected_or_not_at_any_zoom(qt, themed, tmp_path, s, level):
    """On a selected row the style puts the text in one place whatever the zoom, and at 160 % the box had grown over
    it: "$117.60" under the tick."""
    from minute_filler.gui import zoom
    from minute_filler.gui.theme import LIGHT
    zoom.set_zoom(level)
    themed(qt.QApplication.instance(), "light")
    w = open_window(qt, days_of(tmp_path, s, pages=(30, 30)), s)
    w.table.selectRow(1)
    pump(qt)
    picture = w.table.viewport().grab().toImage()
    for r, background in ((0, LIGHT["card"]), (1, LIGHT["sel"])):
        rect = w.table.visualItemRect(cell(w, r, D))
        y = rect.center().y()
        right = max(x for x in range(rect.left() + 8, rect.left() + zoom.z(50))
                    if picture.pixelColor(x, y).name() == LIGHT["accent"])  # (the box's blue: its right edge)
        assert picture.pixelColor(right + 2, y).name() == background
        gap = [picture.pixelColor(right + dx, yy).name() for dx in range(2, 5)
               for yy in range(rect.top() + 2, rect.bottom() - 1)]
        assert set(gap) == {background}, (r, set(gap))
    w.close()


# ------------------------------------------------------------------ clicks
@pytest.fixture
def clicking(qt, themed, tmp_path, s):
    """A window on one day, Dana and Alex ordering it, and the times the main window was told of a change."""
    told = []
    w = open_window(qt, days_of(tmp_path, s), s, told)
    w.activateWindow()
    w.table.setFocus()
    pump(qt)
    yield w, told
    w.close()


def click_at(qt, w, row, key, button=None, x=None):
    """A click in a firm's cell, at x from its left (default: well to the right of the box)."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    rect = w.table.visualItemRect(cell(w, row, key))
    at = QPoint(rect.right() - 6 if x is None else rect.left() + x, rect.center().y())
    QTest.mouseClick(w.table.viewport(), button or Qt.LeftButton, Qt.NoModifier, at)
    pump(qt)


def test_a_click_anywhere_in_a_firms_cell_ticks_it_once(qt, clicking):
    w, told = clicking
    click_at(qt, w, 0, D)  # off the box
    assert w.runs[0].keys == [A] and told == [1]
    click_at(qt, w, 0, D, x=12)  # on the box: once too, not twice
    assert sorted(w.runs[0].keys) == sorted([D, A]) and told == [1, 1]
    click_at(qt, w, 0, K)  # a firm unticked: ticked
    assert K in w.runs[0].keys


def test_a_right_click_on_a_cell_is_the_runs_menu_and_ticks_nothing(qt, clicking, monkeypatch):
    """Only the left button ticks: the right one is the run's menu, and the middle one does nothing either."""
    from PySide6.QtCore import Qt
    w, told = clicking
    click_at(qt, w, 0, D, Qt.RightButton)
    click_at(qt, w, 0, D, Qt.MiddleButton)
    assert sorted(w.runs[0].keys) == sorted([D, A]) and told == []


def typing(qt, w, text, row=0):
    """A run typed in Page numbers, the editor still open: not kept until it closes."""
    from PySide6.QtWidgets import QAbstractItemView, QLineEdit
    from minute_filler.gui.excerpts import PAGES
    w.table.setCurrentCell(row, PAGES)
    w.table.editItem(w.table.item(row, PAGES))
    pump(qt)
    editor = qt.QApplication.focusWidget()
    assert isinstance(editor, QLineEdit) and w.table.state() == QAbstractItemView.EditingState
    editor.setText(text)
    return editor


def test_the_click_that_finishes_typing_a_run_ticks_nothing(qt, clicking):
    """Type, then tick is the how-to's own order. The press takes the focus, so the run is kept and the table shown
    again before the press lands, and the release ticked whatever was under the mouse by then: Dana unticked on 101-110,
    so not billed for those pages. Only the next click ticks."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    w, told = clicking
    rect = w.table.visualItemRect(cell(w, 0, D))
    at = QPoint(rect.right() - 6, rect.center().y())
    typing(qt, w, "111-120")
    QTest.mouseClick(w.table.viewport(), Qt.LeftButton, Qt.NoModifier, at)
    pump(qt)
    both = sorted([D, A])
    assert [(r.start, r.end, sorted(r.keys)) for r in w.runs] == [(1, 10, both), (11, 20, both), (21, 30, both)]
    assert told == [1]
    QTest.mouseClick(w.table.viewport(), Qt.LeftButton, Qt.NoModifier, at)
    pump(qt)
    assert w.runs[0].keys == [A] and told == [1, 1]


def test_the_click_that_finishes_a_run_refused_leaves_the_message(qt, clicking):
    """A number no page has: refused. The tick landed anyway, and showing that cleared the ⚠ at once."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    w, told = clicking
    rect = w.table.visualItemRect(cell(w, 0, D))
    typing(qt, w, "999-1000")
    QTest.mouseClick(w.table.viewport(), Qt.LeftButton, Qt.NoModifier, QPoint(rect.right() - 6, rect.center().y()))
    pump(qt)
    assert w.problem.text().startswith("⚠") and "101–130" in w.problem.text()
    assert sorted(w.runs[0].keys) == sorted([D, A]) and len(w.runs) == 1 and told == []


def test_a_click_after_the_typing_was_kept_by_enter_ticks(qt, clicking):
    """Only a press that closes the editor is passed over: the typing kept by Enter, the next click is a click."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    w, told = clicking
    QTest.keyClick(typing(qt, w, "111-120"), Qt.Key_Return)
    pump(qt)
    assert told == [1]
    click_at(qt, w, 0, D)
    assert w.runs[0].keys == [A] and told == [1, 1]


def test_a_click_that_closes_an_unchanged_editor_ticks_nothing(qt, clicking):
    """The same text: nothing to keep, and the click was still on the way out of the cell."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    w, told = clicking
    rect = w.table.visualItemRect(cell(w, 0, D))
    typing(qt, w, w.table.item(0, 2).text())
    QTest.mouseClick(w.table.viewport(), Qt.LeftButton, Qt.NoModifier, QPoint(rect.right() - 6, rect.center().y()))
    pump(qt)
    assert sorted(w.runs[0].keys) == sorted([D, A])


def test_a_dragged_press_leaves_nothing_to_pass_over_for_the_next_click(qt, clicking):
    """A press that closed the editor, let go over another cell: no release reaches the delegate. The next click ticks."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    w, told = clicking
    rect, other = w.table.visualItemRect(cell(w, 0, D)), w.table.visualItemRect(cell(w, 0, K))
    typing(qt, w, "111-120")
    viewport = w.table.viewport()
    QTest.mousePress(viewport, Qt.LeftButton, Qt.NoModifier, QPoint(rect.right() - 6, rect.center().y()))
    QTest.mouseMove(viewport, other.center())
    QTest.mouseRelease(viewport, Qt.LeftButton, Qt.NoModifier, other.center())
    pump(qt)
    assert told == [1] and K not in w.runs[0].keys
    click_at(qt, w, 0, K)
    assert K in w.runs[0].keys and told == [1, 1]


def test_the_date_chooses_the_row_without_ticking(qt, clicking):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from minute_filler.gui.excerpts import DATE
    w, told = clicking
    rect = w.table.visualItemRect(w.table.item(0, DATE))
    QTest.mouseClick(w.table.viewport(), Qt.LeftButton, Qt.NoModifier, QPoint(rect.center().x(), rect.center().y()))
    pump(qt)
    assert w.table.currentRow() == 0 and w._chosen() is w.runs[0] and told == []


def test_a_drag_from_cell_to_cell_ticks_nothing(qt, clicking):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    w, told = clicking
    start = w.table.visualItemRect(cell(w, 0, D)).center()
    end = w.table.visualItemRect(cell(w, 0, K)).center()
    QTest.mousePress(w.table.viewport(), Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(w.table.viewport(), end)
    QTest.mouseRelease(w.table.viewport(), Qt.LeftButton, Qt.NoModifier, end)
    pump(qt)
    assert sorted(w.runs[0].keys) == sorted([D, A]) and told == []


def test_a_double_click_leaves_the_tick_as_it_was(qt, clicking):
    """As the system sends one: a click, the table shown again, a double click and its release. Two ticks and no
    change, rather than a firm dropped by a double click meant to choose the row."""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest
    w, told = clicking
    at = w.table.visualItemRect(cell(w, 0, D)).center()
    QTest.mouseClick(w.table.viewport(), Qt.LeftButton, Qt.NoModifier, at)
    viewport = w.table.viewport()
    point = QPointF(at)
    global_at = QPointF(viewport.mapToGlobal(at))
    qt.QApplication.sendEvent(viewport, QMouseEvent(QEvent.MouseButtonDblClick, point, global_at, Qt.LeftButton,
                                                    Qt.LeftButton, Qt.NoModifier))
    QTest.mouseRelease(viewport, Qt.LeftButton, Qt.NoModifier, at)
    pump(qt)
    assert sorted(w.runs[0].keys) == sorted([D, A]) and len(told) == 2


def test_space_ticks_and_stays_on_its_cell_so_a_second_one_unticks(qt, clicking):
    """The table shown again went to the row's first column, where a second Space did nothing."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    w, told = clicking
    column = section_of(w, K)
    w.table.setCurrentCell(0, column)
    pump(qt)
    QTest.keyClick(w.table, Qt.Key_Space)
    assert K in w.runs[0].keys and (w.table.currentRow(), w.table.currentColumn()) == (0, column)
    QTest.keyClick(w.table, Qt.Key_Space)
    assert K not in w.runs[0].keys and (w.table.currentRow(), w.table.currentColumn()) == (0, column)
    assert told == [1, 1]


def test_a_page_numbers_cell_still_opens_to_type_in(qt, clicking):
    """(The one delegate is table-wide: a double click on Page numbers still edits it.)"""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QAbstractItemView
    from minute_filler.gui.excerpts import PAGES
    w, told = clicking
    viewport = w.table.viewport()
    at = w.table.visualItemRect(w.table.item(0, PAGES)).center()
    QTest.mouseClick(viewport, Qt.LeftButton, Qt.NoModifier, at)
    qt.QApplication.sendEvent(viewport, QMouseEvent(QEvent.MouseButtonDblClick, QPointF(at),
                                                    QPointF(viewport.mapToGlobal(at)), Qt.LeftButton, Qt.LeftButton,
                                                    Qt.NoModifier))
    pump(qt)
    assert w.table.state() == QAbstractItemView.EditingState and told == []


# ------------------------------------------------------------------ the speed boxes
def aligned(w) -> bool:
    """Every firm's box is over its section, inside it, the 4 px at the edges left to resize it, and shown."""
    from minute_filler.gui.firm_columns import BAND, BOX_INSET, GAP
    from minute_filler.gui.zoom import z
    head = w.table.horizontalHeader()
    for a in w.firms:
        box = w.firm_speed_boxes[a.key()]
        logical = section_of(w, a.key())
        x, size = head.sectionViewportPosition(logical), head.sectionSize(logical)
        g = box.geometry()
        if box.isHidden() or box.parent() is not head.viewport():
            return False
        if (g.left(), g.width()) != (x + z(BOX_INSET), size - 2 * z(BOX_INSET)):
            return False
        # (under the band and the name: the heading asks for the height, FirmHeader.sizeHint)
        if g.bottom() >= head.viewport().height() or g.top() < z(BAND) + z(GAP) + head.fontMetrics().height():
            return False
    return True


def assert_labels_fit(box):
    """Each of a speed box's closed labels fits in it uncut, at its width now."""
    from PySide6.QtWidgets import QStyle, QStyleOptionComboBox
    opt = QStyleOptionComboBox()
    box.initStyleOption(opt)
    room = box.style().subControlRect(QStyle.CC_ComboBox, opt, QStyle.SC_ComboBoxEditField, box).width()
    for i in range(box.count()):
        box.setCurrentIndex(i)
        assert box.fontMetrics().horizontalAdvance(box.short_text()) <= room, box.short_text()


def test_the_boxes_follow_their_columns(qt, themed, tmp_path, s):
    from minute_filler.gui.excerpts import PAGES, PLACE
    w = open_window(qt, days_of(tmp_path, s), s)
    assert aligned(w)
    w.resize(620, 500)
    pump(qt)
    assert aligned(w)
    w.place.setChecked(True)
    pump(qt)
    assert not w.table.isColumnHidden(PLACE) and aligned(w)
    w.place.setChecked(False)
    pump(qt)
    assert aligned(w)
    w.table.setColumnWidth(PAGES, 260)
    pump(qt)
    assert aligned(w)
    bar = w.table.horizontalScrollBar()
    assert bar.maximum() > 0
    bar.setValue(bar.maximum())
    pump(qt)
    assert aligned(w)
    assert w.firm_speed_boxes[D].x() < w.table.horizontalHeader().sectionViewportPosition(0) + 500  # (it moved left)
    bar.setValue(0)
    pump(qt)
    assert aligned(w)
    w.close()


def test_a_count_hidden_under_columns_moves_no_box_off_its_firm(qt, themed, tmp_path, s):
    w = open_window(qt, days_of(tmp_path, s), s)
    w.count_actions["your_billed"].setChecked(False)
    pump(qt)
    assert aligned(w)
    w.count_actions["your_billed"].setChecked(True)
    pump(qt)
    assert aligned(w)
    w.close()


def test_the_heading_and_the_boxes_follow_the_zoom(qt, themed, tmp_path, s):
    from minute_filler.gui import zoom
    w = open_window(qt, days_of(tmp_path, s), s)
    head = w.table.horizontalHeader()
    high, wide = head.height(), w.table.columnWidth(section_of(w, D))
    for level, grows in ((1.3, True), (0.7, False)):
        zoom.set_zoom(level)
        themed(qt.QApplication.instance(), "light")
        pump(qt)
        w.load(w.group)
        pump(qt)
        assert aligned(w), level
        assert (head.height() > high) is grows and (w.table.columnWidth(section_of(w, D)) > wide) is grows, level
        box = w.firm_speed_boxes[D]
        assert box.height() == box.sizeHint().height() and box.y() + box.height() <= head.height()
        assert_labels_fit(box)
    w.close()


def test_the_main_windows_zoom_reaches_the_window(qt, tmp_path, make_window, s, themed):
    """Ctrl + in the main window: the table's columns fit again, not only the style sheet's sizes."""
    from test_show_the_math import settled
    win = settled(make_window(s))
    from minute_filler.gui.excerpts import ExcerptsWindow
    from minute_filler.gui.zoom import zoom
    jobs = days_of(tmp_path, s)
    win.jobs, win.cur = jobs, jobs[0]
    win.excerpts = w = ExcerptsWindow(s, lambda: None, win)
    w.load(jobs)
    w.show()
    pump(qt)
    wide, shown_for = w.table.columnWidth(section_of(w, D)), []
    win._follow_excerpts = lambda real=win._follow_excerpts: (shown_for.append(zoom()), real())
    win.set_zoom(1.3)
    pump(qt)
    assert 1.3 in shown_for
    assert w.isVisible() and w.table.columnWidth(section_of(w, D)) > wide and aligned(w)
    w.close()


def test_a_rebuild_leaves_the_boxes_their_open_list_focus_and_the_scrolling(qt, themed, tmp_path, s):
    """Anything the main window does shows the table again (a read ending, an AI answer): built afresh with the
    table, a box closed its list under the mouse and lost the focus."""
    jobs = days_of(tmp_path, s)
    w = open_window(qt, jobs, s)
    w.resize(560, 500)
    pump(qt)
    bar = w.table.horizontalScrollBar()
    bar.setValue(3)
    pump(qt)
    before = dict(w.firm_speed_boxes)
    box = before[A]
    removed = []
    box.model().rowsRemoved.connect(lambda *_: removed.append(1))
    w.activateWindow()
    box.setFocus()
    pump(qt)
    assert box.hasFocus()
    w.load(w.group)
    pump(qt)
    assert w.firm_speed_boxes == before and box.hasFocus() and bar.value() == 3 and aligned(w)
    box.showPopup()
    pump(qt)
    assert box.view().isVisible()
    w.load(w.group)
    pump(qt)
    assert box.view().isVisible() and not box.isHidden() and removed == [] and bar.value() == 3
    box.hidePopup()
    w.close()


def test_a_rebuild_with_a_row_chosen_leaves_the_scrolling(qt, themed, tmp_path, s):
    """Choosing the cell again scrolls to it: scrolled away to read the counts, the table jumped back on every change
    in the main window."""
    from minute_filler.gui.excerpts import DATE
    w = open_window(qt, days_of(tmp_path, s), s)
    split(w, w.days[0], *((i, i, [D, A]) for i in range(1, 31)))
    w.resize(560, 300)
    pump(qt)
    w.table.setCurrentCell(0, DATE)
    across, down = w.table.horizontalScrollBar(), w.table.verticalScrollBar()
    across.setValue(3)
    down.setValue(down.maximum())
    pump(qt)
    kept = across.value(), down.value()
    assert kept[0] == 3 and kept[1] > 0
    w.load(w.group)
    pump(qt)
    assert (across.value(), down.value()) == kept and (w.table.currentRow(), w.table.currentColumn()) == (0, DATE)
    w.close()


def test_a_firm_gone_while_a_list_is_open_doesnt_close_another_firms(qt, themed, tmp_path, s):
    """Dana unlisted while Kim's list is open, with the first count hidden: Kim's column moves, and that count's
    column is hidden at the number Kim's had. Her box isn't to go with it while the table is filled
    (FirmHeader.hold)."""
    s.excerpt_hidden_cols = ["your_billed"]
    jobs = days_of(tmp_path, s)
    w = open_window(qt, jobs, s)
    kim, dana = w.firm_speed_boxes[K], w.firm_speed_boxes[D]
    kim.showPopup()
    pump(qt)
    jobs[0].case.attorneys = [a for a in jobs[0].case.attorneys if a.key() != D]
    w.load(jobs)
    pump(qt)
    assert kim.view().isVisible() and not kim.isHidden() and dana.isHidden() and aligned(w)
    assert w.firm_speed_boxes[K] is kim and set(w.firm_speed_boxes) == {A, K}
    kim.hidePopup()
    w.close()


def test_a_firm_added_isnt_left_hidden_with_a_count_it_took_the_place_of(qt, themed, tmp_path, s):
    """A firm added takes the column number of the first count: hidden under Columns, it stayed hidden, firm and box."""
    s.excerpt_hidden_cols = ["your_billed"]
    jobs = days_of(tmp_path, s, firms=(DANA, ALEX))
    w = open_window(qt, jobs, s)
    jobs[0].case.attorneys.append(Attorney(**KIM, checked=False))
    w.load(jobs)
    pump(qt)
    assert not w.table.isColumnHidden(section_of(w, K)) and aligned(w)
    assert w.table.isColumnHidden(section_of(w, K) + 1)  # (the count itself, one along)
    w.close()


def test_a_right_click_on_a_box_is_the_headings_menu(qt, themed, tmp_path, s):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QContextMenuEvent
    w = open_window(qt, days_of(tmp_path, s), s)
    shown = []
    w.columns_menu.exec = lambda at: shown.append(at)
    box = w.firm_speed_boxes[D]
    at = QPoint(6, 6)
    qt.QApplication.sendEvent(box, QContextMenuEvent(QContextMenuEvent.Mouse, at, box.mapToGlobal(at)))
    pump(qt)
    assert shown == [box.mapToGlobal(at)]
    w.close()


def test_a_box_says_the_speed_short_closed_and_whole_in_its_list(qt, themed, tmp_path, s):
    """"The form's (Expedite)" took 166 px of a column that needs 110; the list keeps the whole, wider than the box
    if need be."""
    w = open_window(qt, days_of(tmp_path, s), s)
    box = w.firm_speed_boxes[D]
    assert box.currentText() == "The form's (Expedite)" and box.short_text() == "Expedite"
    assert box.width() >= box.fontMetrics().horizontalAdvance("Expedite") + 40
    box.showPopup()
    pump(qt)
    assert box.view().width() >= box.view().sizeHintForColumn(0)
    assert box.view().width() > box.width()
    box.hidePopup()
    w.close()


def test_a_closed_box_draws_the_short_label_and_an_arrow(qt, themed, tmp_path, s):
    """The form's speed and that speed chosen look the same closed: "Expedite". A style-sheet box has no arrow, and
    in a heading looked like a field to type in; a firm that ordered nothing has no list, so no arrow."""
    from minute_filler.gui.zoom import z
    w = open_window(qt, days_of(tmp_path, s), s)
    box = w.firm_speed_boxes[D]
    form = box.grab().toImage()
    assert box.currentText() == "The form's (Expedite)"
    box.setCurrentIndex(box.findData("Expedite"))
    assert form == box.grab().toImage()
    box.setCurrentIndex(box.findData("Regular"))
    assert form != box.grab().toImage()

    def dark_pixels(b):
        """Pixels of the text's colour where the arrow goes, at the box's right end."""
        picture = b.grab().toImage()
        return sum(picture.pixelColor(x, y).lightness() < 100 for x in range(b.width() - z(22), b.width() - z(2))
                   for y in range(z(6), b.height() - z(6)))
    assert dark_pixels(box) > 0 and dark_pixels(w.firm_speed_boxes[K]) == 0
    w.close()


def test_choosing_in_a_box_sets_the_firms_speed(qt, themed, tmp_path, s):
    told = []
    jobs = days_of(tmp_path, s)
    w = open_window(qt, jobs, s, told)
    box = w.firm_speed_boxes[D]
    box.setCurrentIndex(box.findData("Daily"))
    box.activated.emit(box.currentIndex())
    pump(qt)
    assert jobs[0].speeds[D] == "Daily" and told == [1]
    assert w.firm_speed_boxes[D] is box and box.short_text() == "Daily"
    w.close()


@pytest.mark.parametrize("focused", [True, False])
def test_a_wheel_going_by_never_changes_a_firms_speed(qt, themed, tmp_path, s, focused):
    """The boxes keep the focus across a rebuild now. Choose Daily, one notch of the wheel over the box: Dana went to
    Immediate, repriced with no message (the accident believed to have turned off the user's math). The table takes
    the wheel."""
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    told = []
    jobs = days_of(tmp_path, s)
    w = open_window(qt, jobs, s, told)
    box = w.firm_speed_boxes[D]
    box.setCurrentIndex(box.findData("Daily"))
    box.activated.emit(box.currentIndex())
    pump(qt)
    w.activateWindow()
    if focused:
        box.setFocus()
        pump(qt)
        assert box.hasFocus()
    centre = box.rect().center()
    for notch in (-120, 120):
        wheel = QWheelEvent(QPointF(centre), QPointF(box.mapToGlobal(centre)), QPoint(0, 0), QPoint(0, notch),
                            Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
        qt.QApplication.sendEvent(box, wheel)
        pump(qt)
        assert not wheel.isAccepted()
    assert jobs[0].speeds[D] == "Daily" and box.currentData() == "Daily" and told == [1]
    w.close()


def test_a_firm_that_ordered_nothing_has_no_speed_to_set(qt, themed, tmp_path, s):
    """Kim ordered nothing: there is no day to set a speed on. Tick a run first, it says, and then the box works."""
    from PySide6.QtCore import Qt
    jobs = days_of(tmp_path, s)
    w = open_window(qt, jobs, s)
    box = w.firm_speed_boxes[K]
    assert not box.isEnabled() and "tick a run first" in box.toolTip() and box.short_text() == "–"
    assert box.isVisible() and aligned(w)
    cell(w, 0, K).setCheckState(Qt.Checked)
    pump(qt)
    assert w.firm_speed_boxes[K] is box and box.isEnabled() and box.findData("Daily") >= 0
    w.close()


# ------------------------------------------------------------------ the fit
def firm_widths(w):
    return [w.table.columnWidth(section_of(w, a.key())) for a in w.firms]


def test_three_firms_fit_the_window_at_its_size(qt, themed, tmp_path, s):
    """Prices under $1,000, the four counts shown and the Weekday: no sideways scrolling (the picture before needed
    it)."""
    if not os.environ.get("QT_QPA_FONTDIR"):
        pytest.skip("needs the real fonts to measure the text (see conftest.qt)")
    w = open_window(qt, days_of(tmp_path, s), s)
    head = w.table.horizontalHeader()
    assert (w.width(), head.length() <= w.table.viewport().width()) == (1000, True), head.length()
    assert not w.table.horizontalScrollBar().maximum()
    w.close()


def test_the_firms_columns_are_one_width_and_a_tick_doesnt_move_them(qt, themed, tmp_path, s):
    """What a click lands on stays under the mouse: untick the firm with the widest text and nothing shifts."""
    from PySide6.QtCore import Qt
    w = open_window(qt, days_of(tmp_path, s, pages=(120,)), s)
    widths = firm_widths(w)
    assert len(set(widths)) == 1
    cell(w, 0, D).setCheckState(Qt.Unchecked)  # (Alex alone: a shorter text)
    assert "(÷2)" not in cell(w, 0, A).text() and firm_widths(w) == widths
    cell(w, 0, K).setCheckState(Qt.Checked)
    assert firm_widths(w) == widths or firm_widths(w)[0] > widths[0]
    w.close()


def test_the_columns_fit_what_they_hold_and_a_long_name_is_cut(qt, themed, tmp_path, s):
    """The widest text and the box come out whole; a name past FIRM_NAME_MAX doesn't widen every firm's column."""
    from minute_filler.gui.excerpts import FIRM_NAME_MAX
    from minute_filler.gui.zoom import z
    long_firm = dict(name="", firm="Law Offices of the Very Long Firm Name Partners and Associates", party="Plaintiff")
    w = open_window(qt, days_of(tmp_path, s, firms=(long_firm, ALEX), ticked=(Attorney(**long_firm).key(), A)), s)
    assert firm_widths(w)[0] <= max(z(FIRM_NAME_MAX), w.table.sizeHintForColumn(section_of(w, A)) + z(10))
    for a in w.firms:
        column = section_of(w, a.key())
        assert w.table.columnWidth(column) >= w.table.sizeHintForColumn(column)
        assert_labels_fit(w.firm_speed_boxes[a.key()])
    w.close()


def test_a_nobody_run_doesnt_widen_its_count_column(qt, themed, tmp_path, s):
    """"0 (nobody ordered it)" moved the column 53 px as a run's last firm was unticked."""
    from minute_filler.gui.excerpts import FIRST_FIRM
    w = open_window(qt, days_of(tmp_path, s), s)
    split(w, w.days[0], (1, 10, []), (11, 30, [D, A]))
    assert w.table.item(0, FIRST_FIRM + len(w.firms)).text() == "0 (nobody)"
    w.close()


# ------------------------------------------------------------------ what a cell says
def test_a_price_alone_at_the_headings_speed(qt, themed, tmp_path, s):
    """Alex shares pages 1-10 and has 11-30 alone: its invoice bills one speed for both, so the run alone shows what it
    pays, with no column for each speed (a blank cell and two Each pays columns disagreed with the invoice)."""
    w = open_window(qt, days_of(tmp_path, s), s)
    split(w, w.days[0], (1, 10, [D, A]), (11, 30, [A]))
    assert cell(w, 1, A).text() == "$152.00" and cell(w, 1, D).text() == ""
    assert not w.speeds_label.isVisible() and w.table.columnCount() == 4 + 3 + 4  # (no Each pays columns)
    assert "alone" in cell(w, 1, A).toolTip() and "$152.00" in cell(w, 1, A).toolTip()
    w.close()


def test_a_price_shared_at_one_speed(qt, themed, tmp_path, s):
    w = open_window(qt, days_of(tmp_path, s), s)
    assert cell(w, 0, D).text() == "$147.00 (÷2)" and cell(w, 0, A).text() == "$147.00 (÷2)"
    tip = cell(w, 0, D).toolTip()
    assert "Dana Smith pays $147.00" in tip
    assert "the 2 firms that ordered them split the original and the judge's index" in tip
    assert "each pays for its own copy and e-mailed copy" in tip
    w.close()


def test_a_price_shared_at_different_speeds_says_shared_not_a_divisor(qt, themed, tmp_path, s):
    """÷2 would be false: the fastest firm pays what is left of the one original, not half of anything shown."""
    jobs = days_of(tmp_path, s)
    w = open_window(qt, jobs, s)
    jobs[0].speeds = {D: "Daily", A: "Immediate"}
    w.load(jobs)
    assert cell(w, 0, D).text().endswith(" · shared") and "÷" not in cell(w, 0, D).text()
    assert cell(w, 0, D).text() != cell(w, 0, A).text() and cell(w, 0, D).text().startswith("$")
    tip = cell(w, 0, D).toolTip()
    assert "Ordered together at different speeds" in tip and "Split invoices" in tip and "Dana Smith pays $" in tip
    w.close()


def test_a_speed_other_than_the_headings_is_said_in_the_cell(qt, themed, tmp_path, s):
    jobs = days_of(tmp_path, s)
    w = open_window(qt, jobs, s)
    jobs[0].speeds = {D: "Expedite", A: "Expedite"}
    split(w, w.days[0], (1, 10, [D, A]), (11, 30, [D, A]))
    w.table.selectRow(1)
    w._set_run_speed(D, "Daily")
    w._set_run_speed(A, "Daily")
    assert w.firm_speed_boxes[D].short_text() == "(varies)"
    assert cell(w, 0, D).text() == "Expedite · $49.00 (÷2)"
    assert cell(w, 1, D).text().startswith("Daily · $") and cell(w, 1, D).text().endswith(" (÷2)")
    w.close()


def test_a_speed_to_commit_to_is_amber_with_a_question_mark(qt, themed, tmp_path, s):
    from minute_filler.gui.excerpts import AMBER
    s.split_speeds = "ask"
    w = open_window(qt, days_of(tmp_path, s), s)
    it = cell(w, 0, D)
    assert it.text() == "Expedite? · $147.00 (÷2)"
    assert it.foreground().color().name() == AMBER and "Generate asks" in it.toolTip()
    assert w.firm_speed_boxes[D].short_text() == "Not set"  # (not "Chooses": it must commit)
    w.close()


def test_a_firm_choosing_from_its_invoice_has_a_blank_cell_and_its_prices_in_each_pays(qt, themed, tmp_path, s):
    jobs = days_of(tmp_path, s, ticked=(D,))
    w = open_window(qt, jobs, s)
    assert w.runs[0].keys == [D] and cell(w, 0, D).text() == "" and cell(w, 0, D).checkState()
    assert w.firm_speed_boxes[D].short_text() == "Chooses"
    assert w.firm_speed_boxes[D].currentText() == "Chooses on the invoice"
    heads = [w.table.horizontalHeaderItem(c).text() for c in range(w.table.columnCount())]
    assert heads[-2:] == ["Each pays · Regular", "Each pays · Expedite"]
    assert w.table.item(0, len(heads) - 1).text() == "$228.00"
    assert w.speeds_label.text() == "Show prices for:" and w.speeds_label.isVisible()
    assert_labels_fit(w.firm_speed_boxes[D])  # (a blank cell: the box and the name are what set the width)
    w.close()


def test_the_divisor_is_the_one_the_price_is_divided_by(qt, themed, tmp_path, s):
    """Parties 3 with 2 firms ticked: the price is divided three ways, and the cell said ÷2 (its firms)."""
    jobs = days_of(tmp_path, s)
    jobs[0].parties = 3
    w = open_window(qt, jobs, s)
    # (the original three ways, each its own copies: $5.40 / 3 + $2.20 = $4.00 a page)
    assert cell(w, 0, D).text() == "$120.00 (÷3)"
    assert "the 3 parties ordering them" in cell(w, 0, D).toolTip()
    w.close()


@pytest.mark.usefixtures("split_orders_choose")
def test_each_pays_says_the_same_divisor(qt, themed, tmp_path, s):
    jobs = days_of(tmp_path, s)
    jobs[0].parties = 3
    w = open_window(qt, jobs, s)
    assert cell(w, 0, D).text() == ""  # (they choose from their invoices here)
    text = w.table.item(0, w.table.columnCount() - 1).text()
    assert text == "$120.00 (÷3)", text
    w.close()


def test_a_tooltip_doesnt_say_whose_speed_it_isnt(qt, themed, tmp_path, s):
    """A shared run's firm with no speed set: billed at the form's, said, and where to change it (no more "above the
    table", where the row of boxes was)."""
    w = open_window(qt, days_of(tmp_path, s), s)
    tip = cell(w, 0, D).toolTip()
    assert "Billed at Expedite, the agreement form's speed" in tip and "under the firm's name" in tip
    assert "above the table" not in tip
    w.close()


# ------------------------------------------------------------------ the money adds up
@pytest.mark.parametrize("rounding", ["exact", "page"])
def test_a_committed_firms_cells_add_up_to_its_invoice(qt, themed, tmp_path, s, rounding):
    """Its run alone was priced by its own at every speed; its invoice bills one speed for all of it. Alex's cells,
    read back and added up, are what its invoice comes to, within rounding up to the cent; and that is the
    invoice's amount when Generate makes it."""
    from minute_filler.batch import fill_jobs
    from minute_filler.deliver import ledger_for
    s.invoice_rounding = rounding
    jobs = days_of(tmp_path, s, pages=(33,))
    w = open_window(qt, jobs, s)
    split(w, w.days[0], (1, 11, [D, A]), (12, 33, [A]))
    p = prices(w.days, w.runs, s)
    due = {key: amounts for key, amounts in p.firms}
    assert set(due[A]) == {"Expedite"}  # (one speed: no choice on its invoice)
    total = sum((Decimal(cell(w, r, A).text().split(" ")[0].lstrip("$").replace(",", "")) for r in (0, 1)), Decimal(0))
    assert abs(total - due[A]["Expedite"]) < Decimal("0.01"), (total, due[A])
    fill_jobs(jobs, s, outputs=["invoice"])
    billed = {i.bill_to: Decimal(i.amounts["Expedite"]) for i in ledger_for(s).invoices()}
    assert billed == {"Alex B. Counsel": due[A]["Expedite"], "Dana Smith": due[D]["Expedite"]}
    w.close()


def test_a_lone_firm_with_a_speed_on_another_day_is_at_that_speed_as_its_invoice(tmp_path, s):
    """prices(): a firm with a speed set on one run is billed that speed on its other runs too, as Generate sets them
    (batch.settle_split_speeds). A firm with no speed and no shared pages still chooses."""
    jobs = days_of(tmp_path, s, pages=(10, 20), ticked=(A, K))
    d1, d2 = days = case_days(jobs)
    firms = firms_of(jobs)
    store(d1, [Run(d1, 1, 10, [A], {A: "Daily"})], firms)
    store(d2, [Run(d2, 1, 20, [A]), ], firms)
    runs = [r for d in days for r in runs_of(d, firms)]
    p = prices(days, runs, s)
    assert id(runs[1]) in p.ordered and id(runs[1]) not in p.runs
    assert p.ordered[id(runs[1])][A][0] == "Daily"  # (Generate gives it its speed on its other pages, not the form's)
    store(d2, [Run(d2, 1, 20, [K])], firms)
    runs = [r for d in days for r in runs_of(d, firms)]
    p = prices(days, runs, s)
    assert id(runs[1]) in p.runs and id(runs[1]) not in p.ordered  # (Kim alone, and nothing set: she chooses)


# ------------------------------------------------------------------ a firm's invoice line
def invoice_line(w, name):
    """The firm's line under "Each firm's invoice", without its square."""
    import html
    import re
    below = w.summary.text().split("Each firm's invoice", 1)[1]
    found = [re.sub(r"<[^>]+>", "", x) for x in below.split("<br>") if name in html.unescape(x)]
    assert len(found) == 1, w.summary.text()
    return html.unescape(found[0]).replace("■", "").strip()


@pytest.fixture
def two_reporters(tmp_path, s):
    """A transcript of 30 total pages: the user's first 10, another reporter's 20. Alex alone on the user's, Alex and
    Dana on the other reporter's, so that run has no billed pages."""
    s.profile.initials = "PR"
    jobs = days_of(tmp_path, s, initials=["PR"] * 10 + ["DS"] * 20)
    assert sum(jobs[0].day_mask()) == 10
    return jobs


def test_a_firm_sharing_only_pages_not_billed_is_billed_as_generate_has_it(qt, themed, s, two_reporters):
    """It read "Alex B. Counsel: " with no amount: whether Alex commits to a speed counted the shared run, which his
    invoice doesn't bill (none of its pages are the user's), so he is billed as Generate has it, at Expedite."""
    w = open_window(qt, two_reporters, s)
    split(w, w.days[0], (1, 10, [A]), (11, 30, [A, D]))
    assert invoice_line(w, "Alex B. Counsel") == "Alex B. Counsel: Expedite $76.00"
    w.close()


def test_a_firm_with_nothing_chosen_lists_all_its_amounts_rather_than_none(qt, themed, s, two_reporters):
    """Where Generate asks: the invoice as it stands offers both speeds, and no Show prices for boxes are shown."""
    s.split_speeds = "ask"
    w = open_window(qt, two_reporters, s)
    split(w, w.days[0], (1, 10, [A]), (11, 30, [A, D]))
    assert not w.speeds_label.isVisible()
    assert invoice_line(w, "Alex B. Counsel") == "Alex B. Counsel: Regular $63.00 · Expedite $76.00"
    w.close()


def test_a_held_invoices_line_isnt_blank_and_the_hold_is_said(qt, themed, tmp_path, s):
    """A row naming a firm no longer ticked: "Dana Smith: ", and nothing to say why."""
    jobs = days_of(tmp_path, s)
    w = open_window(qt, jobs, s)
    split(w, w.days[0], (1, 10, [D]), (11, 30, [D, A]))
    next(a for a in jobs[0].case.attorneys if a.key() == A).checked = False
    w.load(jobs)
    assert "$" in invoice_line(w, "Dana Smith")
    assert w.problem.text() == ("⚠ No invoice yet for 6/3/2026: Who ordered which pages… needs checking (it names an "
                                "attorney no longer ticked)")
    w.close()


# ------------------------------------------------------------------ a held invoice
def test_a_held_invoice_says_so_and_stops_saying_so_once_fixed(qt, themed, tmp_path, s):
    """Parties 3 with two firms at different speeds: prices showed, the line was empty, and Generate held it."""
    jobs = days_of(tmp_path, s)
    w = open_window(qt, jobs, s)
    assert w.problem.text() == ""
    jobs[0].parties, jobs[0].speeds = 3, {D: "Daily", A: "Immediate"}
    w.load(jobs)
    assert w.problem.text() == f"⚠ No invoice yet for 6/3/2026: {jobs[0].invoice_hold()}"
    assert "Parties says 3" in w.problem.text()
    jobs[0].parties = 0
    w.load(jobs)
    assert w.problem.text() == ""
    w.close()


def test_a_day_of_several_names_the_day_held(qt, themed, tmp_path, s):
    jobs = days_of(tmp_path, s, pages=(10, 20))
    jobs[1].parties, jobs[1].speeds = 3, {D: "Daily", A: "Immediate"}
    w = open_window(qt, jobs, s)
    assert w.problem.text().startswith("⚠ No invoice yet for 6/4/2026: Parties says 3")
    w.close()


def test_a_day_invoiced_already_isnt_said_to_be_held(qt, themed, tmp_path, s):
    jobs = days_of(tmp_path, s)
    jobs[0].parties, jobs[0].speeds, jobs[0].invoiced = 3, {D: "Daily", A: "Immediate"}, True
    w = open_window(qt, jobs, s)
    assert w.problem.text() == ""
    w.close()


def test_a_day_nobody_is_ticked_on_is_said_to_hold_the_invoice(qt, themed, tmp_path, s):
    """batch.group_problem: Generate makes no invoice for the case until that day says who ordered it."""
    jobs = days_of(tmp_path, s, pages=(10, 20))
    for a in jobs[1].case.attorneys:
        a.checked = False
    w = open_window(qt, jobs, s)
    assert w.problem.text().startswith("⚠ No invoice yet") and "nobody is ticked on" in w.problem.text()
    w.close()


def test_a_refused_run_stays_said_on_a_held_invoice(qt, themed, tmp_path, s):
    """Showing the table again put the hold over the reason just given."""
    from minute_filler.gui.excerpts import PAGES
    jobs = days_of(tmp_path, s)
    jobs[0].parties, jobs[0].speeds = 3, {D: "Daily", A: "Immediate"}
    w = open_window(qt, jobs, s)
    w.table.item(0, PAGES).setText("999-1000")
    assert "101–130" in w.problem.text()
    w.close()


def test_a_refused_run_isnt_said_once_a_speed_is_chosen(qt, themed, tmp_path, s):
    """It stayed under the table, after the firm's speed was set from its heading, until the next tick."""
    from minute_filler.gui.excerpts import PAGES
    jobs = days_of(tmp_path, s)
    w = open_window(qt, jobs, s)
    w.table.item(0, PAGES).setText("999-1000")
    assert w.problem.text().startswith("⚠") and "101–130" in w.problem.text()
    box = w.firm_speed_boxes[D]
    box.setCurrentIndex(box.findData("Daily"))
    box.activated.emit(box.currentIndex())
    pump(qt)
    assert w.problem.text() == ""
    w.close()


def test_a_hold_is_still_said_after_a_speed_is_chosen(qt, themed, tmp_path, s):
    """What the speed chosen brings stays: a refused run's message goes, a third speed's comes."""
    from minute_filler.gui.excerpts import PAGES
    jobs = days_of(tmp_path, s, ticked=(D, A, K))
    jobs[0].speeds = {D: "Daily", A: "Immediate", K: "Daily"}
    w = open_window(qt, jobs, s)
    w.table.item(0, PAGES).setText("999-1000")
    box = w.firm_speed_boxes[K]
    box.setCurrentIndex(box.findData("Regular"))
    box.activated.emit(box.currentIndex())
    pump(qt)
    assert "3 different speeds" in w.problem.text() and "101–130" not in w.problem.text()
    w.close()


# ------------------------------------------------------------------ what the lines under the table say
def without_tags(text):
    import html
    import re
    return html.unescape(re.sub(r"<[^>]+>", "", text.replace("<br>", "\n"))).replace("■\xa0", "")


def test_no_cost_said_without_an_amount(qt, themed, tmp_path, s):
    """Every "Show prices for" box unticked, one firm choosing, others at their speeds: "Alex B. Counsel only: 10 of your
    pages billed (10 total pages) - costs ", with nothing after it. The pages are still said."""
    jobs = days_of(tmp_path, s, ticked=(D, A, K))
    w = open_window(qt, jobs, s)
    d = w.days[0]
    store(d, [Run(d, 1, 10, [A], {}), Run(d, 11, 30, [D, K], {})], w.firms, s)
    w.load(jobs)
    assert "Alex B. Counsel only: 10 of your pages billed (10 total pages) - costs Regular" in without_tags(w.summary.text())
    for box in w.speed_boxes.values():
        box.setChecked(False)
    pump(qt)
    text = without_tags(w.summary.text())
    assert "Alex B. Counsel only: 10 of your pages billed (10 total pages)\n" in text
    assert "costs \n" not in text and "costs" not in text.split("\n")[1]
    w.close()


def test_firms_together_without_an_amount_say_their_pages_alone(qt, themed, tmp_path, s):
    """The same, for firms choosing together where they needn't commit: no "each of the 2 pays " with nothing after it."""
    from minute_filler import courthouses
    from dataclasses import replace
    was = courthouses.current()
    courthouses.use(replace(was, speed_upfront=False))
    try:
        jobs = days_of(tmp_path, s)
        w = open_window(qt, jobs, s)
        d = w.days[0]
        store(d, [Run(d, 1, 10, [K], {K: "Daily"}), Run(d, 11, 30, [D, A], {})], w.firms, s)
        w.load(jobs)
        for box in w.speed_boxes.values():
            box.setChecked(False)
        pump(qt)
        text = without_tags(w.summary.text())
        assert "Dana Smith + Alex B. Counsel: 20 of your pages billed (20 total pages)\n" in text, text
        assert "pays \n" not in text
        w.close()
    finally:
        courthouses.use(was)


@pytest.mark.parametrize("typed, line", [
    ("40", "40 of your pages billed (1 total page)"),
    ("", "1 of your pages billed (1 total page)")])
def test_one_total_page_is_one_page(qt, themed, tmp_path, s, typed, line):
    """A caption page and 40 typed read "(1 total pages)"; so did any run of one page."""
    from minute_filler.models import SRC_USER, FieldState
    jobs = days_of(tmp_path, s, pages=(1,))
    if typed:
        jobs[0].case.fields["est_pages"] = FieldState(typed, SRC_USER, 0.95, [typed])
    w = open_window(qt, jobs, s)
    assert line in without_tags(w.summary.text())
    w.close()


def test_a_run_of_one_page_nobody_ordered_says_one_page(qt, themed, tmp_path, s):
    jobs = days_of(tmp_path, s, pages=(10,))
    w = open_window(qt, jobs, s)
    split(w, w.days[0], (1, 9, [D, A]), (10, 10, []))
    text = without_tags(w.summary.text())
    assert "Nobody: 1 total page, it is yours (not billed)" in text, text
    assert "total pages" in text.replace("Nobody: 1 total page", "")  # (the others' line: 9 of them)
    w.close()


def test_a_number_typed_of_one_page_says_one_page(qt, themed, tmp_path, s):
    jobs = typed_day(tmp_path, s, "20")
    w = open_window(qt, jobs, s)
    split(w, w.days[0], (1, 1, [D, A]), (2, 2, []), (3, 20, [A]))
    text = without_tags(w.summary.text())
    assert "1 of your pages billed (1 page typed)" in text and "Nobody: 1 page typed (not billed)" in text, text
    assert "18 pages typed" in text
    w.close()


# ------------------------------------------------------------------ pages typed (a number in the Pages field)
def typed_day(tmp_path, s, typed="20"):
    """One day of a transcript of 30 total pages, with `typed` typed in its Pages field (Est. number of pages)."""
    from minute_filler.models import SRC_USER, FieldState
    jobs = days_of(tmp_path, s)
    jobs[0].case.fields["est_pages"] = FieldState(typed, SRC_USER, 0.95, [typed])
    assert jobs[0].pages_typed() and jobs[0].invoice_pages() == int(typed)
    return jobs


def counts_of(w, r):
    """Row r's counts as the table says them, in the order of COUNTS."""
    from minute_filler.gui.excerpts import COUNTS, FIRST_FIRM
    first = FIRST_FIRM + len(w.firms)
    return [w.table.item(r, first + k).text() for k in range(len(COUNTS))]


def test_a_number_typed_isnt_called_total_pages(qt, themed, tmp_path, s):
    """A transcript of 30 total pages, 20 typed. Total pages transcribed said 20, and "(20 total pages)": a typed number
    is the user's own count. The whole day's total is known, so each heading stays true with the transcript's."""
    from minute_filler.gui.excerpts import PLACE
    w = open_window(qt, typed_day(tmp_path, s), s)
    assert counts_of(w, 0) == ["20", "?", "30", "30"]
    assert "20 of your pages billed (30 total pages)" in w.summary.text()
    assert w.table.item(0, PLACE).text() == "1–20 of 20 pages typed"
    w.close()


def test_a_run_cut_from_a_number_typed_says_pages_typed(qt, themed, tmp_path, s):
    """Its places are in the number typed: how many of the transcript's pages it holds can't be told."""
    jobs = typed_day(tmp_path, s)
    w = open_window(qt, jobs, s)
    split(w, w.days[0], (1, 5, [D, A]), (6, 15, []), (16, 20, [A]))
    assert counts_of(w, 0) == ["5", "?", "5 typed", "5 typed"]
    assert counts_of(w, 1) == ["0 (nobody)", "?", "10 typed", "0"]
    from minute_filler.excerpts import count_runs
    assert count_runs(w.runs)[id(w.runs[0])].typed
    text = w.summary.text()
    assert "5 of your pages billed (5 pages typed)" in text, text
    assert "Nobody: 10 pages typed (not billed)" in text and "total pages" not in text.replace("\n", " ")
    from minute_filler.gui.excerpts import FIRST_FIRM
    assert "typed" in w.table.item(0, FIRST_FIRM + len(w.firms) + 2).toolTip()
    w.close()


def test_a_number_typed_without_a_transcript_says_pages_typed(qt, themed, tmp_path, s):
    jobs = typed_day(tmp_path, s, "40")
    jobs[0].transcript_pages = lambda: 0
    w = open_window(qt, jobs, s)
    assert counts_of(w, 0) == ["40", "?", "40 typed", "40 typed"]
    assert "40 of your pages billed (40 pages typed)" in w.summary.text()
    w.close()


def test_days_typed_and_counted_say_each(qt, themed, tmp_path, s):
    """A line of two days, one counted and a run of one typed: both, not one added into the other."""
    from minute_filler.models import SRC_USER, FieldState
    jobs = days_of(tmp_path, s, pages=(10, 30))
    jobs[1].case.fields["est_pages"] = FieldState("20", SRC_USER, 0.95, ["20"])
    w = open_window(qt, jobs, s)
    split(w, w.days[1], (1, 5, [D, A]), (6, 20, []))
    assert "15 of your pages billed (10 total pages, 5 pages typed)" in w.summary.text(), w.summary.text()
    w.close()


def test_a_job_of_several_days_typed_says_the_transcripts_total(qt, themed, tmp_path, s):
    from minute_filler.excerpts import count_runs
    from minute_filler.models import SRC_USER, FieldState
    s.batch_combine_dates = True
    docs, errors = read_docs([str(transcript_pdf(tmp_path / "D1.pdf", 30)),
                              str(transcript_pdf(tmp_path / "D2.pdf", 20, date="June 4, 2026"))], s)
    assert not errors
    job, = group(docs, s)
    job.case.attorneys = [Attorney(**DANA, checked=True)]
    job.case.fields["est_pages"] = FieldState("40", SRC_USER, 0.95, ["40"])
    run = runs_of(case_days([job])[0])[0]
    c = count_runs([run])[id(run)]
    assert (c.your_billed, c.total_transcribed, c.total_billed, c.typed) == (40, 50, 50, False)


# ------------------------------------------------------------------ the row and the column chosen
def test_the_row_chosen_after_typing_a_run_is_the_run_typed(qt, clicking):
    """Type 111-120 on row 0: row 0 is then 101-110, and Remove run or Delete acted on that, not on the run typed."""
    from minute_filler.gui.excerpts import PAGES
    w, _ = clicking
    w.table.setCurrentCell(0, PAGES)
    w.table.item(0, PAGES).setText("111-120")
    pump(qt)
    run = w._chosen()
    assert (run.start, run.end) == (11, 20) and w.table.currentRow() == 1
    assert w.table.currentColumn() == PAGES  # (ready for the next run to type)
    w._remove()
    assert [(r.start, r.end) for r in w.runs] == [(1, 20), (21, 30)] or [(r.start, r.end) for r in w.runs] == [(1, 30)]


def test_the_row_chosen_after_a_run_typed_with_enter(qt, clicking):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    w, _ = clicking
    QTest.keyClick(typing(qt, w, "121-125"), Qt.Key_Return)
    pump(qt)
    assert (w._chosen().start, w._chosen().end) == (21, 25)


def test_a_firm_added_before_the_cell_chosen_leaves_the_same_firm_chosen(qt, clicking):
    """The column was kept by its number: with a firm added before it, Space ticked the firm beside."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    w, _ = clicking
    column = section_of(w, K)
    w.table.setCurrentCell(0, column)
    job = w.group[0]
    job.case.attorneys.insert(0, Attorney(name="Pat Lee", firm="Lee LLP", party="Plaintiff", checked=False))
    w.load(w.group)
    pump(qt)
    assert w.table.currentColumn() == section_of(w, K) == column + 1
    QTest.keyClick(w.table, Qt.Key_Space)
    assert K in w.runs[0].keys and len(w.runs[0].keys) == 3 and w.table.currentColumn() == column + 1
    w.table.setCurrentCell(0, 0)


def test_a_count_chosen_stays_that_count_when_a_firm_comes_or_goes(qt, clicking):
    from minute_filler.gui.excerpts import COUNTS, FIRST_FIRM
    w, _ = clicking
    w.table.setCurrentCell(0, FIRST_FIRM + len(w.firms) + 2)
    w.group[0].case.attorneys = [a for a in w.group[0].case.attorneys if a.key() != K]
    w.load(w.group)
    pump(qt)
    assert w.table.currentColumn() == FIRST_FIRM + len(w.firms) + 2 and len(COUNTS) == 4


def test_the_chosen_firm_gone_goes_to_the_date(qt, clicking):
    from minute_filler.gui.excerpts import DATE
    w, _ = clicking
    w.table.setCurrentCell(0, section_of(w, K))
    w.group[0].case.attorneys = [a for a in w.group[0].case.attorneys if a.key() != K]
    w.load(w.group)
    pump(qt)
    assert w.table.currentColumn() == DATE and w.table.currentRow() == 0


# ------------------------------------------------------------------ the words
def labels(qt, w):
    return " ".join(x.text() for x in w.findChildren(qt.QLabel))


def test_split_invoices_is_named_only_while_a_run_is_at_different_speeds(qt, themed, tmp_path, s):
    jobs = days_of(tmp_path, s)
    w = open_window(qt, jobs, s)
    assert "Each price is what that firm pays." in w.note.text()
    assert "Split invoices" not in labels(qt, w)
    jobs[0].speeds = {D: "Daily", A: "Immediate"}
    w.load(jobs)
    assert "Split invoices" in w.note.text()
    jobs[0].speeds = {}
    w.load(jobs)
    assert "Split invoices" not in labels(qt, w)
    w.close()


def test_the_names_under_the_table_have_their_squares_and_are_escaped(qt, themed, tmp_path, s):
    firm_only = dict(name="", firm="Counsel & Counsel", party="Defendant")
    key = Attorney(**firm_only).key()
    w = open_window(qt, days_of(tmp_path, s, firms=(DANA, firm_only), ticked=(D, key)), s)
    text = w.summary.text()
    from minute_filler.gui.badges import badge_html
    assert f"{badge_html(w._marks[key], 'Counsel & Counsel')}" in text and "Counsel &amp; Counsel" in text
    assert "Counsel & Counsel" not in text
    assert "&amp;amp;" not in text
    w.close()


def test_the_names_of_the_buttons_and_the_page_numbers_heading(qt, themed, tmp_path, s):
    from minute_filler.gui.excerpts import PAGES
    w = open_window(qt, days_of(tmp_path, s), s)
    texts = {b.text() for b in w.findChildren(qt.QPushButton)}
    assert {"Split run…", "Remove run", "Make this day whole", "Make every day whole"} <= texts
    assert w.table.horizontalHeaderItem(PAGES).text() == "Page numbers\n(type here)"
    menu, _ = w._run_menu(w.runs[0])
    assert [a.text() for a in menu.actions()][:4] == ["Split run…", "Remove run", "Make this day whole",
                                                      "Make every day whole"]
    assert not hasattr(w, "firm_speeds_label") and not hasattr(w, "firm_speed_row")
    w.close()


def test_type_here_only_where_a_shown_day_can_be_typed_in(qt, themed, tmp_path, s):
    """A job of several days is ordered whole: its cell can't be typed in."""
    from minute_filler.gui.excerpts import PAGES
    s.batch_combine_dates = True
    docs, errors = read_docs([str(transcript_pdf(tmp_path / "D1.pdf", 30)),
                              str(transcript_pdf(tmp_path / "D2.pdf", 20, date="June 4, 2026"))], s)
    assert not errors
    job, = group(docs, s)
    job.case.attorneys = [Attorney(**DANA, checked=True)]
    w = open_window(qt, [job], s)
    assert not w.days[0].splittable and w.table.horizontalHeaderItem(PAGES).text() == "Page numbers"
    w.close()


# ------------------------------------------------------------------ Split run…
def answering(monkeypatch, *answers, meanwhile=None):
    """QInputDialog.getText answers these (text, ok) in turn, after `meanwhile`; returns what it asked."""
    from PySide6.QtWidgets import QInputDialog
    asked, left = [], list(answers)

    def get(parent, title, label, mode, text, *_a, **_k):
        asked.append((title, label, text))
        if meanwhile:
            meanwhile()
        return left.pop(0)
    monkeypatch.setattr(QInputDialog, "getText", get)
    return asked


def test_split_run_asks_where_starting_from_the_middle(qt, themed, tmp_path, s, monkeypatch):
    """It cut a run at its middle, wherever the excerpt ended."""
    jobs = days_of(tmp_path, s)
    w = open_window(qt, jobs, s)
    w.table.selectRow(0)
    asked = answering(monkeypatch, ("112", True))
    w._split()
    assert asked == [("Split run", "Cut the run 101–130 after which page number?", w.days[0].span(15, 15))]
    assert [(r.start, r.end, r.keys) for r in w.runs] == [(1, 12, [D, A]), (13, 30, [D, A])]
    assert jobs[0].portions == [(12, [D, A]), (30, [D, A])]
    assert w.table.currentRow() == 0
    w.close()


def test_split_run_cancelled_changes_nothing(qt, themed, tmp_path, s, monkeypatch):
    told = []
    jobs = days_of(tmp_path, s)
    w = open_window(qt, jobs, s, told)
    w.table.selectRow(0)
    answering(monkeypatch, ("112", False))
    w._split()
    assert len(w.runs) == 1 and told == [] and jobs[0].portions is None
    w.close()


@pytest.mark.parametrize("typed, why", [("500", "page numbers are 101–130"), ("130", "before its last page"),
                                        ("x", "type the run")])
def test_split_run_says_why_it_cant_cut_there(qt, themed, tmp_path, s, monkeypatch, typed, why):
    w = open_window(qt, days_of(tmp_path, s), s)
    w.table.selectRow(0)
    answering(monkeypatch, (typed, True))
    w._split()
    assert why in w.problem.text() and len(w.runs) == 1
    w.close()


def test_split_run_with_the_table_changed_meanwhile(qt, themed, tmp_path, s, monkeypatch):
    """A read ending while it asks shows the days afresh: the same run, new objects, is the one cut; gone, it says
    so."""
    jobs = days_of(tmp_path, s)
    w = open_window(qt, jobs, s)
    w.table.selectRow(0)
    answering(monkeypatch, ("112", True), meanwhile=lambda: w.load(jobs))
    w._split()
    assert [(r.start, r.end) for r in w.runs] == [(1, 12), (13, 30)]
    w.table.selectRow(0)

    def cut_away():
        jobs[0].portions = None
        w.load(jobs)
    answering(monkeypatch, ("105", True), meanwhile=cut_away)
    w._split()
    assert "changed meanwhile" in w.problem.text() and [(r.start, r.end) for r in w.runs] == [(1, 30)]
    w.close()


# ------------------------------------------------------------------ one rebuild for one change
@pytest.fixture
def beside_main(qt, themed, tmp_path, s, make_window):
    """The window as the main window opens it, on one day of Dana and Alex; how many times its table was rebuilt."""
    from test_show_the_math import settled
    win = settled(make_window(s))
    jobs = days_of(tmp_path, s)
    win.jobs, win.cur = jobs, jobs[0]
    win._show_job()
    win._who_ordered(jobs[0])
    pump(qt)
    w, shows = win.excerpts, []
    show = w._show
    w._show = lambda: (shows.append(1), show())[1]
    yield win, w, shows
    w.close()


def test_a_tick_rebuilds_the_table_once(qt, beside_main):
    """It rebuilt it, then the main window's answer rebuilt it again: seconds each on a long trial."""
    from PySide6.QtCore import Qt
    from minute_filler.gui.excerpts import FIRST_FIRM
    win, w, shows = beside_main
    w.table.item(0, FIRST_FIRM).setCheckState(Qt.Unchecked)
    assert shows == [1]
    assert w.runs[0].keys == [A] and cell(w, 0, D).checkState() == Qt.Unchecked and cell(w, 0, A).checkState() == Qt.Checked
    assert "Alex B. Counsel" in w.summary.text() and "Dana Smith" not in without_tags(w.summary.text()).split("Each firm")[1]
    assert win.cur.ticked_keys() == [A]  # (the main window told)


def test_a_speed_from_a_heading_rebuilds_the_table_once(qt, beside_main):
    win, w, shows = beside_main
    box = w.firm_speed_boxes[D]
    box.setCurrentIndex(box.findData("Daily"))
    box.activated.emit(box.currentIndex())
    pump(qt)
    assert shows == [1] and win.cur.speeds[D] == "Daily" and "Daily" in w.firm_speed_boxes[D].short_text()


def test_make_every_day_whole_rebuilds_the_table_once(qt, beside_main, monkeypatch):
    win, w, shows = beside_main
    d = w.days[0]
    store(d, [Run(d, 1, 10, [A]), Run(d, 11, 30, [A, D])], w.firms, w.s)
    w.load(w.group)
    shows.clear()
    monkeypatch.setattr(qt_box(), "question", lambda *a, **k: qt_box().Yes)
    w._remove_all()
    assert shows == [1] and [(r.start, r.end) for r in w.runs] == [(1, 30)]


def qt_box():
    from PySide6.QtWidgets import QMessageBox
    return QMessageBox


def test_a_tick_is_shown_where_the_main_window_doesnt_follow(qt, themed, tmp_path, s):
    """A window with nothing behind it that loads it: it shows the change itself."""
    from PySide6.QtCore import Qt
    from minute_filler.gui.excerpts import FIRST_FIRM
    told = []
    w = open_window(qt, days_of(tmp_path, s), s, told)
    shows, show = [], w._show
    w._show = lambda: (shows.append(1), show())[1]
    w.table.item(0, FIRST_FIRM).setCheckState(Qt.Unchecked)
    assert told == [1] and shows == [1] and cell(w, 0, D).checkState() == Qt.Unchecked
    w.close()


def test_a_run_typed_is_shown_though_the_main_window_waits_for_the_cell_to_close(qt, beside_main):
    """load() leaves the table alone while a cell is being typed in: the run typed still shows at once, and the days are
    read again when the cell has closed."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    win, w, shows = beside_main
    QTest.keyClick(typing(qt, w, "111-120"), Qt.Key_Return)
    pump(qt)
    assert [(r.start, r.end) for r in w.runs] == [(1, 10), (11, 20), (21, 30)] and w._pending is None
    assert win.cur.portions is not None and (w._chosen().start, w._chosen().end) == (11, 20)


def test_a_tick_still_shows_when_telling_the_main_window_fails(qt, themed, tmp_path, s):
    """(The table isn't left saying what no longer is.)"""
    from PySide6.QtCore import Qt
    from minute_filler.gui.excerpts import ExcerptsWindow, FIRST_FIRM

    def broken():
        raise RuntimeError("the main window couldn't")
    jobs = days_of(tmp_path, s)
    w = ExcerptsWindow(s, broken)
    w.load(jobs)
    w.show()
    pump(qt)
    shows, show = [], w._show
    w._show = lambda: (shows.append(1), show())[1]
    with pytest.raises(RuntimeError):
        w._tell_and_show(w._show)
    assert shows == [1]
    w.close()


def test_the_window_closing_on_a_tick_shows_nothing_more(qt, beside_main):
    """The main window has no days left to show it (ExcerptsWindow.clear): the table isn't rebuilt on nothing."""
    win, w, shows = beside_main
    w.changed = w.clear
    w._tell_and_show(w._show)
    assert shows == [] and not w.isVisible() and w.table.rowCount() == 0
