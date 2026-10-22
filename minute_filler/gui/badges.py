"""How a firm's mark (firm_marks.Mark: '1', 'A', '001') looks in the window: a small tag in its side's colour with
the badge in white (badge_icon, beside the firm's name in a table; badge_html in rich text), and in a table a thin
stripe of the same colour at the left edge of the name (StripeDelegate, STRIPE_ROLE). Plaintiffs' firms in
oranges, the defense in blues, the others in grey-greens (the user, 2026-10-21): orange against blue stays apart
for the commoner colour blindness; the firms of one side are told apart by their badges, their colours only
helping. No shade behind the name (the user, 2026-10-22): a pale orange there read as the amber of a field to
check, so the colour is only in the tag and the stripe, and none of the oranges is that amber. The colours are
the same in both themes (white text on them reads in either)."""
from __future__ import annotations

import html

from PySide6.QtCore import QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from ..firm_marks import DEFENSE, PLAINTIFF, Mark

# by side, the firms' colours in turn (Mark.shade): a bright and a deep one in turn, so the next firm differs
SHADES = {
    PLAINTIFF: ["#ea580c", "#9a3412", "#c2410c", "#7c2d12"],
    DEFENSE: ["#2563eb", "#0e7490", "#4f46e5", "#1e40af"],
    "other": ["#047857", "#4b5563", "#15803d"],
}

TAG_HEIGHT = 18  # a tag's height in a table, before zoom (zoom.z): its badge has to read at a glance
STRIPE_ROLE = Qt.UserRole + 7  # a table cell's stripe colour ("#ea580c"), drawn by StripeDelegate


def tag_color(mark: Mark) -> QColor:
    """The colour of the firm's tag and stripe."""
    row = SHADES.get(mark.side, SHADES["other"])
    return QColor(row[mark.shade % len(row)])


def badge_icon(mark: Mark, height: int = TAG_HEIGHT) -> QIcon:
    """The firm's tag: its badge in white bold on a rounded rectangle of its colour, as wide as the badge needs
    ('001' wider than '1'). The view showing it needs an icon size as wide (badge_size)."""
    w, h = badge_size(height)
    pix = QPixmap(w, h)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(tag_color(mark))
    font = QFont()
    font.setBold(True)
    font.setPixelSize(max(9, int(h * 0.78)))
    text_w = QFontMetrics(font).horizontalAdvance(mark.badge) + h // 2
    box = QRectF((w - max(h, text_w)) / 2, 0, max(h, text_w), h)
    p.drawRoundedRect(box, h / 4, h / 4)
    p.setPen(QColor("white"))
    p.setFont(font)
    p.drawText(box, Qt.AlignCenter, mark.badge)
    p.end()
    return QIcon(pix)


def badge_size(height: int = TAG_HEIGHT) -> tuple[int, int]:
    """The size of a tag (badge_icon): room for three characters ('001') at this height."""
    return int(height * 2.2), height


def badge_html(mark: Mark | None, name: str) -> str:
    """A firm's name in rich text with its tag before it ('Dana Smith' after a blue 'A'); just the name (escaped)
    without a mark."""
    if mark is None:
        return html.escape(name)
    return (f"<span style='background-color:{tag_color(mark).name()}; color:white'><b>&nbsp;"
            f"{html.escape(mark.badge)}&nbsp;</b></span>&nbsp;{html.escape(name)}")


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
        size = super().sizeHint(option, index)
        return size + QSize(stripe_width(option), 0) if index.data(STRIPE_ROLE) else size
