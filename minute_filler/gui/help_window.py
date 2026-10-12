"""The Help window (Help → How to use, F1): the manual's topics (help_topics) with a contents list and a search box.

It is not modal, so it can stay open beside the job. Typing in the search box lists the topics found
(help_search), each with a line of it, the words found in bold; Enter opens the first (Up and Down choose another).
The topic shown has the words searched for highlighted. Links between topics (topic:id) open them here, Back and
Forward go through the ones seen, and other links open in the browser.

open_help(topic_id, owner) shows it: one window per owner. A modal dialog (Settings) blocks every window but its
own, so F1 there opens a window of the dialog's own (closed with it); everywhere else it is the main window's."""
from __future__ import annotations

import html
import re

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, QUrl
from PySide6.QtGui import QKeySequence, QShortcut, QTextCharFormat, QTextCursor, QTextTable
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLineEdit, QPushButton, QSplitter,
                               QStackedWidget, QTextBrowser, QTextEdit, QToolButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from .. import help_meaning, help_search
from ..help_topics import CHAPTERS, TOPICS, topic
from .widgets import open_url
from .zoom import z

FIRST = "start-steps"  # the topic shown when none is asked for
SEARCH_DELAY_MS = 150  # typing pauses this long before the search runs
PLACEHOLDER = "Search: holidays, bill by email…"


def help_topic_of(w: QWidget | None) -> str:
    """The help topic of a widget: its own help_topic property, or the nearest parent's ("" for none)."""
    while w is not None:
        t = w.property("help_topic")
        if t:
            return str(t)
        w = w.parentWidget()
    return ""


class HelpWindow(QWidget):
    """The manual: search box and contents on the left, the topic on the right. show_topic(id) opens one."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, Qt.Window)
        from .dialogs import WEBSITE_URL
        self.website = WEBSITE_URL
        self.setWindowTitle("How to use YinItAgreementForm")
        self.resize(z(900), z(680))
        self.history: list[str] = []
        self.at = -1  # where in history the topic shown is
        self.current = ""
        self.hits: list[help_search.Hit] = []
        self.chosen = 0  # the result Enter opens
        help_meaning.prepare(TOPICS)  # (the word table's topic vectors, made in the background)

        lay = QVBoxLayout(self)
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText(PLACEHOLDER)
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip("Type a few words, in your own words: it also finds words that mean the same,\n"
                               "and forgives a typo. Enter opens the first topic found; Up and Down choose.")
        self.search.installEventFilter(self)
        ll.addWidget(self.search)
        self.stack = QStackedWidget()
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.items: dict[str, QTreeWidgetItem] = {}
        for chapter in CHAPTERS:
            top = QTreeWidgetItem([chapter])
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            top.setFlags(Qt.ItemIsEnabled)
            self.tree.addTopLevelItem(top)
            for t in TOPICS:
                if t.chapter == chapter:
                    item = QTreeWidgetItem([t.title])
                    item.setData(0, Qt.UserRole, t.id)
                    item.setToolTip(0, t.title)
                    top.addChild(item)
                    self.items[t.id] = item
        self.tree.itemClicked.connect(self._tree_clicked)
        self.tree.itemActivated.connect(self._tree_clicked)
        self.stack.addWidget(self.tree)
        self.results = QTextBrowser()
        self.results.setOpenLinks(False)
        self.results.anchorClicked.connect(lambda url: self.show_topic(url.toString().removeprefix("topic:"),
                                                                       self.search.text()))
        self.stack.addWidget(self.results)
        ll.addWidget(self.stack, 1)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        nav = QHBoxLayout()
        self.back = QToolButton()
        self.back.setText("◀ Back")
        self.back.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.back.clicked.connect(lambda: self._go(-1))
        self.forward = QToolButton()
        self.forward.setText("Forward ▶")
        self.forward.clicked.connect(lambda: self._go(1))
        nav.addWidget(self.back)
        nav.addWidget(self.forward)
        nav.addStretch(1)
        rl.addLayout(nav)
        self.text = QTextBrowser()
        self.text.setOpenLinks(False)
        self.text.anchorClicked.connect(self._link)
        rl.addWidget(self.text, 1)
        split.addWidget(right)
        split.setStretchFactor(0, 1)  # (a narrower window narrows both sides, the topic less)
        split.setStretchFactor(1, 2)
        split.setSizes([z(300), z(600)])
        lay.addWidget(split, 1)

        row = QHBoxLayout()
        site = QPushButton("Open the website")
        site.setToolTip(self.website)
        site.clicked.connect(lambda: open_url(self.website))
        row.addWidget(site)
        row.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        row.addWidget(close)
        lay.addLayout(row)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(SEARCH_DELAY_MS)
        self.timer.timeout.connect(self._search)
        self.search.textChanged.connect(lambda _: self.timer.start())
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._focus_search)
        QShortcut(QKeySequence.Back, self, activated=lambda: self._go(-1))
        QShortcut(QKeySequence.Forward, self, activated=lambda: self._go(1))
        self.show_topic(FIRST)

    # --- topics
    def show_topic(self, topic_id: str, highlight: str = "", remember: bool = True) -> bool:
        """Shows the topic (False for an unknown id), the words of `highlight` marked; remember: add it to the
        history Back goes through."""
        t = topic(topic_id)
        if t is None:
            return False
        body = t.html.replace("{website}", self.website)
        self.text.setHtml(f"<h2>{html.escape(t.title)}</h2>{body}"
                          f"<p style='margin-top:18px'><i>{html.escape(t.chapter)}</i></p>")
        self.current = t.id
        if remember and (self.at < 0 or self.history[self.at] != t.id):
            del self.history[self.at + 1:]
            self.history.append(t.id)
            self.at = len(self.history) - 1
        self.back.setEnabled(self.at > 0)
        self.forward.setEnabled(self.at < len(self.history) - 1)
        item = self.items.get(t.id)
        if item is not None:
            self.tree.blockSignals(True)
            self.tree.setCurrentItem(item)
            item.parent().setExpanded(True)
            self.tree.blockSignals(False)
        self._highlight(highlight)
        return True

    def _go(self, step: int) -> None:
        """Back (-1) or Forward (1) through the topics seen."""
        if 0 <= self.at + step < len(self.history):
            self.at += step
            self.show_topic(self.history[self.at], remember=False)

    def _link(self, url: QUrl) -> None:
        """A link in a topic: topic:id opens that topic here, anything else in the browser."""
        s = url.toString()
        if s.startswith("topic:"):
            self.show_topic(s.removeprefix("topic:"))
        else:
            open_url(s)

    def _tree_clicked(self, item: QTreeWidgetItem, _col: int = 0) -> None:
        """A topic clicked in the contents opens it; a chapter's heading opens or closes the chapter."""
        tid = item.data(0, Qt.UserRole)
        if tid:
            self.show_topic(tid)
        else:
            item.setExpanded(not item.isExpanded())

    def _highlight(self, question: str) -> None:
        """Marks the question's words (by their stems: "dated" marks "dates"; "day off" marks "holiday") in the topic
        shown, and scrolls to the first."""
        stems = [s for s in help_search.marked_stems(question) if len(s) > 2] if question.strip() else []
        marks = []
        if stems:
            from PySide6.QtCore import QRegularExpression
            rx = QRegularExpression(r"\b(" + "|".join(re.escape(s) for s in stems) + r")\w*",
                                    QRegularExpression.CaseInsensitiveOption)
            fmt = QTextCharFormat()
            fmt.setBackground(self.palette().highlight())
            fmt.setForeground(self.palette().highlightedText())
            doc = self.text.document()
            cur = doc.find(rx, 0)
            while not cur.isNull():
                sel = QTextEdit.ExtraSelection()
                sel.cursor, sel.format = cur, fmt
                marks.append(sel)
                cur = doc.find(rx, cur)
        self.text.setExtraSelections(marks)
        if marks:
            c = QTextCursor(marks[0].cursor)
            c.clearSelection()
            self.text.setTextCursor(c)
            self.text.ensureCursorVisible()
        else:
            self.text.moveCursor(QTextCursor.Start)

    # --- search
    def _focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def _search(self) -> None:
        """Lists the topics found for what is typed (the contents again when the box is empty)."""
        q = self.search.text().strip()
        if not q:
            self.hits = []
            self.stack.setCurrentWidget(self.tree)
            return
        self.hits = help_search.search(q)
        self.chosen = 0
        self.stack.setCurrentWidget(self.results)
        self._show_results()

    def _show_results(self) -> None:
        """The results list: each topic's title and a line of it; the one Enter opens is marked."""
        if not self.hits:
            self.results.setHtml("<p><i>Nothing found. Try other words, or fewer.</i></p>")
            return
        pal = self.palette()
        hi, hi_text = pal.highlight().color().name(), pal.highlightedText().color().name()
        rows = []
        for n, h in enumerate(self.hits):
            style = f" style='background:{hi}; color:{hi_text}'" if n == self.chosen else ""
            colour = f" style='color:{hi_text}'" if n == self.chosen else ""
            rows.append(f"<tr><td{style}><a href='topic:{h.topic.id}'{colour}><b>{html.escape(h.topic.title)}</b>"
                        f"</a><br><small>{h.snippet}</small></td></tr>")
        bar = self.results.verticalScrollBar()
        at = bar.value()
        self.results.setHtml("<table width='100%' cellspacing='0' cellpadding='5'>" + "".join(rows) + "</table>")
        # (setHtml goes back to the top: the list is put back where it was, then scrolled to the result chosen,
        # which Down may have moved out of sight in a short window)
        bar.setValue(at)
        table = next((f for f in self.results.document().rootFrame().childFrames() if isinstance(f, QTextTable)),
                     None)
        if table is not None and self.chosen < table.rows():
            self.results.setTextCursor(table.cellAt(self.chosen, 0).firstCursorPosition())
            self.results.ensureCursorVisible()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """In the search box: Up and Down choose a result, Enter opens it, Esc empties the box."""
        if obj is self.search and event.type() == QEvent.KeyPress:
            key = event.key()
            if key in (Qt.Key_Down, Qt.Key_Up) and self.hits:
                self.chosen = max(0, min(len(self.hits) - 1, self.chosen + (1 if key == Qt.Key_Down else -1)))
                self._show_results()
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                if self.timer.isActive():  # (Enter typed before the pause: search now)
                    self.timer.stop()
                    self._search()
                if self.hits:
                    self.show_topic(self.hits[self.chosen].topic.id, self.search.text())
                return True
            if key == Qt.Key_Escape and self.search.text():
                self.search.clear()
                return True
        return super().eventFilter(obj, event)


def open_help(topic_id: str = "", owner: QWidget | None = None) -> HelpWindow:
    """Shows the Help window at the topic (the one shown before, or the first, when "" or unknown) and brings it
    forward. owner: the window it belongs to; a modal dialog that is open (Settings) takes its place, as it blocks
    every window but its own."""
    modal = QApplication.activeModalWidget()
    owner = modal or owner
    win = getattr(owner, "_help_window", None) if owner is not None else None
    if win is None:
        win = HelpWindow(owner)
        if owner is not None:
            owner._help_window = win
            if isinstance(owner, QDialog):  # (a dialog closed is only hidden: its help window would stay open)
                owner.finished.connect(win.close)
    if topic_id:
        win.show_topic(topic_id)
    if win.isMinimized():  # (show() and raise_() leave a window that was minimized in the taskbar)
        win.setWindowState(win.windowState() & ~Qt.WindowMinimized)
    win.show()
    win.raise_()
    win.activateWindow()
    return win
