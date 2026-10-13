"""Settings -> Records: the tick boxes of the Records window's invoices and the colour of its rows (see
tracking.py), as two tables.

The boxes: whether each is in use, its name (the column's heading), what the Status column says when it is ticked
and when it isn't, and whether ticking it ticks the other invoices of the transcript. The user can add boxes of
their own, and remove those; the built-in ones can be renamed or switched off.

The colours: each row a colour, a name, and for each box in use (and Every firm paid) a cell clicked through
ticked (✓), not ticked (✗) and either way (–). The first row that matches an invoice colours it; a row naming a
box not in use is skipped, and one with no condition colours every invoice (the Note column says so).

Under them, what the main window's Records button counts ("Records · Ready to send: 3"): nothing, the invoices not
paid, or those of a colour (Settings.records_count)."""
from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QColorDialog, QComboBox, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..tracking import (EVERY_PAID, EVERY_PAID_NAME, PAID, ColourRule, TrackBox, box_rows, clean_boxes,
                        clean_rules, count_names, counted, default_boxes, default_rules, new_key, reachable, rule_rows,
                        usable)
from .widgets import refill_combo
from .zoom import z

USE, NAME, YES, NO, WHOLE = range(5)  # the boxes table's columns
SWATCH, RULE_NAME = 0, 1              # the colours table's first columns; then a box each, then the note
MARKS = {True: "✓", False: "✗", None: "–"}
NEW_COLOUR = "#db2777"  # (pink: not one of the colours given, so a new one stands apart)


def _words(name: str) -> tuple[str, str]:
    """A box's Status words made from its name: 'Proofread' -> ('Proofread', 'Not proofread')."""
    return name, "Not " + name[:1].lower() + name[1:]


def _note(text: str) -> QLabel:
    """A small grey note under a table."""
    label = QLabel(text)
    label.setObjectName("muted")
    label.setWordWrap(True)
    return label


def _table(heads: list[str], height: int) -> QTableWidget:
    """A table of one row selected at a time, its cells typed into with a double-click, F2 or any key."""
    t = QTableWidget(0, len(heads))
    t.setHorizontalHeaderLabels(heads)
    t.verticalHeader().setVisible(False)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setWordWrap(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    t.horizontalHeader().setStretchLastSection(True)
    t.setMinimumHeight(z(height))
    return t


def _buttons(*specs) -> QHBoxLayout:
    """A row of buttons: (label, slot, tooltip) each. In a dialog a button presses on Enter by default: these
    don't (Enter in a cell keeps the typing)."""
    row = QHBoxLayout()
    for label, slot, tip in specs:
        b = QPushButton(label)
        b.setToolTip(tip)
        b.setAutoDefault(False)
        b.clicked.connect(slot)
        row.addWidget(b)
    row.addStretch(1)
    return row


class TrackingEditor(QWidget):
    """Settings -> Records: the boxes and the colours. boxes(), rules() and colours_on() give them back, checked
    (tracking.clean_boxes, clean_rules), for Settings.tracking_boxes, tracking_rules and records_colours;
    count_name() for Settings.records_count."""

    def __init__(self, boxes: list[TrackBox], rules: list[ColourRule], colours_on: bool, count: str = "",
                 parent=None):
        """boxes, rules: as Settings has them (copied, not changed); colours_on: Settings.records_colours; count:
        Settings.records_count."""
        super().__init__(parent)
        self._boxes = [replace(b) for b in boxes]
        self._rules = [replace(r, when=dict(r.when)) for r in rules]
        self._count = count
        self._loading = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(_note("Tick boxes for each invoice in Records, as many or as few as you like: Paid, and those "
                            "ticked Use below. Each is a column after Paid, and the Status column says each one "
                            "in its words (\"Paid, Transcribed, Not sent\"). Nothing pops up or reminds you."))
        self.box_table = _table(["Use", "Name (the column)", "Says when ticked", "Says when not", "Whole transcript"],
                                150)
        self.box_table.itemChanged.connect(self._box_edited)
        self.box_table.currentCellChanged.connect(lambda *_: self._show_remove())
        lay.addWidget(self.box_table)
        row = _buttons(("Add a box", self._add_box, "A box of your own, e.g. Proofread"),
                       ("Remove", self._remove_box, "Removes the box of your own selected (the colours that use "
                                                    "it go with it); the boxes the app has can be switched off"),
                       ("Up", lambda: self._move_box(-1), "Moves the box up (its column and its word in the status)"),
                       ("Down", lambda: self._move_box(1), "Moves the box down"),
                       ("Restore defaults", self._default_boxes, "The boxes as they were at first (yours are "
                                                                 "removed)"))
        self.remove_box = row.itemAt(1).widget()
        lay.addLayout(row)
        lay.addWidget(_note("A word left blank says nothing. Whole transcript: ticking it on one firm's invoice "
                            "ticks it on the other firms' invoices of the same transcript (the same index number, "
                            "days and reporter)."))

        self.colours = QCheckBox("Colour the rows")
        self.colours.setChecked(colours_on)
        self.colours.setToolTip("Each invoice in Records gets the colour of the first row below that matches it")
        lay.addWidget(self.colours)
        self.rule_table = _table([], 220)
        self.rule_table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.rule_table.itemChanged.connect(self._rule_edited)
        self.rule_table.cellClicked.connect(self._rule_clicked)
        lay.addWidget(self.rule_table)
        lay.addLayout(_buttons(("Add a colour", self._add_rule, "A new colour, under the one selected"),
                               ("Remove", self._remove_rule, "Removes the colour selected"),
                               ("Up", lambda: self._move_rule(-1), "Moves the colour up: the first that matches "
                                                                   "an invoice colours it"),
                               ("Down", lambda: self._move_rule(1), "Moves the colour down"),
                               ("Restore defaults", self._default_rules, "The colours as they were at first")))
        lay.addWidget(_note(f"Click a box's cell: ✓ ticked, ✗ not ticked, – either way. {EVERY_PAID_NAME}: every "
                            "firm that ordered pages of the same days has paid (the transcript is delivered once "
                            "every party has paid). Click a colour to change it."))
        # what the Records button counts: refilled as the boxes and colours change (_fill_count)
        row = QHBoxLayout()
        row.addWidget(QLabel("Count on the Records button:"))
        self.count = QComboBox()
        self.count.setToolTip("The main window's Records button says how many invoices have this status\n"
                              "(\"Records · Ready to send: 3\"), updated as you work. Nothing: no count.")
        self.count.currentIndexChanged.connect(self._count_chosen)
        row.addWidget(self.count)
        row.addStretch(1)
        lay.addLayout(row)
        self._fill_boxes(0)

    # ------------------------------------------------------------------ what was chosen
    def boxes(self) -> list[TrackBox]:
        """The boxes, checked (a box of your own with no name is left out; a name another column has gets
        " (2)")."""
        return clean_boxes(box_rows(self._boxes))

    def rules(self) -> list[ColourRule]:
        """The colours, checked against the boxes."""
        return clean_rules(rule_rows(self._rules), self.boxes())

    def colours_on(self) -> bool:
        """Colour the rows."""
        return self.colours.isChecked()

    def count_name(self) -> str:
        """What the Records button counts: "Not paid", a colour's name, or "" for nothing."""
        return self._count

    # ------------------------------------------------------------------ the Records button's count
    def _fill_count(self) -> None:
        """The count's choices as the boxes and colours are now: Nothing, Not paid and the colours that can colour
        a row (tracking.count_names). A colour chosen that can't with these boxes stays chosen, and says what is
        counted meanwhile (tracking.counted: Not paid, or nothing without Paid)."""
        boxes = self.boxes()
        names = count_names(boxes, self.rules())
        items = [("Nothing", "")] + [(n, n) for n in names]
        if self._count and self._count not in names:
            instead = counted(self._count, boxes, self.rules())
            items.append((f"{self._count} (with these boxes: {instead or 'nothing'})", self._count))
        refill_combo(self.count, items, self._count)

    def _count_chosen(self, _=None) -> None:
        """A count was chosen from the list."""
        self._count = self.count.currentData() or ""

    # ------------------------------------------------------------------ the boxes
    def _fill_boxes(self, select: int) -> None:
        """Lists the boxes again (and the colours, whose columns follow them) and selects one."""
        t = self.box_table
        self._loading = True
        t.setRowCount(0)
        for b in self._boxes:
            r = t.rowCount()
            t.insertRow(r)
            for c, item in enumerate(self._box_items(b)):
                t.setItem(r, c, item)
        t.resizeColumnsToContents()
        self._loading = False
        if self._boxes:
            t.setCurrentCell(max(0, min(select, len(self._boxes) - 1)), NAME)
        self._show_remove()
        self._fill_rules(self.rule_table.currentRow())

    @staticmethod
    def _box_items(b: TrackBox) -> list[QTableWidgetItem]:
        """A box's row: Use, its name and words (typed into), Whole transcript (none for Paid: each firm pays
        its own)."""
        def tick(on: bool) -> QTableWidgetItem:
            it = QTableWidgetItem()
            it.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            it.setCheckState(Qt.Checked if on else Qt.Unchecked)
            return it
        name = QTableWidgetItem(b.name)
        name.setToolTip("The app's own box: rename it or switch it off" if b.built_in else "A box of your own")
        whole = tick(b.whole)
        if b.kind == PAID:
            whole = QTableWidgetItem()
            whole.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            whole.setToolTip("Each firm pays its own invoice")
        return [tick(b.on), name, QTableWidgetItem(b.yes), QTableWidgetItem(b.no), whole]

    def _box_edited(self, item: QTableWidgetItem) -> None:
        """A cell of the boxes was changed: the box follows it, and the colours' columns follow the boxes."""
        r = item.row()
        if self._loading or not 0 <= r < len(self._boxes):
            return
        t, b = self.box_table, self._boxes[r]
        text = lambda c: t.item(r, c).text().strip() if t.item(r, c) else ""  # noqa: E731
        b.on = t.item(r, USE).checkState() == Qt.Checked
        old = b.name
        b.name = text(NAME) or b.name  # (a name typed away: the one it had)
        b.yes, b.no = text(YES), text(NO)
        b.whole = b.kind != PAID and t.item(r, WHOLE).checkState() == Qt.Checked
        if item.column() == NAME and (b.yes, b.no) == _words(old) and b.name != old:
            b.yes, b.no = _words(b.name)  # (words still the name's own, as Add gives them: "New box", "Not new box")
        if item.column() == NAME:
            self._loading = True
            for c, value in ((NAME, b.name), (YES, b.yes), (NO, b.no)):
                if t.item(r, c) is not None and t.item(r, c).text() != value:
                    t.item(r, c).setText(value)
            self._loading = False
        self._fill_rules(self.rule_table.currentRow())

    def _show_remove(self) -> None:
        """Remove is for a box of your own only."""
        r = self.box_table.currentRow()
        self.remove_box.setEnabled(0 <= r < len(self._boxes) and not self._boxes[r].built_in)

    def _add_box(self) -> None:
        """Add a box: one of your own under the one selected, in use, its name ready to type."""
        r = self.box_table.currentRow() + 1 if self._boxes else 0
        self._boxes.insert(r, TrackBox(new_key(self._boxes), "New box", *_words("New box"), True))
        self._fill_boxes(r)
        self.box_table.editItem(self.box_table.item(r, NAME))

    def _remove_box(self) -> None:
        """Removes the box of your own selected, and the colours that name it (no asking: Cancel in Settings
        brings them back)."""
        r = self.box_table.currentRow()
        if 0 <= r < len(self._boxes) and not self._boxes[r].built_in:
            key = self._boxes.pop(r).key
            self._rules = [x for x in self._rules if key not in x.when]
            self._fill_boxes(r)

    def _move_box(self, step: int) -> None:
        """Up (-1) and Down (1): the box selected swaps places with its neighbour."""
        i, j = self.box_table.currentRow(), self.box_table.currentRow() + step
        if 0 <= i < len(self._boxes) and 0 <= j < len(self._boxes):
            self._boxes[i], self._boxes[j] = self._boxes[j], self._boxes[i]
            self._fill_boxes(j)

    def _default_boxes(self) -> None:
        """The boxes as they were at first, after asking (yours go, and the colours that use them)."""
        if QMessageBox.question(self, "Tick boxes", "Put back the boxes as they were at first? Boxes of your own are "
                                "removed, and only Paid is in use.") == QMessageBox.Yes:
            self._boxes = default_boxes()
            keys = {b.key for b in self._boxes} | {EVERY_PAID}
            self._rules = [x for x in self._rules if all(k in keys for k in x.when)]
            self._fill_boxes(0)

    # ------------------------------------------------------------------ the colours
    def _rule_keys(self) -> list[tuple[str, str]]:
        """(key, heading) of the colours' condition columns: each box in use, and Every firm paid with Paid."""
        keys = [(b.key, b.name) for b in self._boxes if b.on]
        if any(b.on and b.kind == PAID for b in self._boxes):
            keys.append((EVERY_PAID, EVERY_PAID_NAME))
        return keys

    def _fill_rules(self, select: int) -> None:
        """Lists the colours again, a column for each box in use, and selects one."""
        keys = self._rule_keys()
        can = reachable(self._boxes, self._rules)
        t = self.rule_table
        self._loading = True
        t.setRowCount(0)
        t.setColumnCount(len(keys) + 3)
        t.setHorizontalHeaderLabels(["Colour", "Name"] + [h for _, h in keys] + ["Note"])
        for n, rule in enumerate(self._rules):
            r = t.rowCount()
            t.insertRow(r)
            swatch = QTableWidgetItem()
            swatch.setFlags(Qt.ItemIsEnabled)  # (not selectable: the row selected would hide its colour)
            swatch.setBackground(QColor(rule.colour))
            swatch.setToolTip("Click to choose the colour")
            t.setItem(r, SWATCH, swatch)
            t.setItem(r, RULE_NAME, QTableWidgetItem(rule.name))
            for c, (key, head) in enumerate(keys, 2):
                mark = QTableWidgetItem(MARKS[rule.when.get(key)])
                mark.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                mark.setTextAlignment(Qt.AlignCenter)
                mark.setToolTip(f"{head}: click for ticked (✓), not ticked (✗) or either way (–)")
                t.setItem(r, c, mark)
            note = QTableWidgetItem(self._rule_note(rule, n in can))
            note.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            t.setItem(r, len(keys) + 2, note)
        t.resizeColumnsToContents()
        t.setColumnWidth(SWATCH, max(t.columnWidth(SWATCH), z(56)))
        self._loading = False
        if self._rules:
            t.setCurrentCell(max(0, min(select, len(self._rules) - 1)), RULE_NAME)
        self._fill_count()

    def _rule_note(self, rule: ColourRule, can: bool) -> str:
        """What the Note column says of a colour: skipped for a box not in use, that it colours every row, or
        that the colours above it always come first (can: it may colour a row, tracking.reachable)."""
        if not usable(rule, self._boxes):
            off = [next((b.name for b in self._boxes if b.key == k), EVERY_PAID_NAME) for k in rule.when
                   if k not in {key for key, _ in self._rule_keys()}]
            return f"Not used: {', '.join(off)} {'is' if len(off) == 1 else 'are'} not in use"
        if not can:
            return "Not used with these boxes: the colours above it come first"
        if not rule.when:
            return "Colours every row: the colours under it never apply"
        return ""

    def _rule_edited(self, item: QTableWidgetItem) -> None:
        """A colour's name was typed (the count's choices follow it, and a count of that colour its new name)."""
        r = item.row()
        if not self._loading and item.column() == RULE_NAME and 0 <= r < len(self._rules):
            old, new = self._rules[r].name, item.text().strip()
            self._rules[r].name = new
            if old and old == self._count and new and all(x.name != old for x in self._rules):
                self._count = new
            self._fill_count()

    def _rule_clicked(self, r: int, c: int) -> None:
        """A click on a colour's swatch chooses another colour; on a box's cell, ticked → not ticked → either way
        → ticked."""
        if not 0 <= r < len(self._rules):
            return
        rule, keys = self._rules[r], self._rule_keys()
        if c == SWATCH:
            colour = QColorDialog.getColor(QColor(rule.colour), self, "Colour")
            if colour.isValid():
                rule.colour = colour.name()
                self._fill_rules(r)
        elif 2 <= c < 2 + len(keys):
            key = keys[c - 2][0]
            now = rule.when.get(key)
            if now is None:
                rule.when[key] = True
            elif now:
                rule.when[key] = False
            else:
                del rule.when[key]
            self._fill_rules(r)

    def _add_rule(self) -> None:
        """Add a colour: under the one selected, for invoices with Paid ticked, its name ready to type."""
        r = self.rule_table.currentRow() + 1 if self._rules else 0
        paid = next((b.key for b in self._boxes if b.kind == PAID), None)
        self._rules.insert(r, ColourRule("New colour", NEW_COLOUR, {paid: True} if paid else {}))
        self._fill_rules(r)
        self.rule_table.editItem(self.rule_table.item(r, RULE_NAME))

    def _remove_rule(self) -> None:
        """Removes the colour selected (no asking: Cancel in Settings brings it back)."""
        r = self.rule_table.currentRow()
        if 0 <= r < len(self._rules):
            del self._rules[r]
            self._fill_rules(r)

    def _move_rule(self, step: int) -> None:
        """Up (-1) and Down (1): the colour selected swaps places with its neighbour."""
        i, j = self.rule_table.currentRow(), self.rule_table.currentRow() + step
        if 0 <= i < len(self._rules) and 0 <= j < len(self._rules):
            self._rules[i], self._rules[j] = self._rules[j], self._rules[i]
            self._fill_rules(j)

    def _default_rules(self) -> None:
        """The colours as they were at first, after asking."""
        if QMessageBox.question(self, "Colours", "Put back the colours as they were at first? Yours are "
                                "replaced.") == QMessageBox.Yes:
            self._rules = default_rules()
            self._fill_rules(0)
