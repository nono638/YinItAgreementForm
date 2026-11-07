"""The firms' columns of Who ordered which pages (gui/excerpts.py): what makes a column read as one firm's, from
its heading down.

A firm's heading (FirmHeader) has a band of the firm's colour (the colour of its square, badges.tag_color), its
name under it and, at the bottom, the speed it ordered all its pages at (FirmSpeedBox). Its cells (FirmCellDelegate)
have a stripe of the same colour at their left edge, and a click anywhere in one ticks it, not only on the box. No
shade behind the name (the user, 2026-10-22: a pale orange read as the amber of a field to check; see badges.py).

The speed boxes are children of the header's viewport, kept from one showing of the table to the next: the table is
filled afresh on every change, here or in the main window (a read ending, a tick), and a box built afresh with it
would close its list and lose the focus each time. hold() makes them stay as they are while the table is filled.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QRect, QSignalBlocker, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPalette, QPen
from PySide6.QtWidgets import (QApplication, QHeaderView, QStyle, QStyleOptionComboBox, QStyleOptionHeader,
                               QStyleOptionViewItem, QStylePainter)

from .badges import STRIPE_ROLE, StripeDelegate, stripe_width
from .widgets import QuietCombo
from .zoom import z

BAND = 7  # how high a firm's band of colour is, before zoom (with its edge: a thinner one hardly showed its colour)
GAP = 3  # the room under the band and under the name
BOX_INSET = 4  # each side of a speed box: the 4 px at a column's edge that resize it stay within reach
BOX_FOOT = 4  # under a speed box
SHORT_ROLE = Qt.UserRole + 8  # a speed box's item: what the box says while closed ("Expedite")
MOUSE = {QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick}


class FirmSpeedBox(QuietCombo):
    """A firm's speed in its heading. Closed it says the short label of its choice ("Expedite"), as the column is
    narrow; its list, and currentText(), have the whole ("The form's (Expedite)": the app's Fusion style opens a list
    as wide as its text needs). A style-sheet box draws no arrow, and in a heading it read as a field to type in, so
    this one draws its own."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[tuple] | None = None  # (as last set: unchanged, the list isn't touched)

    def set_choices(self, items: list[tuple], at: int) -> None:
        """The list ((text in the list, data, label while closed) of each item) and the item chosen, without any
        signal. The items are replaced only when they differ, so a list open meanwhile stays open."""
        with QSignalBlocker(self):
            if items != self._items:
                self.clear()
                for text, data, short in items:
                    self.addItem(text, data)
                    self.setItemData(self.count() - 1, short, SHORT_ROLE)
                self._items = list(items)
            self.setCurrentIndex(at)
        self.update()

    def short_text(self) -> str:
        """What the box says while closed."""
        return self.currentData(SHORT_ROLE) or self.currentText()

    def widest_short(self) -> int:
        """The room, in pixels, the longest of its closed labels takes in the box: the box's padding, its frame and
        the arrow's room around the text (about 43 at 100 %, from the theme's QComboBox rules)."""
        fm = self.fontMetrics()
        labels = [self.itemData(i, SHORT_ROLE) or self.itemText(i) for i in range(self.count())]
        return max((fm.horizontalAdvance(x) for x in labels), default=0) + z(43)

    def contextMenuEvent(self, e) -> None:  # noqa: N802 (Qt's name)
        """Not taken: a right-click on the box is one on the heading (its Columns menu), as anywhere else on it."""
        e.ignore()

    def wheelEvent(self, e) -> None:  # noqa: N802
        """Never taken, focus or not: the table behind it scrolls. These boxes keep the focus while the table is shown
        again, so a wheel going by after a choice moved the firm to the next speed and repriced it with no word."""
        e.ignore()

    def paintEvent(self, _e) -> None:  # noqa: N802
        """As any combo box, with the short label and the arrow."""
        p = QStylePainter(self)
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        p.drawComplexControl(QStyle.CC_ComboBox, opt)
        field = self.style().subControlRect(QStyle.CC_ComboBox, opt, QStyle.SC_ComboBoxEditField, self)
        opt.currentText = self.fontMetrics().elidedText(self.short_text(), Qt.ElideRight, field.width())
        p.drawControl(QStyle.CE_ComboBoxLabel, opt)
        if not self.isEnabled():  # (a firm that ordered nothing: it has no list to open)
            return
        x, y, half = self.width() - z(22) // 2 - 1, self.height() // 2, z(4)  # (in the theme's 22 px for a drop-down)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(opt.palette.color(QPalette.Text), max(1.0, z(1) * 1.3)))
        p.drawPolyline([QPointF(x - half, y - half / 2), QPointF(x, y + half / 2), QPointF(x + half, y - half / 2)])


class FirmHeader(QHeaderView):
    """The table's headings: the usual ones, and for each firm a band, its name and its speed box.

    The colour is the header item's STRIPE_ROLE (none: no band); which sections are firms', and their boxes, is
    told by set_firm_columns. The boxes follow their columns through place(), on every signal that can move one.
    (A scroll needs none: QHeaderView.setOffset scrolls the viewport, and that moves its children.)"""

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.setSectionsClickable(True)  # (as a QTableView's own header is made)
        self.setHighlightSections(True)
        self.setDefaultAlignment(Qt.AlignHCenter | Qt.AlignBottom)  # (the headings' words just over their columns)
        self._boxes: dict[int, FirmSpeedBox] = {}  # by logical section
        self._held = False
        self.sectionResized.connect(self.place)
        self.sectionCountChanged.connect(self.place)
        self.geometriesChanged.connect(self.place)

    def hold(self) -> None:
        """The boxes stay as they are until set_firm_columns: the table is being filled, and its sections for now
        mean nothing. (Moved or hidden meanwhile, a box closes its open list and loses the focus.)"""
        self._held = True

    def set_firm_columns(self, boxes: dict[int, FirmSpeedBox]) -> None:
        """The firms' sections, with their boxes; a box no longer among them is hidden. The heading's height follows."""
        for box in self._boxes.values():
            if box not in boxes.values():
                box.hide()
        self._boxes = dict(boxes)
        self._held = False
        self.geometriesChanged.emit()
        self.place()

    def box_rect(self, logical: int, box: FirmSpeedBox) -> QRect:
        """Where a section's box goes: across its section, at the bottom of the heading, in viewport coordinates."""
        inset, height = z(BOX_INSET), box.sizeHint().height()
        return QRect(self.sectionViewportPosition(logical) + inset, self.viewport().height() - height - z(BOX_FOOT),
                     max(0, self.sectionSize(logical) - 2 * inset), height)

    def place(self) -> None:
        """Puts each box over its section."""
        if self._held:
            return
        for logical, box in self._boxes.items():
            box.setGeometry(self.box_rect(logical, box))
            box.setVisible(not self.isSectionHidden(logical))

    def resizeEvent(self, e) -> None:  # noqa: N802 (Qt's name)
        super().resizeEvent(e)
        self.place()

    def changeEvent(self, e) -> None:  # noqa: N802
        """The style sheet or the font changed (a zoom): the heading's height and the boxes' sizes with it."""
        super().changeEvent(e)
        if e.type() in (QEvent.StyleChange, QEvent.FontChange):
            self.geometriesChanged.emit()

    def sizeHint(self) -> QSize:  # noqa: N802
        """High enough for a band, a name and a box. (QTableView reads this to lay the header out.)"""
        hint = super().sizeHint()
        if self._boxes:
            box = max(b.sizeHint().height() for b in self._boxes.values())
            hint.setHeight(max(hint.height(), z(BAND) + z(GAP) + self.fontMetrics().height() + z(GAP) + box
                               + z(BOX_FOOT)))
        return hint

    def paintSection(self, painter, rect, logical) -> None:  # noqa: N802
        """A firm's section: the section's background, the band with a lighter edge (navy on the dark theme's
        heading hardly shows without one, as on the square: badges.badge_icon), and the name, cut to the room."""
        if logical not in self._boxes:
            super().paintSection(painter, rect, logical)
            return
        opt = QStyleOptionHeader()
        self.initStyleOption(opt)
        self.initStyleOptionForIndex(opt, logical)
        opt.rect = rect
        name, opt.text = opt.text, ""
        self.style().drawControl(QStyle.CE_HeaderSection, opt, painter, self)
        colour = self.model().headerData(logical, Qt.Horizontal, STRIPE_ROLE)
        if colour:
            colour = QColor(colour)
            band = QRect(rect.left(), rect.top(), rect.width() - 1, z(BAND))
            painter.fillRect(band, colour)
            painter.save()
            painter.setPen(QPen(colour.lighter(170), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(band.adjusted(0, 0, -1, -1))
            painter.restore()
        margin = z(BOX_INSET)
        room = rect.width() - 2 * margin
        font = QFont(self.font())
        font.setBold(True)  # (the widest the style sheet and a highlighted section can make it)
        opt.rect = QRect(rect.left() + margin, rect.top() + z(BAND) + z(GAP), room, self.fontMetrics().height())
        opt.text = QFontMetrics(font).elidedText(name, Qt.ElideRight, room)
        opt.textAlignment = Qt.AlignCenter
        self.style().drawControl(QStyle.CE_HeaderLabel, opt, painter, self)


class FirmCellDelegate(StripeDelegate):
    """The table's cells. A firm's (a box to tick) has the stripe of its colour, its text in its own colour even on
    a selected row (the style sheet's item:selected sets one colour there, which took the amber of a speed to
    commit to), and a left click anywhere in it ticks or unticks it. Other cells as usual."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._closing = False  # an editor closed just now: the press being handled is what closed it
        self._pass_over = False  # the press that closed it was on a firm's cell: its release ticks nothing
        self.closeEditor.connect(self._editor_closed)

    def _editor_closed(self, *_) -> None:
        """The cell typed in has closed, kept or not. If a press took the focus from it, that press is delivered next,
        before the timer's zero is up; closed any other way (Enter, Escape), the mark is gone by the next press."""
        self._closing = True
        QTimer.singleShot(0, self._closed_a_while_ago)

    def _closed_a_while_ago(self) -> None:
        self._closing = False

    @staticmethod
    def _is_firms(index) -> bool:
        """A cell with a box to tick: only the firms' are (ExcerptsWindow._cell makes the others uncheckable)."""
        return bool(index.flags() & Qt.ItemIsUserCheckable) and index.data(Qt.CheckStateRole) is not None

    def paint(self, painter, option, index) -> None:
        if not self._is_firms(index):
            super().paint(painter, option, index)
            return
        colour = index.data(STRIPE_ROLE)
        width = stripe_width(option) if colour else 0
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.rect = option.rect.adjusted(width, 0, 0, 0)
        widget = opt.widget
        style = widget.style() if widget is not None else QApplication.style()
        # The text's place from the box's, the same on any row at any zoom: where the style would put the text, a
        # selected row has it 3 px further left, and at 160 % over a box the zoom has made bigger
        box = style.subElementRect(QStyle.SE_ItemViewItemCheckIndicator, opt, widget)
        margin = style.pixelMetric(QStyle.PM_FocusFrameHMargin, None, widget) + 1
        room = QRect(opt.rect)
        room.setLeft(box.right() + 1 + 2 * margin)
        room.setRight(opt.rect.right() - margin)
        text, opt.text = opt.text, ""
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, widget)
        if text:
            painter.save()
            painter.setFont(opt.font)
            painter.setPen(opt.palette.color(QPalette.Text))
            painter.drawText(room, Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
                             opt.fontMetrics.elidedText(text, Qt.ElideRight, room.width()))
            painter.restore()
        if colour:
            painter.fillRect(QRect(option.rect.left(), option.rect.top(), width, option.rect.height()), QColor(colour))

    def editorEvent(self, event, model, option, index) -> bool:  # noqa: N802 (Qt's name)
        """A left click anywhere in a firm's cell flips its tick through the model, so the table's itemChanged runs
        as for any tick. On the release only: the press chooses the row as on any cell, and the view sends the release
        only when it is over the cell pressed, so a drag ticks nothing. A press that closed the cell being typed in
        ticks nothing: it was to leave that cell, and keeping what was typed has shown the table again, so a different
        run may be under the mouse by its release (firm dropped from pages it ordered; a run refused and its message
        cleared). The other buttons are left alone (a right-click is the run's menu). Space comes here too, and is the
        base class's."""
        if event.type() in MOUSE and self._is_firms(index):
            if event.button() != Qt.LeftButton:
                return False
            if event.type() == QEvent.MouseButtonPress:
                self._pass_over = self._closing
            if event.type() != QEvent.MouseButtonRelease or self._pass_over:
                return False
            on = Qt.CheckState(index.data(Qt.CheckStateRole)) == Qt.Checked
            return model.setData(index, Qt.Unchecked if on else Qt.Checked, Qt.CheckStateRole)
        return super().editorEvent(event, model, option, index)
