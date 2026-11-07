"""The Excerpts window, titled "Who ordered which pages" (its button's name since 2026-10-28: "Excerpts…" before):
who ordered which pages of the whole case, as a table (see excerpts.py). Its ? (and the one beside its button in
the main window) shows how to use it, step by step (show_how_to).

A row per run of pages of a day: its date and weekday (in italics on the day's later runs), its page numbers
(typed in the transcript's own page numbers, "141-170", or by place in the day when they aren't known; the runs
around a run typed make room for it; a job of several days shows the numbers printed on its transcripts),
optionally its place in the day ("1–20 of 85 total pages": Settings.excerpt_show_place), a column per firm
(firms_of: one for a firm, however many of its attorneys appear, gui/firm_columns.py: a band of the firm's colour
over its name in the heading, the same colour as a stripe down its cells; ticked = that firm ordered the run, a
click anywhere in the cell ticks it), its pages counted (COUNTS: the user's billed and transcribed, every
reporter's transcribed and billed; each can be hidden under Columns ▾) and, for each speed offered, what each firm
choosing from its invoice pays for it. Only your pages hides, as it is ticked, the runs with none of the user's
pages, and Clear filter shows them again. Under the table the same prices by the firms ordering together ("A + B:
15 of your pages billed (30 total pages) - each of the 2 pays ...": every count says whose pages it counts, the
user's or every reporter's, the user, 2026-10-30) and each firm's invoice, each firm with its colour's square.
Split run… cuts a run in two where it is told; Remove run (or the Delete key) gives a run's pages to the run above
it (excerpts.remove: every page stays in one run); Make this day whole makes a day one run again, Make every day
whole every day of the case. A right-click on a run offers the same. Every change is kept at once (on the days'
jobs) and the main window follows it; a change made there (an attorney ticked, a speed, Peripherals...) shows here
at once too: the window stays open beside it.

Each firm orders its pages at a speed (Job.speeds, and a run's own in Job.portions; see excerpts.py). The box under
a firm's name sets its speed for all its pages of the case (_firm_speed_boxes); a right-click on a firm's cell of a
run sets the speed of that run alone ("Smith Law on this run at…", _run_menu). A ticked cell of a run whose firm
is billed one speed says what the firm pays for the run (_price_cell): "$91.20" alone, "$68.60 (÷2)" sharing it
(already that firm's share: a price with the sum still to do read wrong), "$172.50 · shared" sharing it at different
speeds (÷ would be false: the split rule divides it), the speed first when it isn't the one in the heading
("Daily · $172.50 (÷2)"). Firms that ordered a run together must commit to one (until then it reads
"Expedite? · $68.60 (÷2)", priced at the agreement form's speed, in amber). Only the runs of a firm billed alone,
choosing from its invoice, are priced at each speed offered: their cells are blank, and the "Show prices for" boxes
and their columns are hidden while there is none.
"""
from __future__ import annotations

import html
import re
from datetime import date

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout,
)

from .. import courthouses
from ..batch import pin_orders, speeds_to_ask
from ..excerpts import (
    Day, Run, carve, case_days, count_runs, firms_of, prices, remove, runs_of, sharers, store, whole_day,
)
from ..invoice import default_speed, own_words, shared_words
from ..invoice_calc import fmt
from ..invoice_math import money_exact
from ..rates import speed_key
from ..takes import run_numbers
from .badges import STRIPE_ROLE, badge_html
from .firm_columns import BOX_INSET, FirmCellDelegate, FirmHeader, FirmSpeedBox
from .zoom import z, zoom

DATE, WEEKDAY, PAGES, PLACE = 0, 1, 2, 3  # the first columns
FIRST_FIRM = 4  # then a column per firm, the counts (COUNTS) and a price per speed
# (the heading says where to type: a ✎ already means "corrected by you" on Page numbers in Who transcribed what)
PAGES_HEAD = "Page numbers\n(type here)"
# The counts of a run's pages after the firms (excerpts.Counts), each of which can be hidden (Columns ▾, kept in
# Settings.excerpt_hidden_cols): (key, header, what it counts). One "Pages billed" read as every reporter's
# pages, not the user's (the user, 2026-10-29)
COUNTS = (
    ("your_billed", "Your pages\nbilled",
     "Your pages of the run that your invoice bills (as Whose pages… says); 0 when no firm ordered the run"),
    ("your_transcribed", "Your pages\ntranscribed",
     "The pages of the run with your initials, whether a firm ordered them or not"),
    ("total_transcribed", "Total pages\ntranscribed", "Every reporter's pages of the run"),
    ("total_billed", "Total pages\nbilled", "Every reporter's pages of the run, when a firm ordered it; else 0"),
)
PAGES_TIP = ("The page numbers printed on the transcript, as read from it (where they aren't known: the run's place in "
             "the day, place 1–20). Type a run here, e.g. 141-170, or by its place, place 40-44. How many of the pages "
             "are yours: the count columns")
PLACE_TIP = "The run's place among the day's pages: 1–20 of 85 total pages (every reporter's)"
UNKNOWN = ("Which of these pages are yours can't be told: set your initials in Settings → My info, or say whose "
           "the first pages are under Whose pages… (a day whose Est. number of pages was typed in isn't counted by page)")
AMBER = "#d97706"  # (a firm's cell without the speed it must commit to: the warnings' amber, light and dark)
VARIES = "(varies)"  # the Speed box of a firm whose days or runs are at different speeds
CHOOSES = "Chooses on the invoice"  # the Speed box of a firm none is set for, that may choose from its invoice
FIRM_NAME_MAX = 170  # a firm's column needn't be wider than this for its name, before zoom: a longer one is cut


TITLE = "Who ordered which pages"  # the window's title (the main window's button says it with "…")
# How to use the window, in steps, for a new user: the ? beside its button in Who ordered, and the one in the
# window, show it (show_how_to; the user, 2026-10-28)
HOW_TO = """<p>Use it when a firm ordered <b>only some pages</b> of a day (an excerpt), not the whole transcript.</p>
<ol>
<li>Each row is a <b>run of pages</b> of a day. At first a day is one run: every ticked firm ordered all of it.</li>
<li>To make a run, type its pages in the transcript's printed page numbers (<i>141-170</i>) in the Page numbers cell. The
rows around it make room. Where a page has no number, or the numbers start again, type its place in the day
(<i>place 40-44</i>).</li>
<li><b>Tick the firms that ordered</b> each run, and untick the ones that didn't: click anywhere in the firm's cell.
(To choose a row without ticking, click its date.) A run nobody ticks is billed to nobody.</li>
<li>Set each firm's <b>speed</b> in the list under its name. A run at another speed: right-click the firm's cell
in that run.</li>
<li><b>Split run…</b> cuts a run in two where you say. <b>Remove run</b> (or the Delete key) gives a run's pages back
to the run above it. <i>Make this day whole</i> makes the day one run again.</li>
<li>Each firm has its colour, over its name and down its column. A price is what that firm pays: <i>(÷2)</i> says
it is already its share of pages two firms ordered. Under the table: what each set of firms pays.</li>
<li>Each run counts <b>your pages</b> (billed and transcribed) and every reporter's. <i>Columns ▾</i> hides
counts you don't need; <b>Only your pages</b> shows only the runs with pages of yours.</li>
</ol>
<p>Every change is kept at once; the window can stay open beside the main window.</p>"""


def show_how_to(parent, show_help=None) -> None:
    """The steps of HOW_TO in a box, with "More in the manual" opening the help at the window's topic
    (show_help, the main window's: help_topics "exc-table") when given."""
    box = QMessageBox(QMessageBox.Information, f"{TITLE}: how to use it", HOW_TO, parent=parent)
    box.setTextFormat(Qt.RichText)
    more = box.addButton("More in the manual", QMessageBox.HelpRole) if show_help else None
    box.addButton(QMessageBox.Close)
    box.exec()
    if more is not None and box.clickedButton() is more:
        show_help("exc-table")


def weekdays(label: str) -> str:
    """The weekday of the date(s) in a day's label: '9/28/2026' -> 'Monday'; '6/3/2026, 6/4/2026' (a job of
    several days) -> 'Wed, Thu'; '' when it holds no date."""
    found = []
    for m, d, y in re.findall(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", label or ""):
        try:
            found.append(date(int(y), int(m), int(d)))
        except ValueError:
            continue
    if len(found) == 1:
        return found[0].strftime("%A")
    return ", ".join(x.strftime("%a") for x in found)


class ExcerptsWindow(QDialog):
    """Who ordered which pages of the case: see the module docstring. load(group) shows the days of an invoice
    (MainWindow keeps it up to date); changed() is called after each change is kept."""

    def __init__(self, s, changed, parent=None, marks=None, trial=None):
        """s: the settings (the rate sheet, the speeds, what this window hides); changed: called after a change
        is kept on the jobs, so the main window shows it; marks: a job -> the marks of its trial's firms, by
        Attorney.key(), as the main window shows them (MainWindow._marks: every day of the trial loaded, those
        not on this invoice too, so a firm has the same colour here); without it, those of the days shown. trial:
        the jobs shown -> every day of their trials (MainWindow._trial_of), which the table's ticks are pinned on
        (_pin); without it, the days shown."""
        super().__init__(parent)
        self.s, self.changed, self.marks, self.trial = s, changed, marks, trial
        self.setWindowTitle(TITLE)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.group: list = []  # the jobs shown (the days of an invoice)
        self.days: list[Day] = []
        self.runs: list[Run] = []
        self.firms = []
        self.speeds: list[str] = []
        self._loading = False
        self._pending = None  # the jobs to show once the cell being typed in is left (see load)
        self._marks: dict = {}  # each firm's mark, by Attorney.key(), as last shown (a firm without one: none)
        self.firm_speed_boxes: dict[str, FirmSpeedBox] = {}  # the firms' boxes shown now, by Attorney.key()
        self._speed_box_of: dict[str, FirmSpeedBox] = {}  # every box made, kept for the next showing (firm_columns)
        self._heading_speed: dict[str, str | None] = {}  # the speed a firm's box says, if one (_firm_speed_boxes)
        self._firm_width, self._firm_width_for = 0, None  # a firm column's width, and for which firms (_fit_columns)
        self.setProperty("help_topic", "exc-table")  # (what F1 opens, unless the focus is on something of its own)
        QShortcut(QKeySequence("F1"), self, activated=self.show_help)
        lay = QVBoxLayout(self)
        # (the steps are the ? button's, show_how_to; how the prices are split is the note by Close)
        intro = QLabel("Tick who ordered each run. Type in Page numbers to make a new run.")
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        top = QHBoxLayout()
        top.addWidget(intro, 1)
        how = QToolButton()
        how.setText("?")
        how.setObjectName("quick")
        how.setToolTip("How to use this window, step by step")
        how.clicked.connect(lambda: show_how_to(self, getattr(parent, "show_help", None)))
        top.addWidget(how, 0, Qt.AlignTop)
        self.how = how
        lay.addLayout(top)
        opts = QHBoxLayout()
        self.place = QCheckBox("Show each run's place in the day")
        self.place.setChecked(s.excerpt_show_place)
        self.place.setToolTip("Besides the page numbers: the run's place in the day, 1–20 of 85 total pages")
        self.place.toggled.connect(self._place_toggled)
        opts.addWidget(self.place)
        opts.addSpacing(z(12))
        # The count columns, each shown or hidden (also a right-click on the table's header)
        self.columns = QToolButton()
        self.columns.setText("Columns ▾")
        self.columns.setToolTip("Show or hide the counts of each run's pages: yours and every reporter's")
        self.columns.setPopupMode(QToolButton.InstantPopup)
        self.columns.setProperty("help_topic", "exc-your-pages")
        self.columns_menu = QMenu(self.columns)
        self.count_actions = {}
        for key, head, tip in COUNTS:
            act = self.columns_menu.addAction(head.replace("\n", " "))
            act.setCheckable(True)
            act.setChecked(key not in s.excerpt_hidden_cols)
            act.setToolTip(tip)
            act.toggled.connect(self._columns_toggled)
            self.count_actions[key] = act
        self.columns.setMenu(self.columns_menu)
        opts.addWidget(self.columns)
        opts.addSpacing(z(12))
        # Only the runs with pages of the user's, at once as it is ticked (the user, 2026-10-29)
        self.only_mine = QCheckBox("Only your pages")
        self.only_mine.setChecked(s.excerpt_only_mine)
        self.only_mine.setToolTip("Shows only the runs with pages you transcribed, billed or not")
        self.only_mine.toggled.connect(self._only_mine_toggled)
        self.only_mine.setProperty("help_topic", "exc-your-pages")
        opts.addWidget(self.only_mine)
        self.clear_filter = QPushButton("Clear filter")
        self.clear_filter.setAutoDefault(False)
        self.clear_filter.setToolTip("Shows every run again")
        self.clear_filter.clicked.connect(lambda: self.only_mine.setChecked(False))
        self.clear_filter.setVisible(False)
        self.clear_filter.setProperty("help_topic", "exc-your-pages")
        opts.addWidget(self.clear_filter)
        self.filter_note = QLabel("")
        self.filter_note.setObjectName("muted")
        opts.addWidget(self.filter_note)
        opts.addSpacing(z(18))
        self.speeds_label = QLabel("Show prices for:")
        opts.addWidget(self.speeds_label)
        self.speed_row = QHBoxLayout()
        opts.addLayout(self.speed_row)
        self.speed_boxes: dict[str, QCheckBox] = {}
        opts.addStretch(1)
        lay.addLayout(opts)
        self.table = QTableWidget(0, 0)
        head = FirmHeader()
        self.table.setHorizontalHeader(head)
        self.table.setItemDelegate(FirmCellDelegate(self.table))  # (table-wide: the firms' columns move)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                                   | QAbstractItemView.AnyKeyPressed)
        self.table.itemChanged.connect(self._item_changed)
        self.table.itemDelegate().closeEditor.connect(self._editor_closed)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        head.setContextMenuPolicy(Qt.CustomContextMenu)
        head.customContextMenuRequested.connect(lambda pos: self.columns_menu.exec(head.mapToGlobal(pos)))
        self._counts: dict = {}  # each run's counts (excerpts.count_runs), by id(run), as last shown
        # Delete removes the run chosen, only while the table itself has the focus: in a cell being typed in, Delete
        # deletes text (the editor has the focus then; _remove checks too)
        QShortcut(QKeySequence.Delete, self.table, self._remove, context=Qt.WidgetShortcut)
        lay.addWidget(self.table, 3)
        row = QHBoxLayout()
        for text, slot, tip in (("Split run…", self._split, "Asks where, and cuts the run chosen in two there"),
                                ("Remove run", self._remove,
                                 "The run chosen goes: its pages join the run above it, with that run's firms (the "
                                 "run below, for a day's first run). Delete does it too"),
                                ("Make this day whole", self._whole_day,
                                 "The day of the run chosen: one run of every page, ordered by every firm that "
                                 "ordered any of it"),
                                ("Make every day whole", self._remove_all,
                                 "Every day of the case: one run of every page, ordered by every firm that ordered "
                                 "any of it (asks first)")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setAutoDefault(False)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        self.problem = QLabel("")
        self._speeds_warning = ""  # (the speeds warning shown in it, taken away once the speeds are fixed)
        self.problem.setObjectName("problem")
        self.problem.setWordWrap(True)
        row.addWidget(self.problem, 1)
        lay.addLayout(row)
        self.falling = QLabel("")  # (a line of its own: self.problem is cleared by the next change, this stays)
        self.falling.setObjectName("problem")
        self.falling.setWordWrap(True)
        self.falling.setVisible(False)
        lay.addWidget(self.falling)
        self.summary = QLabel("")
        self.summary.setTextFormat(Qt.RichText)
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.summary, 2)
        self.note = QLabel("")  # (how the prices are split: _show_note)
        self.note.setObjectName("muted")
        self.note.setWordWrap(True)
        self._show_note()
        close = QPushButton("Close")
        close.setAutoDefault(False)
        close.clicked.connect(self.close)
        bottom = QHBoxLayout()
        bottom.addWidget(self.note, 1)
        bottom.addWidget(close, 0, Qt.AlignBottom)
        lay.addLayout(bottom)
        self.resize(z(1000), z(640))

    def show_help(self) -> None:
        """F1: the help on what has the focus (help_window.help_topic_of: the Speed boxes and the counts' controls
        have their own topic), else on the table."""
        from .help_window import help_topic_of, open_help
        open_help(help_topic_of(self.focusWidget()) or "exc-table", self.parentWidget() or self)

    # ------------------------------------------------------------------ showing
    def load(self, group: list) -> None:
        """Shows the days of an invoice (jobs) as they are now. While a cell is being typed in, the table is
        left alone (it would close the editor) but marked stale: it is shown again before the typing is kept,
        or when the editor closes, so runs the main window has changed meanwhile aren't written back."""
        if self.table.state() == QAbstractItemView.EditingState:
            self._pending = list(group)
            return
        self._fill(group)

    def clear(self) -> None:
        """Forgets the days shown and closes the window (their jobs are gone, or have no days to show: New job,
        a job removed, a job without a transcript)."""
        self._pending = None
        self.group, self.days, self.runs, self.firms = [], [], [], []
        self._counts, self._marks = {}, {}
        self._loading = True
        self.table.setRowCount(0)
        self._loading = False
        self.summary.setText("")
        self.problem.setText("")
        self.close()

    def _editor_closed(self, *_):
        """The editor closed without a change kept (Escape, or the same text): a reload skipped while typing
        is done now."""
        if self._pending is not None:
            QTimer.singleShot(0, self._reload_pending)

    def _reload_pending(self) -> None:
        """Shows the jobs load() left waiting, unless a cell is being typed in again by now."""
        if self._pending is not None and self.table.state() != QAbstractItemView.EditingState:
            self._fill(self._pending)

    def _fill(self, group: list) -> None:
        """Reads the days (those with pages), the firms and the runs of these jobs afresh and shows them."""
        self._pending = None
        self.group = list(group)
        self.days = [d for d in case_days(group) if d.pages > 0]
        self.firms = firms_of(group)
        self.runs = [r for d in self.days for r in runs_of(d, self.firms)]
        self._show()

    def _show(self) -> None:
        """Fills the table, the firms' headings (their bands and speed boxes), the prices and the speeds warning
        under it and the note on the prices, from self.runs. The row and column chosen and the scrolling stay as
        they were, and a speed box isn't touched unless its choices changed: this runs on every tick, and on every
        change in the main window (a read ending, an AI answer)."""
        p = prices(self.days, self.runs, self.s)
        self.speeds = p.speeds
        self._speed_boxes(p.speeds)
        # "Show prices for" and its "Each pays · <speed>" columns price the runs whose firms choose from their
        # invoices: hidden while every run is priced at the speeds its firms ordered
        choice = bool(p.runs) or not p.ordered
        self.speeds_label.setVisible(choice)
        for cb in self.speed_boxes.values():
            cb.setVisible(choice)
        shown = [sp for sp in p.speeds if sp not in self.s.excerpt_hidden_speeds] if choice else []
        firms = self.firms
        heads = ["Date", "Weekday", PAGES_HEAD, "Place in the day"] + [a.label() for a in firms] + [
            head for _, head, _ in COUNTS] + [f"Each pays · {sp}" for sp in shown]
        self._counts = count_runs(self.runs)
        self._loading = True
        t = self.table
        header = t.horizontalHeader()
        keep_row, keep_col = t.currentRow(), t.currentColumn()
        across, down = t.horizontalScrollBar().value(), t.verticalScrollBar().value()
        header.hold()  # (the boxes stay as they are while the sections are set again)
        t.clear()
        t.setColumnCount(len(heads))
        t.setHorizontalHeaderLabels(heads)
        from ..batch import trial_marks
        from .badges import side_name, tag_color
        marks = {}  # (each firm's colour, as elsewhere)
        if self.group:
            try:
                marks = self.marks(self.group[0]) if self.marks else trial_marks(self.group[0], self.group)
            except Exception:  # (a colour is a help: never a reason for the table not to show)
                marks = {}
        self._marks = marks
        self._firm_speed_boxes()
        stripe = {k: tag_color(m).name() for k, m in marks.items() if m is not None}
        for c, a in enumerate(firms):
            head = t.horizontalHeaderItem(FIRST_FIRM + c)
            head.setToolTip(" - ".join(x for x in (a.name, a.firm) if x))
            head.setData(STRIPE_ROLE, stripe.get(a.key()))
            if marks.get(a.key()) is not None:
                head.setToolTip(f"{head.toolTip()}\n{side_name(marks[a.key()])}".strip())
        t.horizontalHeaderItem(PAGES).setToolTip(PAGES_TIP)
        t.horizontalHeaderItem(PLACE).setToolTip(PLACE_TIP)
        t.setRowCount(len(self.runs))
        first = FIRST_FIRM + len(firms)
        for k, (_, _, tip) in enumerate(COUNTS):
            t.horizontalHeaderItem(first + k).setToolTip(tip)
        # (the speed Generate bills a firm sharing pages without one at, by day: the agreement form's, or the firm's
        # on its other pages, batch.speeds_to_ask)
        settles = {(id(a.job), a.key): a.speed for a in speeds_to_ask([d.job for d in self.days], self.s)}
        mixed = False  # (a run shared at different speeds: the note says how it is divided)
        for r, run in enumerate(self.runs):
            day = run.day
            new_day = r == 0 or self.runs[r - 1].day is not day
            for c, text in ((DATE, day.label), (WEEKDAY, weekdays(day.label))):
                it = self._cell(r, c, text, False)
                if not new_day:  # a later run of the same day: its date, in italics
                    font = it.font()
                    font.setItalic(True)
                    it.setFont(font)
                    it.setToolTip("The same day as the run above")
            pages = self._cell(r, PAGES, day.span(run.start, run.end), day.splittable)
            pages.setToolTip(f"Type a run of {day.label}'s pages, e.g. {day.example()}"
                             if day.splittable else "This job covers several days: it is ordered whole. These are "
                             "the page numbers printed on its transcripts")
            self._cell(r, PLACE, day.place(run.start, run.end), False)
            at = p.ordered.get(id(run))  # (key -> (speed, what it pays): firms at the speeds they ordered)
            mixed = mixed or bool(at and len({speed_key(sp) for sp, _ in at.values()}) > 1)
            for c, a in enumerate(firms):
                it = QTableWidgetItem("")
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
                on = a.key() in run.keys
                it.setCheckState(Qt.Checked if on else Qt.Unchecked)
                it.setData(STRIPE_ROLE, stripe.get(a.key()))
                if on and at and a.key() in at:
                    self._price_cell(it, run, a, at, settles)
                elif on:  # (it chooses from its invoice: the price is in Each pays)
                    it.setToolTip(f"Ordered together by {len(run.keys)} firms: they share these pages"
                                  if len(run.keys) > 1 else "Ordered by this firm alone")
                t.setItem(r, FIRST_FIRM + c, it)
            n = self._counts[id(run)]
            self._cell(r, first, str(n.your_billed) if run.keys else "0 (nobody)", False)
            mine = self._cell(r, first + 1, "?" if n.your_transcribed is None else str(n.your_transcribed), False)
            if n.your_transcribed is None:
                mine.setToolTip(UNKNOWN)
            self._cell(r, first + 2, str(n.total_transcribed), False)
            self._cell(r, first + 3, str(n.total_billed), False)
            each = p.runs.get(id(run), {})
            for k, sp in enumerate(shown):
                text = money_exact(each[sp]) if sp in each else ""
                if text and sharers(run) > 1:
                    text += f" (÷{sharers(run)})"
                self._cell(r, first + len(COUNTS) + k, text, False)
        t.setColumnHidden(PLACE, not self.s.excerpt_show_place)
        for c in range(FIRST_FIRM, t.columnCount()):  # (a firm added takes the number of a count, perhaps hidden)
            t.setColumnHidden(c, False)
        for k, (key, _, _) in enumerate(COUNTS):
            t.setColumnHidden(first + k, key in self.s.excerpt_hidden_cols)
        self._apply_filter()
        self._fit_columns(first)
        header.set_firm_columns({FIRST_FIRM + c: self.firm_speed_boxes[a.key()] for c, a in enumerate(firms)})
        if 0 <= keep_row < t.rowCount() and not t.isRowHidden(keep_row):  # (a run Only your pages hides isn't chosen)
            # (the same cell, not selectRow, which moves to the first column: a second Space then ticked nothing)
            t.setCurrentCell(keep_row, keep_col if 0 <= keep_col < t.columnCount() and not t.isColumnHidden(keep_col)
                             else DATE)
        t.horizontalScrollBar().setValue(across)
        t.verticalScrollBar().setValue(down)
        self._loading = False
        self.summary.setText(self._summary(p, shown))
        self._show_note(mixed)
        held = [x for d in self.days for x in d.job.speed_problems(self.s)]
        warned, self._speeds_warning = self._speeds_warning, "⚠ " + held[0] if held else ""
        if held:  # (three speeds on the same pages: the invoice waits; a speed the rate sheet lacks: Generate stops)
            self.problem.setText(self._speeds_warning)
        elif warned and self.problem.text() == warned:  # (fixed since, by the strip or a right-click)
            self.problem.setText("")
        self._warn_falling()

    def _warn_falling(self) -> None:
        """The warning that stays while a day's printed page numbers start again ("1–39, 10–29"): a number can be
        on two of its pages, so such a run is refused (Day.parse) unless it is typed by its place."""
        days = [d for d in self.days if d.splittable and d.falls()]
        self.falling.setText("; ".join(f"⚠ {d.label}'s printed page numbers start again ({run_numbers(d.printed).text})"
                                       for d in days)
                             + (": a number can be on two pages, so type such a run by its place in the day, e.g. "
                                "place 40-44." if days else ""))
        self.falling.setVisible(bool(days))

    def _fit_columns(self, first: int) -> None:
        """The columns as wide as what they hold, the firms' (FIRST_FIRM to first) all one width: that of the widest
        cell, name (cut, past FIRM_NAME_MAX) or speed box of any of them. It only grows while the firms and the zoom
        are the same, so a tick doesn't move the columns under the mouse."""
        t = self.table
        header = t.horizontalHeader()
        t.resizeColumnsToContents()
        t.setColumnWidth(PAGES, max(t.columnWidth(PAGES), z(110)))
        shown_for = (tuple(a.key() for a in self.firms), zoom())
        if shown_for != self._firm_width_for:
            self._firm_width, self._firm_width_for = 0, shown_for
        for c, a in enumerate(self.firms, FIRST_FIRM):
            # (a cell sized to the pixel came out "Immediate · …": the box's margin isn't counted)
            self._firm_width = max(self._firm_width, t.sizeHintForColumn(c) + z(10),
                                   min(header.sectionSizeHint(c), z(FIRM_NAME_MAX)),
                                   self.firm_speed_boxes[a.key()].widest_short() + 2 * z(BOX_INSET))
        for c in range(FIRST_FIRM, first):
            t.setColumnWidth(c, self._firm_width)

    def _show_note(self, mixed: bool = False) -> None:
        """The note by Close: what a price in the table is, and how shared pages are split, as Settings say; while a
        run is shared at different speeds (mixed), how that one is divided too."""
        text = (f"Each price is what that firm pays. Pages several firms ordered split {shared_words(self.s)}; each "
                f"firm pays for its own {own_words(self.s)}.")
        if mixed:
            text += (" At different speeds the original is billed once and divided as Settings → Invoice → Split "
                     "invoices says.")
        self.note.setText(text)

    def _price_cell(self, it: QTableWidgetItem, run: Run, firm, at: dict, settles: dict) -> None:
        """A ticked cell of a run priced at the speeds ordered: what the firm pays for it, already its share
        (at: Prices.ordered of the run). The speed only when the firm's heading doesn't say it. A firm that must
        still commit to a speed (settles: batch.speeds_to_ask): the speed it is priced at until then, with a ?, in
        amber."""
        key = firm.key()
        speed, pays = at[key]
        price, n = money_exact(pays), sharers(run)
        mixed = len({speed_key(sp) for sp, _ in at.values()}) > 1
        # (÷n would be false at different speeds: "$7.60 - $3.25" of the original isn't anything over n)
        share = " · shared" if mixed else f" (÷{n})" if n > 1 else ""
        heading = self._heading_speed.get(key)
        billed = (self.s.split_speeds != "ask"
                  and speed_key(settles.get((id(run.day.job), key), speed)) == speed_key(speed))  # (as said)
        if not run.speed(key) and not billed:  # (it must commit to one: priced at the agreement form's until then)
            it.setText(f"{speed}? · {price}{share}")
            it.setForeground(QColor(AMBER))
            why = "these pages are" if len(run.keys) > 1 else "some of its pages are"  # (alone on this run: its others)
            it.setToolTip(f"No speed set: {why} ordered with another firm, so this one commits to a speed (Generate "
                          f"asks). Priced at {speed}, the agreement form's, until then. Right-click to set it, or set "
                          "it under the firm's name.")
            return
        said = heading is not None and speed_key(heading) == speed_key(speed)
        it.setText(f"{price}{share}" if said else f"{speed} · {price}{share}")
        name = firm.label()
        if mixed:
            kinds = list(dict.fromkeys(sp for sp, _ in at.values()))
            tip = (f"Ordered together at different speeds ({self._run_note(kinds)}), divided as Settings → Invoice → "
                   f"Split invoices says. {name} pays {price}.")
        elif n > 1:
            who = f"the {n} firms that ordered them" if n == len(run.keys) else f"the {n} parties ordering them"
            tip = (f"{name} pays {price} for these pages: {who} split {shared_words(self.s)}; each pays for its own "
                   f"{own_words(self.s)}.")
        else:
            tip = f"Ordered by this firm alone: {name} pays {price}."
        if not run.speed(key):
            tip += (f" Billed at {speed}, the agreement form's speed, unless you choose another (right-click, or "
                    "under the firm's name).")
        it.setToolTip(tip)

    def _run_note(self, kinds: list[str]) -> str:
        """How a run ordered at these speeds is divided, given the fastest of them (SplitRule.run_note: "one original,
        at Immediate"): the rule the job was billed by, or an earlier day of its trial (Job.trial_rule), else
        Settings'."""
        order = {sp.name: i for i, sp in enumerate(self.s.sheet().speeds)}  # (cheapest first: the last, fastest)
        billed = next((d.job.split_rule for d in self.days if d.job.split_rule), "") or \
            next((d.job.trial_rule for d in self.days if d.job.trial_rule), "")
        rule = courthouses.split_rule(billed or self.s.invoice_split_rule)
        return rule.run_note(max(kinds, key=lambda sp: order.get(sp, -1)))

    def _cell(self, r: int, c: int, text: str, editable: bool) -> QTableWidgetItem:
        """Puts a text cell in the table (only a run's Pages can be typed in) and returns it."""
        it = QTableWidgetItem(text)
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        it.setFlags(flags | Qt.ItemIsEditable if editable else flags)
        self.table.setItem(r, c, it)
        return it

    def _summary(self, p, shown: list[str]) -> str:
        """The prices under the table: by the firms ordering together (at the speeds they ordered, when set:
        "Counsel & Counsel (Daily) + Smith Law (Immediate): 60 of your pages billed (60 total pages) - Counsel &
        Counsel pays $345.00, Smith Law $435.00 (one original, at Immediate)", the split rule saying how:
        SplitRule.run_note, the job's once billed, else the one its trial was first billed by (Job.trial_rule),
        else Settings'), then each firm's invoice. Each firm a line is about has its colour's square (badge_html,
        its name escaped: "Counsel & Counsel")."""
        names = {a.key(): a.label() for a in self.firms}
        if not shown and not p.ordered:
            return "<i>Tick a speed above to see the prices.</i>"

        def named(k: str) -> str:
            """A firm's name with its colour's square."""
            return badge_html(self._marks.get(k), names.get(k, k))

        lines = ["<b>The pages by who ordered them together</b>"]
        for keys, _, each in p.groups:
            who = " + ".join(named(k) for k in keys)
            alone = len(keys) == 1
            costs = " · ".join(f"{html.escape(sp)} {money_exact(each[sp])}" for sp in shown if sp in each)
            lines.append(f"{who}{' only' if alone else ''}: {self._pages_of(p.members.get(keys, []))} - "
                         + (f"costs {costs}" if alone else f"each of the {len(keys)} pays {costs}"))
        for pairs, _, each in p.ordered_groups:
            who = " + ".join(f"{named(k)} ({html.escape(sp)})" for k, sp in pairs)
            if len(pairs) == 1:
                lines.append(f"{who} only: {self._pages_of(p.members.get(pairs, []))} - costs "
                             f"{money_exact(each[pairs[0][0]])}")
                continue
            pays = ", ".join(f"{html.escape(names.get(k, k))} {'pays ' if n == 0 else ''}{money_exact(each[k])}"
                             for n, (k, _) in enumerate(pairs))
            kinds = list(dict.fromkeys(sp for _, sp in pairs))
            how = f" ({html.escape(self._run_note(kinds))})" if len(kinds) > 1 else ""
            lines.append(f"{who}: {self._pages_of(p.members.get(pairs, []))} - {pays}{how}")
        # (every reporter's pages, as the table's Total pages transcribed has them, not only the invoice's: the
        # user, 2026-10-29), and the user's among them when that can be told
        nobody = [self._counts[id(r)] for r in self.runs if not r.keys]
        total = sum(n.total_transcribed for n in nobody)
        if total:
            mine = [n.your_transcribed for n in nobody]
            yours = "" if None in mine else f", {sum(mine)} of them yours"
            lines.append(f"Nobody: {total} total pages{yours} (not billed)")
        if p.firms:
            how = ("its price a page rounded to the cent" if self.s.invoice_rounding == "page"
                   else "rounded up to the cent")
            lines.append(f"<br><b>Each firm's invoice</b> ({how})")
            for key, amounts in p.firms:
                # (the speeds offered, as ticked above; an invoice of the speed the firm ordered: that one, ticked
                # or not)
                costs = " · ".join(f"{html.escape(sp)} {fmt(amounts[sp])}" for sp in amounts
                                   if key in p.committed or sp in shown or sp not in p.speeds)
                lines.append(f"{named(key)}: {costs}")
        return "<br>".join(lines)

    def _pages_of(self, runs: list[int]) -> str:
        """The pages of a line under the table (the runs, by id, of a set of firms ordering together:
        Prices.members), both counts said: "43 of your pages billed (93 total pages)", as the table's Your pages
        billed and Total pages billed (a bare "43 pp." read as all the pages: the user, 2026-10-30)."""
        counts = [self._counts[i] for i in runs if i in self._counts]
        return (f"{sum(n.your_billed for n in counts)} of your pages billed "
                f"({sum(n.total_billed for n in counts)} total pages)")

    def _firm_speed_boxes(self) -> None:
        """Each firm's box in its heading: the speed it ordered all its pages of the case at (Job.speeds of each day
        it ordered on; VARIES when they differ, or a run has its own), CHOOSES for none; choosing one sets it on
        every day (_firm_speed_chosen). A firm's box is kept from one showing to the next (self._speed_box_of), so
        an open list and the focus stay. _heading_speed notes the speed each says, so the firm's cells needn't say
        it (None for VARIES, CHOOSES and a firm that ordered nothing)."""
        self.firm_speed_boxes, self._heading_speed = {}, {}
        sheet = self.s.sheet()
        speeds = [sp.name for sp in sheet.speeds]
        viewport = self.table.horizontalHeader().viewport()
        for a in self.firms:
            k = a.key()
            box = self._speed_box_of.get(k)
            if box is None:
                box = self._speed_box_of[k] = FirmSpeedBox(viewport)
                box.setProperty("help_topic", "exc-speeds")
                box.activated.connect(lambda _i, key=k, b=box: self._firm_speed_chosen(key, b.currentData()))
            self.firm_speed_boxes[k] = box
            self._heading_speed[k] = None
            mine = {r.speed(k) for r in self.runs if k in r.keys}
            box.setEnabled(bool(mine))
            if not mine:  # (it orders nothing of the case: no day to set a speed on)
                box.set_choices([("No pages ordered", None, "–")], 0)
                box.setToolTip(f"{a.label()} ordered no pages of these days: tick a run first, then set its speed here")
                continue
            items = [(VARIES, None, VARIES)] if len(mine) > 1 else []
            # (none set: a firm ordering pages with another is billed the agreement form's speed, as Who ordered
            # says, unless Generate asks; one alone chooses on its invoice)
            shared = next((r for r in self.runs if k in r.keys and len(r.keys) > 1 and not r.speed(k)), None)
            form = None
            if shared is not None and courthouses.speed_upfront() and self.s.split_speeds != "ask":
                form = default_speed(shared.day.job.case, self.s)
                items.append((f"The form's ({form})", "", form))
            else:
                # (sharing pages where Generate asks, it doesn't choose: it hasn't said. No wider than "Immediate",
                # always in the list: the column doesn't jump as a tick makes it one of these)
                items.append((CHOOSES, "", "Not set" if shared is not None and courthouses.speed_upfront()
                               else "Chooses"))
            items += [(sp, sp, sp) for sp in speeds]
            now = next(iter(mine)) if len(mine) == 1 else None
            found = sheet.find(now) if now else None  # ("Expedited" is the sheet's "Expedite")
            if now and found is None:  # (a speed the rate sheet doesn't have: kept, and said, as in the card)
                items.append((f"{now} (not on the rate sheet)", now, now))
            wanted = found.name if found else now
            box.set_choices(items, 0 if now is None else next((i for i, x in enumerate(items) if x[1] == wanted), 0))
            if now is not None:
                self._heading_speed[k] = wanted or form
            box.setToolTip(f"The speed {a.label()} ordered all its pages of the case at. A firm ordering pages "
                           "together with another commits to one; a firm alone may choose from its invoice. A run "
                           "at another speed: right-click the firm's cell in that run.")

    def _firm_speed_chosen(self, key: str, speed) -> None:
        """A firm's speed for all its pages of the case (the box under its name): set on every day it ordered
        on, its runs' own speeds cleared (Job.set_speed); "" = chooses from its invoice. The table is shown again
        after the box's own signal."""
        if speed is None:
            return
        for day in self.days:
            if any(key in r.keys for r in self._day_runs(day)):
                day.job.set_speed(key, speed)
        QTimer.singleShot(0, self._speeds_kept)

    def _speeds_kept(self) -> None:
        """After a speed is set: the days read again and shown, and the main window told."""
        self._fill(self.group)
        self.changed()

    def _speed_boxes(self, speeds: list[str]) -> None:
        """A box per speed offered: unticked hides its prices (kept in Settings.excerpt_hidden_speeds)."""
        if list(self.speed_boxes) == speeds:
            return
        while self.speed_row.count():
            w = self.speed_row.takeAt(0).widget()
            if w is not None:
                w.hide()  # (at once, as in _firm_speed_boxes)
                w.deleteLater()
        self.speed_boxes = {}
        for sp in speeds:
            cb = QCheckBox(sp)
            cb.setChecked(sp not in self.s.excerpt_hidden_speeds)
            cb.toggled.connect(self._speeds_toggled)
            self.speed_row.addWidget(cb)
            self.speed_boxes[sp] = cb

    def _speeds_toggled(self, _=None) -> None:
        """A speed's box ticked or unticked: its prices shown or hidden, and the choice saved."""
        hidden = [sp for sp, cb in self.speed_boxes.items() if not cb.isChecked()]
        # (a speed hidden that this case doesn't offer stays hidden for the next case that does)
        self.s.excerpt_hidden_speeds = hidden + [x for x in self.s.excerpt_hidden_speeds if x not in self.speed_boxes]
        self._save_settings()
        self._show()

    def _place_toggled(self, on: bool) -> None:
        """Show each run's place in the day: the column shown or hidden, and the choice saved."""
        self.s.excerpt_show_place = on
        self._save_settings()
        self.table.setColumnHidden(PLACE, not on)

    def _columns_toggled(self, _=None) -> None:
        """A count ticked or unticked under Columns ▾: its column shown or hidden at once, and the choice saved
        (a column of the counts not in COUNTS, from a later version, stays hidden)."""
        hidden = [key for key, act in self.count_actions.items() if not act.isChecked()]
        self.s.excerpt_hidden_cols = hidden + [x for x in self.s.excerpt_hidden_cols if x not in self.count_actions]
        self._save_settings()
        if self.table.columnCount() >= FIRST_FIRM + len(self.firms) + len(COUNTS):
            for k, (key, _, _) in enumerate(COUNTS):
                self.table.setColumnHidden(FIRST_FIRM + len(self.firms) + k, key in hidden)

    def _only_mine_toggled(self, on: bool) -> None:
        """Only your pages: the runs without any of the user's pages hidden, or shown again, at once; the choice
        saved."""
        self.s.excerpt_only_mine = on
        self._save_settings()
        self._apply_filter()

    def _apply_filter(self) -> None:
        """Hides, while Only your pages is ticked, each run with none of the user's pages (one whose pages can't be
        told stays shown), and says how many are shown; Clear filter is there only meanwhile. The rows are
        hidden, not taken out: row r is still self.runs[r], for the buttons and the right-click. A row hidden is
        chosen no longer (else Split run or the Delete key acted on a run not shown)."""
        known = [c for c in self._counts.values() if c.your_transcribed is not None]
        self.only_mine.setEnabled(bool(known) or not self.runs)
        self.only_mine.setToolTip("Shows only the runs with pages you transcribed, billed or not" if known or
                                  not self.runs else UNKNOWN)
        on = self.only_mine.isChecked() and self.only_mine.isEnabled()
        shown = 0
        for r, run in enumerate(self.runs):
            c = self._counts.get(id(run))
            hide = on and c is not None and c.your_transcribed == 0
            self.table.setRowHidden(r, hide)
            shown += not hide
        if self.table.isRowHidden(self.table.currentRow()):
            self.table.clearSelection()
            self.table.setCurrentCell(-1, -1)
        self.clear_filter.setVisible(on)
        self.filter_note.setText(f"Showing {shown} of {len(self.runs)} runs" if on else "")

    def _save_settings(self) -> None:
        """Saves a choice of what is shown; a failure is let go (only that choice would be lost)."""
        try:
            self.s.save()
        except OSError:
            pass

    # ------------------------------------------------------------------ changing
    def _day_runs(self, day: Day) -> list[Run]:
        """The runs of one day, in order."""
        return [r for r in self.runs if r.day is day]

    def _keep(self, day: Day, runs: list[Run]) -> None:
        """A day's new runs: kept on its job, shown, and passed on to the main window."""
        store(day, runs, self.firms, self.s)
        self._pin()
        i = next(k for k, r in enumerate(self.runs) if r.day is day)
        self.runs = [r for r in self.runs if r.day is not day]
        self.runs[i:i] = runs
        self.problem.setText("")
        self._show()
        self.changed()

    def _pin(self) -> None:
        """The table says who ordered each day: a firm ticked on some of its days only orders those, and isn't
        spread to the others (batch.pin_orders; a tick in Who ordered is the whole trial). The trial's days not
        shown (the window shows one invoice's) are pinned too: a firm ordering pages of a day shown, and no
        other day, orders those pages only."""
        jobs = [d.job for d in self.days]
        pin_orders(self.trial(jobs) if self.trial is not None else jobs, self.firms)

    def _item_changed(self, it: QTableWidgetItem) -> None:
        """A run typed, or a firm ticked or unticked."""
        if self._loading:
            return
        r, c = it.row(), it.column()
        if not 0 <= r < len(self.runs):
            return
        run = self.runs[r]
        text, on = it.text(), it.checkState() == Qt.Checked
        key = self.firms[c - FIRST_FIRM].key() if FIRST_FIRM <= c < FIRST_FIRM + len(self.firms) else None
        if self._pending is not None:
            # The main window changed the days while this was typed: the change goes to the runs as they are
            # now (the table is shown again first), not to the old ones, which would undo the main window's.
            job, start, end = run.day.job, run.start, run.end
            self._fill(self._pending)
            run = next((x for x in self.runs if x.day.job is job and (x.start, x.end) == (start, end)), None)
            if run is None or (c != PAGES and key not in {a.key() for a in self.firms}):
                self.problem.setText("The table changed while you typed: please do it again.")
                return
        day = run.day
        runs = self._day_runs(day)
        i = runs.index(run)
        if c == PAGES:
            try:
                a, b = day.parse(text)
                runs = carve(runs, i, a, b)
            except ValueError as e:
                self.problem.setText(f"⚠ {e}")
                self._show()  # back to the run as it was
                return
            self._keep(day, runs)
        elif key is not None:
            keys = set(run.keys) - {key} | ({key} if on else set())
            run.keys = [a.key() for a in self.firms if a.key() in keys]
            self._keep(day, runs)

    def _chosen(self) -> Run | None:
        """The run of the row chosen; None, after asking for one, when no row is (or it is hidden: _apply_filter)."""
        r = self.table.currentRow()
        if not 0 <= r < len(self.runs) or self.table.isRowHidden(r):
            self.problem.setText("Choose a run in the table first.")
            return None
        return self.runs[r]

    def _select(self, job, page: int) -> None:
        """Chooses the row of the run that holds a page of a day (its job; the table may have been read afresh
        since, with new days and runs)."""
        row = next((k for k, r in enumerate(self.runs) if r.day.job is job and r.start <= page <= r.end), None)
        if row is not None and not self.table.isRowHidden(row):
            self.table.selectRow(row)

    def _split(self) -> None:
        """Split run…: asks after which page to cut the run chosen, starting from its middle, and it becomes two
        there ("1-20" cut after 12: "1-12", "13-20"), both with its firms. The table can be read afresh while it
        asks: the same run is found again, or, when it is gone, it says so."""
        run = self._chosen()
        if run is None:
            return
        if not run.day.splittable:
            self.problem.setText("This job covers several days: it is ordered whole.")
            return
        if run.end == run.start:
            self.problem.setText("This run can't be cut in two.")
            return
        job, start, end = run.day.job, run.start, run.end
        span, mid = run.day.span(start, end), (start + end) // 2
        text, ok = QInputDialog.getText(self, "Split run", f"Cut the run {span} after which page number?",
                                        QLineEdit.Normal, run.day.span(mid, mid))
        if not ok:
            return
        run = next((r for r in self.runs if r.day.job is job and (r.start, r.end) == (start, end)), None)
        if run is None:
            self.problem.setText("The table changed meanwhile: please choose the run again.")
            return
        try:
            cut = run.day.parse(text)[1]
        except ValueError as e:
            self.problem.setText(f"⚠ {e}")
            return
        if not start <= cut < end:
            self.problem.setText(f"⚠ To cut the run {span}, type a page number in it, before its last page.")
            return
        runs = self._day_runs(run.day)
        self._keep(run.day, carve(runs, runs.index(run), start, cut))

    def _remove(self) -> None:
        """Remove run (or Delete): the run chosen goes, its pages to the run above it (excerpts.remove: the run
        below for a day's first run), and the row now holding its first page is chosen. Nothing while a cell
        is being typed in (Delete there deletes the text)."""
        if self.table.state() == QAbstractItemView.EditingState:
            return
        run = self._chosen()
        if run is None:
            return
        day = run.day
        if not day.splittable:
            self.problem.setText("This job covers several days: it is ordered whole.")
            return
        runs = self._day_runs(day)
        try:
            runs = remove(runs, runs.index(run))
        except ValueError as e:  # (the day's only run)
            self.problem.setText(str(e))
            return
        job, page = day.job, run.start
        self._keep(day, runs)
        self._select(job, page)
        if not any(r.keys for r in runs):
            self.problem.setText("Nobody orders this day now: tick a firm.")

    def _whole_day(self) -> None:
        """Make this day whole: the day of the run chosen becomes one run of all its pages, ordered by
        every firm that ordered any of its runs, or by the firms ticked on its job when none did
        (excerpts.whole_day)."""
        run = self._chosen()
        if run is None:
            return
        day = run.day
        self._keep(day, whole_day(day, self._day_runs(day), day.job.ticked_keys(), self.firms))
        self._select(day.job, 1)

    def _remove_all(self) -> None:
        """Make every day whole, after asking: every day of the case with excerpts (Job.portions) becomes one
        run of all its pages, ordered by every firm that ordered any of it (excerpts.whole_day). The days are
        kept, then the table shown and the main window told once."""
        days = [d for d in self.days if d.splittable and d.job.portions is not None]
        if not days:
            self.problem.setText("Every day is whole already: each is one run.")
            return
        if QMessageBox.question(self, "Make every day whole", "Every day of the case becomes one run, ordered by "
                                "every firm that ordered any of it. Make every day whole?") != QMessageBox.Yes:
            return
        # Looked up again: a read or an AI answer that ended while the question was open shows the days afresh
        # (new Day objects), and the days found above would match none of them
        days = [d for d in self.days if d.splittable and d.job.portions is not None]
        if not days:
            self.problem.setText("The table changed meanwhile: every day is whole already.")
            return
        r = self.table.currentRow()
        shown = 0 <= r < len(self.runs) and not self.table.isRowHidden(r)
        chosen = (self.runs[r].day.job, self.runs[r].start) if shown else None
        change = {id(d) for d in days}
        runs = []
        for day in self.days:
            own = self._day_runs(day)
            if id(day) in change:
                own = whole_day(day, own, day.job.ticked_keys(), self.firms)
                store(day, own, self.firms, self.s)
            runs += own
        self._pin()
        self.runs = runs
        self.problem.setText("")
        self._show()
        self.changed()
        if chosen is not None:
            self._select(*chosen)

    def _run_menu(self, run: Run, key: str | None = None) -> tuple[QMenu, list]:
        """The right-click menu of a run, and the slot of each of its actions (by the action's data): Split run…
        (not for a run that can't be cut), Remove run (not for a day's only run), Make this day whole and
        Make every day whole; on the cell of a firm that ordered the run (key), "<firm> on this run at…" with the
        rate sheet's speeds (the run's own ticked), and "<firm>: same as its other pages" when the run's speed
        isn't the day's and the day has other runs."""
        menu = QMenu(self)
        slots = []
        for text, slot, on in (("Split run…", self._split, run.day.splittable and run.end > run.start),
                               ("Remove run", self._remove, len(self._day_runs(run.day)) > 1),
                               ("Make this day whole", self._whole_day, True),
                               ("Make every day whole", self._remove_all, True)):
            act = menu.addAction(text)
            act.setEnabled(on)
            act.setData(len(slots))
            slots.append(slot)
        if key is not None and key in run.keys:
            name = next((a.label() for a in self.firms if a.key() == key), key)
            menu.addSeparator()
            sub = menu.addMenu(f"{name} on this run at…")
            for sp in self.s.sheet().speeds:
                act = sub.addAction(sp.name)
                act.setCheckable(True)
                act.setChecked(bool(run.speed(key)) and speed_key(run.speed(key)) == sp.key)  # ("Expedited")
                act.setData(len(slots))
                slots.append(lambda k=key, name=sp.name: self._set_run_speed(k, name))
            day_speed = run.day.job.speeds.get(key, "")
            if run.speed(key) != day_speed and len(self._day_runs(run.day)) > 1:
                act = menu.addAction(f"{name}: same as its other pages" + (f" ({day_speed})" if day_speed else ""))
                act.setData(len(slots))
                slots.append(lambda k=key: self._set_run_speed(k, None))
        return menu, slots

    def _set_run_speed(self, key: str, speed: str | None) -> None:
        """The speed firm `key` ordered the run chosen at (None: the same as its other pages of the day, Job.speeds),
        kept on its day (excerpts.store keeps a run's own speed only where it differs)."""
        run = self._chosen()
        if run is None or key not in run.keys:
            return
        day = run.day
        runs = self._day_runs(day)
        if speed is None:
            if day.job.speeds.get(key):
                run.speeds[key] = day.job.speeds[key]
            else:
                run.speeds.pop(key, None)
        else:
            run.speeds[key] = speed
        self._keep(day, runs)
        self._select(day.job, run.start)

    def _context_menu(self, pos) -> None:
        """A right-click on a run: its row is chosen, then its menu (_run_menu) shown, with the speeds of the firm
        whose cell was clicked. The table can be read afresh while the menu is open (the main window changed the
        days): what is picked acts on the same run found again, or, when it is gone, says so."""
        row = self.table.rowAt(pos.y())
        if not 0 <= row < len(self.runs):
            return
        self.table.selectRow(row)
        run = self.runs[row]
        col = self.table.columnAt(pos.x())  # (a firm's cell: its speed on this run too)
        key = self.firms[col - FIRST_FIRM].key() if FIRST_FIRM <= col < FIRST_FIRM + len(self.firms) else None
        menu, slots = self._run_menu(run, key)
        act = menu.exec(self.table.viewport().mapToGlobal(pos))
        if act is None or not act.isEnabled():
            return
        job, start, end = run.day.job, run.start, run.end
        row = next((k for k, r in enumerate(self.runs) if r.day.job is job and (r.start, r.end) == (start, end)),
                   None)
        if row is None:
            self.problem.setText("The table changed meanwhile: please choose the run again.")
            return
        self.table.selectRow(row)
        slots[act.data()]()
