"""Settings -> Dates -> Court holidays: the days the courts are closed, as a table of names and rules in plain words
(workdays.parse_rule: "4th Thursday of November"), each with the next day it falls on, so a rule mistyped shows
at once ("⚠ not understood"). Under it, what a holiday on a weekend does, the holidays coming up and examples of
the rules. rows() and weekend() give them back as Settings.holidays and Settings.holiday_weekend keep them;
"Restore the court's holidays" puts back the courthouse's list (courthouses.Courthouse.holidays)."""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import courthouses, workdays
from ..settings import HOLIDAY_WEEKEND
from .zoom import z

NAME, WHEN, NEXT = range(3)  # the table's columns
NOT_UNDERSTOOD = "⚠ not understood"
EXAMPLES = ("Write when each one falls like this: " + ", ".join(f"\"{e}\"" for e in workdays.RULE_EXAMPLES)
            + ". A date with its year is that day only (a one-off closing); the others are every year.")
COMING_DAYS = 90  # the holidays "Coming up" lists: those of the next three months


def _note(text: str) -> QLabel:
    """A small grey note under the table."""
    label = QLabel(text)
    label.setObjectName("muted")
    label.setWordWrap(True)
    return label


class HolidayEditor(QWidget):
    """The court holidays as a table (Holiday | When | Next), with Add, Remove and Restore under it, the choice of
    what a holiday on a weekend does, and the holidays of the next three months. today: the day "Next" counts
    from (default: today; a test sets it)."""

    def __init__(self, rows: list[dict], weekend: str = "nearest", parent=None, today: date | None = None):
        """rows: Settings.holidays (copied, not changed); weekend: Settings.holiday_weekend."""
        super().__init__(parent)
        self._today = today
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Holiday", "When", "Next"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setMinimumHeight(z(220))
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(NAME, QHeaderView.Stretch)
        hh.setSectionResizeMode(WHEN, QHeaderView.Stretch)
        hh.setSectionResizeMode(NEXT, QHeaderView.ResizeToContents)
        self.table.itemChanged.connect(self._edited)
        lay.addWidget(self.table)
        buttons = QHBoxLayout()
        court = courthouses.current().name
        for label, slot, tip in (("Add", self._add, "A new holiday at the end: name it and say when it falls"),
                                 ("Remove", self._remove, "Removes the holiday selected (the court is open that day)"),
                                 ("Restore the court's holidays", self._restore,
                                  f"Puts back the holidays of {court}: the New York State courts' legal holidays")):
            b = QPushButton(label)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            buttons.addWidget(b)
        buttons.addStretch(1)
        lay.addLayout(buttons)
        row = QHBoxLayout()
        row.addWidget(QLabel("A holiday on a weekend is"))
        self.weekend_box = QComboBox()
        for key, label in HOLIDAY_WEEKEND.items():
            self.weekend_box.addItem(label, key)
        self.weekend_box.setCurrentIndex(max(0, self.weekend_box.findData(weekend)))
        self.weekend_box.setToolTip("On a Saturday: closed the Friday before; on a Sunday: the Monday after, as New "
                                    "York's courts are\n(Independence Day 2026, a Saturday: Friday 7/3).")
        self.weekend_box.currentIndexChanged.connect(lambda _: self._show_next())
        row.addWidget(self.weekend_box)
        row.addStretch(1)
        lay.addLayout(row)
        self.coming = _note("")
        lay.addWidget(self.coming)
        lay.addWidget(_note(EXAMPLES))
        self._fill(rows)

    # ---- what Settings keeps
    def rows(self) -> list[dict]:
        """The holidays as Settings.holidays keeps them, in the table's order (blank rows left out; a rule that
        can't be read is kept, and ignored until it is put right)."""
        out = []
        for r in range(self.table.rowCount()):
            name, when = self._text(r, NAME), self._text(r, WHEN)
            if name or when:
                out.append({"name": name, "when": when})
        return out

    def weekend(self) -> str:
        """What a holiday on a weekend does: a key of HOLIDAY_WEEKEND."""
        return self.weekend_box.currentData()

    # ---- the table
    def _text(self, r: int, c: int) -> str:
        """A cell's text, without spaces around it ("" for none)."""
        item = self.table.item(r, c)
        return item.text().strip() if item is not None else ""

    def _fill(self, rows: list[dict]) -> None:
        """The table from these rows, each with its next day."""
        with QSignalBlocker(self.table):
            self.table.setRowCount(0)
            for h in rows:
                self._append(h.get("name", ""), h.get("when", ""))
        self._show_next()

    def _append(self, name: str, when: str) -> int:
        """A row at the end (Next is worked out, not typed); returns its number."""
        # (signals held: each setItem is an itemChanged, and _edited would look for this row's Next before it has one)
        with QSignalBlocker(self.table):
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, NAME, QTableWidgetItem(name))
            self.table.setItem(r, WHEN, QTableWidgetItem(when))
            nxt = QTableWidgetItem("")
            nxt.setFlags(nxt.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r, NEXT, nxt)
        return r

    def _edited(self, item: QTableWidgetItem) -> None:
        """A name or a rule typed: the next days follow."""
        if item.column() != NEXT:
            self._show_next()

    def _show_next(self) -> None:
        """Each row's next day ("Thu 11/26/2026"; "⚠ not understood" for a rule that can't be read, with the
        examples as its tooltip; "(past)" for a one-day closing gone by), and the holidays of the next three months
        under the table."""
        today = self._today or workdays.now().date()
        weekend = self.weekend()
        with QSignalBlocker(self.table):
            for r in range(self.table.rowCount()):
                when, item = self._text(r, WHEN), self.table.item(r, NEXT)
                if item is None:  # (a row still being made)
                    continue
                rule = workdays.parse_rule(when)
                if rule is None:
                    text, tip = (NOT_UNDERSTOOD if when or self._text(r, NAME) else ""), EXAMPLES
                else:
                    days = workdays.Holidays([{"name": "x", "when": when}], weekend).between(
                        today, today + timedelta(days=800))
                    text = workdays.full(days[0][0]) if days else "(past)"
                    tip = ""
                item.setText(text)
                item.setToolTip(tip)
                self.table.item(r, WHEN).setToolTip(tip)
        coming = workdays.Holidays(self.rows(), weekend).between(today, today + timedelta(days=COMING_DAYS))
        self.coming.setText("Coming up: " + ", ".join(f"{n} {workdays.full(d)}" for d, n in coming) if coming else
                            "No court holidays in the next three months.")

    def _add(self) -> None:
        """Add: a blank row at the end, its name ready to type."""
        r = self._append("", "")
        self._show_next()
        self.table.setCurrentCell(r, NAME)
        self.table.editItem(self.table.item(r, NAME))

    def _remove(self) -> None:
        """Remove: the row selected goes (no asking: Cancel in Settings still brings it back)."""
        r = self.table.currentRow()
        if 0 <= r < self.table.rowCount():
            self.table.removeRow(r)
            self._show_next()

    def _restore(self) -> None:
        """Back to the courthouse's holidays and its weekend rule, after asking."""
        if QMessageBox.question(self, "Court holidays", "Put back the court's holidays? Holidays you added or "
                                "changed are replaced.") == QMessageBox.Yes:
            with QSignalBlocker(self.weekend_box):
                self.weekend_box.setCurrentIndex(
                    max(0, self.weekend_box.findData(courthouses.current().holiday_weekend)))
            self._fill(courthouses.holiday_rows())
