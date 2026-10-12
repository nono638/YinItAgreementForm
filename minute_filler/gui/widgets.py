"""Small building blocks shared by the windows: pictures, opening files, combo boxes, checkbox rows, errors, a label
cut to its width and a label that can be clicked."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSignalBlocker, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QHBoxLayout, QLabel, QMessageBox, QSizePolicy,
                               QWidget)

from ..log import error as log_error

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def repolish(w: QWidget) -> None:
    """Re-applies the style sheet after a dynamic property changed."""
    w.style().unpolish(w)
    w.style().polish(w)


def rounded(path: Path, width: int, radius: int):
    """The picture file at `path` as a pixmap scaled to `width`, with rounded corners (HiDPI aware)."""
    from PySide6.QtGui import QPixmap
    return round_corners(QPixmap(str(path)), width, radius)


def round_corners(src, width: int, radius: int):
    """A pixmap scaled to `width` with rounded corners (HiDPI aware), e.g. a frame of the DropZone's moving
    picture. A null pixmap comes back as it is."""
    from PySide6.QtGui import QPainter, QPainterPath, QPixmap
    if src.isNull():
        return src
    dpr = QApplication.instance().devicePixelRatio() if QApplication.instance() else 1.0
    src = src.scaledToWidth(int(width * dpr), Qt.SmoothTransformation)
    out = QPixmap(src.size())
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(0, 0, src.width(), src.height(), radius * dpr, radius * dpr)
    p.setClipPath(clip)
    p.drawPixmap(0, 0, src)
    p.end()
    out.setDevicePixelRatio(dpr)
    return out


def open_path(path) -> None:
    """Opens a file or folder with its usual program; nothing happens when it no longer exists."""
    if path and Path(path).exists():
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def open_url(url: str) -> None:
    """Opens a web address in the default browser."""
    QDesktopServices.openUrl(QUrl(url))


class QuietCombo(QComboBox):
    """A combo box the mouse wheel doesn't change until it is clicked: scrolling the window over it scrolls the
    window. (A wheel over the agreement form's Speed once changed it, and made that speed the job's own choice.)"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.StrongFocus)  # (no focus from the wheel)

    def wheelEvent(self, e) -> None:
        """The wheel changes the choice only once the box has been clicked (has the focus)."""
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()  # the scroll area behind it takes the wheel


def refill_combo(combo: QComboBox, items, keep=None, tips=None) -> None:
    """Replaces a combo box's (label, data) items without firing change signals, then selects the item whose
    data is `keep` (else the first). tips: a tooltip per item, or None."""
    with QSignalBlocker(combo):
        combo.clear()
        for i, (label, data) in enumerate(items):
            combo.addItem(label, data)
            if tips and tips[i]:
                combo.setItemData(i, tips[i], Qt.ToolTipRole)
        combo.setCurrentIndex(max(0, combo.findData(keep)))


def check_row(items: dict[str, str], checked, on_toggle=None, spacing: int = 6) -> tuple[QHBoxLayout, dict]:
    """A row of checkboxes, one per key -> label, ticked for the keys in `checked`. on_toggle: connected to each
    box's toggled signal. Returns (the row, {key: checkbox})."""
    row, boxes = QHBoxLayout(), {}
    for key, label in items.items():
        cb = QCheckBox(label)
        cb.setChecked(key in checked)
        if on_toggle:
            cb.toggled.connect(on_toggle)
        boxes[key] = cb
        row.addWidget(cb)
        row.addSpacing(spacing)
    return row, boxes


def set_checks(boxes: dict[str, QCheckBox], checked) -> None:
    """Ticks exactly the boxes whose key is in `checked`, without firing their signals."""
    for key, cb in boxes.items():
        with QSignalBlocker(cb):
            cb.setChecked(key in checked)


def show_save_error(parent: QWidget, e: Exception, what: str = "Could not save", note: str = "") -> None:
    """Tells the user why a file could not be written. A locked file (open in Excel or a PDF viewer) is the
    usual reason and is said plainly; anything else goes to the log too. note: added below the message."""
    if isinstance(e, PermissionError):
        QMessageBox.warning(parent, what, f"{e}\n\nIs the file open in another program (a PDF viewer or Excel)?"
                            + note)
    else:
        log_error(what.lower(), e)
        QMessageBox.critical(parent, what, f"{type(e).__name__}: {e}{note}")


def plural(n: int, word: str) -> str:
    """plural(1, 'file') -> '1 file'; plural(3, 'file') -> '3 files'."""
    return f"{n} {word}{'' if n == 1 else 's'}"


class ElidedLabel(QLabel):
    """One line of plain text cut to the room it has, with "…" ("Jane Roe v. X.Y. Holding Corp… · 712345/2021"):
    it asks for no width of its own, so a long text never widens the window. full() is the whole text, which is
    also its tooltip."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 (Qt's name)
        """Shows text, cut to the width."""
        self._full = text
        self.setToolTip(text)
        self._elide()

    def full(self) -> str:
        """The whole text, as set."""
        return self._full

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        """No width: the label takes what the layout gives it."""
        return QSize(0, super().minimumSizeHint().height())

    def resizeEvent(self, e) -> None:  # noqa: N802
        """Cut the text again to the new width."""
        super().resizeEvent(e)
        self._elide()

    def _elide(self) -> None:
        """The text cut to the width (it is cut again each time the label is laid out at another width)."""
        width = self.width()
        super().setText(self.fontMetrics().elidedText(self._full, Qt.ElideRight, width) if width > 0 else self._full)


class ClickLabel(QLabel):
    """A label that says when it is clicked (clicked), with the pointing hand while it can be (set_clickable)."""
    clicked = Signal()

    def set_clickable(self, on: bool) -> None:
        """Whether a click means something now: the hand cursor shows it."""
        self.setCursor(Qt.PointingHandCursor if on else Qt.ArrowCursor)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        """A left click inside the label: clicked."""
        super().mouseReleaseEvent(e)
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
