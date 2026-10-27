"""How a firm's mark (firm_marks.Mark: its side and its place among its side's firms) looks in the window: a small
square of its colour, nothing written on it (badge_icon, beside the firm's name in a table or the Excerpts window's
column heading; badge_html in rich text), and in a table a thin stripe of the same colour at the left edge of the
name (StripeDelegate, STRIPE_ROLE). Plaintiffs' firms in warm colours, the defense in cool ones, the others in greys
and greens (the user, 2026-10-21): orange against blue stays apart for the commoner colour blindness. No number or
letter on the square (the user, 2026-10-26: 1, A, 001 had nothing to do with the firms' names and only confused),
so the firms of one side are told apart by their colours alone, each its own (firm_marks.SHADES: the run sheet's
Who Ordered tab colours them alike), and the square's tooltip names the side (SIDE_NAMES). No shade behind the name
(the user, 2026-10-22): a pale orange there read as the amber of a field to check, so the colour is only in the
square and the stripe, and none of the colours is that amber. The colours are the same in both themes; the square
has a lighter edge of its colour, so a dark one (navy, brown) still shows on the dark theme's tables."""
from __future__ import annotations

import html

from PySide6.QtCore import QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from ..firm_marks import DEFENSE, OTHER, PLAINTIFF, Mark, shade_of

SIDE_NAMES = {PLAINTIFF: "A plaintiffs' firm", DEFENSE: "A defense firm", OTHER: "A firm on neither side"}

TAG_HEIGHT = 14  # a square's side in a table, before zoom (zoom.z)
STRIPE_ROLE = Qt.UserRole + 7  # a table cell's stripe colour ("#ea580c"), drawn by StripeDelegate


def tag_color(mark: Mark) -> QColor:
    """The colour of the firm's square and stripe (firm_marks.shade_of)."""
    return QColor(shade_of(mark))


def side_name(mark: Mark) -> str:
    """What the square's tooltip says: 'A plaintiffs' firm', 'A defense firm' or 'A firm on neither side'."""
    return SIDE_NAMES.get(mark.side, SIDE_NAMES[OTHER])


def badge_icon(mark: Mark, height: int = TAG_HEIGHT) -> QIcon:
    """The firm's square: a rounded square of its colour with a lighter edge (a dark colour on the dark theme),
    nothing on it, drawn for the screen's scaling (sharp at 150%). The view showing it needs an icon size as big
    (badge_size)."""
    w, h = badge_size(height)
    screen = QGuiApplication.primaryScreen()
    dpr = screen.devicePixelRatio() if screen is not None else 1.0
    pix = QPixmap(round(w * dpr), round(h * dpr))
    pix.setDevicePixelRatio(dpr)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    colour = tag_color(mark)
    p.setPen(QPen(colour.lighter(170), 1))
    p.setBrush(colour)
    p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), h / 4, h / 4)
    p.end()
    icon = QIcon(pix)
    icon.addPixmap(pix, QIcon.Selected)  # (else Qt tints it on a selected row: orange read as brown)
    return icon


def badge_size(height: int = TAG_HEIGHT) -> tuple[int, int]:
    """The size of a square (badge_icon) of this height."""
    return height, height


def badge_html(mark: Mark | None, name: str) -> str:
    """A firm's name in rich text with its square before it (a filled square in its colour, then the name,
    escaped); just the name without a mark."""
    if mark is None:
        return html.escape(name)
    return f"<span style='color:{tag_color(mark).name()}'>&#9632;</span>&nbsp;{html.escape(name)}"


def stripe_width(option: QStyleOptionViewItem) -> int:
    """How wide a stripe is: a quarter of the text's height (it follows the zoom), 3 pixels at least."""
    return max(3, option.fontMetrics.height() // 4)


class StripeDelegate(QStyledItemDelegate):
    """Draws a cell as usual, moved right to make room for a stripe of the colour in its STRIPE_ROLE at its left
    edge (a firm's colour, by its name); a cell without one as usual."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        color = index.data(STRIPE_ROLE)
        if not color:
            super().paint(painter, option, index)
            return
        w = stripe_width(option)
        moved = QStyleOptionViewItem(option)
        moved.rect = option.rect.adjusted(w, 0, 0, 0)
        super().paint(painter, moved, index)
        painter.fillRect(QRect(option.rect.left(), option.rect.top(), w, option.rect.height()), QColor(color))

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        """As usual, wider by the stripe in a cell with one, so the column fits its text with the stripe."""
        size = super().sizeHint(option, index)
        return size + QSize(stripe_width(option), 0) if index.data(STRIPE_ROLE) else size
