"""The app's dialogs: the invoice text editor of Settings (the Settings window itself is gui/settings_dialog.py),
the "please clarify" questions before filling, the speed the agreement form names when an e-mail asks for another
(SpeedDialog), the speed each firm of a split order ordered at (SplitSpeedsDialog), the run sheet choice, a job's
invoice Peripherals (for that job only), granular detail and whose pages of a transcript of several reporters to
bill, another reporter's invoice details (ReporterDialog), the Ollama setup help (with a model download) and About.
The preview before saving, the math and the first-run welcome are in preview.py; the Excerpts window (who ordered
which pages) is gui/excerpts.py; the Help window (the manual, F1) is gui/help_window.py."""
from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QRadioButton, QTextBrowser, QVBoxLayout, QWidget,
)

from .. import __version__
from ..log import error as log_error
from ..models import Attorney, FIELD_LABELS
from ..settings import (DETAIL_ITEMS, INDEX_RULES, ReporterProfile, TEXT_PLACEHOLDERS, TEXT_PLACES, TEXT_WHEN, Settings,
                        default_invoice_texts)
from ..settings_catalog import path
from .widgets import open_url, rounded
from .zoom import z


class InvoiceTextEditor(QWidget):
    """Settings -> Invoices -> Invoice text: the invoice's own text as rows. Each row says where it goes
    (TEXT_PLACES), when it is shown (TEXT_WHEN, e.g. only when more than one party ordered) and what it says,
    with {placeholders}; the row selected is edited in the box under the list. rows() gives them as
    Settings.invoice_texts keeps them."""

    def __init__(self, rows: list[dict], on_preview=None, parent=None):
        """rows: Settings.invoice_texts (copied, not changed); on_preview: called by Preview… (no such button
        without it)."""
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.table = QListWidget()
        self.table.setMinimumHeight(z(130))
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # long rows are cut short with "…"
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.currentRowChanged.connect(self._show_row)
        lay.addWidget(self.table)
        pick = QHBoxLayout()
        self.where, self.when = QComboBox(), QComboBox()
        for combo in (self.where, self.when):  # as narrow as the Settings window needs, not as the longest choice
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(12)
        for key, label in TEXT_PLACES.items():
            self.where.addItem(label, key)
        for key, label in TEXT_WHEN.items():
            self.when.addItem(label, key)
        self.where.currentIndexChanged.connect(self._edited)
        self.when.currentIndexChanged.connect(self._edited)
        pick.addWidget(QLabel("Where:"))
        pick.addWidget(self.where, 1)
        pick.addWidget(QLabel("Show when:"))
        pick.addWidget(self.when, 1)
        lay.addLayout(pick)
        self.text = QPlainTextEdit()
        self.text.setFixedHeight(z(84))
        self.text.setPlaceholderText("What the invoice says, e.g. The {transcript} {is} delivered once every party "
                                     "has paid.")
        self.text.textChanged.connect(self._edited)
        lay.addWidget(self.text)
        buttons = QHBoxLayout()
        for label, slot, tip in (("Add", self._add, "A new row of text"),
                                 ("Remove", self._remove, "Removes the row selected"),
                                 ("Up", lambda: self._move(-1), "Moves the row up (rows in one place are shown in "
                                                                "this order)"),
                                 ("Down", lambda: self._move(1), "Moves the row down"),
                                 ("Restore defaults", self._defaults, "The text the invoice had at first"),
                                 ("Preview…", on_preview, "A made-up invoice with this text")):
            if slot is None:
                continue
            b = QPushButton(label)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            buttons.addWidget(b)
        buttons.addStretch(1)
        lay.addLayout(buttons)
        lay.addWidget(_tip(f"Placeholders: {TEXT_PLACEHOLDERS}. A row is shown only when its condition holds: "
                           "\"More than one party ordered\" for a transcript shared by several attorneys, say."))
        self._rows = [dict(r) for r in rows]
        self._loading = False
        self._refresh(0)

    def rows(self) -> list[dict]:
        """The rows as Settings.invoice_texts keeps them (blank ones left out)."""
        return [dict(r) for r in self._rows if r["text"].strip()]

    def _label(self, r: dict) -> str:
        """'Under the amounts · More than one party ordered: The {transcript} {is} delivered…'."""
        first = r["text"].strip().splitlines()[0] if r["text"].strip() else "(empty)"
        return f"{TEXT_PLACES.get(r['where'], r['where'])} · {TEXT_WHEN.get(r['when'], r['when'])}:  {first}"

    def _refresh(self, select: int) -> None:
        """Lists the rows again and selects one."""
        self.table.blockSignals(True)
        self.table.clear()
        for r in self._rows:
            self.table.addItem(self._label(r))
        self.table.blockSignals(False)
        if self._rows:
            self.table.setCurrentRow(max(0, min(select, len(self._rows) - 1)))
        self._show_row(self.table.currentRow())

    def _show_row(self, i: int) -> None:
        """Puts the row selected in the boxes under the list (empty and greyed out when there is none)."""
        has = 0 <= i < len(self._rows)
        for w in (self.where, self.when, self.text):
            w.setEnabled(has)
        self._loading = True
        if has:
            r = self._rows[i]
            self.where.setCurrentIndex(max(0, self.where.findData(r["where"])))
            self.when.setCurrentIndex(max(0, self.when.findData(r["when"])))
            self.text.setPlainText(r["text"])
        else:
            self.text.setPlainText("")
        self._loading = False

    def _edited(self, _=None) -> None:
        """A box under the list was changed: the row selected follows it."""
        i = self.table.currentRow()
        if self._loading or not 0 <= i < len(self._rows):
            return
        self._rows[i] = {"where": self.where.currentData(), "when": self.when.currentData(),
                         "text": self.text.toPlainText()}
        self.table.item(i).setText(self._label(self._rows[i]))

    def _add(self) -> None:
        """Add: a blank row under the one selected, ready to type in."""
        i = self.table.currentRow() + 1 if self._rows else 0
        self._rows.insert(i, {"where": "amounts", "when": "always", "text": ""})
        self._refresh(i)
        self.text.setFocus()

    def _remove(self) -> None:
        """Remove: the row selected goes (no asking: Cancel in Settings still brings it back)."""
        i = self.table.currentRow()
        if 0 <= i < len(self._rows):
            del self._rows[i]
            self._refresh(i)

    def _move(self, step: int) -> None:
        """Up (step -1) and Down (1): the row selected swaps places with its neighbour, and stays selected."""
        i, j = self.table.currentRow(), self.table.currentRow() + step
        if 0 <= i < len(self._rows) and 0 <= j < len(self._rows):
            self._rows[i], self._rows[j] = self._rows[j], self._rows[i]
            self._refresh(j)

    def _defaults(self) -> None:
        """Back to the text the invoice had at first (the payment and footer rows too, after asking)."""
        if QMessageBox.question(self, "Invoice text", "Put back the text the invoice had at first? Your own rows, "
                                "including your payment details, are replaced.") == QMessageBox.Yes:
            self._rows = default_invoice_texts()
            self._refresh(0)


class ClarifyDialog(QDialog):
    """Asks about blank or conflicting fields, and which attorney(s) ordered."""

    def __init__(self, questions: list[tuple[str, str, list[str]]], attorneys: list[Attorney] | None, parent=None):
        """questions: (field key, current value, other candidates) for each field to confirm.
        attorneys: shown as a checklist of who ordered, or None to skip that question.
        """
        super().__init__(parent)
        self.setWindowTitle("A few details before filling")
        self.setMinimumWidth(z(560))
        lay = QVBoxLayout(self)
        intro = QLabel("Please confirm or fill in these items. Anything left blank stays blank on the form.")
        intro.setWordWrap(True)
        intro.setObjectName("subtitle")
        lay.addWidget(intro)
        form = QFormLayout()
        form.setVerticalSpacing(8)
        self.combos: dict[str, QComboBox] = {}
        for key, current, options in questions:
            cb = QComboBox()
            cb.setEditable(True)
            cb.setInsertPolicy(QComboBox.NoInsert)
            opts = list(dict.fromkeys([current] + options)) if current else list(dict.fromkeys(options))
            cb.addItems(opts)
            cb.setCurrentText(current)
            cb.lineEdit().setPlaceholderText("(leave blank)")
            cb.setMinimumContentsLength(40)
            self.combos[key] = cb
            form.addRow(FIELD_LABELS.get(key, key), cb)
        lay.addLayout(form)

        self.att_list = None
        if attorneys:
            lbl = QLabel("Which attorney(s) ordered these minutes?  One form is made for each one checked "
                         "(a firm is one, however many of its attorneys it names).")
            lbl.setWordWrap(True)
            lbl.setObjectName("section")
            lay.addWidget(lbl)
            self.att_list = QListWidget()
            for i, a in enumerate(attorneys):
                text = " - ".join(x for x in (a.name, a.firm, a.party) if x)
                item = QListWidgetItem(text)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if a.checked else Qt.Unchecked)
                item.setData(Qt.UserRole, i)
                self.att_list.addItem(item)
            self.att_list.setMaximumHeight(z(min(200, 30 * len(attorneys) + 10)))
            lay.addWidget(self.att_list)

        buttons = QDialogButtonBox()
        buttons.addButton("Fill form", QDialogButtonBox.AcceptRole)
        buttons.addButton("Go back", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def answers(self) -> dict[str, str]:
        """The text of each question's box, by field key (blank means leave the field empty)."""
        return {k: cb.currentText().strip() for k, cb in self.combos.items()}

    def checked_attorneys(self) -> list[int] | None:
        """Indexes of the ticked attorneys, or None if the attorney question was not asked."""
        if self.att_list is None:
            return None
        return [self.att_list.item(i).data(Qt.UserRole) for i in range(self.att_list.count())
                if self.att_list.item(i).checkState() == Qt.Checked]


class SpeedDialog(QDialog):
    """Asks which speed the minute agreement form names, for jobs whose e-mail (or letter, or pasted text) asks
    for another speed than the form names now (batch.Job.speed_question): a row per job, 'Jane Roe v. Sam Poe,
    9/28/2026: the e-mail mentions "daily copy"', and a box of the speeds offered. MainWindow._ask_speeds keeps
    each answer as the user's choice for the job."""

    def __init__(self, rows: list[tuple[str, list[tuple[str, str]], str]], parent=None):
        """rows: (the question, the speeds offered as (label, name), the speed preselected) for each job."""
        super().__init__(parent)
        self.setWindowTitle("Which speed?")
        self.setMinimumWidth(z(560))
        lay = QVBoxLayout(self)
        intro = QLabel("The minute agreement form names one speed. Please choose a speed for "
                       + ("this job:" if len(rows) == 1 else "each of these jobs:"))
        intro.setWordWrap(True)
        intro.setObjectName("subtitle")
        lay.addWidget(intro)
        self.combos: list[QComboBox] = []
        for question, speeds, chosen in rows:
            lab = QLabel(question)
            lab.setWordWrap(True)
            lay.addWidget(lab)
            cb = QComboBox()
            for label, name in speeds:
                cb.addItem(label, name)
            cb.setCurrentIndex(max(0, cb.findData(chosen)))
            self.combos.append(cb)
            lay.addWidget(cb)
        buttons = QDialogButtonBox()
        buttons.addButton("Use these speeds" if len(rows) > 1 else "Use this speed", QDialogButtonBox.AcceptRole)
        buttons.addButton("Go back", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def chosen(self) -> list[str]:
        """The speed chosen for each row, in order."""
        return [cb.currentData() or "" for cb in self.combos]


INDEX_PATTERNS_TIP = (
    "Your own index number patterns, one per line: regular expressions the app tries as well as its own.\n"
    "Each finds the number and the year as two groups in parentheses, in that order, and no others\n"
    "((?:...) groups without one; or named (?P<number>...) and (?P<year>...)). Capitals don't matter.\n"
    "A number found by one of yours counts as surely as one after \"Index No.\". One that takes more\n"
    "than a second on a document is stopped there.\n\n"
    "CV-(\\d{6})-(\\d{2})/QU   finds  CV-012345-25/QU  (12345/2025)")


class SplitSpeedsDialog(QDialog):
    """Asks the speed each firm of a split order ordered at (firms that ordered the same pages commit to one:
    courthouses.speed_upfront), for the firms whose speed isn't set yet (batch.speeds_to_ask): the case's name
    above its days, then a row per day and firm (its colour's square before its name, as in the main window), with
    who it ordered the pages with ("(its speed on its other pages)" for a firm asked because it has a speed on some
    pages only) and a box of the rate sheet's speeds, set to the speed it starts from (the firm's on its other pages
    of the case, else the agreement form's), matched loosely ("Expedited" is "Expedite").
    MainWindow._ask_split_speeds keeps the answers (Job.speeds); "Go back" makes nothing."""

    def __init__(self, asks: list, speeds: list[tuple[str, str]], button: str = "Generate", parent=None,
                 marks: dict | None = None):
        """asks: batch.SpeedAsk each; speeds: the rate sheet's, (label, name) each, cheapest first; button: the
        Generate pressed, in short ("Generate", or "Generate all" for the button that says "Generate all 3 days"),
        named on OK ("Generate all with these speeds"); marks: each firm's mark by its job and key ({id(job):
        batch.trial_marks of its trial}: a firm can have another mark in another trial), its square before its name."""
        from .badges import badge_html
        super().__init__(parent)
        self.setWindowTitle("Which speed did each firm order?")
        self.setMinimumWidth(z(620))
        lay = QVBoxLayout(self)
        intro = QLabel("These firms ordered the same pages, so each one commits to a speed and is billed that "
                       "speed alone (a firm ordering by itself can still choose from its invoice). At different "
                       f"speeds, the original is divided as {path('invoice_split_rule')} says, and each "
                       "firm pays its own copies at its own speed. Which speed did each one order?")
        intro.setWordWrap(True)
        intro.setObjectName("subtitle")
        lay.addWidget(intro)
        grid = QGridLayout()
        for c, head in enumerate(("Day", "Firm", "Ordered pages with", "Speed")):
            lab = QLabel(f"<b>{head}</b>")
            grid.addWidget(lab, 0, c)
        self.combos: list[QComboBox] = []
        r, case = 1, None
        for a in asks:
            if a.job.title() and a.job.title() != case:  # the case once, above its days (a title is long)
                case = a.job.title()
                head = QLabel(case)
                head.setTextFormat(Qt.PlainText)
                font = head.font()
                font.setBold(True)
                head.setFont(font)
                grid.addWidget(head, r, 0, 1, 4)
                r += 1
            for c, text in enumerate((a.days or a.job.case.get("dates") or "(no date)", a.name,
                                      a.shared_with or "(its speed on its other pages)")):
                lab = QLabel(text)
                lab.setTextFormat(Qt.PlainText)
                mark = (marks or {}).get(id(a.job), {}).get(a.key)
                if c == 1 and mark is not None:
                    lab.setTextFormat(Qt.RichText)
                    lab.setText(badge_html(mark, text))
                lab.setWordWrap(True)
                grid.addWidget(lab, r, c)
            cb = QComboBox()
            for label, name in speeds:
                cb.addItem(label, name)
            from ..rates import speed_key
            # (spelled as on the rate sheet or not: "Expedited" is its "Expedite")
            exact = [i for i, (_, name) in enumerate(speeds) if name == a.speed]
            alike = [i for i, (_, name) in enumerate(speeds) if speed_key(name) == speed_key(a.speed)]
            cb.setCurrentIndex((exact or alike or [0])[0])
            self.combos.append(cb)
            grid.addWidget(cb, r, 3)
            r += 1
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 2)
        lay.addLayout(grid)
        lay.addWidget(_tip("The speeds are kept with each day: change them later in the Who ordered card, or in "
                           f"Who ordered which pages…; {path('split_speeds')} can bill the speeds Who "
                           "ordered shows without asking."))
        buttons = QDialogButtonBox()
        buttons.addButton(f"{button} with these speeds", QDialogButtonBox.AcceptRole)
        buttons.addButton("Go back", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def chosen(self) -> list[str]:
        """The speed chosen for each row, in order."""
        return [cb.currentData() or "" for cb in self.combos]


DEFAULTS_TIP = "Your defaults for every invoice are in Settings → Invoices."
# Peripherals... changes one job only: said at the top and the bottom of it, as it was taken for the settings
# (the user, 2026-10-30: every count says whose pages)
JOB_ONLY_TIP = ("These choices are for this job only. New jobs start from Settings → Invoices, where the {n} total "
                "pages of the automatic index are set.")


def _tip(text: str) -> QLabel:
    """A small grey note."""
    label = QLabel(text)
    label.setObjectName("muted")
    label.setWordWrap(True)
    return label


def _invoice_buttons(dlg: QDialog, on_defaults) -> QDialogButtonBox:
    """OK, Cancel and "Same as Settings" (the job's own choices given up for the defaults Settings has), which calls
    on_defaults and closes the window with OK."""
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    reset = buttons.addButton("Same as Settings", QDialogButtonBox.ResetRole)
    reset.clicked.connect(on_defaults)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    return buttons


class InvoicePeripheralsDialog(QDialog):
    """Peripherals...: what one job's invoice includes besides the original and the copies, for that job only: an
    e-mailed copy for each party, and the index (automatic, from the threshold's pages of the whole transcript;
    yes; no). It says it is for this job only, at the top and the bottom: it was taken for the settings. values()
    gives (email, index), None where it is as Settings say; on_typed() the answer to Generate's index question
    for a Pages number typed below the transcript's count (Job.index_on_typed)."""

    def __init__(self, email: bool | None, index: str | None, s: Settings, days: int = 1, parent=None,
                 typed: tuple[int, int] | None = None, on_typed: bool | None = None):
        """email, index: the job's choices (None = Settings); days: how many days the invoice covers. typed: (the
        pages typed, the transcripts' own) of the days typed below their transcripts' count, which Auto may judge
        on the number typed (on_typed: as answered; None: not asked yet, so Generate asks)."""
        super().__init__(parent)
        self.typed_answer, self.reset = on_typed, False
        self.setWindowTitle("Peripherals for this job")
        self.setMinimumWidth(z(480))
        self.s = s
        self.default_email = s.invoice_include_email
        self.default_index = "auto" if s.invoice_include_index else "off"
        lay = QVBoxLayout(self)
        intro = QLabel("For this job's invoice only" + (f" (all {days} days of the case on it)" if days > 1 else "")
                       + ":")
        intro.setObjectName("subtitle")
        lay.addWidget(intro)
        self.email = QCheckBox("An e-mailed copy for each party, for this job (Email column of the rate sheet)")
        self.email.setChecked(self.default_email if email is None else email)
        lay.addWidget(self.email)
        lay.addSpacing(6)
        from ..invoice import judge_billed
        # (no word of the judge's index when Settings leave it off)
        lay.addWidget(QLabel("Index for this job" + (" (and one for the judge)" if judge_billed(s) else "") + ":"))
        t = s.invoice_index_threshold
        self.index = QButtonGroup(self)
        self.on_typed_box = None
        if typed:
            n, whole = typed
            # (the user, 2026-10-30: every count says whose pages)
            self.on_typed_box = QCheckBox(f"Judge it on the {n:,} pages you typed, not the transcript's {whole:,} "
                                          f"total pages")
            self.on_typed_box.setToolTip("Your answer when Generate asked (Est. number of pages typed below the\n"
                                         "transcript's count). Not asked yet: Generate asks. Same as Settings\n"
                                         "has it ask again.")
            self.on_typed_box.setChecked(bool(on_typed))
        for key, label in (("auto", f"Auto: when the whole transcript has {t} total pages or more"),
                           ("on", "Yes, for this job (however short the transcript)"), ("off", "No, for this job")):
            rb = QRadioButton(label)
            rb.setProperty("key", key)
            rb.setChecked(key == (self.default_index if index is None else index))
            self.index.addButton(rb)
            lay.addWidget(rb)
            if key == "auto" and self.on_typed_box is not None:  # (under Auto, which it is part of)
                self.on_typed_box.setEnabled(rb.isChecked())
                rb.toggled.connect(self.on_typed_box.setEnabled)
                row = QHBoxLayout()
                row.addSpacing(z(22))
                row.addWidget(self.on_typed_box, 1)
                lay.addLayout(row)
        rule = f" Several days: {INDEX_RULES.get(s.invoice_index_rule, '').lower()}." if days > 1 else ""
        lay.addWidget(_tip(f"Auto counts every reporter's pages of the transcript, not only yours.{rule}"))
        lay.addSpacing(6)
        lay.addWidget(_tip(JOB_ONLY_TIP.format(n=t)))
        lay.addWidget(_invoice_buttons(self, self._defaults))

    def _defaults(self):
        """Same as Settings: the boxes as Settings say, and the window closes with OK (values() gives (None,
        None))."""
        self.email.setChecked(self.default_email)
        for b in self.index.buttons():
            b.setChecked(b.property("key") == self.default_index)
        self.reset = True  # (Generate asks about a typed count again)
        self.accept()

    def on_typed(self) -> bool | None:
        """Whether Auto judges the index of the typed days on the number typed (Job.index_on_typed): the box as
        left; None (Generate asks) when there is no box, after Same as Settings, or when it was never answered
        and is left unticked."""
        if self.on_typed_box is None or self.reset:
            return None
        ticked = self.on_typed_box.isChecked()
        return None if self.typed_answer is None and not ticked else ticked

    def values(self) -> tuple[bool | None, str | None]:
        """(email, index) for the job; None where the choice is the same as Settings, so it follows them."""
        email = self.email.isChecked()
        b = self.index.checkedButton()
        index = b.property("key") if b else self.default_index
        return (None if email == self.default_email else email), (None if index == self.default_index else index)


class InvoiceShowDialog(QDialog):
    """What "Show granular detail" adds to one job's invoice (keys of DETAIL_ITEMS). values() gives the list,
    or None when it is the same as Settings."""

    def __init__(self, items: list | None, s: Settings, parent=None):
        """items: the job's choice (None = Settings.invoice_detail_items)."""
        super().__init__(parent)
        self.setWindowTitle("Granular detail")
        self.setMinimumWidth(z(420))
        self.default = list(s.invoice_detail_items)
        lay = QVBoxLayout(self)
        intro = QLabel("With \"Show granular detail\" ticked, this job's invoice also shows:")
        intro.setObjectName("subtitle")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        chosen = self.default if items is None else items
        self.boxes: dict[str, QCheckBox] = {}
        for key, label in DETAIL_ITEMS.items():
            cb = QCheckBox(label)
            cb.setChecked(key in chosen)
            self.boxes[key] = cb
            lay.addWidget(cb)
        lay.addSpacing(6)
        lay.addWidget(_tip(f"\"{DETAIL_ITEMS['days']}\" is shown when the invoice covers several days. "
                           + DEFAULTS_TIP))
        lay.addWidget(_invoice_buttons(self, self._defaults))

    def _defaults(self):
        """Same as Settings: the boxes as Settings say, and the window closes with OK (values() gives None)."""
        for key, cb in self.boxes.items():
            cb.setChecked(key in self.default)
        self.accept()

    def values(self) -> list | None:
        """The items ticked; None when they are the same as Settings, so the job follows them."""
        items = [k for k, cb in self.boxes.items() if cb.isChecked()]
        return None if set(items) == set(self.default) else items


class PagesOwnerDialog(QDialog):
    """Whose pages…: for each transcript several reporters wrote (their initials alternate at the foot of its
    pages), whose pages to bill: the user's own (the default), any of the other reporters' (each on invoices in
    their name, with the details Settings keep for them: Details... edits them), or the whole transcript; and,
    when it begins with pages nobody's initials are on, whose those are. values() gives Job.page_basis and
    Job.front_owner for these transcripts."""

    def __init__(self, transcripts: list[tuple[str, str, list[str]]], own: set[str], basis: dict, front: dict,
                 reason: str = "", parent=None, settings: Settings | None = None):
        """transcripts: (Doc.key(), file name, Doc.owners()) of each transcript to ask about; own: the user's
        initials (empty when not known); basis, front: the job's Job.page_basis and Job.front_owner; reason:
        why the dialog opened by itself (shown at the top); settings: where the other reporters' details are
        kept (Details... saves them there)."""
        super().__init__(parent)
        self.setWindowTitle("Whose pages to bill")
        self.setMinimumWidth(z(520))
        self.own = set(own)
        self.s = settings
        self.items: list[dict] = []
        lay = QVBoxLayout(self)
        intro = QLabel("These transcripts have pages by more than one reporter: the initials at the foot of the pages "
                       "change. An invoice bills your own pages unless you choose otherwise. Tick another reporter "
                       "to make the invoices for their pages too, in their name.")
        intro.setObjectName("subtitle")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        if reason:
            why = QLabel("⚠ " + reason[0].upper() + reason[1:])
            why.setObjectName("problem")
            why.setWordWrap(True)
            lay.addWidget(why)
        for key, name, owners in transcripts:
            found = list(dict.fromkeys(o for o in owners if o))
            leading = next((i for i, o in enumerate(owners) if o), 0)
            frame = QFrame()
            frame.setObjectName("outputPanel")
            fl = QVBoxLayout(frame)
            title = QLabel(name)
            title.setObjectName("section")
            fl.addWidget(title)
            # "radios" holds checkboxes now (several reporters can be billed at once); the name stayed
            item = {"key": key, "owners": owners, "found": found, "radios": {}, "front": None, "count": QLabel("")}
            item["count"].setObjectName("muted")
            item["count"].setWordWrap(True)
            fl.addWidget(item["count"])
            if len(found) > 1 and leading:
                row = QHBoxLayout()
                pages = "page has" if leading == 1 else f"{leading} pages have"
                row.addWidget(QLabel(f"The first {pages} no reporter's initials. They count for:"))
                combo = QComboBox()
                combo.addItem("Choose…", None)
                for x in found:
                    combo.addItem(x.upper() + (" (you)" if x in self.own else ""), x)
                combo.addItem("Nobody (not billed)", "none")
                current = front.get(key)
                if current is not None:
                    combo.setCurrentIndex(max(0, combo.findData(current)))
                combo.currentIndexChanged.connect(self._update)
                row.addWidget(combo)
                row.addStretch(1)
                fl.addLayout(row)
                item["front"] = combo
            choices = [("me", "My pages")] + [(x, f"{x.upper()}'s pages") for x in found if x not in self.own] + [
                ("*", "The whole transcript")]
            row = QHBoxLayout()
            row.addWidget(QLabel("Bill:"))
            for value, label in choices:
                cb = QCheckBox(label)
                if value == "me" and not self.own:
                    cb.setEnabled(False)
                    cb.setToolTip("Your initials aren't known: enter them under Settings → My info")
                elif value not in ("me", "*"):
                    cb.setToolTip(f"Invoices in {value.upper()}'s name for their pages, numbered apart from yours")
                item["radios"][value] = cb
                cb.toggled.connect(lambda on, it=item, v=value: self._ticked(it, v, on))
                row.addWidget(cb)
                if value not in ("me", "*") and self.s is not None:
                    more = QPushButton("Details…")
                    more.setToolTip(f"{value.upper()}'s name, address and payment details, for their invoices")
                    more.clicked.connect(lambda _=False, v=value: self._details(v))
                    row.addWidget(more)
            row.addStretch(1)
            fl.addLayout(row)
            v = basis.get(key, "me")
            chosen = [x for x in ([v] if isinstance(v, str) else v if isinstance(v, list) else [])
                      if x in item["radios"] and item["radios"][x].isEnabled()]
            if not chosen:
                chosen = ["*" if not self.own else "me"]
            for x in chosen:
                with QSignalBlocker(item["radios"][x]):
                    item["radios"][x].setChecked(True)
            item["labels"] = dict(choices)
            lay.addWidget(frame)
            self.items.append(item)
        self.error = QLabel("")
        self.error.setObjectName("problem")
        self.error.setWordWrap(True)
        self.error.setVisible(False)
        lay.addWidget(self.error)
        ok = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok.accepted.connect(self.accept)
        ok.rejected.connect(self.reject)
        lay.addWidget(ok)
        self._update()

    def _ticked(self, item: dict, value: str, on: bool) -> None:
        """A box ticked or unticked: the whole transcript goes alone (it bills every page, on the user's
        invoices); some pages must stay billed (the last box can't be unticked)."""
        boxes = item["radios"]
        if on and value == "*":
            others = [b for v, b in boxes.items() if v != "*"]
        elif on:
            others = [boxes["*"]]
        else:
            others = []
            if not any(b.isChecked() for b in boxes.values()):
                with QSignalBlocker(boxes[value]):
                    boxes[value].setChecked(True)
        for b in others:
            with QSignalBlocker(b):
                b.setChecked(False)
        self._update()

    def _details(self, initials: str) -> None:
        """Details...: another reporter's invoice details, saved in the settings at once."""
        dlg = ReporterDialog(initials, self.s.reporter(initials), self)
        if dlg.exec() == QDialog.Accepted:
            self.s.reporters = {**self.s.reporters, initials: dlg.value()}
            try:
                self.s.save()
            except OSError as e:
                # (kept in the settings all the same, as Settings' own Save keeps them: saved again on closing)
                log_error("could not save the settings", e)
                QMessageBox.warning(self, "Could not save the settings",
                                    f"{type(e).__name__}: {e}\n\nThese details are kept for now and saved again "
                                    "when the app closes.")

    @staticmethod
    def _count(owners: list[str], targets: set[str], front: str | None) -> int:
        """How many pages are the targets' (pages without initials at the start count for `front`)."""
        return sum(1 for o in owners if (o or front or "") in targets)

    def _update(self, _=None) -> None:
        """Each transcript's line of who wrote what, and the page count on each choice, as chosen now."""
        for item in self.items:
            owners, found = item["owners"], item["found"]
            if item["front"] is not None:
                front = item["front"].currentData()
            else:
                front = found[0] if len(found) == 1 else None
            # (the user, 2026-10-30: every count says whose pages): "150 total pages · PR (you): 65 pages · ..."
            parts = [f"{x.upper()}{' (you)' if x in self.own else ''}: {self._count(owners, {x}, front)} pages"
                     for x in found]
            unknown = sum(1 for o in owners if not o and front in (None, "none"))  # (Nobody: still no initials)
            if unknown:
                parts.append(f"no initials: {unknown} pages")
            item["count"].setText(f"{len(owners)} total pages · " + " · ".join(parts))
            for value, rb in item["radios"].items():
                n = len(owners) if value == "*" else self._count(owners, self.own if value == "me" else {value}, front)
                rb.setText(f"{item['labels'][value]} ({n})")

    def problem(self) -> str:
        """What must still be chosen ("" when nothing): whose the first pages are, when the pages billed depend
        on it."""
        for item in self.items:
            combo = item["front"]
            if combo is not None and combo.currentData() is None and not item["radios"]["*"].isChecked():
                return "Choose whose the first pages are (or bill the whole transcript)."
        return ""

    def accept(self):
        """Closes with OK once nothing is left to choose (else says what)."""
        why = self.problem()
        self.error.setText(why)
        self.error.setVisible(bool(why))
        if not why:
            super().accept()

    def values(self) -> tuple[dict, dict]:
        """(Job.page_basis, Job.front_owner) for the transcripts shown: by Doc.key(), "me", initials or "*", or a
        list of "me" and initials when several are ticked; and the initials (or "none") the first pages count
        for."""
        basis, front = {}, {}
        for item in self.items:
            ticked = [v for v, cb in item["radios"].items() if cb.isChecked()] or ["me"]
            basis[item["key"]] = ticked[0] if len(ticked) == 1 else ticked
            if item["front"] is not None and item["front"].currentData() is not None:
                front[item["key"]] = item["front"].currentData()
        return basis, front


class ReporterDialog(QDialog):
    """Another reporter's details, for the invoices the user makes for their pages: name, address, how to pay
    them, and how their invoice numbers begin. value() gives them (a settings.ReporterProfile)."""

    def __init__(self, initials: str, profile: ReporterProfile, parent=None):
        """initials: the reporter's ("ds"); profile: their details so far, shown to edit."""
        super().__init__(parent)
        self.setWindowTitle(f"Invoices for {initials.upper()}")
        self.setMinimumWidth(z(520))
        self.initials, self.base = initials, profile
        lay = QVBoxLayout(self)
        intro = QLabel(f"The invoices you make for {initials.upper()}'s pages carry these details instead of yours, "
                       "and their own numbers. Your earnings in Records leave them out.")
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        lay.addWidget(intro)
        f = QFormLayout()
        self.name = QLineEdit(profile.name)
        self.name.setToolTip("As the run sheet's Reporter column says it")
        self.full_name = QLineEdit(profile.full_name)
        self.full_name.setPlaceholderText(profile.name or "Dana Smith")
        self.title = QLineEdit(profile.title)
        self.address1, self.address2 = QLineEdit(profile.address1), QLineEdit(profile.address2)
        self.phone, self.email = QLineEdit(profile.phone), QLineEdit(profile.email)
        self.payment = QPlainTextEdit(profile.payment)
        self.payment.setPlaceholderText("Zelle: ...\nCheck: payable to ...")
        self.payment.setFixedHeight(z(90))
        self.prefix = QLineEdit(profile.prefix)
        self.prefix.setPlaceholderText(initials.upper())
        self.prefix.setToolTip("Their invoice numbers: this, a dash and your number format (DS-2026-0001), "
                               "counted apart from yours")
        for label, w in (("Name (run sheet)", self.name), ("Name on invoices", self.full_name),
                         ("Title", self.title), ("Address", self.address1), ("", self.address2),
                         ("Phone", self.phone), ("E-mail", self.email), ("Payment", self.payment),
                         ("Numbers begin with", self.prefix)):
            f.addRow(label, w)
        lay.addLayout(f)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def value(self) -> ReporterProfile:
        """The details as entered (spaces trimmed; the prefix without spaces)."""
        return ReporterProfile(
            name=self.name.text().strip(), full_name=self.full_name.text().strip(),
            title=self.title.text().strip(), address1=self.address1.text().strip(),
            address2=self.address2.text().strip(), phone=self.phone.text().strip(), email=self.email.text().strip(),
            payment=self.payment.toPlainText().strip(), prefix="".join(self.prefix.text().split()))


class RunSheetDialog(QDialog):
    """Asks whether a transcript's takes go on a run sheet that seems to be this case's, or on a new one."""

    def __init__(self, found: list, title: str, parent=None):
        """found: runsheet.Found entries, the likeliest first. title: the job, as the window names it."""
        super().__init__(parent)
        self.setWindowTitle("Run sheet")
        self.setMinimumWidth(z(520))
        lay = QVBoxLayout(self)
        intro = QLabel(f"There may already be a run sheet for {title}. Add this transcript's takes to it, or start "
                       "a new run sheet?")
        intro.setWordWrap(True)
        intro.setObjectName("subtitle")
        lay.addWidget(intro)
        if any(f.why == "name" for f in found):
            note = QLabel("A run sheet with the same case name but another index number may be the same trial: "
                          "several index numbers are often billed together.")
            note.setWordWrap(True)
            note.setObjectName("muted")
            lay.addWidget(note)
        self.group = QButtonGroup(self)
        for i, f in enumerate(found):
            rb = QRadioButton(f"Add to  {f.path.name}\n({f.reason()}{'' if f.ours else ', made elsewhere'})")
            rb.setToolTip(str(f.path))
            rb.setProperty("path", str(f.path))
            rb.setChecked(i == 0)
            self.group.addButton(rb)
            lay.addWidget(rb)
        rb = QRadioButton("Start a new run sheet")
        rb.setProperty("path", "")
        self.group.addButton(rb)
        lay.addWidget(rb)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def choice(self) -> str:
        """The run sheet to add to, or "" for a new one."""
        b = self.group.checkedButton()
        return b.property("path") if b else ""


OLLAMA_GUIDE = """
<h3>Optional: local AI helper (Ollama + gemma)</h3>
<p>The app works without AI. Photos and scanned PDFs are read by <b>Windows' built-in text recognition (OCR)</b>,
which needs no setup and takes about 2 seconds. The AI model is an optional second pass that <i>organizes</i>
the text. It is most useful for informal e-mails, where it can pick out names, firms and dates that the
built-in rules miss. Everything runs on this computer; nothing is sent to the internet.</p>

<h4>1. Install Ollama</h4>
<ol>
<li>Go to <a href="https://ollama.com/download">https://ollama.com/download</a> and download <b>Ollama for Windows</b>.</li>
<li>Run <b>OllamaSetup.exe</b>. Ollama starts by itself and shows a llama icon in the system tray.
It starts automatically with Windows from then on.</li>
</ol>

<h4>2. Download the model</h4>
<p>Click <b>Download {model}</b> below, <i>or</i> open PowerShell and run:</p>
<pre>   ollama pull {model}</pre>
<p>The download is several gigabytes (4.6 to 7.5 GB for gemma4:e2b and 6.6 to 9.5 GB for gemma4:e4b, depending
on the version Ollama picks for your computer), so allow time on a
slow connection. <code>ollama list</code> shows the installed models.</p>
<p><b>Which model?</b> Settings → AI helper → Model offers two. <b>gemma4:e2b</b> is smaller and faster, and the usual
choice. <b>gemma4:e4b</b> is larger and more accurate, but much slower on a laptop without a graphics card
(GPU). Choose the model there first: this window downloads the one chosen.</p>

<h4>3. Check it</h4>
<p>Close this window and click <b>Test connection</b> in Settings → AI helper. The main window shows "● AI ready" at the
bottom left.</p>

<h4>What to expect</h4>
<p>On a laptop without a dedicated graphics card, the model runs on the processor, so each document takes about
<b>30–60 seconds</b>. The app shows the rule-based results right away and adds the AI suggestions when they
arrive, and you can keep editing in the meantime. Suggestions from the AI have a purple <b>AI</b> badge.
A computer with an NVIDIA graphics card is several times faster.</p>

<h4>If photos come out blank (Windows OCR missing)</h4>
<p>English Windows normally includes OCR. If it is missing, open PowerShell <b>as administrator</b> and run:</p>
<pre>   Add-WindowsCapability -Online -Name "Language.OCR~~~en-US~0.0.1.0"</pre>
"""


class _PullThread(QThread):
    """Downloads an Ollama model in the background (the model is several GB).

    progress carries the status text and a percentage (-1 when unknown); finished_ok carries the
    final message, a tick or a cross, whichever way it ended.
    """
    progress = Signal(str, int)   # status text, percent (-1 = unknown)
    finished_ok = Signal(str)

    def __init__(self, model: str, host: str):
        """model: the Ollama model name; host: the Ollama URL (empty for the default)."""
        super().__init__()
        self.model, self.host = model, host

    def run(self):
        """Streams the download and reports progress. Any error, including Ollama not running, is turned into a
        message."""
        try:
            import ollama
            from ..extract_llm import client_options
            # (no timeout: a model is GBs. Ollama on this computer reached directly, as every other client of it
            # is: a proxy set up in Windows may not pass "localhost" on)
            client = ollama.Client(host=self.host or None, timeout=None, **client_options(self.host))
            for part in client.pull(self.model, stream=True):
                total, done = getattr(part, "total", None), getattr(part, "completed", None)
                pct = int(done * 100 / total) if total and done else -1
                self.progress.emit(getattr(part, "status", "") or "", pct)
            self.finished_ok.emit(f"✓ {self.model} is installed.")
        except Exception as e:
            msg = str(e)
            if "connect" in msg.lower() or "refused" in msg.lower():
                msg = "Ollama is not running. Install it (step 1) and try again."
            self.finished_ok.emit(f"✗ {msg}")


class OllamaHelpDialog(QDialog):
    """Step-by-step help for installing Ollama, with a button that downloads the model.

    The download keeps going if the dialog is closed (see _BACKGROUND).
    """
    def __init__(self, model: str, host: str, parent=None):
        """model: the model the guide and download button refer to; host: the Ollama URL."""
        super().__init__(parent)
        self.model, self.host = model, host
        self.setWindowTitle("Setting up the AI helper")
        self.resize(z(640), z(640))
        lay = QVBoxLayout(self)
        text = QTextBrowser()
        text.setOpenExternalLinks(True)
        text.setHtml(OLLAMA_GUIDE.replace("{model}", model))
        lay.addWidget(text, 1)
        row = QHBoxLayout()
        self.pull_btn = QPushButton(f"Download {model}")
        self.pull_btn.clicked.connect(self._pull)
        site = QPushButton("Open ollama.com/download")
        site.clicked.connect(lambda: open_url("https://ollama.com/download"))
        row.addWidget(site)
        row.addWidget(self.pull_btn)
        row.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        self.bar = QProgressBar()
        self.bar.setVisible(False)
        self.bar.setTextVisible(False)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        lay.addWidget(self.bar)
        lay.addWidget(self.status)
        lay.addLayout(row)
        self.thread = None
        # a download started before, from this help closed since, still going: shown here, and Download stays
        # off until it ends (pressed again, it would download the model a second time beside it)
        running = next((t for t in _BACKGROUND if isinstance(t, _PullThread) and not t.isFinished()), None)
        if running is not None:
            self._follow(running, "Downloading (started before)…")

    def _pull(self):
        """Starts the model download on a background thread and shows the progress bar."""
        thread = _PullThread(self.model, self.host)
        self._follow(thread, "Starting download…")
        # kept from the start, not only when the dialog closes: the app can quit with the dialog still open
        # (Windows logging off), and the dialog's own reference goes with it (finished downloads let go here)
        _BACKGROUND[:] = [t for t in _BACKGROUND if not t.isFinished()] + [thread]
        thread.start()

    def _follow(self, thread: "_PullThread", status: str) -> None:
        """Shows a download's progress here, Download greyed out until it ends (the thread's own end too: a
        download that ended as this help opened gives Download back)."""
        self.thread = thread
        self.pull_btn.setEnabled(False)
        self.bar.setVisible(True)
        self.bar.setRange(0, 0)
        self.status.setText(status)
        thread.progress.connect(self._progress)
        thread.finished_ok.connect(self._done)
        thread.finished.connect(self._ended)  # (a method, not a lambda: let go when this help is deleted)
        if thread.isFinished():  # (it ended between the look in __init__ and now)
            self._ended()

    def _ended(self) -> None:
        """The download followed ended (its message, if it reached this help, is shown by _done): Download is
        offered again."""
        self.bar.setVisible(False)
        self.pull_btn.setEnabled(True)

    def _progress(self, status: str, pct: int):
        """Shows download progress: a percentage bar when the total is known, a busy bar otherwise."""
        if pct >= 0:
            self.bar.setRange(0, 100)
            self.bar.setValue(pct)
            self.status.setText(f"{status}  {pct}%")
        else:
            self.bar.setRange(0, 0)
            self.status.setText(status)

    def _done(self, msg: str):
        """Hides the progress bar, shows the final message and allows a new download."""
        self.bar.setVisible(False)
        self.status.setText(msg)
        self.pull_btn.setEnabled(True)

    def reject(self):
        """Escape or the window's close button behaves like Close (a download still running goes on)."""
        self.accept()


# Downloads, from the moment each starts (OllamaHelpDialog._pull), so they outlive their dialog. Qt aborts the
# program if a QThread is destroyed while it still runs, so a reference is kept here until it is finished (let
# go at the next download); main() doesn't wait at exit for one still running (os._exit).
_BACKGROUND: list[QThread] = []


CONTACT_EMAIL = "noahcollincourtreporter@gmail.com"
WEBSITE_URL = "https://nono638.github.io/YinItAgreementForm/"
SOURCE_URL = "https://github.com/nono638/YinItAgreementForm"
FEEDBACK_URL = f"mailto:{CONTACT_EMAIL}?subject=YinItAgreementForm%20{__version__}"
COFFEE_URL = "https://buymeacoffee.com/noahcollin"
# The About window's disclaimer (the AGPL's own, sections 15 and 16, in short)
NO_WARRANTY = ("<b>No warranty.</b> This program is provided \"as is\", without warranty of any kind, express or "
               "implied, including the implied warranties of merchantability and fitness for a particular purpose. "
               "You are responsible for checking every form, invoice and amount it makes before you use or send "
               "it; it is not legal, billing or tax advice. The author is not liable for any loss or damage "
               "arising from its use (sections 15 and 16 of the license).")

COMPONENTS = [
    ("Qt / PySide6", "LGPL-3.0", "https://www.qt.io/qt-for-python"),
    ("PyMuPDF", "AGPL-3.0 (or Artifex commercial license)", "https://pymupdf.readthedocs.io"),
    ("Pillow", "MIT-CMU", "https://python-pillow.org"),
    ("ollama-python", "MIT", "https://github.com/ollama/ollama-python"),
    ("PyWinRT (Windows OCR bindings)", "MIT", "https://github.com/pywinrt/pywinrt"),
    ("openpyxl (run sheets)", "MIT", "https://openpyxl.readthedocs.io"),
    ("RapidFuzz (the Records search's Fuzzy box, typos in the Help search)", "MIT",
     "https://github.com/rapidfuzz/RapidFuzz"),
    ("regex (the Records search's Regex box)", "Apache-2.0 and CNRI-Python", "https://github.com/mrabarnett/mrab-regex"),
    ("pillow-heif (iPhone HEIC photos)", "BSD-3-Clause", "https://github.com/bigcat88/pillow_heif"),
    ("libheif and libde265 (used by pillow-heif)", "LGPL-3.0", "https://github.com/strukturag/libheif"),
    ("x265 (used by pillow-heif)", "GPL-2.0-or-later", "https://www.videolan.org/developers/x265.html"),
    ("et_xmlfile (used by openpyxl)", "MIT", "https://foss.heptapod.net/openpyxl/et_xmlfile"),
    ("HTTPX (used by ollama-python)", "BSD-3-Clause", "https://www.python-httpx.org"),
    ("httpcore, h11, anyio, idna (used by HTTPX)", "BSD-3-Clause and MIT", "https://github.com/encode/httpcore"),
    ("certifi (used by HTTPX)", "MPL-2.0", "https://github.com/certifi/python-certifi"),
    ("Pydantic (used by ollama-python)", "MIT", "https://docs.pydantic.dev"),
    ("OpenSSL (the look for a newer version)", "Apache-2.0", "https://www.openssl.org"),
    ("SQLite (the records)", "public domain", "https://www.sqlite.org"),
    ("Python", "PSF License", "https://www.python.org"),
    ("EmbeddingGemma 2 by Google (the help search's word table is made from it)", "Apache-2.0",
     "https://huggingface.co/google/embeddinggemma-2"),
]


class AboutDialog(QDialog):
    """The About window: version, author, licence, links, where settings are kept and the open-source credits."""
    def __init__(self, parent=None):
        """Builds the window; the version and settings folder shown come from the running program."""
        super().__init__(parent)
        from pathlib import Path
        from ..settings import settings_dir
        self.setWindowTitle("About YinItAgreementForm")
        self.setMinimumWidth(z(560))
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        pic = Path(__file__).resolve().parent.parent / "assets" / "yin_done.jpg"
        img = None
        if pic.exists():
            img = QLabel()
            img.setPixmap(rounded(pic, 420, 12))
            img.setAlignment(Qt.AlignCenter)
            lay.addWidget(img)
        title = QLabel("YinItAgreementForm")
        title.setObjectName("title")
        lay.addWidget(title)
        ver = QLabel(f"Version {__version__}")
        ver.setObjectName("muted")
        lay.addWidget(ver)
        body = QLabel(
            "Fills in New York UCS Court Reporter Minute Agreement Forms from transcripts, invoices, "
            "photos and e-mails. (It was called DjinnItAgreementForm before version 2.0.)<br>"
            f'Website, with a guide and the latest version: <a href="{WEBSITE_URL}">'
            f'{WEBSITE_URL.split("//")[1].rstrip("/")}</a><br><br>'
            "Created by <b>Noah Collin</b>, Senior Court Reporter.<br>"
            f'Questions, bugs or ideas: <a href="mailto:{CONTACT_EMAIL}?subject=YinItAgreementForm">'
            f"{CONTACT_EMAIL}</a><br><br>"
            "Free software under the GNU AGPL-3.0 license."
            + (f' Source code: <a href="{SOURCE_URL}">{SOURCE_URL}</a>' if SOURCE_URL else "")
            + f"<br><br>{NO_WARRANTY}"
            + f'<br><br>If this saves you time, you can <a href="{COFFEE_URL}">buy me a coffee</a> ☕')
        body.setWordWrap(True)
        body.setMinimumWidth(z(520))  # so its height is measured at the width it's shown at (else the end is cut)
        body.setTextFormat(Qt.RichText)
        body.setOpenExternalLinks(True)
        lay.addWidget(body)
        where = QLabel(f"Settings and rate sheets: {settings_dir()}")
        where.setObjectName("muted")
        where.setWordWrap(True)
        where.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(where)
        row = QHBoxLayout()
        credits = QPushButton("Open-source components")
        credits.clicked.connect(self._credits)
        mail = QPushButton("Email Noah")
        mail.clicked.connect(lambda: open_url(FEEDBACK_URL))
        coffee = QPushButton("☕  Buy me a coffee")
        coffee.clicked.connect(lambda: open_url(COFFEE_URL))
        ok = QPushButton("Close")
        ok.clicked.connect(self.accept)
        row.addWidget(credits)
        row.addWidget(mail)
        row.addWidget(coffee)
        row.addStretch(1)
        row.addWidget(ok)
        lay.addLayout(row)
        # Qt opens a window at most 2/3 of the screen tall, which cut off the end of the text on a laptop at 125 %
        # (1080 px): as tall as it needs, as long as the screen has room; short of room (a high zoom on a small
        # screen), the picture gets smaller first, or goes, so the text is all there
        hint, screen = self.sizeHint(), self.screen()
        room = screen.availableGeometry().height() - z(40) if screen else hint.height()
        if img is not None and hint.height() > room:
            tall = img.pixmap().deviceIndependentSize().height()
            keep = tall - (hint.height() - room)
            if keep >= z(60):
                img.setPixmap(rounded(pic, int(420 * keep / tall), 12))
            else:
                img.hide()
            hint = self.sizeHint()
        self.resize(hint.width(), min(hint.height(), room))

    def _credits(self):
        """Shows the list of open-source components (COMPONENTS) and how the optional AI features are supplied."""
        box = QDialog(self)
        box.setWindowTitle("Open-source components")
        box.resize(z(520), z(360))
        lay = QVBoxLayout(box)
        t = QTextBrowser()
        t.setOpenExternalLinks(True)
        rows = "".join(f'<tr><td><a href="{u}">{n}</a></td><td>&nbsp;&nbsp;{l}</td></tr>' for n, l, u in COMPONENTS)
        t.setHtml(f"<p>This program is built with these open-source components:</p><table>{rows}</table>"
                  "<p>Optional AI features use <a href='https://ollama.com'>Ollama</a> (MIT) and Google's "
                  "Gemma 4 models (Apache-2.0), installed separately by the user. Text recognition uses "
                  "the OCR engine built into Windows.</p>")
        lay.addWidget(t)
        b = QPushButton("Close")
        b.clicked.connect(box.accept)
        lay.addWidget(b, 0, Qt.AlignRight)
        box.exec()
