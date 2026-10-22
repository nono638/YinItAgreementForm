"""How a firm's mark (firm_marks.Mark: '1', 'A', '001') looks in the window: a small tag in its side's strong colour
with the badge in white (badge_icon, beside the firm's name in a table; badge_html in rich text), and a pale
shade of the same colour behind the name (background). Plaintiffs' firms in oranges, the defense in blues, the
others in grey-greens (the user, 2026-10-21): orange against blue stays apart for the commoner colour blindness;
the firms of one side are told apart by their badges, their shades only helping. Each colour has a light and a
dark theme version: a pale shade under dark text, a deep one under light text."""
from __future__ import annotations

import html

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPixmap

from ..firm_marks import DEFENSE, PLAINTIFF, Mark

# by side, for each shade: (behind the name, light theme; behind the name, dark theme; the tag)
SHADES = {
    PLAINTIFF: [("#fed7aa", "#7c2d12", "#ea580c"), ("#fde68a", "#78350f", "#b45309"),
                ("#fdba74", "#9a3412", "#c2410c"), ("#fcd34d", "#92400e", "#d97706")],
    DEFENSE: [("#bfdbfe", "#1e3a8a", "#2563eb"), ("#a5f3fc", "#164e63", "#0e7490"),
              ("#c7d2fe", "#312e81", "#4f46e5"), ("#93c5fd", "#1e40af", "#1d4ed8")],
    "other": [("#d1fae5", "#064e3b", "#047857"), ("#e5e7eb", "#374151", "#4b5563"),
              ("#bbf7d0", "#14532d", "#15803d")],
}


TAG_HEIGHT = 18  # a tag's height in a table, before zoom (zoom.z): its badge has to read at a glance


def _shade(mark: Mark) -> tuple[str, str, str]:
    row = SHADES.get(mark.side, SHADES["other"])
    return row[mark.shade % len(row)]


def background(mark: Mark, dark: bool) -> QColor:
    """The shade behind the firm's name, in the light or the dark theme."""
    light, deep, _ = _shade(mark)
    return QColor(deep if dark else light)


def tag_color(mark: Mark) -> QColor:
    """The colour of the firm's tag (the same in both themes: white text on it reads in either)."""
    return QColor(_shade(mark)[2])


def badge_icon(mark: Mark, height: int = TAG_HEIGHT) -> QIcon:
    """The firm's tag: its badge in white bold on a rounded rectangle of its tag colour, as wide as the badge
    needs ('001' wider than '1'). The view showing it needs an icon size as wide (badge_size)."""
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


def badge_html(mark: Mark | None, name: str, dark: bool) -> str:
    """A firm's name in rich text with its tag before it and its shade behind it ('Dana Smith' with a blue 'A');
    just the name (escaped) without a mark."""
    if mark is None:
        return html.escape(name)
    return (f"<span style='background-color:{tag_color(mark).name()}; color:white'><b>&nbsp;"
            f"{html.escape(mark.badge)}&nbsp;</b></span>&nbsp;<span style='background-color:"
            f"{background(mark, dark).name()}'>{html.escape(name)}</span>")
