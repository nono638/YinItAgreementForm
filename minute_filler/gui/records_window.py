"""The Records window: the invoice ledger (totals, filters, mark paid, amounts corrected after the PDF was
changed) and the history of everything made. Each table has many columns (INVOICE_COLS, ACTIVITY_COLS); the
user picks which are shown (Columns..., or a right-click on the headings), and the choice is kept in
Settings.records_columns. Records can be deleted to the trash (restored for 30 days; the files are not
touched); the Trash button shows what is in it. An invoice made in another reporter's name (Whose pages...,
numbered apart: "DS-2026-0001") is theirs: it is always left out of the totals and the summary, and listed (its
file in Everything made too) only after "Show them" on the line that says how many the filters match. Each time
Records is opened they are hidden again (MainWindow.open_records).

An invoice's tick boxes (Settings -> Records; see tracking.py): Paid, and those switched on there (Invoice sent,
Transcribed, Transcript sent, the user's own), each a column after Paid. The Status column says each box, ticked
or not ("Paid, Transcribed, Not sent"), and each row is coloured by the first colour rule that matches it (a
see-through tint, read on the light and the dark theme). Ticking Transcribed ticks it on the other invoices of
the transcript; several invoices selected are ticked at once from the right-click menu. Notes are typed into
their column (double-click or F2).

Along the bottom: the exports, Summary... (a month or a year summed up, SummaryDialog), Backups... (the daily
copies of the records, BackupsDialog) and Undo (Ctrl+Z: the last change made here - paid, a box ticked, void,
amounts, notes, a delete - is taken back). A right-click also prints a record's file and opens its job again in
the main window (RecordsWindow.on_reopen). A delete, a restore, an undo or a backup put back is told to the main
window (RecordsWindow.on_changed), which reads again how each trial was first billed (an invoice in the trash no
longer counts)."""
from __future__ import annotations

import calendar
import html
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QTabWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from ..deliver import backup_folder, ledger_for
from ..pdfout import safe_filename
from ..invoice_calc import fmt, money
from ..log import error as log_error
from ..rates import parse_amount
from ..records import (BACKUPS_KEPT, FORCED_KEPT, KINDS, PERIODS, TRASH_DAYS, Activity, Invoice, _month_name, backup_counts,
                       backup_day, backups, gone_for_good, period, period_stats, stats_rows, summarize, us_date)
from ..settings import Settings
from ..tracking import (PAID, TICK, ColourRule, Transcripts, TrackBox, carried, rule_for, rule_names,
                        status_words)
from .widgets import open_path, plural, refill_combo, show_save_error
from .zoom import z

SUM_COLS = ["", "Invoices", "Billed", "Paid", "Outstanding"]
# The Status filter's fixed choices (Ledger.invoices' status); the names of the colour rules come after All
STATUS_FILTERS = [("All", ""), ("Not paid", "open"), ("Paid", "paid"), ("Void", "void")]
RULE = "rule:"  # the Status filter's data for a colour rule: "rule:Ready to send"
SEARCH_TIP = ("Words found anywhere in a record, in any order: a firm, an attorney, a case,\n"
              "an index number (712345/2021 or 712345-2021), an invoice number, a judge…")
# the Status column's text, without row colours (Settings -> Records): readable on light and dark
STATUS_COLORS = {"open": "#d97706", "paid": "#16a34a", "void": "#8a8797"}
TINT = 80  # how opaque a row's colour is (of 255): see-through, so it reads on the light and the dark theme
UNDO_MAX = 30  # changes Undo can take back, the latest first
BOX = "box:"  # a tick box's column key: "box:transcribed"


@dataclass(frozen=True)
class Col:
    """A column of a Records table: its key (kept in Settings.records_columns), heading, the value shown for a
    record, whether it is shown until the user chooses, how it sorts ("text", "num", "money" or "date") and,
    for "date", the ISO date it sorts by. trash: shown only while the trash is."""
    key: str
    head: str
    get: Callable
    shown: bool = False
    kind: str = "text"
    sort: Callable | None = None
    trash: bool = False


def _ordered(i: Invoice) -> str:
    """The speed ordered: the one paid for, or the only one offered; "" while the attorney hasn't chosen."""
    return i.paid_speed if i.status == "paid" and i.paid_speed else next(iter(i.amounts)) if len(i.amounts) == 1 else ""


def _bill_to(i: Invoice) -> str:
    """'Counsel & Counsel (Alex B. Counsel)', or whichever of the two there is."""
    return i.client if not i.firm else f"{i.firm} ({i.bill_to})" if i.bill_to else i.firm


INVOICE_COLS = [
    Col("paid", "Paid", lambda i: "", True),
    Col("no", "No.", lambda i: i.invoice_no, True),
    Col("date", "Date", lambda i: us_date(i.created), True, "date", lambda i: i.created),
    Col("case", "Case", lambda i: i.case_name, True),
    Col("index_no", "Index No.", lambda i: i.index_no),
    Col("court", "Court", lambda i: i.court),
    Col("part", "Part", lambda i: i.part),
    Col("judge", "Judge", lambda i: i.judge),
    Col("dates", "Date(s) of proceeding", lambda i: i.dates),
    Col("bill_to", "Bill to", _bill_to, True),
    Col("firm", "Firm", lambda i: i.firm),
    Col("email", "E-mail", lambda i: i.email),
    Col("pages", "Pages billed", lambda i: i.pages, True, "num"),
    Col("my_pages", "My pages", lambda i: i.my_pages or "", True, "num"),
    Col("transcript_pages", "Transcript pages", lambda i: i.transcript_pages or "", True, "num"),
    Col("reporters", "Reporters", lambda i: i.reporters),
    # made in another reporter's name (Whose pages...): theirs, so left out of the totals and By firm / By month
    Col("for_reporter", "For reporter", lambda i: i.reporter.upper(), True),
    Col("excerpt", "Excerpt", lambda i: i.excerpt or ("Whole" if i.transcript_pages else ""), True),
    Col("parties", "Parties", lambda i: i.parties, False, "num"),
    Col("speeds", "Speeds offered", lambda i: ", ".join(i.amounts), True),
    Col("offered", "Offered (each party)", Invoice.offered_text),
    Col("email_copy", "E-mailed copy", lambda i: i.email_copy),
    Col("index", "Index", lambda i: i.index),
    Col("billed", "Billed", lambda i: i.billed, True, "money"),
    Col("status", "Status", lambda i: "", True),  # (its words: tracking.status_words, see show_invoices)
    Col("ordered", "Speed ordered", _ordered, True),
    Col("amount_paid", "Amount paid", lambda i: i.paid if i.status == "paid" else "", False, "money"),
    Col("paid_date", "Date paid", lambda i: us_date(i.paid_date), True, "date", lambda i: i.paid_date),
    Col("notes", "Notes", lambda i: i.notes, True),  # (typed into: see _item_changed)
    Col("file", "File", lambda i: i.file_path),
    Col("deleted", "Deleted on", lambda i: us_date(i.deleted[:10]), True, "date", lambda i: i.deleted, True),
    Col("gone", "Gone for good on", lambda i: gone_for_good(i.deleted), True, "date", lambda i: i.deleted, True),
]
ACTIVITY_COLS = [
    Col("date", "Date", lambda a: us_date(a.ts), True, "date", lambda a: a.ts),
    Col("time", "Time", lambda a: a.ts[11:16], True),
    Col("made", "Made", lambda a: KINDS.get(a.kind, a.kind), True),
    Col("case", "Case", lambda a: a.case_name, True),
    Col("index_no", "Index No.", lambda a: a.index_no, True),
    Col("dates", "Date(s) of proceeding", lambda a: a.dates),
    Col("judge", "Judge", lambda a: a.judge),
    Col("part", "Part", lambda a: a.part),
    Col("attorney", "Attorney", lambda a: a.attorney, True),
    Col("firm", "Firm", lambda a: a.firm, True),
    Col("pages", "Pages", lambda a: a.pages or "", True, "num"),
    Col("my_pages", "My pages", lambda a: a.my_pages or "", True, "num"),
    Col("transcript_pages", "Transcript pages", lambda a: a.transcript_pages or "", True, "num"),
    Col("invoice_no", "Invoice No.", lambda a: a.invoice_no, True),
    Col("file", "File", lambda a: a.file_path, True),
    Col("deleted", "Deleted on", lambda a: us_date(a.deleted[:10]), True, "date", lambda a: a.deleted, True),
    Col("gone", "Gone for good on", lambda a: gone_for_good(a.deleted), True, "date", lambda a: a.deleted, True),
]
TABLES = {"invoices": INVOICE_COLS, "activity": ACTIVITY_COLS}


def col_index(cols: list[Col], key: str) -> int:
    """The position of a column by its key (the tests and the window find columns this way, not by number)."""
    return next(i for i, c in enumerate(cols) if c.key == key)


class _Item(QTableWidgetItem):
    """A cell that sorts by the value kept under UserRole + 1 (a number, or an ISO date) when there is one, else by
    its text, whatever the capitals."""

    def __lt__(self, other):
        a, b = self.data(Qt.UserRole + 1), other.data(Qt.UserRole + 1)
        if a is not None and b is not None:
            try:
                return a < b
            except TypeError:
                pass
        # (not super().__lt__: PySide6 sends that back to this override, which recursed until the app crashed on
        # a click on a text column's heading)
        return self.text().casefold() < other.text().casefold()


# A cell's flags but Editable (a QTableWidgetItem's own, less that one): worked out once, as a table of thousands
# of invoices has a hundred thousand cells and these sums are slow in Python
_READ_ONLY = (Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled
              | Qt.ItemIsDropEnabled)
_GREYED = _READ_ONLY & ~Qt.ItemIsEnabled  # (a tick box that can't be ticked: a void invoice's, the trash's)


class _LinkLine(QLabel):
    """A line of text with a link in it (Not listed: … Show them): Tab goes straight to the link, as to a button.
    A QLabel whose links take the keyboard stops on itself first, where Enter does nothing."""

    def focusInEvent(self, e):
        super().focusInEvent(e)
        if e.reason() in (Qt.TabFocusReason, Qt.BacktabFocusReason):
            self.focusNextPrevChild(e.reason() == Qt.TabFocusReason)


def _item(text, align_right: bool = False, data=None, sort=None) -> QTableWidgetItem:
    """A read-only table cell showing text (None shows as blank). data, when given, is kept under UserRole;
    sort (a number or an ISO date) under UserRole + 1, to sort by."""
    it = _Item("" if text is None else str(text))
    it.setFlags(_READ_ONLY)
    if align_right:
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if data is not None:
        it.setData(Qt.UserRole, data)
    if sort is not None:
        it.setData(Qt.UserRole + 1, sort)
    return it


def _money_item(d) -> QTableWidgetItem:
    """A right-aligned cell showing an amount as "$1,234.50", with the plain number kept under UserRole + 1."""
    return _item(fmt(d), True, sort=float(d))


def _cell(col: Col, record) -> QTableWidgetItem:
    """The cell of one column for one record, sorting as the column says."""
    value = col.get(record)
    if col.kind == "money":
        return _money_item(value) if value != "" else _item("", True, sort=-1.0)
    if col.kind == "num":
        return _item(value, True, sort=float(value) if value != "" else -1.0)
    if col.kind == "date":
        return _item(value, sort=(col.sort(record) if col.sort else "") or "")
    return _item(value)


def _table(cols: list[str]) -> QTableWidget:
    """An empty table with these column headings: whole-row selection (several rows with Ctrl or Shift),
    striped rows, no row numbers, sorted by clicking a heading (not sorted until then)."""
    t = QTableWidget(0, len(cols))
    t.setHorizontalHeaderLabels(cols)
    t.verticalHeader().setVisible(False)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.ExtendedSelection)
    t.setAlternatingRowColors(True)
    t.setWordWrap(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    t.horizontalHeader().setStretchLastSection(True)
    t.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
    return t


class PaidDialog(QDialog):
    """Asks which speed was paid for, how much and when. The amount starts at the price of the chosen speed. OK
    is refused while the amount is blank or not a number (as in AmountsDialog)."""

    def __init__(self, inv: Invoice, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Invoice {inv.invoice_no} paid")
        self.inv = inv
        f = QFormLayout(self)
        f.addRow(QLabel(f"<b>{html.escape(inv.case_name or inv.invoice_no)}</b><br>{html.escape(inv.client)}"))
        self.speed = QComboBox()
        for sp, amt in inv.amounts.items():
            self.speed.addItem(f"{sp}  —  {fmt(money(amt))}", sp)
        self.speed.setCurrentIndex(max(0, self.speed.findData(inv.billed_speed)))
        self.amount = QLineEdit()
        self.amount.setPlaceholderText("0.00")
        self.speed.currentIndexChanged.connect(self._speed_changed)
        self.when = QDateEdit(QDate.currentDate())
        self.when.setCalendarPopup(True)
        self.when.setDisplayFormat("M/d/yyyy")
        f.addRow("Paid for:", self.speed)
        f.addRow("Amount received:", self.amount)
        f.addRow("Date paid:", self.when)
        self.error = QLabel("")
        self.error.setObjectName("problem")
        self.error.setWordWrap(True)
        self.error.setVisible(False)
        f.addRow(self.error)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
        self._speed_changed()

    def accept(self):
        """Closes with OK only when the amount received is an amount (see rates.parse_amount): else "sixty
        three" or "-5" would be recorded as paid ($0.00, or a payment taken back)."""
        why = "" if parse_amount(self.amount.text()) is not None else "Type the amount received, such as 63.00."
        self.error.setText(why)
        self.error.setVisible(bool(why))
        if not why:
            super().accept()

    def _speed_changed(self, _=None):
        """Puts the chosen speed's price in the amount box."""
        self.amount.setText(str(money(self.inv.amounts.get(self.speed.currentData(), "0"))))

    def values(self) -> tuple[str, str, str]:
        """(speed, amount, date paid), e.g. ("Expedite", "125.00", "2026-09-30"), as Ledger.mark_paid takes them."""
        d = self.when.date()
        amount = parse_amount(self.amount.text())
        return self.speed.currentData() or "", str(amount if amount is not None else money(self.amount.text())), \
            date(d.year(), d.month(), d.day()).isoformat()


class AmountsDialog(QDialog):
    """Change amounts…: a money box per speed of the invoice, starting at what the records have. OK is
    refused while a box is blank or not a number."""

    def __init__(self, inv: Invoice, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Invoice {inv.invoice_no}: amounts")
        f = QFormLayout(self)
        f.addRow(QLabel(f"<b>{html.escape(inv.case_name or inv.invoice_no)}</b><br>{html.escape(inv.client)}"))
        note = QLabel("Change these when you corrected an amount in the invoice PDF.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        f.addRow(note)
        self.boxes: dict[str, QLineEdit] = {}
        for sp, amt in inv.amounts.items():
            box = QLineEdit(str(money(amt)))
            box.setPlaceholderText("0.00")
            self.boxes[sp] = box
            f.addRow(f"{sp}:", box)
        self.error = QLabel("")
        self.error.setObjectName("problem")
        self.error.setWordWrap(True)
        self.error.setVisible(False)
        f.addRow(self.error)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def problem(self) -> str:
        """What is wrong with the amounts typed ("" when nothing is): each must be an amount and nothing else
        (see rates.parse_amount)."""
        bad = [sp for sp, box in self.boxes.items() if parse_amount(box.text()) is None]
        return f"Type an amount for {', '.join(bad)}, such as 63.00 or $1,250.00." if bad else ""

    def accept(self):
        """Closes with OK only when every box holds an amount; otherwise says which one doesn't."""
        why = self.problem()
        self.error.setText(why)
        self.error.setVisible(bool(why))
        if not why:
            super().accept()

    def values(self) -> dict[str, str]:
        """{speed: "63.00"}, as Ledger.set_amounts takes them."""
        return {sp: str(parse_amount(box.text()) or money(box.text())) for sp, box in self.boxes.items()}


class SummaryDialog(QDialog):
    """Summary...: a period summed up (invoices, pages, billed, paid, owed, payments received, the firms billed
    most), for this or last month, this or last year, or all time. Copy puts it on the clipboard as text.
    Invoices made in another reporter's name are left out (records.period_stats)."""

    def __init__(self, invoices: list[Invoice], parent=None, today: date | None = None):
        """invoices: every invoice not in the trash; today: the day the periods are counted from."""
        super().__init__(parent)
        self.invoices, self.today = invoices, today or date.today()
        self.setWindowTitle("Summary")
        self.resize(z(520), z(560))
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("Period:"))
        self.period = QComboBox()
        self.period.addItems(PERIODS)
        self.period.setCurrentText("This year")
        self.period.currentIndexChanged.connect(self.show_period)
        row.addWidget(self.period)
        row.addStretch(1)
        lay.addLayout(row)
        self.text = QTextBrowser()
        lay.addWidget(self.text, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        copy = bb.addButton("Copy", QDialogButtonBox.ActionRole)
        copy.clicked.connect(self._copy)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.plain = ""
        self.show_period()

    def show_period(self, _=None) -> None:
        """Sums up the period chosen and shows it."""
        since, until, title = period(self.period.currentText(), self.today)
        st = period_stats(self.invoices, since, until)
        rows = stats_rows(st)
        firms = [(name, f"{fmt(sm.billed)} ({plural(sm.count, 'invoice')})") for name, sm in st.firms[:5]]
        e = html.escape
        table = "".join(f"<tr><td style='padding:3px 18px 3px 0'>{e(k)}</td><td align='right'><b>{e(v)}</b></td></tr>"
                        for k, v in rows)
        top = "".join(f"<tr><td style='padding:3px 18px 3px 0'>{e(k)}</td><td align='right'>{e(v)}</td></tr>"
                      for k, v in firms)
        self.text.setHtml(f"<h3>{e(title)}</h3><table>{table}</table>"
                          + (f"<h4>Billed most</h4><table>{top}</table>" if firms else "")
                          + ("" if st.invoices else "<p>No invoices were made in this period.</p>"))
        self.plain = "\n".join([title] + [f"{k}: {v}" for k, v in rows]
                               + (["", "Billed most:"] + [f"{k}: {v}" for k, v in firms] if firms else []))

    def _copy(self) -> None:
        """Copy: the period shown, as plain text on the clipboard."""
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.plain)


class BackupsDialog(QDialog):
    """Backups...: the copies of the records the app makes (one a day when it starts, the last BACKUPS_KEPT
    days are kept). Back up now makes one more; Restore puts the records back as they were in the copy chosen
    (the records as they are now are copied first, so that can be taken back too). `restored` is True
    afterwards. busy, when given, says whether files are being made right now (Generate all): no copy is put
    back then, as the invoices being made would leave the records."""

    def __init__(self, s: Settings, ledger, parent=None, busy: Callable[[], bool] | None = None):
        super().__init__(parent)
        self.s, self.ledger, self.restored, self.busy = s, ledger, False, busy
        self.folder = backup_folder(s)
        self.setWindowTitle("Backups of the records")
        self.resize(z(560), z(420))
        lay = QVBoxLayout(self)
        note = QLabel(f"A copy of your records is made each day you open the app; the last {BACKUPS_KEPT} days' "
                      f"are kept (and the last {FORCED_KEPT} made with Back up now or before a restore), "
                      f"in\n{self.folder}\nYour PDF files are not in them: only the records (invoices, paid or "
                      "not, and the list of everything made).")
        note.setObjectName("muted")
        note.setWordWrap(True)
        lay.addWidget(note)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _: self.restore())
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.restore_btn = QPushButton("Restore this copy…")
        self.restore_btn.clicked.connect(lambda: self.restore())  # (not the button's "checked" as `ask`)
        now = QPushButton("Back up now")
        now.clicked.connect(self.backup_now)
        folder = QPushButton("Open folder")
        folder.clicked.connect(lambda: (self.folder.mkdir(parents=True, exist_ok=True), open_path(self.folder)))
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        for b in (self.restore_btn, now, folder):
            b.setAutoDefault(False)
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)
        self.refill()

    def refill(self) -> None:
        """Lists the copies in the folder, newest first, with what each holds."""
        self.list.clear()
        for p in backups(self.folder):
            counts = backup_counts(p)
            what = f"{plural(counts[0], 'invoice')}, {plural(counts[1], 'file')} made" if counts else "can't be read"
            item = QListWidgetItem(f"{backup_day(p)}   ·   {what}")
            item.setData(Qt.UserRole, str(p))
            if counts is None:
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        self.restore_btn.setEnabled(self.list.count() > 0)

    def backup_now(self) -> None:
        """Makes a copy now, whatever today's holds."""
        try:
            made = self.ledger.backup(self.folder, force=True)
        except Exception as e:
            show_save_error(self, e, "Could not back up the records")
            return
        if made is None:
            QMessageBox.information(self, "Nothing to back up", "There are no records yet.")
        self.refill()

    def restore(self, ask: bool = True) -> None:
        """Puts the records back as they were in the copy chosen, after asking (unless ask is False). Refused
        while files are being made (see busy)."""
        item = self.list.currentItem()
        if item is None:
            return
        copy = Path(item.data(Qt.UserRole))
        if self.busy is not None and self.busy():
            QMessageBox.information(self, "Restore", "Files are being made right now (Generate all). Restore a "
                                    "copy once that is done.")
            return
        if ask and QMessageBox.question(
                self, "Restore", f"Put the records back as they were on {backup_day(copy)}?\n\nInvoices made and "
                "payments entered since then leave the records (the PDF files stay where they are). The records "
                "as they are now are backed up first, so you can come back to them.") != QMessageBox.Yes:
            return
        try:
            self.ledger.restore_backup(copy, self.folder)
        except Exception as e:
            log_error("could not restore a backup of the records", e)
            QMessageBox.warning(self, "Could not restore", f"{type(e).__name__}: {e}")
            return
        self.restored = True
        self.refill()


class RecordsWindow(QDialog):
    """The Records window. Two tabs: Invoices (filters, totals, paid ticks, by-firm and by-month sums) and
    Everything made (each file the app made). Each has the Columns... choice and the Trash. The window does not
    load anything until reload() is called."""

    def __init__(self, s: Settings, parent=None):
        super().__init__(parent)
        self.s = s
        self.ledger = ledger_for(s)
        self.shown: list[Invoice] = []
        self.act_shown: dict[int, Activity] = {}  # the rows of everything made shown, by id
        self.on_reopen: Callable[[str], bool] | None = None  # opens a job again in the main window (set by it)
        self.on_settings: Callable[[str], None] | None = None  # opens Settings at a tab ("Records"; set by it)
        # tells the main window the records were changed here (a delete, a restore, an undo, a backup put back):
        # what it read from them (the way each trial was first billed) is read again (set by it)
        self.on_changed: Callable[[], None] | None = None
        self.undo_stack: list[tuple[str, Callable]] = []  # (what was done, how to take it back), latest last
        self.boxes: list[TrackBox] = s.boxes()   # the tick boxes and row colours, as Settings were at the last
        self.rules: list[ColourRule] = s.rules()  # reload()
        self.inv_cols: list[Col] = self._invoice_cols()  # the Invoices table's columns, the tick boxes' too
        self._stale = False  # the table wasn't shown afresh while a note was being typed: it is when that ends
        self.theirs = False  # the invoices made in a colleague's name are listed too (show_theirs)
        self.setWindowTitle("Records")
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.resize(z(1180), z(760))
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self.tabs.addTab(self._build_invoices(), "Invoices")
        self.tabs.addTab(self._build_activity(), "Everything made")

        bottom = QHBoxLayout()
        for label, slot, tip in (
                ("Report (HTML)…", self.export_html, "A report of the invoices shown, opened in your browser"),
                ("Excel…", self.export_xlsx, "Invoices, everything made, and totals by firm and month"),
                ("CSV…", self.export_csv, "invoices.csv and activity.csv"),
                ("Open records folder", self.open_folder, "Where the CSV copies are kept up to date")):
            b = QPushButton(label)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            bottom.addWidget(b)
        bottom.addSpacing(z(14))
        for label, slot, tip in (
                ("Summary…", self.show_summary, "A month or a year summed up: invoices, pages, billed, paid, owed"),
                ("Backups…", self.show_backups, "The daily copies of your records, to go back to one")):
            b = QPushButton(label)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            bottom.addWidget(b)
        self.undo_btn = QPushButton("Undo")
        self.undo_btn.clicked.connect(self.undo)
        bottom.addWidget(self.undo_btn)
        QShortcut(QKeySequence.Undo, self, activated=self._undo_key)
        self.setProperty("help_topic", "rec-overview")
        QShortcut(QKeySequence("F1"), self, activated=self.show_help)
        self._show_undo()
        bottom.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        bottom.addWidget(close)
        root.addLayout(bottom)
        # In a dialog every button presses on Enter by default: Enter in a search box opened the Columns menu
        for b in self.findChildren(QPushButton):
            b.setAutoDefault(False)
            b.setDefault(False)
        self.apply_columns("invoices")
        self.apply_columns("activity")

    # ------------------------------------------------------------ building
    def _filters(self, lay: QHBoxLayout, with_client: bool) -> tuple[QComboBox, QComboBox, QComboBox | None]:
        """Adds Year and Month boxes (and a Firm box when with_client) to lay. The year and firm lists stay
        empty until reload() fills them from the records."""
        year, month = QComboBox(), QComboBox()
        month.addItem("All months", 0)
        for m in range(1, 13):
            month.addItem(calendar.month_name[m], m)
        lay.addWidget(QLabel("Year:"))
        lay.addWidget(year)
        lay.addWidget(QLabel("Month:"))
        lay.addWidget(month)
        client = None
        if with_client:
            client = QComboBox()
            client.setMinimumWidth(z(220))
            lay.addWidget(QLabel("Firm:"))
            lay.addWidget(client)
        return year, month, client

    def _search(self, lay: QHBoxLayout, placeholder: str, on_change) -> tuple[QLineEdit, QCheckBox, QCheckBox]:
        """Adds a search box with its Regex and Fuzzy boxes (both unticked: plain words) to a filter row;
        on_change runs when any of them changes. The two boxes exclude each other."""
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        edit.setClearButtonEnabled(True)
        edit.setToolTip(SEARCH_TIP)
        lay.addWidget(edit, 1)
        regex, fuzzy = QCheckBox("Regex"), QCheckBox("Fuzzy")
        regex.setToolTip("Search with a regular expression, e.g.  ^Smith  or  2026-00(1|2)  (any case)")
        fuzzy.setToolTip("Also find near misses and misspellings: \"Counsle\" finds \"Counsel & Counsel\"")
        for box, other in ((regex, fuzzy), (fuzzy, regex)):
            box.toggled.connect(lambda on, o=other: o.setChecked(False) if on else None)
            box.toggled.connect(on_change)
            lay.addWidget(box)
        edit.textChanged.connect(on_change)
        return edit, regex, fuzzy

    @staticmethod
    def _how(regex: QCheckBox, fuzzy: QCheckBox) -> str:
        """The search mode the boxes ask for: "regex", "fuzzy" or plain "words" (see records.matcher)."""
        return "regex" if regex.isChecked() else "fuzzy" if fuzzy.isChecked() else "words"

    @staticmethod
    def _search_problem(edit: QLineEdit, problem: str) -> None:
        """Marks a search box whose regular expression can't be read (amber, with the reason as its tooltip)."""
        from .widgets import repolish
        edit.setProperty("review", bool(problem))
        edit.setToolTip(problem or SEARCH_TIP)
        repolish(edit)

    def _table_buttons(self, lay: QHBoxLayout, which: str) -> QPushButton:
        """Adds Columns… and the Trash toggle to a filter row; returns the Trash button."""
        cols = QPushButton("Columns…")
        cols.setToolTip("Choose the columns shown (also: right-click a column heading)")
        cols.clicked.connect(lambda: self._columns_menu(which, cols.mapToGlobal(cols.rect().bottomLeft())))
        lay.addWidget(cols)
        trash = QPushButton("🗑 Trash")
        trash.setCheckable(True)
        trash.setToolTip(f"Show what was deleted: it can be restored for {TRASH_DAYS} days, then it is gone for good")
        lay.addWidget(trash)
        return trash

    def _theirs_line(self) -> QLabel:
        """A line under a tab's filters for the invoices made in a colleague's name that they match, with the
        link that shows or hides them (see _say_theirs); hidden while there are none."""
        line = _LinkLine()
        line.setObjectName("muted")
        line.setWordWrap(True)
        line.setTextFormat(Qt.RichText)
        line.setTextInteractionFlags(Qt.LinksAccessibleByMouse | Qt.LinksAccessibleByKeyboard)
        line.linkActivated.connect(lambda href: self.show_theirs(href == "show"))
        line.setVisible(False)
        return line

    @staticmethod
    def _say_theirs(line: QLabel, n: int, listed: bool) -> None:
        """Says on a _theirs_line how many invoices made in a colleague's name the filters match (n), listed or
        not, with the link that hides or shows them. No line when there are none."""
        it, was = "it" if n == 1 else "them", line.text()
        if listed:
            line.setText(f"Also listed: {plural(n, 'invoice')} made in a colleague's name (theirs, never in your "
                         f"totals). <a href='hide'>Hide {it}</a>")
        else:
            line.setText(f"Not listed: {plural(n, 'invoice')} made in a colleague's name (Whose pages…). "
                         f"<a href='show'>Show {it}</a>")
        line.setVisible(n > 0)
        # New text loses the link's focus (Enter would do nothing until Tab again). It is given back once the key
        # press is over: within it, Qt moves the focus on to the next widget instead. The same text keeps it (a
        # refresh): asking then would move the focus on.
        if line.hasFocus() and line.text() != was:
            QTimer.singleShot(0, line, lambda: line.hasFocus() and line.focusNextPrevChild(True))

    def show_theirs(self, on: bool) -> None:
        """Lists the invoices made in a colleague's name too (and their files in Everything made), or no longer.
        They are hidden each time Records is opened: they are not the user's."""
        self.theirs = on
        self._fill_firms()
        self.show_invoices()
        self.show_activity()

    def _whose(self, invoices: list[Invoice]) -> list[Invoice]:
        """The invoices to list: the user's own, and those made in a colleague's name once asked (show_theirs)."""
        return invoices if self.theirs else [i for i in invoices if not i.reporter]

    def _build_invoices(self) -> QWidget:
        """The Invoices tab: filters, the four total tiles, and the Invoices / By firm / By month tables."""
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(12, 12, 12, 12)
        fl = QHBoxLayout()
        self.i_year, self.i_month, self.i_client = self._filters(fl, True)
        self._year_picked = None  # the year the Invoices tab last opened on by itself (see reload)
        self.i_status = QComboBox()
        self.i_status.setToolTip("Not paid, Paid or Void, or the invoices of one colour (Settings → Records)")
        # as wide as "Ready to send", not as the longest colour's name (its list still shows them whole)
        self.i_status.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.i_status.setMinimumContentsLength(13)
        self._fill_status()
        fl.addWidget(QLabel("Status:"))
        fl.addWidget(self.i_status)
        self.i_text, self.i_regex, self.i_fuzzy = self._search(
            fl, "Search: firm, attorney, case, index no., invoice no.…", self.show_invoices)
        self.i_trash = self._table_buttons(fl, "invoices")
        v.addLayout(fl)
        for c in (self.i_year, self.i_month, self.i_client, self.i_status):
            c.currentIndexChanged.connect(self.show_invoices)
        self.i_trash.toggled.connect(lambda on: self._trash_toggled(on, self.i_year))

        tiles = QHBoxLayout()
        self.kpi: dict[str, QLabel] = {}
        for key, label in (("billed", "Billed"), ("paid", "Paid"), ("outstanding", "Outstanding"),
                           ("count", "Invoices")):
            f = QFrame()
            f.setObjectName("card")
            fv = QVBoxLayout(f)
            fv.setContentsMargins(14, 8, 14, 8)
            cap = QLabel(label)
            cap.setObjectName("muted")
            val = QLabel("—")
            val.setObjectName("kpiValue")
            if key in ("paid", "outstanding"):
                val.setProperty("tone", "ok" if key == "paid" else "warn")
            fv.addWidget(cap)
            fv.addWidget(val)
            self.kpi[key] = val
            tiles.addWidget(f)
        v.addLayout(tiles)
        self.trash_note = QLabel(f"The trash: deleted records, kept {TRASH_DAYS} days in case you want them back. "
                                 "Right-click to restore one (the PDF files were never deleted).")
        self.trash_note.setObjectName("muted")
        self.trash_note.setWordWrap(True)
        self.trash_note.setVisible(False)
        v.addWidget(self.trash_note)
        self.i_theirs = self._theirs_line()
        v.addWidget(self.i_theirs)

        inner = QTabWidget()
        self.inv_table = _table(self._heads())
        self._order_columns()
        # Only Notes can be typed into: a double-click or F2 (not any key: typing in the table must not start it)
        self.inv_table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.inv_table.itemChanged.connect(self._item_changed)
        self.inv_table.itemDelegate().closeEditor.connect(self._editor_closed)
        self.inv_table.itemDoubleClicked.connect(self._double_clicked)
        self.inv_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.inv_table.customContextMenuRequested.connect(self._invoice_menu)
        self._header_menu(self.inv_table, "invoices")
        self.inv_table.setToolTip("Tick Paid when an invoice is paid (and your other boxes: Settings → Records) · "
                                  "double-click opens the PDF, or types a note in Notes · right-click for more · "
                                  "Delete moves it to the trash")
        # Delete moves records to the trash only while the table itself has the focus: in a note being typed,
        # Delete deletes text (_delete_selected checks too)
        QShortcut(QKeySequence.Delete, self.inv_table, activated=lambda: self._delete_selected("invoices"),
                  context=Qt.WidgetShortcut)
        self.firm_table = _table(["Firm / attorney"] + SUM_COLS[1:])
        self.month_table = _table(["Month"] + SUM_COLS[1:])
        inner.addTab(self.inv_table, "Invoices")
        inner.addTab(self.firm_table, "By firm")
        inner.addTab(self.month_table, "By month")
        self.inv_inner = inner
        v.addWidget(inner, 1)
        return w

    def _build_activity(self) -> QWidget:
        """The Everything made tab: kind, year and month filters, a search box and the table of files."""
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(12, 12, 12, 12)
        fl = QHBoxLayout()
        self.a_kind = QComboBox()
        self.a_kind.addItem("Everything", "")
        for k, label in KINDS.items():
            self.a_kind.addItem(label + "s", k)
        fl.addWidget(QLabel("Show:"))
        fl.addWidget(self.a_kind)
        self.a_year, self.a_month, _ = self._filters(fl, False)
        self.a_text, self.a_regex, self.a_fuzzy = self._search(
            fl, "Search: firm, attorney, case, index no., file…", self.show_activity)
        self.a_trash = self._table_buttons(fl, "activity")
        v.addLayout(fl)
        for c in (self.a_kind, self.a_year, self.a_month):
            c.currentIndexChanged.connect(self.show_activity)
        self.a_trash.toggled.connect(lambda on: self._trash_toggled(on, self.a_year))
        self.a_count = QLabel("")
        self.a_count.setObjectName("muted")
        v.addWidget(self.a_count)
        self.a_theirs = self._theirs_line()
        v.addWidget(self.a_theirs)
        self.act_table = _table([c.head for c in ACTIVITY_COLS])
        self.act_table.itemDoubleClicked.connect(lambda it: self._open_activity(it.row()))
        self.act_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.act_table.customContextMenuRequested.connect(self._activity_menu)
        self._header_menu(self.act_table, "activity")
        self.act_table.setToolTip("Double-click opens the file · right-click for more · Delete moves it to the trash")
        QShortcut(QKeySequence.Delete, self.act_table, activated=lambda: self._delete_selected("activity"),
                  context=Qt.WidgetShortcut)
        v.addWidget(self.act_table, 1)
        return w

    # ------------------------------------------------------------ columns
    def _table_of(self, which: str) -> QTableWidget:
        """The table of "invoices" or "activity" (everything made)."""
        return self.inv_table if which == "invoices" else self.act_table

    def _in_trash(self, which: str) -> bool:
        """Whether that table's Trash button is on (it lists what was deleted)."""
        return (self.i_trash if which == "invoices" else self.a_trash).isChecked()

    def _invoice_cols(self) -> list[Col]:
        """The Invoices table's columns: INVOICE_COLS (Paid first), then one for each tick box in use besides
        Paid (BOX + its key; at the end, so the others keep their places, and shown after Paid: _order_columns)."""
        return INVOICE_COLS + [Col(BOX + b.key, b.name, lambda i: "", True)
                               for b in self.boxes if b.on and b.kind == TICK]

    def _heads(self) -> list[str]:
        """The Invoices table's headings: Paid's as the Paid box is named (Settings → Records)."""
        paid = next((b.name for b in self.boxes if b.kind == PAID), "Paid")
        return [paid if c.key == "paid" else c.head for c in self.inv_cols]

    def _order_columns(self) -> None:
        """Shows the tick boxes' columns right after Paid (they come last in inv_cols)."""
        h = self.inv_table.horizontalHeader()
        ticks = [i for i, c in enumerate(self.inv_cols) if c.key.startswith(BOX)]
        order = [0] + ticks + [i for i in range(1, len(self.inv_cols)) if i not in ticks]
        for pos, logical in enumerate(order):
            h.moveSection(h.visualIndex(logical), pos)

    def _rebuild_columns(self) -> None:
        """The tick boxes in use, or their names, changed (Settings → Records): the Invoices table gets their
        columns (show_invoices fills them)."""
        self.inv_cols = self._invoice_cols()
        t = self.inv_table
        t.blockSignals(True)
        t.setColumnCount(len(self.inv_cols))
        t.setHorizontalHeaderLabels(self._heads())
        t.blockSignals(False)
        self._order_columns()
        self.apply_columns("invoices")

    def _cols(self, which: str) -> list[Col]:
        """The columns of a table ("invoices", with the tick boxes', or "activity")."""
        return self.inv_cols if which == "invoices" else ACTIVITY_COLS

    @staticmethod
    def _is_box(key: str) -> bool:
        """A tick box's column: Paid, or one of Settings → Records (shown when the box is in use, not chosen
        with Columns…)."""
        return key == "paid" or key.startswith(BOX)

    def columns(self, which: str) -> list[str]:
        """The keys of the columns chosen for a table ("invoices" or "activity"): the user's choice
        (Settings.records_columns), else those shown by default. The tick boxes are not among them."""
        known = {c.key for c in self._cols(which) if not c.trash and not self._is_box(c.key)}
        chosen = [k for k in self.s.records_columns.get(which, []) if k in known]
        return chosen or [c.key for c in self._cols(which) if c.shown and not c.trash and not self._is_box(c.key)]

    def apply_columns(self, which: str) -> None:
        """Shows the chosen columns of a table (and, in the trash, when each record was deleted); the tick
        boxes in use, but not in the trash."""
        keep, trash = set(self.columns(which)), self._in_trash(which)
        t = self._table_of(which)
        paid = any(b.on and b.kind == PAID for b in self.boxes)
        for i, c in enumerate(self._cols(which)):
            if self._is_box(c.key):
                t.setColumnHidden(i, trash or (c.key == "paid" and not paid))
            else:
                t.setColumnHidden(i, not (c.key in keep or (c.trash and trash)))

    def set_columns(self, which: str, keys: list[str] | None) -> None:
        """Keeps a new choice of columns (None: back to the default ones) and shows it."""
        cols = dict(self.s.records_columns)
        if keys is None:
            cols.pop(which, None)
        else:
            cols[which] = [c.key for c in self._cols(which) if c.key in keys and not c.trash
                           and not self._is_box(c.key)]
        self.s.records_columns = cols
        try:
            self.s.save()
        except OSError as e:
            log_error("could not save the columns chosen", e)
        self.apply_columns(which)

    def _columns_menu(self, which: str, at) -> None:
        """The menu of a table's columns, ticked when shown; clicking one shows or hides it."""
        m = QMenu(self)
        chosen = self.columns(which)
        for c in self._cols(which):
            if c.trash or self._is_box(c.key):
                continue
            act = m.addAction(c.head)
            act.setCheckable(True)
            act.setChecked(c.key in chosen)
            act.toggled.connect(lambda on, k=c.key: self.set_columns(
                which, [x for x in self.columns(which) if x != k] + ([k] if on else [])))
        m.addSeparator()
        m.addAction("Back to the usual columns", lambda: self.set_columns(which, None))
        if which == "invoices" and self.on_settings is not None:
            m.addAction("Tick boxes and colours… (Settings → Records)", lambda: self.on_settings("Records"))
        m.exec(at)

    def _header_menu(self, t: QTableWidget, which: str) -> None:
        """Right-click on a table's headings: the columns menu."""
        h = t.horizontalHeader()
        h.setContextMenuPolicy(Qt.CustomContextMenu)
        h.customContextMenuRequested.connect(lambda pos: self._columns_menu(which, h.mapToGlobal(pos)))

    # ------------------------------------------------------------ data
    def reload(self) -> None:
        """Re-reads the records (after new files were made, or Settings saved) and keeps the filters chosen. The
        tick boxes and colours are read from Settings again: a box switched on or off, or renamed, changes the
        columns, and the CSV copies get its column at once."""
        boxes, rules = self.s.boxes(), self.s.rules()
        changed = [(b.key, b.name, b.on) for b in boxes] != [(b.key, b.name, b.on) for b in self.boxes]
        self.boxes, self.rules = boxes, rules
        self.ledger = ledger_for(self.s)  # the records folder may have been changed in Settings
        if changed:
            self._rebuild_columns()
            self.ledger.mirror()
        self._fill_status()
        years = self.ledger.years()
        this_year = date.today().year
        # Invoices are dated as a form is, so one can be a year ahead of the clock: made on Fri 12/31/2027 (New
        # Year's Day 2028, observed) it is dated Mon 1/3/2028 and numbered 2028-0001. The Invoices tab opens on the
        # newest year with an invoice (this year while none is newer), so a new invoice is in sight, and follows it
        # while the year shown is the one it picked; a year chosen by hand is kept. (A colleague's invoice counts
        # only while theirs are listed: else Records could open on a year listing nothing.)
        newest = max([this_year] + (years if self.theirs else self.ledger.years(theirs=False)))
        year_items = [("All years", 0)] + [(str(y), y) for y in sorted(set(years) | {this_year}, reverse=True)]
        keep = self.i_year.currentData()
        refill_combo(self.i_year, year_items, newest if keep is None or keep == self._year_picked else keep)
        self._year_picked = newest
        keep = self.a_year.currentData()  # (Activity: what was done, by the clock)
        refill_combo(self.a_year, year_items, this_year if keep is None else keep)
        self._fill_firms()
        self.show_invoices()
        self.show_activity()

    def _fill_firms(self) -> None:
        """The Firm filter's choices: the firms and attorneys billed on the invoices listed (a colleague's too
        once shown: show_theirs). The firm chosen is kept while it is among them."""
        firms = self.ledger.clients(theirs=self.theirs)
        refill_combo(self.i_client, [("All firms", "")] + [(c, c) for c in firms], self.i_client.currentData() or "")

    def _trash_toggled(self, on: bool = False, year: QComboBox | None = None) -> None:
        """The Trash button: lists what was deleted instead of the records, and back. The trash shows every
        year (year: that tab's Year box), as what was deleted may be from an older one."""
        if on and year is not None:
            year.blockSignals(True)  # (listed again below)
            year.setCurrentIndex(max(0, year.findData(0)))  # "All years"
            year.blockSignals(False)
        trash = self.i_trash.isChecked()
        self.trash_note.setVisible(trash)
        self.inv_inner.setTabEnabled(1, not trash)
        self.inv_inner.setTabEnabled(2, not trash)
        for which in TABLES:
            self.apply_columns(which)
        self.show_invoices()
        self.show_activity()

    def _fill_status(self) -> None:
        """The Status filter's choices: All, the names of the colour rules that can colour a row (Settings →
        Records; "Paid" and "Not paid" only once), Not paid, Paid and Void. The choice made is kept."""
        fixed = {label.lower() for label, _ in STATUS_FILTERS}
        items = STATUS_FILTERS[:1] + [(n, RULE + n) for n in rule_names(self.boxes, self.rules)
                                      if n.lower() not in fixed] + STATUS_FILTERS[1:]
        refill_combo(self.i_status, items, self.i_status.currentData() or "")

    def _chosen_rule(self) -> str:
        """The colour chosen in the Status filter ("Ready to send"), or ""."""
        data = self.i_status.currentData() or ""
        return data[len(RULE):] if data.startswith(RULE) else ""

    def _invoice_filters(self) -> dict:
        """The Invoices tab's filters as keyword arguments for Ledger.invoices ("All" is None or ""; a colour
        chosen in the Status filter is not one of them: see _by_rule)."""
        status = self.i_status.currentData() or ""
        return dict(year=self.i_year.currentData() or None, month=self.i_month.currentData() or None,
                    client=self.i_client.currentData() or "", status="" if status.startswith(RULE) else status,
                    text=self.i_text.text().strip(), how=self._how(self.i_regex, self.i_fuzzy),
                    fuzzy_numbers=self.s.fuzzy_numbers)

    def _transcripts(self) -> Transcripts:
        """Every invoice not in the trash, by transcript, for Every firm paid and Transcribed ticked on a whole
        transcript (a firm of the transcript may be outside the filters)."""
        return Transcripts(self.ledger.invoices())

    def _by_rule(self, invoices: list[Invoice], name: str, transcripts: Transcripts | None) -> list[Invoice]:
        """The invoices the colour rule `name` colours (all of them with no name)."""
        if not name:
            return invoices
        return [i for i in invoices
                if (r := rule_for(i, self.boxes, self.rules, transcripts)) is not None and r.name == name]

    def show_invoices(self, _=None) -> None:
        """Lists the invoices that match the filters (those in the trash with the Trash button; a colleague's only
        once asked: show_theirs), each row in the colour of the first rule that matches it (Settings → Records; none
        in the trash), and updates the totals and the by-firm and by-month tabs. The rows selected, the current one
        and where the list was scrolled to are kept. While a note is being typed, nothing is done until the typing
        ends (_editor_closed)."""
        t = self.inv_table
        if t.state() == QAbstractItemView.EditingState:  # (filling the table would close the note being typed)
            self._stale = True
            return
        self._stale = False
        trash = self.i_trash.isChecked()
        rule_name = "" if trash else self._chosen_rule()
        colours = self.s.records_colours and not trash
        transcripts = None
        try:
            shown = self.ledger.invoices(**self._invoice_filters(), trash=trash)
            if colours or rule_name:
                transcripts = self._transcripts()
            matched = self._by_rule(shown, rule_name, transcripts)
            self.shown = self._whose(matched)
            self._say_theirs(self.i_theirs, sum(1 for i in matched if i.reporter), self.theirs)
            self._search_problem(self.i_text, "")
        except ValueError as e:  # a regular expression still being typed ("(smith")
            self.shown = []
            self._say_theirs(self.i_theirs, 0, self.theirs)
            self._search_problem(self.i_text, str(e))
        place = self._place()
        t.blockSignals(True)  # setting the ticks and the notes must not look like the user changing them
        t.setSortingEnabled(False)
        t.setRowCount(0)
        status_col, notes_col = col_index(self.inv_cols, "status"), col_index(self.inv_cols, "notes")
        for inv in self.shown:
            r = t.rowCount()
            t.insertRow(r)
            rule = rule_for(inv, self.boxes, self.rules, transcripts) if colours else None
            tint = None
            if rule is not None:
                tint = QColor(rule.colour)
                tint.setAlpha(TINT)
            for c, col in enumerate(self.inv_cols):
                it = self._tick_item(inv, col.key, trash) if self._is_box(col.key) else _cell(col, inv)
                if c == status_col:
                    self._status_cell(it, inv, rule, colours)
                elif c == notes_col:
                    it.setData(Qt.UserRole, inv.invoice_no)  # (the row may move, sorted, before the note is kept)
                    it.setToolTip(inv.notes)
                    if not trash:
                        it.setFlags(it.flags() | Qt.ItemIsEditable)
                if tint is not None:
                    it.setBackground(tint)
                t.setItem(r, c, it)
        t.blockSignals(False)
        t.setSortingEnabled(True)
        t.resizeColumnsToContents()
        for key, widest in (("case", 300), ("bill_to", 260), ("file", 360), ("reporters", 200), ("excerpt", 240),
                            ("notes", 300)):
            i = col_index(self.inv_cols, key)
            t.setColumnWidth(i, min(t.columnWidth(i), z(widest)))
        self._put_back_place(place)

        total, by_client, by_month = summarize(self.shown)
        # (no totals of deleted invoices: they would read as money billed)
        self.kpi["billed"].setText("—" if trash else fmt(total.billed))
        self.kpi["paid"].setText("—" if trash else fmt(total.paid))
        self.kpi["outstanding"].setText("—" if trash else fmt(total.outstanding))
        self.kpi["count"].setText("—" if trash else str(total.count))
        self._fill_summary(self.firm_table, [(k, v) for k, v in by_client.items()], total)
        self._fill_summary(self.month_table, [(_month_name(k), v) for k, v in reversed(list(by_month.items()))],
                           total)

    @staticmethod
    def _tick_item(inv: Invoice, key: str, trash: bool) -> QTableWidgetItem:
        """A tick box's cell ("paid", or BOX + a box's key): ticked as the invoice is, with its number (UserRole),
        sorting ticked last; greyed out on a void invoice and in the trash. A ticked box's tooltip says when it was
        ticked (not Paid's: Date paid says that)."""
        it = _Item()
        it.setFlags(_GREYED if inv.status == "void" or trash else _READ_ONLY)
        box = key[len(BOX):]
        on = inv.status == "paid" if key == "paid" else box in inv.checks
        it.setCheckState(Qt.Checked if on else Qt.Unchecked)
        it.setData(Qt.UserRole, inv.invoice_no)
        it.setData(Qt.UserRole + 1, 1 if on else 0)
        if on and key != "paid":
            it.setToolTip(f"Ticked on {us_date(inv.checks[box])}")
        return it

    def _status_cell(self, it: QTableWidgetItem, inv: Invoice, rule: ColourRule | None, colours: bool) -> None:
        """The Status cell: each box in use, ticked or not ("Paid, Transcribed, Not sent"), with the colour's
        name, the speed paid and when each box was ticked in its tooltip. Without row colours, the text has the
        colour of the invoice's status (STATUS_COLORS: amber not paid, green paid); a void invoice's is always grey."""
        it.setText(status_words(inv, self.boxes))
        tips = [rule.name] if rule is not None and rule.name else []
        if inv.status == "paid":
            tips.append(f"Paid{f' ({inv.paid_speed})' if inv.paid_speed else ''}"
                        f"{f' on {us_date(inv.paid_date)}' if inv.paid_date else ''}")
        tips += [f"{b.name} on {us_date(inv.checks[b.key])}" for b in self.boxes
                 if b.on and b.kind == TICK and b.key in inv.checks]
        it.setToolTip("\n".join(tips))
        if inv.status == "void" or not colours:
            it.setForeground(QColor(STATUS_COLORS.get(inv.status, STATUS_COLORS["void"])))

    def _place(self, t: QTableWidget | None = None) -> tuple:
        """Where the Invoices table (or `t`, Everything made's) is: the invoices selected (by number; the rows of
        everything made by id: each row's UserRole), the current one and its column, and how far it is scrolled
        (see _put_back_place)."""
        t = self.inv_table if t is None else t
        number = lambda r: t.item(r, 0).data(Qt.UserRole) if t.item(r, 0) else None  # noqa: E731
        return ({number(i.row()) for i in t.selectedIndexes()} - {None}, number(t.currentRow()),
                t.currentColumn(), t.verticalScrollBar().value(), t.horizontalScrollBar().value())

    def _put_back_place(self, place: tuple, t: QTableWidget | None = None) -> None:
        """Selects the same invoices (or rows of `t`) again, and scrolls back to where the table was, after it
        was filled afresh (a box ticked down the list must not send it back to the top; a reload while the
        right-click menu is open must not leave its Delete nothing to act on)."""
        from PySide6.QtCore import QItemSelectionModel
        selected, current, column, down, across = place
        t = self.inv_table if t is None else t
        sm = t.selectionModel()
        for r in range(t.rowCount()):
            no = t.item(r, 0).data(Qt.UserRole)
            if no == current:
                t.setCurrentCell(r, max(0, column), QItemSelectionModel.NoUpdate)
            if no in selected:
                sm.select(t.model().index(r, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
        t.verticalScrollBar().setValue(down)
        t.horizontalScrollBar().setValue(across)

    @staticmethod
    def _fill_summary(t: QTableWidget, rows, total) -> None:
        """Fills a by-firm or by-month table from (name, Summary) rows, with a bold Total row last."""
        t.setRowCount(0)
        for name, sm in rows + [("Total", total)]:
            r = t.rowCount()
            t.insertRow(r)
            for c, it in enumerate([_item(name), _item(sm.count, True), _money_item(sm.billed),
                                    _money_item(sm.paid), _money_item(sm.outstanding)]):
                if name == "Total" and r == len(rows):
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                t.setItem(r, c, it)
        t.resizeColumnsToContents()

    def show_activity(self, _=None) -> None:
        """Lists the files made that match the Everything made filters (those in the trash with the Trash
        button; an invoice made in a colleague's name only once asked: show_theirs), with a count of each kind.
        The rows selected stay so, found by id, and the table stays scrolled where it was (_put_back_place): the
        main window reloads Records whenever it makes a file, also while a right-click menu here is open."""
        y, m = self.a_year.currentData() or 0, self.a_month.currentData() or 0
        since = until = ""
        if y:
            since, until = f"{y}-{m or 1:02}-01", f"{y}-{m or 12:02}-{calendar.monthrange(y, m or 12)[1]:02}"
        try:
            rows = self.ledger.activity(self.a_kind.currentData() or "", since, until, self.a_text.text().strip(),
                                        trash=self.a_trash.isChecked(), how=self._how(self.a_regex, self.a_fuzzy),
                                        fuzzy_numbers=self.s.fuzzy_numbers)
            self._search_problem(self.a_text, "")
        except ValueError as e:  # a regular expression still being typed
            rows = []
            self._search_problem(self.a_text, str(e))
        # A month in every year ("March", All years) is not one date range, so it is filtered here.
        if m and not y:
            rows = [a for a in rows if a.ts[5:7] == f"{m:02}"]
        # an invoice made in a colleague's name is theirs: its file is listed, as the invoice is, only once asked
        theirs = self.ledger.their_invoice_nos() if rows else set()
        self._say_theirs(self.a_theirs, sum(1 for a in rows if a.invoice_no in theirs), self.theirs)
        if not self.theirs:
            rows = [a for a in rows if a.invoice_no not in theirs]
        self.act_shown = {a.id: a for a in rows}
        t = self.act_table
        place = self._place(t)
        t.setSortingEnabled(False)
        t.setRowCount(0)
        for a in rows:
            r = t.rowCount()
            t.insertRow(r)
            for c, col in enumerate(ACTIVITY_COLS):
                t.setItem(r, c, _cell(col, a))
            t.item(r, 0).setData(Qt.UserRole, a.id)
        t.setSortingEnabled(True)
        t.resizeColumnsToContents()
        for key, widest in (("case", 300), ("file", 420)):
            i = col_index(ACTIVITY_COLS, key)
            t.setColumnWidth(i, min(t.columnWidth(i), z(widest)))
        self._put_back_place(place, t)
        counts = {k: sum(1 for a in rows if a.kind == k) for k in KINDS}
        self.a_count.setText("  ·  ".join([plural(len(rows), "file")] +
                                          [plural(n, KINDS[k].lower()) for k, n in counts.items()]))

    # ------------------------------------------------------------ actions
    def _inv_at(self, row: int) -> Invoice | None:
        """The invoice shown on this table row, or None (row -1 is below the last row)."""
        it = self.inv_table.item(row, 0)
        no = it.data(Qt.UserRole) if it else None
        return next((i for i in self.shown if i.invoice_no == no), None)

    def _act_at(self, row: int) -> Activity | None:
        """The row of everything made shown on this table row, or None."""
        it = self.act_table.item(row, 0)
        return self.act_shown.get(it.data(Qt.UserRole)) if it else None

    def _selected(self, which: str) -> list:
        """The invoices (or rows of everything made) selected, in table order."""
        t = self._table_of(which)
        rows = sorted({i.row() for i in t.selectedIndexes()})
        get = self._inv_at if which == "invoices" else self._act_at
        return [x for x in (get(r) for r in rows) if x is not None]

    def _open_activity(self, row: int) -> None:
        """Opens the file of a row of everything made."""
        a = self._act_at(row)
        if a is not None and a.file_path:
            open_path(a.file_path)

    def _item_changed(self, item: QTableWidgetItem) -> None:
        """A cell of the Invoices table was changed by the user: a Paid tick (asked about), another box ticked or
        unticked, or a note typed. Dealt with once the click or the typing is over, not in the middle of it: that
        puts new cells in this table."""
        if item.column() >= len(self.inv_cols):
            return
        key, no = self.inv_cols[item.column()].key, item.data(Qt.UserRole)
        if key == "paid":
            paid = item.checkState() == Qt.Checked
            QTimer.singleShot(0, lambda: self._set_paid(no, paid))
        elif key.startswith(BOX):
            on = item.checkState() == Qt.Checked
            QTimer.singleShot(0, lambda: self._set_box([no], key[len(BOX):], on))
        elif key == "notes":
            inv, text = next((i for i in self.shown if i.invoice_no == no), None), item.text()
            if inv is not None and text != inv.notes:  # (the same text: nothing typed, a tooltip or a colour set)
                QTimer.singleShot(0, lambda: self._set_note(no, text))

    def _double_clicked(self, item: QTableWidgetItem) -> None:
        """A double-click opens the invoice's PDF; on a note that can be typed into, it types instead, and on a tick
        box it only ticks (two quick clicks to tick and untick shouldn't open a PDF too)."""
        key = self.inv_cols[item.column()].key
        if (key == "notes" and item.flags() & Qt.ItemIsEditable) or self._is_box(key):
            return
        self._open_invoice(self._inv_at(item.row()))

    def _editor_closed(self, *_) -> None:
        """A note was typed (or Escape pressed): the table is shown afresh if that waited for it."""
        if self._stale:
            QTimer.singleShot(0, self._show_stale)

    def _show_stale(self) -> None:
        """Shows the invoices afresh, as show_invoices left them for the typing, unless a note is being typed
        again by now."""
        if self._stale and self.inv_table.state() != QAbstractItemView.EditingState:
            self.show_invoices()

    def _box(self, key: str) -> TrackBox | None:
        """A tick box in use besides Paid, by its key."""
        return next((b for b in self.boxes if b.key == key and b.on and b.kind == TICK), None)

    def _set_box(self, invoice_nos: list[str], key: str, on: bool) -> None:
        """Ticks (on) or unticks a box on these invoices, and on the other invoices of their transcripts for a
        box that says so (Transcribed: TrackBox.whole), then shows their rows afresh (_show_ticked). Nothing is
        asked; Undo takes it back, on all of them at once. A void invoice is left alone."""
        box = self._box(key)
        try:
            if box is not None:
                live = self.ledger.invoices()
                void = {i.invoice_no for i in live if i.status == "void"}
                targets = [n for n in invoice_nos if n not in void]
                if box.whole and targets:
                    tr = Transcripts(live)
                    targets = list(dict.fromkeys(m for n in targets for m in (tr.mates(n) or [n])))
                before = self.ledger.set_checks(targets, key, on)
                if before:
                    which = f"invoice {before[0].invoice_no}" if len(before) == 1 else plural(len(before), "invoice")
                    had = set(targets)
                    self._undoable(f"{box.name} {'ticked' if on else 'unticked'} on {which}",
                                   back=lambda: self._box_back(before, had, key) if box.whole
                                   else self.ledger.put_back_checks(before))
                    self._show_ticked({i.invoice_no for i in before})
                    return
        except Exception as e:
            log_error("could not tick a box of an invoice", e)
            QMessageBox.warning(self, "Could not save", f"{type(e).__name__}: {e}")
        self.show_invoices()  # (nothing changed, or it failed: the boxes as they are)

    def _box_back(self, before: list[Invoice], had: set[str], key: str) -> None:
        """Undo of a box of the whole transcript (Transcribed) ticked or unticked: the invoices as they were before
        (put_back_checks), and an invoice of those transcripts made since (had: the invoices of the transcripts
        then), which started as its transcript was, follows them back: as an invoice made now would start
        (tracking.carried), unticked, or ticked with the day the others have."""
        self.ledger.put_back_checks(before)
        every = self.ledger.invoices()
        tr = Transcripts(every)
        since = set(m for i in before for m in tr.mates(i.invoice_no) if m not in had)
        others = [i for i in every if i.invoice_no not in since]
        for inv in (i for i in every if i.invoice_no in since):
            day = carried(inv, others, self.boxes).get(key)
            if day != inv.checks.get(key):
                self.ledger.set_checks([inv.invoice_no], key, False)
                if day:
                    self.ledger.set_checks([inv.invoice_no], key, True, today=day)

    def _show_ticked(self, invoice_nos: set[str]) -> None:
        """After boxes were ticked: those invoices' rows shown afresh where they are (their boxes, status and
        colour: a tick changes nothing else), not the whole table, which takes seconds with thousands of
        invoices. The whole table is filled afresh when a colour is chosen in the Status filter (a row may leave
        it), and while a note is typed (later: show_invoices)."""
        t = self.inv_table
        if self._chosen_rule() or self.i_trash.isChecked() or t.state() == QAbstractItemView.EditingState:
            self.show_invoices()
            return
        colours = self.s.records_colours
        every = self.ledger.invoices()
        transcripts = Transcripts(every) if colours else None
        fresh = {i.invoice_no: i for i in every if i.invoice_no in invoice_nos}
        at = {i.invoice_no: n for n, i in enumerate(self.shown)}
        rows = {t.item(r, 0).data(Qt.UserRole): r for r in range(t.rowCount())}
        status_col = col_index(self.inv_cols, "status")
        t.blockSignals(True)
        t.setSortingEnabled(False)  # (rows stay put while they change; sorted again below)
        for no, inv in fresh.items():
            if no not in rows or no not in at:
                continue
            self.shown[at[no]] = inv
            r, rule = rows[no], rule_for(inv, self.boxes, self.rules, transcripts) if colours else None
            brush = QBrush()
            if rule is not None:
                tint = QColor(rule.colour)
                tint.setAlpha(TINT)
                brush = QBrush(tint)
            for c, col in enumerate(self.inv_cols):
                if self._is_box(col.key):
                    t.setItem(r, c, self._tick_item(inv, col.key, False))
                elif c == status_col:
                    self._status_cell(t.item(r, c), inv, rule, colours)
                t.item(r, c).setBackground(brush)
        t.blockSignals(False)
        t.setSortingEnabled(True)

    def _set_note(self, invoice_no: str, text: str) -> None:
        """Keeps a note typed into the table. The table isn't filled afresh (nothing else changes); when the
        records can't be changed (locked, the disk full), it says so and shows the note as it was. An invoice no
        longer listed (its colleague's invoices hidden with the note typed) still gets it."""
        inv = next((i for i in self.shown if i.invoice_no == invoice_no), None)
        if inv is None:
            inv = self.ledger.invoice(invoice_no)
            if inv is not None and inv.deleted:
                inv = None
        if inv is None or inv.notes == text:
            return
        try:
            before = self.ledger.invoice(invoice_no) or inv
            self.ledger.set_notes(invoice_no, text)
            self._undoable(f"the notes of invoice {invoice_no} changed", before)
        except Exception as e:
            log_error("could not change an invoice", e)
            QMessageBox.warning(self, "Could not save", f"{type(e).__name__}: {e}")
            self.show_invoices()
            return
        inv.notes = text
        t, notes_col = self.inv_table, col_index(self.inv_cols, "notes")
        t.blockSignals(True)
        for r in range(t.rowCount()):
            it = t.item(r, notes_col)
            if it is not None and it.data(Qt.UserRole) == invoice_no:
                it.setToolTip(text)
        t.blockSignals(False)

    def _set_paid(self, invoice_no: str, paid: bool) -> None:
        """Marks an invoice paid (asking at which speed) or not paid, then shows the list afresh."""
        try:
            inv = self.ledger.invoice(invoice_no)  # as it is now, whatever the table showed
            if inv is not None and inv.deleted:
                pass  # (in the trash: restore it first)
            elif inv is not None and paid and inv.status != "paid":
                dlg = PaidDialog(inv, self)
                if dlg.exec() == QDialog.Accepted:
                    self.ledger.mark_paid(inv.invoice_no, *dlg.values())
                    self._undoable(f"invoice {inv.invoice_no} marked paid", inv)
            elif inv is not None and not paid and inv.status == "paid":
                if QMessageBox.question(self, "Not paid", f"Mark invoice {inv.invoice_no} as not paid?") \
                        == QMessageBox.Yes:
                    self.ledger.mark_unpaid(inv.invoice_no)
                    self._undoable(f"invoice {inv.invoice_no} marked not paid", inv)
        except Exception as e:
            log_error("could not update an invoice", e)
            QMessageBox.warning(self, "Could not save", f"{type(e).__name__}: {e}")
        self.show_invoices()

    def _open_invoice(self, inv: Invoice | None) -> None:
        """Opens the invoice's PDF, or says where it was if it has been moved or deleted."""
        if inv is None:
            return
        if inv.file_path and Path(inv.file_path).exists():
            open_path(inv.file_path)
        else:
            QMessageBox.information(self, "File not found", f"The PDF of invoice {inv.invoice_no} is no longer at\n"
                                    f"{inv.file_path or '(unknown)'}")

    def _invoice_menu(self, pos) -> None:
        """The right-click menu on an invoice: open, show in folder, paid / not paid, void / restore, change the
        amounts, notes, delete; in the trash: restore or delete for good."""
        row = self.inv_table.rowAt(pos.y())
        inv = self._inv_at(row)
        if inv is None:
            return
        if not any(i.row() == row for i in self.inv_table.selectedIndexes()):
            self.inv_table.selectRow(row)  # the menu is about the row clicked
        many = self._selected("invoices")
        m = QMenu(self)
        m.addAction("Open the PDF", lambda: self._open_invoice(inv))
        m.addAction("Show in folder", lambda: open_path(str(Path(inv.file_path).parent)) if inv.file_path else None)
        m.addAction(f"Print {plural(len(many), 'invoice')}…", lambda: self._print([i.file_path for i in many]))
        if self.on_reopen is not None:
            m.addAction("Open this job again (in the main window)", lambda: self.reopen(inv))
        m.addSeparator()
        if inv.deleted:
            self._trash_actions(m, "invoices", many)
        else:
            if inv.status != "paid":
                m.addAction("Mark paid…", lambda: self._set_paid(inv.invoice_no, True))
            else:
                m.addAction("Mark not paid", lambda: self._set_paid(inv.invoice_no, False))
            # each box in use, on every invoice selected (not void) at once: ticked, or unticked when all are
            live = [i for i in many if i.status != "void"]
            for b in self.boxes:
                if b.on and b.kind == TICK and live:
                    on = not all(b.key in i.checks for i in live)
                    m.addAction(f"{'Tick' if on else 'Untick'} {b.name}"
                                + (f" ({plural(len(live), 'invoice')})" if len(live) > 1 else ""),
                                lambda b=b, on=on: self._set_box([i.invoice_no for i in live], b.key, on))
            if inv.status != "void":
                m.addAction("Void (cancelled, not counted)", lambda: self._set_void(inv))
            else:
                m.addAction("Restore (not void)", lambda: self._unvoid(inv))
            if inv.amounts:
                m.addAction("Change amounts…", lambda: self._change_amounts(inv))
            m.addAction("Notes…", lambda: self._notes(inv))
            m.addSeparator()
            m.addAction(f"Delete {plural(len(many), 'record')} (to the trash)…",
                        lambda: self._delete_selected("invoices"))
        m.exec(self.inv_table.viewport().mapToGlobal(pos))

    def _activity_menu(self, pos) -> None:
        """The right-click menu on a row of everything made: open the file, show in folder, delete; in the
        trash: restore or delete for good. Delete acts on the rows chosen as the menu opened (_delete_chosen):
        the list may be read again while it is open."""
        row = self.act_table.rowAt(pos.y())
        a = self._act_at(row)
        if a is None:
            return
        if not any(i.row() == row for i in self.act_table.selectedIndexes()):
            self.act_table.selectRow(row)
        many = self._selected("activity")
        m = QMenu(self)
        m.addAction("Open the file", lambda: open_path(a.file_path) if a.file_path else None)
        m.addAction("Show in folder", lambda: open_path(str(Path(a.file_path).parent)) if a.file_path else None)
        m.addAction(f"Print {plural(len(many), 'file')}…", lambda: self._print([x.file_path for x in many]))
        if self.on_reopen is not None:
            m.addAction("Open this job again (in the main window)", lambda: self.reopen(a))
        m.addSeparator()
        if a.deleted:
            self._trash_actions(m, "activity", many)
        else:
            ids = [x.id for x in many]
            m.addAction(f"Delete {plural(len(many), 'record')} (to the trash)…", lambda: self._delete_chosen(ids))
        m.exec(self.act_table.viewport().mapToGlobal(pos))

    def _delete_chosen(self, ids: list) -> None:
        """The right-click menu's Delete on Everything made: the rows chosen when the menu opened (by id), found
        again in the list as it is now (the main window reloads Records whenever it makes a file, also while the
        menu is open). Only those still listed, and not in the trash, go, after asking; those no longer listed
        are said so, and nothing else is deleted."""
        still = [self.act_shown[i] for i in ids if i in self.act_shown and not self.act_shown[i].deleted]
        gone = len(ids) - len(still)
        if not still:
            QMessageBox.information(self, "Delete", f"{'That record is' if gone == 1 else 'Those records are'} no "
                                    "longer listed (the list was read again while the menu was open): nothing was "
                                    "deleted.")
            return
        one = gone == 1
        note = (f"{gone} of the {len(ids)} chosen {'is' if one else 'are'} no longer listed (the list was read "
                f"again meanwhile): {'it stays as it is' if one else 'they stay as they are'}.") if gone else ""
        self.delete("activity", still, note=note)

    def _trash_actions(self, m: QMenu, which: str, records: list) -> None:
        """Restore and Delete for good, for records in the trash."""
        m.addAction(f"Restore {plural(len(records), 'record')}", lambda: self.restore(which, records))
        m.addAction("Delete for good…", lambda: self.delete_forever(which, records))

    @staticmethod
    def _keys(which: str, records: list) -> dict:
        """The keyword arguments of Ledger.delete / restore / delete_forever for these records."""
        if which == "invoices":
            return {"invoices": [i.invoice_no for i in records]}
        return {"activity": [a.id for a in records]}

    def _delete_selected(self, which: str) -> None:
        """Delete (or the Delete key): the records selected go to the trash, after asking. Nothing while a note
        is being typed (Delete there deletes text)."""
        if self._in_trash(which) or self._table_of(which).state() == QAbstractItemView.EditingState:
            return
        records = self._selected(which)
        if records:
            self.delete(which, records)

    def delete(self, which: str, records: list, ask: bool = True, note: str = "") -> None:
        """Moves records to the trash (asking first unless ask is False; note: a line more in the question). The
        PDF files stay where they are."""
        what = plural(len(records), "invoice" if which == "invoices" else "record")
        if ask and QMessageBox.question(
                self, "Delete", f"Move {what} to the trash?\n\nThey can be restored for {TRASH_DAYS} days "
                "(Trash button). The files themselves are not deleted." + (f"\n\n{note}" if note else "")
                ) != QMessageBox.Yes:
            return
        keys = self._keys(which, records)
        if self._try_change(lambda: self.ledger.delete(**keys)):
            self._undoable(f"{what} deleted", back=lambda: self.ledger.restore(**keys))

    def restore(self, which: str, records: list) -> None:
        """Takes records out of the trash."""
        keys = self._keys(which, records)
        if self._try_change(lambda: self.ledger.restore(**keys)):
            self._undoable(f"{plural(len(records), 'record')} restored", back=lambda: self.ledger.delete(**keys))

    def delete_forever(self, which: str, records: list, ask: bool = True) -> None:
        """Deletes records in the trash for good, after asking."""
        if ask and QMessageBox.question(
                self, "Delete for good", f"Delete {plural(len(records), 'record')} for good? This can't be undone "
                "(the files themselves are not deleted).") != QMessageBox.Yes:
            return
        self._try_change(lambda: self.ledger.delete_forever(**self._keys(which, records)))

    def _try_change(self, fn) -> bool:
        """Makes a change to the records, says so if it fails, and shows both lists afresh. True when it was
        made."""
        ok = True
        try:
            fn()
        except Exception as e:
            ok = False
            log_error("could not change the records", e)
            QMessageBox.warning(self, "Could not save", f"{type(e).__name__}: {e}")
        self.reload()
        if ok:
            self._changed()
        return ok

    def _changed(self) -> None:
        """The records were changed here: the main window is told (on_changed)."""
        if self.on_changed is not None:
            self.on_changed()

    # ------------------------------------------------------------ undo
    def _undoable(self, what: str, before: Invoice | None = None, back: Callable | None = None) -> None:
        """Notes a change just made so Undo can take it back: an invoice as it was before it (before), or the
        call that reverses it (back). what: said on the Undo button's tooltip ("invoice 2026-0003 marked paid")."""
        if before is not None:
            back = lambda: self.ledger.put_back(before)  # noqa: E731
        self.undo_stack = (self.undo_stack + [(what, back)])[-UNDO_MAX:]
        self._show_undo()

    def _show_undo(self) -> None:
        """The Undo button: greyed out with nothing to take back, else its tooltip says what."""
        self.undo_btn.setEnabled(bool(self.undo_stack))
        self.undo_btn.setToolTip(f"Take back: {self.undo_stack[-1][0]} (Ctrl+Z)" if self.undo_stack else
                                 "Takes back the last change made in this window (Ctrl+Z)")

    def show_help(self) -> None:
        """F1: the Help window (the main window's, beside this one) at the Records overview."""
        from .help_window import help_topic_of, open_help
        open_help(help_topic_of(self.focusWidget()) or "rec-overview", self.parentWidget() or self)

    def _undo_key(self) -> None:
        """Ctrl+Z: in a search box it undoes the typing, as everywhere; else the last change to the records."""
        w = self.focusWidget()
        if isinstance(w, QLineEdit):
            w.undo()
        else:
            self.undo()

    def undo(self) -> None:
        """Takes back the last change made in this window (paid, not paid, a box ticked or unticked, void,
        amounts, notes, a delete or a restore) and shows the lists afresh."""
        if not self.undo_stack:
            return
        what, back = self.undo_stack.pop()
        self._try_change(back)
        self._show_undo()

    # ------------------------------------------------------------ summary, backups, print, open again
    def show_summary(self) -> None:
        """Summary...: a month or a year summed up (SummaryDialog), from every invoice not in the trash, whatever
        the filters are."""
        try:
            invoices = self.ledger.invoices()
        except Exception as e:
            log_error("could not read the records", e)
            QMessageBox.warning(self, "Summary", f"{type(e).__name__}: {e}")
            return
        SummaryDialog(invoices, self).exec()

    def show_backups(self) -> None:
        """Backups...: the copies of the records (BackupsDialog). After a restore the lists are read again, and
        Undo forgets what it had: those changes were to the records as they were."""
        dlg = BackupsDialog(self.s, self.ledger, self, busy=lambda: bool(getattr(self.parent(), "filling", False)))
        dlg.exec()
        if dlg.restored:
            self.undo_stack = []
            self._show_undo()
            self.reload()
            self._changed()

    def _print(self, files: list[str]) -> None:
        """Prints the files of the records selected (those still where they were saved)."""
        from .preview import print_files
        there = [f for f in files if f and Path(f).exists()]
        if not there:
            QMessageBox.information(self, "Print", "The file is no longer where it was saved.")
            return
        print_files(self, there)

    @staticmethod
    def origin_of_columns(record) -> str:
        """Where a record came from, for one made before the app kept that (no Activity.origin): the case and
        the attorney as the record's own columns have them, in the same form (see batch.job_from_origin)."""
        get = lambda name: getattr(record, name, "") or ""  # noqa: E731
        fields = {k: [v, "regex", 0.9] for k, v in (
            ("case_name", get("case_name")), ("index_no", get("index_no")), ("dates", get("dates")),
            ("judge", get("judge")), ("part", get("part")), ("court", get("court"))) if v}
        name = get("bill_to") or get("attorney")
        attorneys = [{"name": name, "firm": get("firm"), "email": get("email"), "checked": True}] \
            if name or get("firm") else []
        return json.dumps({"sources": [], "case": {"fields": fields, "attorneys": attorneys}})

    def reopen(self, record) -> None:
        """Open this job again: hands the record's origin to the main window (on_reopen), which puts the case
        back in its editor and reads the documents again. An invoice's origin is kept with its row of
        everything made."""
        if self.on_reopen is None:
            return
        try:
            origin = record.origin if isinstance(record, Activity) else self.ledger.origin_of(record.invoice_no)
        except Exception as e:
            log_error("could not read where a record came from", e)
            origin = ""
        if self.on_reopen(origin or self.origin_of_columns(record)):
            self.close()  # (this window stays in front of the main window otherwise: the job would be behind it)

    def _change_amounts(self, inv: Invoice) -> None:
        """Change amounts…: what each speed of the invoice costs, as corrected in its PDF; the list and the
        totals are shown afresh."""
        inv = self.ledger.invoice(inv.invoice_no) or inv  # as it is now, whatever the table showed
        dlg = AmountsDialog(inv, self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            self.ledger.set_amounts(inv.invoice_no, dlg.values())
            self._undoable(f"the amounts of invoice {inv.invoice_no} changed", inv)
        except Exception as e:
            log_error("could not change an invoice's amounts", e)
            QMessageBox.warning(self, "Could not save", f"{type(e).__name__}: {e}")
        self.show_invoices()

    def _set_void(self, inv: Invoice) -> None:
        """Voids the invoice after asking: it stays listed but leaves the totals."""
        if QMessageBox.question(self, "Void invoice", f"Void invoice {inv.invoice_no}? It stays in the list but is "
                                "no longer counted in the totals.") == QMessageBox.Yes:
            self._change_invoice(inv, f"invoice {inv.invoice_no} voided", lambda: self.ledger.void(inv.invoice_no))

    def _unvoid(self, inv: Invoice) -> None:
        """Restore (not void): the invoice counts again, as unpaid."""
        self._change_invoice(inv, f"invoice {inv.invoice_no} restored from void",
                             lambda: self.ledger.mark_unpaid(inv.invoice_no))

    def _change_invoice(self, inv: Invoice, what: str, fn) -> None:
        """Makes a change to one invoice that Undo can take back (what: as the Undo button says it); says so
        when the records can't be changed (locked, or the disk is full) rather than failing in silence."""
        try:
            before = self.ledger.invoice(inv.invoice_no) or inv
            fn()
            self._undoable(what, before)
        except Exception as e:
            log_error("could not change an invoice", e)
            QMessageBox.warning(self, "Could not save", f"{type(e).__name__}: {e}")
        self.show_invoices()

    def _notes(self, inv: Invoice) -> None:
        """Edits the invoice's free-text notes."""
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, f"Invoice {inv.invoice_no}", "Notes:", text=inv.notes)
        if ok:
            self._change_invoice(inv, f"the notes of invoice {inv.invoice_no} changed",
                                 lambda: self.ledger.set_notes(inv.invoice_no, text))

    # ------------------------------------------------------------ exports
    def _filter_title(self) -> str:
        """A title for an export that names the filters, e.g. "Invoices - March 2026 - Dana Smith (not paid)" or
        "(ready to send)"."""
        f = self._invoice_filters()
        bits = []
        if f["month"]:
            bits.append(calendar.month_name[f["month"]])
        if f["year"]:
            bits.append(str(f["year"]))
        title = "Invoices" + (" - " + " ".join(bits) if bits else "")
        if f["client"]:
            title += f" - {f['client']}"
        if self.i_status.currentData():
            title += f" ({self.i_status.currentText().lower()})"
        return title

    def _ask_path(self, title: str, name: str, filt: str) -> Path | None:
        """A Save As box that starts in the records folder with name filled in. None when cancelled."""
        folder = self.s.records_folder()
        folder.mkdir(parents=True, exist_ok=True)
        p, _ = QFileDialog.getSaveFileName(self, title, str(folder / safe_filename(name)), filt)
        return Path(p) if p else None

    def _to_export(self) -> list[Invoice]:
        """The invoices a report or workbook lists: those shown, or with the Trash on, the invoices (not the
        deleted ones) the same filters match (a colour chosen too): a report never passes deleted invoices off as
        billed. Those made in a colleague's name only while they are listed."""
        if not self.i_trash.isChecked():
            return self.shown
        rule = self._chosen_rule()
        return self._whose(self._by_rule(self.ledger.invoices(**self._invoice_filters()), rule,
                                         self._transcripts() if rule else None))

    def _search_blocked(self) -> bool:
        """True (after saying so) when the Invoices tab's search can't be read (a regular expression half
        typed, Fuzzy without its library: the box is amber, see _search_problem): a report of it would list
        nothing, or fail."""
        if not self.i_text.property("review"):
            return False
        QMessageBox.information(self, "Fix the search first", f"Fix the search first: {self.i_text.toolTip()}")
        return True

    def export_html(self) -> None:
        """Saves a report of the invoices shown (see _to_export) as a web page and opens it."""
        if self._search_blocked():
            return
        title = self._filter_title()
        p = self._ask_path("Save the report", f"{title}.html", "Web page (*.html)")
        if p:
            self._try(lambda: open_path(str(self.ledger.export_html(p, self._to_export(), title))))

    def export_xlsx(self) -> None:
        """Saves the invoices shown (see _to_export; and everything made, and totals) as an Excel workbook and
        opens it."""
        if self._search_blocked():
            return
        p = self._ask_path("Export to Excel", f"{self._filter_title()}.xlsx", "Excel workbook (*.xlsx)")
        if p:
            self._try(lambda: open_path(str(self.ledger.export_xlsx(p, self._to_export()))))

    def export_csv(self) -> None:
        """Writes invoices.csv and activity.csv to a folder the user picks and opens it."""
        folder = self.s.records_folder()
        folder.mkdir(parents=True, exist_ok=True)
        d = QFileDialog.getExistingDirectory(self, "Folder for invoices.csv and activity.csv", str(folder))
        if d:
            self._try(lambda: (self.ledger.export_csv(Path(d)), open_path(d)))

    def open_folder(self) -> None:
        """Brings the CSV copies in the records folder up to date, then opens the folder."""
        folder = self.s.records_folder()
        self._try(lambda: (self.ledger.export_csv(folder), open_path(str(folder))))

    def _try(self, fn) -> None:
        """Runs an export and shows why it failed, if it did."""
        try:
            fn()
        except Exception as e:
            show_save_error(self, e, "Could not export the records")
