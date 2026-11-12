"""The Settings window: a list of pages on the left (settings_catalog.PAGES, each with a line saying what is on it),
a "Find a setting" box above it, and the page chosen on the right, its settings in a card per heading. Where each
setting is, and what it is called, is settings_catalog's: every control is made for a catalog entry (_row,
_check) and kept under its key (control(key)), and a setting that needs another is greyed out while that one is
off (Entry.needs). SETTINGS.md says how a setting is placed.

The pages' parts that are editors of their own: the court holidays (gui/holiday_editor.py), the Records window's
tick boxes and colours (gui/tracking_editor.py), the invoice text (dialogs.InvoiceTextEditor), another reporter's
invoice details (dialogs.ReporterDialog) and the Ollama setup help (dialogs.OllamaHelpDialog)."""
from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import replace

from PySide6.QtCore import QEvent, QSize, QTimer, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import courthouses
from ..settings import (AGREEMENT_FALLBACKS, AI_TICKS, CASE_FOLDER_EXISTING, CASE_FOLDER_PATTERN, DETAIL_ITEMS,
                        INDEX_RULES, INDEX_SHARED, JUDGE_INDEX, MATH_SAVES, OUTPUT_FOLDERS, OUTPUTS,
                        RECENT_JOBS_DAYS_MAX, RECENT_JOBS_MAX, ROUNDINGS, RUNSHEET_WITNESS, SPEEDS, SPLIT_SPEEDS,
                        TRIAL_ORDERS, TURNAROUND_FROM, ReporterProfile, Settings, clean_folder_pattern,
                        reporter_key)
from ..settings_catalog import ENTRIES, PAGE, PAGES, SETTINGS, entry, path, search, shown_label
from ..tracking import box_rows, rule_rows
from .dialogs import INDEX_PATTERNS_TIP, InvoiceTextEditor, OllamaHelpDialog, ReporterDialog
from .widgets import QuietCombo, check_row, open_path, refill_combo, show_save_error
from .zoom import z

# Settings' tabs before 2.18 (the names other windows and old notes give): the page each became
OLD_TABS = {"Defaults": "rates", "Options": "files", "Invoice": "invoices", "Run sheet": "runsheets", "AI": "ai"}
FLASH_MS = 1600  # how long a setting found is lit up


def _note(text: str) -> QLabel:
    """A small grey note."""
    label = QLabel(text)
    label.setObjectName("muted")
    label.setWordWrap(True)
    return label


def _combo(items: dict, current) -> QComboBox:
    """A dropdown of key -> label, the key `current` chosen (the first when it isn't one of them)."""
    box = QComboBox()
    for key, label in items.items():
        box.addItem(label, key)
    box.setCurrentIndex(max(0, box.findData(current)))
    return box


class SettingsDialog(QDialog):
    """The Settings window. Nothing is stored until Save (accept), which runs every control's save in turn and
    saves the settings to disk; Cancel leaves the settings, and a picked but unsaved signature image, untouched.

    control(key) is the control of a setting (its first, for one shown in several); a test or a message finds a
    setting through it, wherever its page. The attributes the controls also have (p_, d_, o_, t_, i_, k_, r_,
    a_) are named after the tab each was on before 2.18, and kept for the code and tests that use them."""
    last_page = ""  # the page shown when the window last closed, while the app runs (Cancel too)

    def __init__(self, settings: Settings, parent=None, session_answers: list | None = None):
        """settings: the Settings object to edit in place. session_answers: the window's answers about rows that
        may be one firm given for now only (Remember unticked), listed under Firms you answered marked "for now";
        after Save, `self.session_answers` holds those not forgotten."""
        super().__init__(parent)
        self.s = settings
        self.session_answers = [list(r) for r in session_answers or []]
        self.controls: dict[str, list[QWidget]] = {}  # key -> its controls (the first is control(key))
        self.parts: dict[str, dict] = {}  # key -> {part: control} for a setting of several (output_dirs...)
        self._labels: dict[str, QLabel] = {}  # key -> its row's label (greyed out with it)
        self._saves: list = []  # (key, save(s)) in the order made, run by accept
        self._late: list = []  # saves run after the others (the split rule after the invoice text)
        self._warnings: list[tuple[str, str]] = []  # shown once everything is saved
        self.pages: dict[str, QScrollArea] = {}
        self._flashed: dict = {}  # widget lit up by Find a setting -> its own style sheet, put back after FLASH_MS
        self.setWindowTitle("Settings")
        lay = QVBoxLayout(self)
        body = QHBoxLayout()
        lay.addLayout(body, 1)

        # left: Find a setting, the pages (a line between groups) or, while something is typed, what it finds
        left = QVBoxLayout()
        self.find = QLineEdit()
        self.find.setPlaceholderText("Find a setting")
        self.find.setClearButtonEnabled(True)
        self.find.setToolTip("Type a word or two (\"judge\", \"dark\", \"file name\"): the settings it finds are "
                             "listed; click one to go to it.")
        self.find.textChanged.connect(self._find)
        self.find.installEventFilter(self)  # (Enter goes to a setting found: never Save, the dialog's default)
        left.addWidget(self.find)
        self.list = QListWidget()
        self.list.setObjectName("settingsPages")
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left.addWidget(self.list, 1)
        self.found = QListWidget()
        self.found.setWordWrap(True)
        self.found.itemClicked.connect(self._go_found)
        self.found.installEventFilter(self)
        self.found.hide()
        left.addWidget(self.found, 1)
        side = QWidget()
        side.setLayout(left)
        side.setFixedWidth(z(236))
        left.setContentsMargins(0, 0, 0, 0)
        body.addWidget(side)
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)

        for p in PAGES:
            getattr(self, f"_page_{p.key}")(self._new_page(p.key), settings)
        from .holiday_editor import HolidayEditor
        from .tracking_editor import TrackingEditor
        editors = (HolidayEditor, TrackingEditor, InvoiceTextEditor)

        def in_editor(w: QWidget | None) -> bool:
            """Whether w is inside one of the editors, whose own dropdowns keep their width."""
            while w is not None and w is not self.stack:
                if isinstance(w, editors):
                    return True
                w = w.parentWidget()
            return False
        for box in self.stack.findChildren(QComboBox):  # (a long choice is cut short rather than widening the page)
            if not in_editor(box):
                box.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
                box.setMinimumContentsLength(max(box.minimumContentsLength(), 10))
        self._fill_list()
        self._wire_needs()
        self.list.currentRowChanged.connect(self._list_changed)
        self.show_page(SettingsDialog.last_page or settings.settings_page or PAGES[0].key)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel | QDialogButtonBox.Help)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.helpRequested.connect(self.show_help)
        lay.addWidget(buttons)
        QShortcut(QKeySequence("F1"), self, activated=self.show_help)
        self._fit()

    # --- the frame: pages, cards, rows
    def _new_page(self, key: str) -> QVBoxLayout:
        """A page of the stack (scrolling when long), its help topic set; returns the layout its cards go in."""
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(z(8), z(4), z(8), z(12))
        v.setSpacing(z(12))
        title = QLabel(PAGE[key].title)
        title.setObjectName("title")
        v.addWidget(title)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(inner)
        scroll.setProperty("help_topic", PAGE[key].help)  # (what Help and F1 open: help_window.help_topic_of)
        self.stack.addWidget(scroll)
        self.pages[key] = scroll
        v.addStretch(1)
        return v

    @staticmethod
    def _card(page: QVBoxLayout, heading: str) -> QFormLayout:
        """A card on the page under `heading` (one of the page's sections), its rows in the form returned."""
        card = QFrame()
        card.setObjectName("card")
        v = QVBoxLayout(card)
        v.setContentsMargins(z(12), z(12), z(12), z(14))
        v.setSpacing(z(8))
        head = QLabel(heading)
        head.setObjectName("section")
        v.addWidget(head)
        f = QFormLayout()
        f.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f.setHorizontalSpacing(14)
        f.setVerticalSpacing(9)
        f.setRowWrapPolicy(QFormLayout.DontWrapRows)
        v.addLayout(f)
        page.insertWidget(page.count() - 1, card)  # (above the stretch)
        return f

    def _keep(self, key: str, *widgets, save=None, parts: dict | None = None, late: bool = False) -> None:
        """Keeps the controls of setting `key` (and its parts, by name) and what Save does with them."""
        assert key in {e.key for e in ENTRIES}, key
        self.controls.setdefault(key, []).extend(widgets)
        if parts:
            self.parts.setdefault(key, {}).update(parts)
            self.controls[key].extend(w for w in parts.values() if w not in self.controls[key])
        if save is not None:
            (self._late if late else self._saves).append((key, save))

    def _row(self, f: QFormLayout, key: str, field, *widgets, save=None, parts: dict | None = None,
             label: str | None = None, late: bool = False) -> None:
        """A row of the form for setting `key`: its label (the catalog's) and `field` (a widget or a layout);
        widgets: its controls (field itself when it is a widget)."""
        text = entry(key).label if label is None else label
        if text and text == entry(key).section:
            f.addRow(field)  # (named by its card's heading already)
        else:
            f.addRow(text, field)
            lab = f.labelForField(field)
            if isinstance(lab, QLabel) and text:
                self._labels[key] = lab
        self._keep(key, *(widgets or ([field] if isinstance(field, QWidget) else [])), save=save, parts=parts,
                   late=late)

    def _check(self, f: QFormLayout, key: str, checked: bool, tip: str = "", attr=None) -> QCheckBox:
        """A tick box for setting `key`, labelled as the catalog says, saved as a True/False."""
        cb = QCheckBox(entry(key).label)
        cb.setChecked(checked)
        if tip:
            cb.setToolTip(tip)
        f.addRow(cb)  # (across the card: under a long label, a long tick box would widen the page)
        self._keep(key, cb, save=lambda s: setattr(attr(s) if attr else s, key.split(".")[-1], cb.isChecked()))
        return cb

    def _text(self, f: QFormLayout, key: str, value: str, tip: str = "", keep_old: bool = False,
              lower: bool = False) -> QLineEdit:
        """A line of text for setting `key` (a Profile one too: "profile.name"); keep_old: left blank, the old
        value stays (a file name pattern)."""
        e = QLineEdit(value)
        if tip:
            e.setToolTip(tip)
        name = key.split(".")[-1]

        def save(s: Settings) -> None:
            """Save: the text, stripped, into the setting (or its Profile's); left blank, kept as it was when
            keep_old says so."""
            target = s.profile if key.startswith("profile.") else s
            text = e.text().strip()
            if keep_old and not text:
                return
            setattr(target, name, text)
        self._row(f, key, e, save=save)
        return e

    def control(self, key: str, part: str | None = None) -> QWidget:
        """The control of a setting ("invoice_rounding"), or one part of it ("output_dirs", "invoice")."""
        return self.parts[key][part] if part is not None else self.controls[key][0]

    # --- the pages
    def _page_my_info(self, page: QVBoxLayout, settings: Settings) -> None:
        """My info: your details, your initials, your signature."""
        p = settings.profile
        f = self._card(page, "Contact")
        self.p_name = self._text(f, "profile.name", p.name)
        self.p_title = self._text(f, "profile.title", p.title)
        self.p_addr1 = self._text(f, "profile.address1", p.address1)
        self.p_addr1.setPlaceholderText("e.g. Supreme Court, 123 Courthouse Plaza, Room 100")
        self.p_addr2 = self._text(f, "profile.address2", p.address2)
        self.p_addr2.setPlaceholderText("e.g. Anytown, NY 10000")
        self.p_phone = self._text(f, "profile.phone", p.phone)
        self.p_fax = self._text(f, "profile.fax", p.fax)
        self.p_email = self._text(f, "profile.email", p.email)
        self.p_web = self._text(f, "profile.website", p.website)
        self.p_web.setPlaceholderText("optional, shown on invoices")
        f = self._card(page, "Initials")
        self.p_initials = QLineEdit(p.initials)
        self.p_initials.setPlaceholderText("as you put them at the foot of your transcript pages, e.g. pr")
        self.p_initials.setToolTip("Run sheets and invoices: the pages with these initials are yours (an invoice "
                                   "of a transcript several reporters\nwrote bills yours, unless Whose pages… says "
                                   "otherwise).\n"
                                   "Blank = the first letters of your first and last name.")
        self._row(f, "profile.initials", self.p_initials, label="", save=lambda s: setattr(
            s.profile, "initials", self.p_initials.text().strip().lower().replace(".", "").replace(" ", "")))
        f = self._card(page, "Signature")
        # the picture, shown as it will appear on the form; stored on Save
        self._sig_new: str | None = None  # None = unchanged, "" = removed, else a prepared file
        self.p_sig = QLabel()
        self.p_sig.setObjectName("muted")
        self.p_sig.setMinimumHeight(z(56))
        self.p_sig.setWordWrap(True)
        pick = QPushButton("Choose image...")
        pick.clicked.connect(self._pick_signature)
        self.p_sig_remove = QPushButton("Remove")
        self.p_sig_remove.clicked.connect(self._remove_signature)
        row = QHBoxLayout()
        row.setSpacing(z(6))
        row.addWidget(self.p_sig, 1)
        row.addWidget(pick)
        row.addWidget(self.p_sig_remove)
        self._row(f, "signature_image", row, self.p_sig, pick, self.p_sig_remove, label="Picture",
                  save=lambda s: self._store_signature(self._warnings))
        self.p_sign = self._check(f, "sign_reporter", settings.sign_reporter,
                                  "With your signature picture if you chose one, otherwise your name is typed.")
        self._show_signature(settings.signature_image)

    def _page_reporters(self, page: QVBoxLayout, settings: Settings) -> None:
        """Other reporters: their names on run sheets, and the details of the invoices made for their pages."""
        f = self._card(page, "Reporters")
        f.addRow(_note("Reporters whose pages share your transcripts, by the initials at the foot of their pages. "
                       "Initials = the name for the run sheet's Reporter column, one reporter per line. Without a "
                       "line, the first name of the reporter listed on the transcript's title page is used (and "
                       "yours for your own initials, under My info); failing that, the initials."))
        self.r_names = QPlainTextEdit("\n".join(f"{k} = {v}" for k, v in sorted(settings.reporter_names().items())))
        self.r_names.setPlaceholderText("ds = Dana\nkl = Kim")
        self.r_names.setFixedHeight(z(110))
        self._row(f, "reporters", self.r_names, save=self._save_reporters, label="Names")
        f.addRow(_note("When Whose pages… (in the main window's Invoice card) bills another reporter's pages, the "
                       "invoice is made in their name, with their details: Invoice details…"))
        # the details on the invoices made for another reporter's pages (Whose pages... ticks them)
        self._details = deepcopy(settings.reporters)
        row = QHBoxLayout()
        self.r_who = QComboBox()
        self.r_who.setMinimumContentsLength(14)
        self.r_edit = QPushButton("Invoice details…")
        self.r_edit.setToolTip("Their name, address and how to pay them, for the invoices you make for their "
                               "pages\n(Invoice → Whose pages… ticks whose pages are billed)")
        self.r_edit.clicked.connect(self._edit_reporter)
        row.addWidget(self.r_who, 1)
        row.addWidget(self.r_edit)
        f.addRow("Invoices for", row)
        self._keep("reporters", self.r_who, self.r_edit)
        self.r_names.textChanged.connect(self._fill_reporters)
        self._fill_reporters()

    def _page_reading(self, page: QVBoxLayout, settings: Settings) -> None:
        """Reading documents: what a new job gets when its documents don't say, names, index numbers, firms."""
        f = self._card(page, "When a document doesn't say")
        self.d_court = self._text(f, "default_court", settings.default_court)
        self.d_county = self._text(f, "default_county", settings.default_county)
        self.d_copies = self._text(f, "default_copies", settings.default_copies,
                                   "No. of copies when nobody is ticked in Who ordered and no document says")
        f = self._card(page, "Names")
        self.o_tc = self._check(f, "title_case_names", settings.title_case_names,
                                "\"HONORABLE MARIA T. ALVAREZ\" is written \"Maria T. Alvarez\".")
        f = self._card(page, "Index numbers")
        self._index_patterns_rows(f, settings)
        f = self._card(page, "Firms you answered")
        # the answers about rows that may be one firm ("Smith Law" and "Smith Law Group"), kept and for now: one
        # forgotten is asked about again the next time both appear
        self._firm_answers = [list(r) for r in settings.firm_answers]
        box = QVBoxLayout()
        self.i_firms = QListWidget()
        self.i_firms.setSelectionMode(QListWidget.ExtendedSelection)
        self.i_firms.setMaximumHeight(z(120))
        box.addWidget(self.i_firms)
        row = QHBoxLayout()
        self.i_forget = QPushButton("Forget")
        self.i_forget.setToolTip("Forget the answers selected: after Save, the jobs open now are read again with\n"
                                 "the two rows apart, and you're asked again (there, and the next time both appear).\n"
                                 "\"for now\" marks an answer given with Remember unticked: kept until the app closes.")
        self.i_forget.clicked.connect(lambda: self._forget_firms(False))
        self.i_forget_all = QPushButton("Forget all")
        self.i_forget_all.clicked.connect(lambda: self._forget_firms(True))
        row.addWidget(self.i_forget)
        row.addWidget(self.i_forget_all)
        row.addStretch(1)
        box.addLayout(row)
        f.addRow(_note("When two rows may be one firm (\"Smith Law\" and \"Smith Law Group\"), you're asked; "
                       "an answer you remember is listed here."))
        self._row(f, "firm_answers", box, self.i_firms, self.i_forget, self.i_forget_all,
                  save=lambda s: setattr(s, "firm_answers", [list(r) for r in self._firm_answers]))
        self._fill_firms()

    def _page_ai(self, page: QVBoxLayout, settings: Settings) -> None:
        """AI helper: whether a local AI model helps read the documents, and which."""
        f = self._card(page, "AI helper")
        self.a_use = self._check(f, "use_ai", settings.use_ai)
        self.a_text = self._check(f, "ai_for_text", settings.ai_for_text)
        self.a_ticks = _combo(AI_TICKS, settings.ai_ticks)
        self.a_ticks.setToolTip("A transcript lists who appeared, not who ordered, so the AI's tick is trusted only\n"
                                "from e-mails and pasted text unless you say otherwise.")
        self._row(f, "ai_ticks", self.a_ticks,
                  save=lambda s: setattr(s, "ai_ticks", self.a_ticks.currentData() or s.ai_ticks))
        f = self._card(page, "The model")
        self.a_model = QComboBox()
        self.a_model.setEditable(True)
        self.a_model.setToolTip("Choose one of the two, or any other model Ollama has (you can type its name).")
        self._fill_models([])
        self.a_model.setCurrentText(settings.ollama_model)
        self._row(f, "ollama_model", self.a_model,
                  save=lambda s: setattr(s, "ollama_model", self.a_model.currentText().strip()))
        from ..extract_llm import MODELS
        a_note = QLabel("<br>".join(f"<b>{name}</b>: {what}." for name, what in MODELS.items())
                        + "<br>Not installed yet? The button below downloads the one chosen.")
        a_note.setObjectName("muted")
        a_note.setWordWrap(True)
        f.addRow(a_note)
        self.a_host = QLineEdit(settings.ollama_host)
        self._row(f, "ollama_host", self.a_host,
                  save=lambda s: setattr(s, "ollama_host", self.a_host.text().strip()))
        self.a_timeout = QSpinBox()
        self.a_timeout.setRange(10, 900)
        self.a_timeout.setValue(settings.ai_timeout)
        self.a_timeout.setSuffix(" s")
        self._row(f, "ai_timeout", self.a_timeout, save=lambda s: setattr(s, "ai_timeout", self.a_timeout.value()))
        test = QPushButton("Test connection")
        self.a_status = QLabel("")
        self.a_status.setObjectName("muted")
        self.a_status.setWordWrap(True)
        test.clicked.connect(self._test_ai)
        f.addRow(test, self.a_status)
        guide = QPushButton("How to install Ollama + gemma…")
        guide.clicked.connect(lambda: OllamaHelpDialog(self.a_model.currentText().strip() or Settings.ollama_model,
                                                       self.a_host.text().strip(), self).exec())
        f.addRow("", guide)
        self._load_models()

    def _page_trials(self, page: QVBoxLayout, settings: Settings) -> None:
        """Trials: what a tick means over the days of one case, one invoice (and one set of forms) for them, and
        batches that put them on one form."""
        f = self._card(page, "Who ordered")
        f.addRow(_note("A trial: the days of one case (the same index number), read together or added later."))
        # what a tick in Who ordered means in a trial (batch.spread_orders; the user, 2026-10-24: the whole trial,
        # most often, "though this should be customizable")
        self.o_trial = _combo(TRIAL_ORDERS, settings.trial_orders)
        self.o_trial.setToolTip(
            "A trial (days of one case): a firm you tick in Who ordered orders every day of it, days you drop in\n"
            "later too, at one speed; What in its row makes it one day, or some days or pages\n"
            "(Who ordered which pages…).\n"
            "Only the day shown: each day is ticked on its own.")
        self._row(f, "trial_orders", self.o_trial,
                  save=lambda s: setattr(s, "trial_orders", self.o_trial.currentData() or s.trial_orders))
        f = self._card(page, "Invoices and forms")
        self.i_joint = QComboBox()
        self.i_joint.addItem("One joint invoice for all the days of a case", True)
        self.i_joint.addItem("An invoice for each day", False)
        self.i_joint.setCurrentIndex(0 if settings.invoice_joint else 1)
        self.i_joint.setToolTip("When several days of one case are generated together (Generate all).\n"
                                "A single day selected and generated on its own is always billed alone.\n"
                                "With a joint invoice, the minute agreements and the MOFR are made once for the\n"
                                "whole case too, unless the box below is unticked.")
        self._row(f, "invoice_joint", self.i_joint,
                  save=lambda s: setattr(s, "invoice_joint", bool(self.i_joint.currentData())))
        self.o_per_case = self._check(
            f, "forms_per_case", settings.forms_per_case,
            "Generate all, when the days of a case share an invoice (Days of one case, above):\n"
            "one minute agreement per attorney, listing the days it ordered and every page it ordered on them,\n"
            "whoever wrote them (its invoice bills only your pages of them), and one MOFR for all the days.\n"
            "Off: an agreement per attorney and a MOFR for each day, as before.\n"
            "\"Generate 6/4/2026 only\" (the day shown) always makes that day's forms alone.")
        f = self._card(page, "Batches")
        self.o_combine = self._check(f, "batch_combine_dates", settings.batch_combine_dates,
                                     "A folder of documents (batch): the days of one case make one job, one form "
                                     "for all its days.\nOff: documents about the same case make one job, and one "
                                     "form, per day of proceedings.")

    def _page_dates(self, page: QVBoxLayout, settings: Settings) -> None:
        """Dates (workdays.py): the two dates filled in, each speed's turnaround (its days and the invoice's words
        for it) and how it is counted, the business days (forms and invoices made on a weekend or a court holiday
        dated the next business day, made after the evening hour dated the next day) and the court holidays
        (HolidayEditor)."""
        from PySide6.QtCore import QTime
        from PySide6.QtWidgets import QTimeEdit
        from .holiday_editor import HolidayEditor
        intro = _note("Minute agreement forms and invoices are dated on the court's business days, and turnaround "
                      "days counted in them: weekends and the court holidays below are skipped. The main window "
                      "says so under the dates whenever one was moved.")
        page.insertWidget(page.count() - 1, intro)
        f = self._card(page, "Filling in")
        self.o_today = self._check(f, "agreement_today", settings.agreement_today)
        self.o_deldate = self._check(f, "fill_delivery_date", settings.fill_delivery_date,
                                     "The days of each speed: the rate sheet's Days column, else the Days under "
                                     "Turnaround below.")
        f = self._card(page, "Turnaround")
        grid = QGridLayout()
        grid.setHorizontalSpacing(z(12))
        grid.setVerticalSpacing(z(6))
        days_head, words_head = QLabel("Days"), QLabel(entry("invoice_turnaround").label)
        for c, lab in ((1, days_head), (2, words_head)):
            lab.setObjectName("muted")
            grid.addWidget(lab, 0, c)
        self.days: dict[str, QSpinBox] = {}
        self.i_turn: dict[str, QLineEdit] = {}
        for r, name in enumerate(SPEEDS, 1):
            grid.addWidget(QLabel(name), r, 0, Qt.AlignRight | Qt.AlignVCenter)
            attr = f"days_{name.lower()}"
            spin = QSpinBox()
            spin.setRange(0, 120)
            spin.setValue(getattr(settings, attr))
            spin.setToolTip("Used when the rate sheet has no Days column.")
            self.days[attr] = spin
            grid.addWidget(spin, r, 1)
            self._keep(attr, spin, save=lambda s, a=attr, w=spin: setattr(s, a, w.value()))
            e = QLineEdit(settings.turnaround(name))
            e.setToolTip(f"How the invoice words {name}'s turnaround (\"3 weeks\").")
            self.i_turn[name] = e
            grid.addWidget(e, r, 2)
        grid.setColumnStretch(2, 1)
        f.addRow(grid)
        self._keep("invoice_turnaround", parts=dict(self.i_turn), save=lambda s: setattr(
            s, "invoice_turnaround", {k: e.text().strip() for k, e in self.i_turn.items()}))
        f.addRow(_note("Days: used when a rate sheet has no Days column of its own. On the invoice: what the invoice "
                       "says about each speed's turnaround."))
        self.t_business = self._check(
            f, "turnaround_business_days", settings.turnaround_business_days,
            "Ticked: 5 days from Tuesday 10/13/2026 is Tuesday 10/20/2026 (weekends and court holidays not "
            "counted).\nUnticked: calendar days; a last day on a weekend or a court holiday moves to the next "
            "business day.")
        self.t_from = _combo(TURNAROUND_FROM, settings.turnaround_from)
        self.t_from.setToolTip("Made on Sunday 10/11/2026 (dated Tuesday 10/13), 5 business days are Tuesday 10/20 "
                               "from the date on the form,\nor Monday 10/19 from the day you make it.")
        self._row(f, "turnaround_from", self.t_from,
                  save=lambda s: setattr(s, "turnaround_from", self.t_from.currentData() or s.turnaround_from))
        f = self._card(page, "Business days")
        self.t_dating = self._check(
            f, "business_day_dating", settings.business_day_dating,
            "One made on a weekend or a court holiday is dated the next business day: made on Sunday 10/11/2026,\n"
            "with Columbus Day on the Monday, it is dated Tuesday 10/13/2026. The invoice's number (its year), the\n"
            "records and {today} in the file names go by that date too.")
        row = QHBoxLayout()
        row.setSpacing(z(6))
        self.t_after = QCheckBox("Made after")
        self.t_after.setChecked(settings.after_hours)
        self.t_time = QTimeEdit(QTime.fromString(settings.after_hours_from, "HH:mm"))
        self.t_time.setDisplayFormat("h:mm AP")
        row.addWidget(self.t_after)
        row.addWidget(self.t_time)
        row.addWidget(QLabel(": dated the next day"), 1)
        tip = ("Off at first. A form or an invoice made in the evening is dated as if made the next morning: the next "
               "business day,\nwhen Date forms and invoices on a business day is ticked (made Friday at 6 PM: "
               "Monday).")
        for x in (self.t_after, self.t_time):
            x.setToolTip(tip)
        self._row(f, "after_hours", row, self.t_after,
                  save=lambda s: setattr(s, "after_hours", self.t_after.isChecked()))
        self._keep("after_hours_from", self.t_time,
                   save=lambda s: setattr(s, "after_hours_from", self.t_time.time().toString("HH:mm")))
        f = self._card(page, "Court holidays")
        self.t_holidays = HolidayEditor(settings.holidays, settings.holiday_weekend)
        self._row(f, "holidays", self.t_holidays, save=lambda s: setattr(s, "holidays", self.t_holidays.rows()))
        self._keep("holiday_weekend", self.t_holidays,
                   save=lambda s: setattr(s, "holiday_weekend", self.t_holidays.weekend()))

    def _page_rates(self, page: QVBoxLayout, settings: Settings) -> None:
        """Rates and speeds: the rate sheet, the speeds the invoice offers and the one the form names, and firms
        that ordered the same pages at different speeds."""
        from ..rates import default_dir, speed_key
        f = self._card(page, "Rate sheets")
        self.d_sheet = QComboBox()
        self._sheet_dir = settings.rate_sheets_dir
        self._load_sheet_names()

        def save_sheet(s: Settings) -> None:
            """Save: the rate sheet chosen, of the folder as typed."""
            self._typed_sheet_dir()  # (a folder typed and Save pressed at once: the sheet is one of that folder's)
            s.rate_sheet = self.d_sheet.currentData() or s.rate_sheet
        self.d_sheet.setToolTip("The same list as the main window's Rate sheet (Pages and dates card).")
        row = QHBoxLayout()
        self.d_dir = QLineEdit(settings.rate_sheets_dir)
        self.d_dir.setPlaceholderText(str(default_dir()))
        self.d_dir.editingFinished.connect(self._typed_sheet_dir)  # (typed, not Browsed: its sheets listed too)
        pick = QPushButton("Browse...")
        pick.clicked.connect(self._pick_sheet_dir)
        open_btn = QPushButton("Open folder")
        open_btn.clicked.connect(self._open_sheet_dir)
        row.addWidget(self.d_dir, 1)
        row.addWidget(pick)
        row.addWidget(open_btn)
        self._row(f, "rate_sheets_dir", row, self.d_dir, save=lambda s: setattr(s, "rate_sheets_dir",
                                                                                self.d_dir.text().strip()))
        # (after the folder: Save takes the sheet of the folder typed)
        self._row(f, "rate_sheet", self.d_sheet, save=save_sheet)
        f.addRow(_note("Rate sheets are CSV files (open them in Excel). To add one, e.g. city rates, copy "
                           "\"Rate Sheet TEMPLATE.csv\" in that folder, rename it, and fill in the prices. An "
                           "optional Days column sets each speed's turnaround."))
        f = self._card(page, "Speeds")
        offered = {speed_key(x) for x in settings.invoice_speeds}
        speeds, self.i_speeds = check_row({n: n for n in SPEEDS}, [n for n in SPEEDS if speed_key(n) in offered],
                                          self._show_agreement_speed, spacing=12)
        speeds.addStretch(1)

        def save_speeds(s: Settings) -> None:
            """Save: the speeds ticked, after those a rate sheet names its own way (no box here: kept)."""
            # speeds named otherwise on a rate sheet (ticked under Speeds offered) have no box here: they stay
            keep = [x for x in s.invoice_speeds if speed_key(x) not in {speed_key(n) for n in SPEEDS}]
            s.invoice_speeds = keep + [k for k, cb in self.i_speeds.items() if cb.isChecked()]
        self._row(f, "invoice_speeds", speeds, parts=dict(self.i_speeds), save=save_speeds)
        f.addRow(_note("The attorney chooses one. With one ticked the invoice bills that speed alone. The same "
                           "boxes are in the main window's Who ordered card, beside the Speed."))
        # the one speed the minute agreement form names, out of those offered (Settings.agreement_speed)
        self.i_first = QComboBox()
        names = list(SPEEDS)
        if settings.agreement_speed_first and not any(speed_key(n) == speed_key(settings.agreement_speed_first)
                                                      for n in names):
            names.append(settings.agreement_speed_first)  # a sheet's own spelling ("Expedite"): kept, not Regular
        for n in names:
            self.i_first.addItem(n, n)
        self.i_first.setCurrentIndex(max(0, next((i for i, n in enumerate(names)
                                                  if speed_key(n) == speed_key(settings.agreement_speed_first)), 0)))
        self.i_first.setToolTip("The speed the minute agreement form names, when the invoice offers it.")
        self.i_fallback = _combo(AGREEMENT_FALLBACKS, settings.agreement_speed_fallback)
        self._row(f, "agreement_speed_first", self.i_first, save=lambda s: setattr(
            s, "agreement_speed_first", self.i_first.currentData() or s.agreement_speed_first))
        self._row(f, "agreement_speed_fallback", self.i_fallback, save=lambda s: setattr(
            s, "agreement_speed_fallback", self.i_fallback.currentData() or s.agreement_speed_fallback))
        self.i_agreement_note = _note("")
        f.addRow(self.i_agreement_note)
        self.i_first.currentIndexChanged.connect(self._show_agreement_speed)
        self.i_fallback.currentIndexChanged.connect(self._show_agreement_speed)
        self._show_agreement_speed()
        f = self._card(page, "Same pages, different speeds")
        # firms ordering the same pages commit to a speed: billed what Who ordered shows, or asked at Generate
        self.i_split_speeds = _combo(SPLIT_SPEEDS, settings.split_speeds)
        self.i_split_speeds.setToolTip(
            "Firms that ordered the same pages are each billed one speed. Who ordered names it in each firm's row\n"
            "(the agreement form's speed, unless you choose another there). Bill it: Generate asks nothing.\n"
            "Ask me: Generate asks each firm's speed first, one line per firm for the whole trial.")
        self._row(f, "split_speeds", self.i_split_speeds,
                  save=lambda s: setattr(s, "split_speeds", self.i_split_speeds.currentData() or s.split_speeds))
        # how pages ordered together at different speeds are divided: one of the courthouse's split rules (a
        # courthouse with none bills no such pages, and has no row)
        self.i_split = QComboBox()
        rules = courthouses.split_rules()
        for i, rule in enumerate(rules):
            self.i_split.addItem(rule.label, rule.key)
            self.i_split.setItemData(i, rule.tip, Qt.ToolTipRole)
        chosen = courthouses.split_rule(settings.invoice_split_rule)
        self.i_split.setCurrentIndex(max(0, self.i_split.findData(chosen.key if chosen else "")))
        self.i_split.setToolTip("How firms that ordered the same pages at different speeds share the one original\n"
                                "(and the judge's index, when it is billed). Each always pays its own copies at its "
                                "own speed, and its\nown index too unless Index on shared pages splits it. Point at "
                                "a choice in the list\nto see how it works. The invoice's note on such pages "
                                "(Invoice text) follows the\nchoice, unless you have reworded it. A job invoiced "
                                "already keeps the way it was\nbilled, made again or opened again from Records.")

        def save_split(s: Settings) -> None:
            """Save (after the invoice text, `late`): the split rule chosen, "" while the default is left as it was."""
            split = self.i_split.currentData() or ""
            if not s.invoice_split_rule and rules and split == rules[0].key:
                split = ""  # (the default left as it was: "" follows the courthouse's default, should it change)
            s.use_split_rule(split)  # (after the invoice text, `late`: it may reword the note on such pages)
        if rules:
            self._row(f, "invoice_split_rule", self.i_split, save=save_split, late=True)
        else:
            self._keep("invoice_split_rule", self.i_split)

    def _page_outputs(self, page: QVBoxLayout, settings: Settings) -> None:
        """Outputs: which a new job makes, and how the minute agreement and the MOFR are filled in."""
        from ..fill import FORMS
        f = self._card(page, "Make by default")
        make, self.o_outputs = check_row(OUTPUTS, settings.outputs)
        make.addStretch(1)
        self._row(f, "outputs", make, parts=dict(self.o_outputs), save=lambda s: setattr(
            s, "outputs", [k for k, cb in self.o_outputs.items() if cb.isChecked()]))
        f.addRow(_note("The same boxes as the main window's Outputs box: what you tick there is kept here too."))
        f = self._card(page, "Minute agreement")
        self.o_form = _combo({key: label for key, (_, label) in FORMS.items()}, settings.form_choice)
        self._row(f, "form_choice", self.o_form, save=lambda s: setattr(s, "form_choice", self.o_form.currentData()))
        self.o_instr = self._check(f, "include_instructions", settings.include_instructions,
                                   "Unticked: the saved PDF has the form page only.")
        self.o_per_email = self._check(f, "per_email", settings.per_email)
        f.addRow(_note(f"Signing the court reporter line: {path('sign_reporter')}."))
        f = self._card(page, "MOFR")
        self.o_division = _combo({"civil": "Civil", "criminal": "Criminal"}, settings.mofr_division)
        self._row(f, "mofr_division", self.o_division,
                  save=lambda s: setattr(s, "mofr_division", self.o_division.currentData()))

    def _page_invoices(self, page: QVBoxLayout, settings: Settings) -> None:
        """Invoices: what an invoice charges (its index too), what it shows, its numbers, its math."""
        intro = _note("Invoices bill your pages of a transcript (or the pages typed in Est. number of pages), priced "
                      f"from the rate sheet. Prices and the speeds offered: {path(page='rates')}. One invoice for the days "
                      f"of a trial: {path('invoice_joint')}.")
        page.insertWidget(page.count() - 1, intro)
        f = self._card(page, "Charges")
        self.i_email = self._check(f, "invoice_include_email", settings.invoice_include_email,
                                   "A job's Peripherals… can say yes or no for that job.")
        self.i_rounding = _combo(ROUNDINGS, settings.invoice_rounding)
        self.i_rounding.setToolTip("When a firm's price a page comes to part of a cent (four firms sharing Immediate:\n"
                                   "$6.6125 a page).\n"
                                   "Exact: every fraction of a cent is kept, and the amount is rounded up to the cent\n"
                                   "once, at the end (1,000 of your pages billed: $6,612.50).\n"
                                   "The price a page, to the cent: rounded to the nearest cent first, as most people\n"
                                   "do by hand ($6.61 × 1,000 = $6,610.00; $6.6175 a page would be $6.62). It can\n"
                                   "come out either way.\n"
                                   "The math (Show the math) says which was used.")
        self._row(f, "invoice_rounding", self.i_rounding,
                  save=lambda s: setattr(s, "invoice_rounding", self.i_rounding.currentData()))
        f = self._card(page, "Index")
        idx = QHBoxLayout()
        idx.setSpacing(z(6))
        self.i_index = QCheckBox(entry("invoice_include_index").label)
        self.i_index.setChecked(settings.invoice_include_index)
        self.i_threshold = QSpinBox()
        self.i_threshold.setRange(1, 10000)
        self.i_threshold.setValue(settings.invoice_index_threshold)
        # (the user, 2026-10-30: every count says whose pages): judged on every reporter's pages
        self.i_threshold.setSuffix(" total pages")
        self.i_threshold.setFixedWidth(z(140))
        tip = ("Each firm's own index of the pages it ordered, and the judge's (below).\n"
               "Counted on the whole transcript, every reporter's pages, though each invoice charges the index on\n"
               "its own pages (your 45 pages of 83 total pages get one). A job's Peripherals… can say yes or no\n"
               "for that job.")
        self.i_index.setToolTip(tip)
        self.i_threshold.setToolTip(tip)
        idx.addWidget(self.i_index)
        idx.addWidget(self.i_threshold)
        idx.addStretch(1)
        f.addRow(idx)
        self._keep("invoice_include_index", self.i_index,
                   save=lambda s: setattr(s, "invoice_include_index", self.i_index.isChecked()))
        self._keep("invoice_index_threshold", self.i_threshold,
                   save=lambda s: setattr(s, "invoice_index_threshold", self.i_threshold.value()))
        self.i_rule = _combo(INDEX_RULES, settings.invoice_index_rule)
        self.i_rule.setToolTip("For an invoice covering several days. Every page of a day's transcripts counts,\n"
                               "whoever wrote them. A job's Peripherals… can still turn the index on or off for\n"
                               "that job.")
        self._row(f, "invoice_index_rule", self.i_rule,
                  save=lambda s: setattr(s, "invoice_index_rule", self.i_rule.currentData()))
        self.i_shared = _combo(INDEX_SHARED, settings.invoice_index_shared)
        self.i_shared.setToolTip("When several attorneys ordered the same pages: each pays an index of the pages it\n"
                                 "ordered (of 100 total pages, B orders 10: A pays an index of all 100, B of its 10),\n"
                                 "or one index is split between them like the original. The judge's index is set "
                                 "below.")
        self._row(f, "invoice_index_shared", self.i_shared,
                  save=lambda s: setattr(s, "invoice_index_shared", self.i_shared.currentData()))
        self.i_judge = _combo(JUDGE_INDEX, settings.invoice_judge_index)
        self.i_judge.setToolTip("The index of the judge's copy, priced like the firms' own (the rate sheet's Index "
                                "column).\nBilled: the firms split it page by page, each paying for the pages it "
                                "ordered (of 100 total pages,\nB orders 10: A pays for 95 of them, B for 5).\nNot "
                                "billed: no firm pays for it; each still pays its own index.")
        self._row(f, "invoice_judge_index", self.i_judge,
                  save=lambda s: setattr(s, "invoice_judge_index", self.i_judge.currentData()))
        f = self._card(page, "What the invoice shows")
        shows = QGridLayout()
        shows.setHorizontalSpacing(16)
        shows.setVerticalSpacing(6)
        self.i_items: dict[str, QCheckBox] = {}
        for i, (key, label) in enumerate(DETAIL_ITEMS.items()):
            cb = QCheckBox(label)
            cb.setChecked(key in settings.invoice_detail_items)
            self.i_items[key] = cb
            shows.addWidget(cb, i // 2, i % 2)
        self._row(f, "invoice_detail_items", shows, parts=dict(self.i_items), save=lambda s: setattr(
            s, "invoice_detail_items", [k for k, cb in self.i_items.items() if cb.isChecked()]))
        self.i_detailed_copy = self._check(
            f, "invoice_detailed_copy", settings.invoice_detailed_copy,
            "Next to each invoice, a copy with the granular detail above (the same number, \"... (detailed).pdf\"),"
            "\nready for when someone asks how the amount was reached. A job whose invoice already shows the "
            "detail gets none.")
        f = self._card(page, "Invoice text")
        self.i_texts = InvoiceTextEditor(settings.invoice_texts, self._preview_invoice)
        self._row(f, "invoice_texts", self.i_texts, save=lambda s: setattr(s, "invoice_texts", self.i_texts.rows()))
        f = self._card(page, "Numbers")
        self.i_number = self._text(f, "invoice_number_format", settings.invoice_number_format,
                                   "{year} and {seq} (the count this year, {seq:04} = 0007); {yy} = 26",
                                   keep_old=True)
        f = self._card(page, "The math")
        self.o_math = self._check(f, "show_math", settings.show_math,
                                  "How each amount is reached (pages × rate, the copies, the split between parties):\n"
                                  "the preview's first tab, The math, or, with previews off, a window after saving\n"
                                  "that can copy it or save it as a PDF. For Generate and Generate all.\n"
                                  "(Generate also saves it as PDFs, in a Math folder: Save the math, below.)")
        self.i_save_math = QuietCombo()  # (a wheel going by must not change it: "Don't save it" is last)
        for key, label in MATH_SAVES.items():
            self.i_save_math.addItem(label, key)
        self.i_save_math.setCurrentIndex(max(0, self.i_save_math.findData(settings.save_math)))
        self.i_save_math.setToolTip("How each amount was reached, saved as PDFs when Generate makes the invoices:\n"
                                    "each firm's own (\"... - the math.pdf\", only what that firm owes, to send it) "
                                    "and everyone's in one\n(every firm's amounts, to look back at the job). They go "
                                    "in a Math folder, apart from the invoices\n(in the case's folder; in Save to "
                                    "without a folder for each case; inside the invoices' folder when they have one\n"
                                    "of their own). With Don't save it, the box at the end of Generate says none was "
                                    "saved.\nThe same choice is under the math itself, in the preview and its window.")
        self._row(f, "save_math", self.i_save_math,
                  save=lambda s: setattr(s, "save_math", self.i_save_math.currentData()))

    def _page_runsheets(self, page: QVBoxLayout, settings: Settings) -> None:
        """Run sheets: whether a case's run sheet is added to, and what its witness columns get."""
        f = self._card(page, "Run sheets")
        f.addRow(_note("A run sheet lists who wrote which pages of a trial, take by take, from the initials at the "
                       "foot of each transcript page. There is one per case; a transcript's takes are added to it. "
                       "Each case's run sheet is saved in the Trial Runs folder inside the case's own folder (in Save "
                       "to itself without a folder for each case), unless "
                       f"{path('output_dirs')} gives run sheets a folder of their own. The reporters' names: "
                       f"{path(page='reporters')}."))
        self.r_existing = _combo({"ask": "Ask whether to add to it or start a new one",
                                  "add": "Add to it without asking", "new": "Always start a new run sheet"},
                                 settings.runsheet_existing)
        self.r_existing.setToolTip("A run sheet is the case's when it has the same index number or the same case "
                                   "name\n(a trial with several index numbers is billed together).")
        self._row(f, "runsheet_existing", self.r_existing,
                  save=lambda s: setattr(s, "runsheet_existing", self.r_existing.currentData()))
        self.r_witness = _combo(RUNSHEET_WITNESS, settings.runsheet_witness)
        self.r_witness.setToolTip("What the run sheet's Witness Start and Witness End columns get: the first and "
                                  "the last running head\nprinted at the top of the take's pages, as printed "
                                  "(\"DIRECT - PLAINTIFF - JANE ROE\"), or nothing, for you to type in")
        self._row(f, "runsheet_witness", self.r_witness,
                  save=lambda s: setattr(s, "runsheet_witness", self.r_witness.currentData()))

    def _page_records(self, page: QVBoxLayout, settings: Settings) -> None:
        """Records: the Records window's tick boxes and the colours of its rows, its search, its recaps, and the
        folder of its CSV copies."""
        from .tracking_editor import TrackingEditor
        f = self._card(page, "Tick boxes and colours")
        self.k_track = TrackingEditor(settings.boxes(), settings.rules(), settings.records_colours,
                                      settings.records_count)
        f.addRow(self.k_track)
        k = self.k_track
        self._keep("tracking_boxes", k.box_table, save=lambda s: setattr(s, "tracking_boxes", box_rows(k.boxes())))
        self._keep("tracking_rules", k.rule_table, save=lambda s: setattr(s, "tracking_rules", rule_rows(k.rules())))
        self._keep("records_colours", k.colours, save=lambda s: setattr(s, "records_colours", k.colours_on()))
        self._keep("records_count", k.count, save=lambda s: setattr(s, "records_count", k.count_name()))
        f = self._card(page, "Search")
        self.o_fuzzy_numbers = self._check(
            f, "fuzzy_numbers", settings.fuzzy_numbers,
            "Records → the search box's Fuzzy box. Ticked: numbers are matched like words, so \"2026-0001\" also "
            "finds 2026-0002.\nUnticked: a word with a digit in it (an invoice or index number, a date) must be "
            "found as typed;\nnames and other words still forgive a typo.")
        f = self._card(page, "Recaps")
        # (the user, 2026-10-30: every count says whose pages)
        self.o_recaps = self._check(f, "recaps", settings.recaps,
                                    "\"Last month you made $870.00 with 243 of your pages billed\": once a month, "
                                    "and once a year for the year before.")
        f = self._card(page, "CSV copies")
        row = QHBoxLayout()
        self.i_records = QLineEdit(settings.records_dir)
        self.i_records.setPlaceholderText(str(settings.records_folder()))
        rb = QPushButton("Browse...")
        rb.clicked.connect(lambda: self._pick_into(self.i_records, "Folder for the records (CSV copies)"))
        row.addWidget(self.i_records)
        row.addWidget(rb)
        self._row(f, "records_dir", row, self.i_records,
                  save=lambda s: setattr(s, "records_dir", self.i_records.text().strip()))
        f.addRow(_note("The records are kept in the app's own folder; a CSV copy of them, and the exports, go "
                           "here."))

    def _page_files(self, page: QVBoxLayout, settings: Settings) -> None:
        """Files and folders: where the files are saved (Save to, a folder for each case, one for an output), what
        they are called, and what happens as they are saved."""
        f = self._card(page, "Folders")
        self._folders(f, settings)
        f = self._card(page, "File names")
        today = path(page="dates")
        self.o_pattern = self._text(f, "filename_pattern", settings.filename_pattern,
                                    "Placeholders:\n{case}  {index}  {attorney}\n{date} - date of the minutes\n"
                                    "{today} - the date the form is dated (today, or the next business day: "
                                    f"{today})", keep_old=True)
        self.o_mofr_pattern = self._text(f, "mofr_filename_pattern", settings.mofr_filename_pattern,
                                         self.o_pattern.toolTip(), keep_old=True)
        self.i_pattern = self._text(f, "invoice_filename_pattern", settings.invoice_filename_pattern,
                                    "Placeholders: {number} {case} {index} {attorney} {date} {today}", keep_old=True)
        self.r_pattern = self._text(f, "runsheet_filename_pattern", settings.runsheet_filename_pattern,
                                    "Placeholders: {month} {year} (of the first day)  {case}  {index}  {date}",
                                    keep_old=True)
        f.addRow(_note("Point at a name for its placeholders: {case} is the short caption, {index} the index "
                           "number, {date} the date of the minutes."))
        f = self._card(page, "Saving")
        self.o_preview = self._check(f, "preview_before_saving", settings.preview_before_saving,
                                     "Generate and Generate all first show the files as pictures, with the math of "
                                     "the invoices;\nnothing is saved until you click Save.")
        self.o_open = self._check(f, "open_after", settings.open_after)
        self.o_flat = self._check(f, "flatten", settings.flatten,
                                  "Applies to minute agreements, MOFRs and invoices: they are locked as they are "
                                  "made.\nUnticked, they stay fillable; File → Lock finished PDFs locks a copy later.")

    def _page_program(self, page: QVBoxLayout, settings: Settings) -> None:
        """Program: how it looks, its start card, and whether it looks for new versions."""
        from .zoom import MAX, MIN, zoom
        f = self._card(page, "Look")
        self.o_theme = _combo({"system": "As Windows is", "light": "Light", "dark": "Dark"}, settings.theme)
        self.o_theme.setToolTip("Also View → Theme in the main window.")
        self._row(f, "theme", self.o_theme, save=lambda s: setattr(s, "theme", self.o_theme.currentData()))
        self.o_zoom = QSpinBox()
        self.o_zoom.setRange(round(MIN * 100), round(MAX * 100))
        self.o_zoom.setSingleStep(10)
        self.o_zoom.setSuffix(" %")
        self.o_zoom.setValue(round(zoom() * 100))
        self.o_zoom.setToolTip("How big everything in the window is drawn, on top of Windows' own display scaling.\n"
                               "Also Ctrl + and Ctrl − in the window, or Ctrl and the mouse wheel;\n"
                               "Ctrl 0 goes back to 100 %.")
        self._row(f, "zoom", self.o_zoom, save=lambda s: setattr(s, "zoom", self.o_zoom.value() / 100))
        self.o_yin = self._check(f, "show_yin", settings.show_yin)
        f = self._card(page, "Start card")
        self._recent_jobs_row(f, settings)
        f = self._card(page, "New versions")
        self.o_updates = self._check(f, "check_updates", settings.check_updates,
                                     "The only time the app goes online: it asks GitHub for the number of the latest "
                                     "version\nand shows an Update button at the top of the window when there is a "
                                     "newer one. Nothing about you, your computer or your cases is sent,\nand "
                                     "nothing is installed by itself.")

    # --- the page list, finding a setting, opening at a page
    def _fill_list(self) -> None:
        """The page list: each page's title, its summary under it, a line between groups."""
        group = PAGES[0].group
        for p in PAGES:
            if p.group != group:
                group = p.group
                line = QListWidgetItem()
                line.setFlags(Qt.NoItemFlags)
                line.setSizeHint(QSize(10, z(9)))
                self.list.addItem(line)
                rule = QFrame()
                rule.setFrameShape(QFrame.HLine)
                rule.setObjectName("muted")
                self.list.setItemWidget(line, rule)
            item = QListWidgetItem()
            item.setData(Qt.UserRole, p.key)
            item.setToolTip(p.summary)
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(z(6), z(2), z(6), z(2))
            v.setSpacing(0)
            title = QLabel(p.title)
            title.setStyleSheet("font-weight: 600;")
            summary = QLabel(p.summary)
            summary.setObjectName("muted")
            v.addWidget(title)
            v.addWidget(summary)
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
            self.list.addItem(item)
            self.list.setItemWidget(item, w)
            item.setSizeHint(w.sizeHint() + QSize(0, z(9)))  # (the list's items have a padding of their own)

    def _row_of(self, key: str) -> int:
        """The page list's row of a page."""
        return next(i for i in range(self.list.count()) if self.list.item(i).data(Qt.UserRole) == key)

    def _list_changed(self, row: int) -> None:
        """A page chosen in the list: shown."""
        item = self.list.item(row)
        key = item.data(Qt.UserRole) if item is not None else None
        if key:
            self.stack.setCurrentWidget(self.pages[key])

    def current_page(self) -> str:
        """The key of the page shown."""
        return next(k for k, w in self.pages.items() if w is self.stack.currentWidget())

    def show_page(self, name: str) -> None:
        """Opens at a page: its key ("invoices"), its title ("Invoices") or the name of the tab it was before
        2.18 ("Invoice"); an unknown name opens the first."""
        key = OLD_TABS.get(name, name)
        key = key if key in PAGE else next((p.key for p in PAGES if p.title == name), PAGES[0].key)
        self.list.setCurrentRow(self._row_of(key))
        self.stack.setCurrentWidget(self.pages[key])

    show_tab = show_page  # (the name other windows used, when Settings had tabs)

    def _find(self, text: str) -> None:
        """Find a setting: while something is typed, the settings it finds are listed instead of the pages
        (each with its page and heading); cleared, the pages come back."""
        text = text.strip()
        self.found.clear()
        if not text:
            self.found.hide()
            self.list.show()
            return
        hits = search(text, windows=True)
        for e in hits:
            if e.home == SETTINGS:
                item = QListWidgetItem(f"{shown_label(e.key)}\n{PAGE[e.page].title} › {e.section}")
                item.setData(Qt.UserRole, e.key)
            else:  # (set where it acts: said where, not a page to go to)
                item = QListWidgetItem(f"Not in Settings: {e.where[0].upper()}{e.where[1:]}")
                item.setFlags(Qt.ItemIsEnabled)
            item.setToolTip(e.decides)
            self.found.addItem(item)
        if not hits:
            none = QListWidgetItem("Nothing found. Try another word, or press F1 for the help.")
            none.setFlags(Qt.NoItemFlags)
            self.found.addItem(none)
        self.list.hide()
        self.found.show()

    def _go_found(self, item: QListWidgetItem) -> None:
        """A setting found, clicked: its page, scrolled to it, the setting lit up a moment."""
        key = item.data(Qt.UserRole) if item is not None else None
        if key:
            self.go_to(key)

    def go_to(self, key: str) -> None:
        """Shows setting `key`: its page, scrolled to it and lit up a moment, the cursor in it."""
        e = entry(key)
        self.show_page(e.page)
        target = self.control(key)
        scroll = self.pages[e.page]
        # (timers with the widget as context: dropped if the window is gone meanwhile, closed and deleted)
        QTimer.singleShot(0, scroll, lambda: scroll.ensureWidgetVisible(target, 0, z(60)))
        target.setFocus(Qt.OtherFocusReason)
        lit = self._labels.get(e.row_of or key) or target
        own = self._flashed.setdefault(lit, lit.styleSheet())  # (its own, not one already lit: found twice)
        lit.setStyleSheet(own + "background: palette(highlight); color: palette(highlighted-text);")
        QTimer.singleShot(FLASH_MS, lit, lambda: self._unflash(lit))

    def _unflash(self, lit: QWidget) -> None:
        """A setting found stops being lit up: its own style sheet back (once, whoever asks first)."""
        if lit in self._flashed:
            lit.setStyleSheet(self._flashed.pop(lit))

    def eventFilter(self, obj, event) -> bool:
        """Enter in Find a setting goes to the first setting found, Enter in its list to the one chosen, and no
        further: the dialog would take it as Save. Escape in either clears what is typed, when there is something,
        rather than closing Settings."""
        if event.type() == QEvent.KeyPress and obj in (self.find, self.found):
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if obj is self.found:  # (the row chosen; on "Not in Settings…" or "Nothing found", nothing)
                    item = self.found.currentItem()
                else:
                    item = next((self.found.item(i) for i in range(self.found.count())
                                 if self.found.item(i).data(Qt.UserRole)), None)
                if item is not None and item.data(Qt.UserRole) and not self.found.isHidden():
                    self._go_found(item)
                return True
            if event.key() == Qt.Key_Escape and self.find.text():  # (the box or its list: the search goes)
                self.find.clear()
                self.find.setFocus()
                return True
        return super().eventFilter(obj, event)

    def _wire_needs(self) -> None:
        """A setting that needs another (Entry.needs) is greyed out, its row's label too, while that one is off:
        its tick box unticked, or its choice a no (Days of one case: an invoice for each day)."""
        for e in ENTRIES:
            if e.home != SETTINGS or not e.needs or e.key not in self.controls:
                continue

            def update(_=None, e=e) -> None:
                """Greys setting e out, its row's label too, unless every setting it needs is on."""
                on = all(self._is_on(n) for n in e.needs)
                for w in self.controls[e.key]:
                    w.setEnabled(on)
                if e.key in self._labels:
                    self._labels[e.key].setEnabled(on)
            for need in e.needs:
                for w in self.controls.get(need, []):
                    if isinstance(w, QCheckBox):
                        w.toggled.connect(update)
                    elif isinstance(w, QComboBox):
                        w.currentIndexChanged.connect(update)
            update()

    def _is_on(self, key: str) -> bool:
        """Whether a setting another needs is on: a tick box ticked (any of several, for a setting of several
        boxes), a choice whose value is true."""
        widgets = self.controls.get(key, [])
        boxes = [w for w in widgets if isinstance(w, QCheckBox)]
        if boxes:
            return any(b.isChecked() for b in boxes)
        combo = next((w for w in widgets if isinstance(w, QComboBox)), None)
        return bool(combo.currentData()) if combo is not None else True

    def _fit(self) -> None:
        """A size that shows a page whole on a usual screen, within the screen."""
        self.setMinimumSize(z(760), z(480))
        screen = self.screen().availableGeometry() if self.screen() else None
        w, h = z(980), z(760)
        if screen is not None:
            w, h = min(w, int(screen.width() * 0.95)), min(h, int(screen.height() * 0.9))
            self.setMinimumSize(min(z(760), w), min(z(480), h))
        self.resize(w, h)

    def show_help(self):
        """Help and F1: the help topic of the page shown (or of the control with the cursor, when it has its own),
        in a Help window of this dialog's own (a modal dialog blocks the main window's)."""
        from .help_window import help_topic_of, open_help
        focus = self.focusWidget()
        topic = help_topic_of(focus) if focus is not None and self.stack.isAncestorOf(focus) else ""
        open_help(topic or help_topic_of(self.stack.currentWidget()), self)

    def done(self, result: int) -> None:
        """Closing (Save, Cancel or the X): the page shown is the one it opens at next time."""
        SettingsDialog.last_page = self.current_page()
        super().done(result)

    # --- signature picture
    def _show_signature(self, picture: str):
        """Shows the signature picture at `picture` scaled to the row, or a hint if there is none, and enables
        Remove accordingly."""
        from pathlib import Path
        from PySide6.QtGui import QPixmap
        pix = QPixmap(picture) if picture and Path(picture).is_file() else QPixmap()
        if pix.isNull():
            self.p_sig.setPixmap(QPixmap())
            self.p_sig.setText("None - your name is typed instead.\nA photo or scan of your signature on white paper works.")
        else:
            self.p_sig.setText("")
            self.p_sig.setPixmap(pix.scaled(z(230), z(56), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.p_sig_remove.setEnabled(not pix.isNull())

    def _pick_signature(self):
        """Asks for a photo or scan of the signature and prepares it (transparent background, cropped).

        The result waits in signature_new.png until Save. Choosing a signature also ticks the box to sign
        every form. A picture that cannot be used (for instance a blank one) gives a message instead.
        """
        from ..signature import prepare, signature_path
        src, _ = QFileDialog.getOpenFileName(self, "Picture of your signature", "",
                                             "Pictures (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.heic *.heif)")
        if not src:
            return
        try:
            new = prepare(src, signature_path().with_name("signature_new.png"))
        except Exception as e:
            QMessageBox.warning(self, "Could not use that picture", str(e))
            return
        self._sig_new = str(new)
        self._show_signature(self._sig_new)
        self.p_sign.setChecked(True)  # choosing a signature means wanting it on the forms

    def _remove_signature(self):
        """Marks the signature for removal on Save and shows the empty state."""
        self._sig_new = ""
        self._show_signature("")

    def _store_signature(self, later: list[tuple[str, str]] | None = None):
        """Applies a pick or removal made in this dialog: moves the prepared picture to signature.png (or
        deletes it) and records it in the settings. Does nothing if the signature was not touched, and leaves
        the settings as they were (saying so) if the file cannot be moved or deleted. later: the warning goes
        there as (title, text), to be shown once every setting is in (accept), instead of at once.
        """
        from pathlib import Path
        from ..signature import signature_path
        if self._sig_new is None:
            return
        final = signature_path()
        try:
            if self._sig_new:
                Path(self._sig_new).replace(final)  # in one step: the old picture stays if this fails
            else:
                final.unlink(missing_ok=True)
        except OSError as e:
            warning = ("Signature", "The signature picture couldn't be "
                       f"{'stored' if self._sig_new else 'removed'}, so the one you had stays.\n\n{e}")
            if later is None:
                QMessageBox.warning(self, *warning)
            else:
                later.append(warning)
            return
        self.s.signature_image = str(final) if self._sig_new else ""

    # --- rate sheet helpers
    def _load_sheet_names(self):
        """Lists the rate sheets found in the sheets folder and keeps the current choice if it still exists (else
        rates.pick chooses one)."""
        from ..rates import list_sheets, pick
        sheets, _ = list_sheets(self._sheet_dir)
        self._sheets = {s.name: s for s in sheets}
        current = pick(sheets, self.d_sheet.currentData() or self.s.rate_sheet)
        refill_combo(self.d_sheet, [(s.name, s.name) for s in sheets or [current]], current.name)

    def _show_agreement_speed(self, _=None):
        """The line under Agreement form speed: which speed the form gets with the speeds ticked now (those a
        rate sheet names otherwise, ticked under Speeds offered, have no box here but count too: Save keeps them)."""
        from copy import copy
        from ..rates import speed_key
        if not hasattr(self, "i_agreement_note"):
            return  # (a speed box ticked while the page is made)
        trial = copy(self.s)
        keep = [x for x in self.s.invoice_speeds if speed_key(x) not in {speed_key(n) for n in SPEEDS}]
        trial.invoice_speeds = keep + [k for k, cb in self.i_speeds.items() if cb.isChecked()]
        trial.agreement_speed_first = self.i_first.currentData() or ""
        trial.agreement_speed_fallback = self.i_fallback.currentData() or "slowest"
        ticked = " + ".join(trial.invoice_speeds) or "no speed"
        pick = trial.agreement_speed()
        why = "" if speed_key(pick) == speed_key(trial.agreement_speed_first) else (
            " (the fastest offered)" if trial.agreement_speed_fallback == "fastest" else
            " (the slowest offered: the most turnaround days)")
        self.i_agreement_note.setText(
            f"With {ticked} ticked, every agreement form says {pick}{why}. A speed you choose in Who ordered "
            "comes first; when an e-mail asks for another speed, you are asked which.")

    def _pick_sheet_dir(self):
        """Lets the user choose another rate sheets folder and reloads the sheet list from it."""
        d = QFileDialog.getExistingDirectory(self, "Rate sheets folder", self.d_dir.text() or self.d_dir.placeholderText())
        if d:
            self.d_dir.setText(d)
            self._sheet_dir = d
            self._load_sheet_names()

    def _typed_sheet_dir(self):
        """A sheets folder typed (or pasted) in, Enter pressed or the box left: the Rate sheet list is that
        folder's, as after Browse..., so Save doesn't keep a sheet of the old folder with the new one."""
        d = self.d_dir.text().strip()
        if d != (self._sheet_dir or ""):
            self._sheet_dir = d
            self._load_sheet_names()

    def _open_sheet_dir(self):
        """Opens the rate sheets folder (the one typed in, or the default) in Explorer."""
        from ..rates import sheets_dir
        open_path(sheets_dir(self.d_dir.text().strip()))

    # --- AI helpers
    def _load_models(self):
        """Adds the models Ollama has installed to the model box. Silent if Ollama is not running (waits at most
        2 seconds)."""
        from ..extract_llm import OllamaExtractor
        try:
            names = OllamaExtractor(self.s).installed_models(timeout=2)
        except Exception:
            return
        current = self.a_model.currentText()
        self._fill_models(names)
        self.a_model.setCurrentText(current)

    def _fill_models(self, installed: list[str]) -> None:
        """The model box's list: the models the app offers (extract_llm.MODELS, each with what to know about it
        as its tooltip), then the others Ollama has installed and the one the settings name."""
        from ..extract_llm import MODELS
        self.a_model.clear()
        for name, what in MODELS.items():
            self.a_model.addItem(name)
            self.a_model.setItemData(self.a_model.count() - 1, what[0].upper() + what[1:], Qt.ToolTipRole)
        self.a_model.addItems(sorted({*installed, self.s.ollama_model} - set(MODELS) - {""}))

    def _test_ai(self):
        """Checks the typed model and URL with a throwaway Settings object, so nothing is saved, and shows the
        result."""
        from ..extract_llm import OllamaExtractor
        tmp = Settings()
        tmp.ollama_model, tmp.ollama_host = self.a_model.currentText().strip(), self.a_host.text().strip()
        ok, msg = OllamaExtractor(tmp).status()
        self.a_status.setText(("✓ " if ok else "✗ ") + msg)

    def _preview_invoice(self) -> None:
        """Preview…: a made-up invoice (two parties, the speeds offered) with the text as it is in the editor now,
        before Save, shown as a picture."""
        import tempfile
        from pathlib import Path
        from ..invoice import sample_invoice
        s = deepcopy(self.s)
        s.invoice_texts = self.i_texts.rows()
        s.flatten = False
        try:
            with tempfile.TemporaryDirectory() as tmp:
                png = sample_invoice(s, Path(tmp))
                from PySide6.QtGui import QPixmap
                pix = QPixmap(str(png))
        except Exception as e:
            QMessageBox.warning(self, "Preview", f"Could not make the preview: {e}")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Invoice preview (made-up case)")
        lay = QVBoxLayout(dlg)
        pic = QLabel()
        pic.setPixmap(pix)
        scroll = QScrollArea()
        scroll.setWidget(pic)
        lay.addWidget(scroll)
        ok = QDialogButtonBox(QDialogButtonBox.Close)
        ok.rejected.connect(dlg.reject)
        lay.addWidget(ok)
        dlg.resize(min(pix.width() + z(40), z(900)), z(820))
        dlg.exec()

    # --- folders
    def _folders(self, f: QFormLayout, settings: Settings) -> None:
        """The Folders card: "Save to" (every output), a folder for each case, the documents read copied beside
        the files, then a row for each output (a key of OUTPUTS, so an output added later gets one too) to give it
        a folder of its own."""
        self.o_dir = QLineEdit(settings.output_dir)
        self.o_dir.setPlaceholderText("The folder of the dropped file")
        self._row(f, "output_dir", self._folder_row(self.o_dir, "Save the outputs to", None), self.o_dir,
                  save=lambda s: setattr(s, "output_dir", self.o_dir.text().strip()))
        self._case_folder_rows(f, settings)
        head = QLabel(entry("output_dirs").label)
        head.setObjectName("muted")
        f.addRow(head)
        self.o_dirs: dict[str, QLineEdit] = {}
        for key, label in OUTPUTS.items():
            e = QLineEdit(settings.output_dirs.get(key, ""))
            builtin = OUTPUT_FOLDERS.get(key)
            e.setPlaceholderText(str(Settings().folder_for(key)) if builtin
                                 else "Save to, or its folder inside the case's")
            e.setToolTip(f"Where {label.lower()}s are saved. Blank = "
                         + (f"{Settings().folder_for(key)}" if builtin
                            else "the Save to folder above, or, with a folder for each case, its folder inside "
                                 "the case's") + ".")
            self.o_dirs[key] = e
            f.addRow(f"{label}s", self._folder_row(e, f"Folder for {label.lower()}s", key))
        self._keep("output_dirs", parts=dict(self.o_dirs), save=lambda s: setattr(
            s, "output_dirs", {k: e.text().strip() for k, e in self.o_dirs.items() if e.text().strip()}))
        f.addRow(_note("Give an output a folder of its own, or leave it blank to save it with the case's other "
                           "files. The invoices' math goes in a Math folder inside theirs."))

    def _case_folder_rows(self, f: QFormLayout, settings: Settings) -> None:
        """The Folders rows about a folder for each case inside Save to (Settings.case_folders): the box, the
        folder's name (a pattern of placeholders; only letters, digits, spaces and - , _ ( ) can be typed:
        pdfout.PATTERN_UNSAFE_RE) with an example from a made-up case, and what to do when the folder is already
        there (Settings.case_folder_existing), greyed out while the box is unticked (Entry.needs); then whether
        the documents read are copied beside the files (Settings.save_inputs)."""
        from PySide6.QtCore import QRegularExpression
        from PySide6.QtGui import QRegularExpressionValidator

        from ..models import CaseInfo
        from ..pdfout import CASE_FOLDER_PLACES, FOLDER_ALLOWED, case_folder_name
        self.o_case_folders = self._check(
            f, "case_folders", settings.case_folders,
            "Each case's minute agreements, MOFR, invoices, their math and its run sheet go into a folder of its own "
            "inside Save to, named as below,\neach kind in a folder inside it: Minute Agreements, MOFR, Invoices, "
            "Math, Trial Runs\n(\"D:\\Transcripts\\712345-2021 6-3,4-2026 Roe v Poe\\Invoices\"). An output with a "
            "folder of its own below keeps it. Unticked, they all go in Save to, the math in a Math folder there."
            "\nWhen your documents already sit in the case's folder (its name starts with the index number), it is "
            "used as it is.\nWhen more days of a trial are made later, the case's folder is renamed to name them "
            "too.")
        # (cleaned first: a pattern saved before with a character no longer allowed, "{index}.{case}", would leave
        # the box refusing every key, its whole text never valid)
        self.o_case_pattern = QLineEdit(clean_folder_pattern(settings.case_folder_pattern))
        self.o_case_pattern.setPlaceholderText(CASE_FOLDER_PATTERN)
        # (only what every file system takes can be typed or pasted, besides the placeholders' braces: letters,
        # accented ones too, digits, spaces and - , _ ( ), as pdfout.PATTERN_UNSAFE_RE keeps; Qt's \w is ASCII alone
        # without the Unicode option)
        self.o_case_pattern.setValidator(QRegularExpressionValidator(
            QRegularExpression(r"[\w ,()\-{}]*", QRegularExpression.UseUnicodePropertiesOption), self.o_case_pattern))
        places = " ".join("{" + p + "}" for p in CASE_FOLDER_PLACES)
        self.o_case_pattern.setToolTip(f"The case folder's name. Placeholders: {places}\n"
                                       "({index} 712345-2021, {days} the days \"10-13,14,15-2026\", {case} the short "
                                       "caption, {date} the first day, {dates} \"6-3-2026 to 6-4-2026\").\n"
                                       f"Only letters, digits and {FOLDER_ALLOWED} can be typed. What the documents "
                                       "say is kept to those too (\"Jones v. USA Hauling\" is \"Jones v USA "
                                       "Hauling\"),\nso the folder can go to any computer or cloud drive.")
        example = CaseInfo()
        for key, value in (("case_name", "Jane Roe v. X.Y. Holding Corporation"), ("index_no", "712345/2021"),
                           ("dates", "6/3/2026, 6/4/2026"), ("court", "Supreme"), ("county", "Queens"),
                           ("part", "12"), ("judge", "Hon. A. Justice")):
            example.set(key, value)
        self.o_case_hint = QLabel()
        self.o_case_hint.setObjectName("muted")
        self.o_case_hint.setTextFormat(Qt.PlainText)  # (its "< >" is no tag)
        # short lines, not wrapped: a wrapped label leaves a gap above it in a form

        def show_example(_=None) -> None:
            """The hint: the name the pattern typed gives the made-up case (cut at 70 characters)."""
            name = case_folder_name(example, self.o_case_pattern.text().strip() or CASE_FOLDER_PATTERN)
            name = name if len(name) <= 70 else name[:69] + "…"
            self.o_case_hint.setText(f"e.g. \"{name}\"\nPlaceholders: {places}\n"
                                     f"Only letters, digits and {FOLDER_ALLOWED}")
        self.o_case_pattern.textChanged.connect(show_example)
        show_example()
        # (the box refuses those characters typed or pasted, but not in the pattern it started with: a settings
        # file edited by hand)
        self._row(f, "case_folder_pattern", self.o_case_pattern, save=lambda s: setattr(
            s, "case_folder_pattern", clean_folder_pattern(self.o_case_pattern.text())))
        f.addRow("", self.o_case_hint)
        self._keep("case_folder_pattern", self.o_case_hint)
        self.o_case_existing = _combo(CASE_FOLDER_EXISTING, settings.case_folder_existing)
        self.o_case_existing.setToolTip("When Generate finds a folder of the very same name already there with files "
                                        "in it (the same days made before, or another case of that name).\n"
                                        "A later day of a case joins the case's folder without asking, the folder "
                                        "renamed for its days;\nwith \"Make a new one beside it\", it gets a folder of "
                                        "its own instead.")
        self._row(f, "case_folder_existing", self.o_case_existing,
                  save=lambda s: setattr(s, "case_folder_existing", self.o_case_existing.currentData()))
        self.o_save_inputs = self._check(
            f, "save_inputs", settings.save_inputs,
            "At Generate, the transcripts, e-mails and photos the files were made from (and pasted text, as a .txt "
            "file)\nare copied into an Inputs folder in the case's folder (in Save to without case folders), to look "
            "back at should a file come out wrong.\nOff as a rule: it keeps a second copy of every transcript. A "
            "document already where the files go (in the case's folder) isn't copied.")

    def _folder_row(self, edit: QLineEdit, title: str, key: str | None) -> QHBoxLayout:
        """[folder] [Browse...] [Open] for one of the Folders rows."""
        row = QHBoxLayout()
        row.addWidget(edit, 1)
        browse = QPushButton("Browse...")
        browse.clicked.connect(lambda: self._pick_into(edit, title))
        row.addWidget(browse)
        opener = QPushButton("Open")
        opener.setToolTip("Opens the folder (made first when it isn't there yet)")
        opener.clicked.connect(lambda: self._open_folder(edit, key))
        row.addWidget(opener)
        return row

    def _open_folder(self, edit: QLineEdit, key: str | None) -> None:
        """Opens the folder of a Folders row as typed (before Save): its own, else where its files go now."""
        from pathlib import Path
        typed = edit.text().strip()
        if typed:
            folder = Path(typed)
        elif key in OUTPUT_FOLDERS:
            folder = Settings().folder_for(key)
        elif self.o_dir.text().strip():
            folder = Path(self.o_dir.text().strip())
        else:
            QMessageBox.information(self, "Folders", "Without a Save to folder, the files are saved next to the "
                                    "first document dropped (or in Documents\\Minute Agreements).")
            return
        try:
            folder.mkdir(parents=True, exist_ok=True)  # not made until the first file is saved there
        except OSError as e:
            QMessageBox.warning(self, "Could not open the folder", str(e))
            return
        open_path(folder)

    def _pick_into(self, edit: QLineEdit, title: str):
        """Asks for a folder, starting at the one in `edit`, and puts the choice into `edit`."""
        d = QFileDialog.getExistingDirectory(self, title, edit.text() or edit.placeholderText())
        if d:
            edit.setText(d)

    # --- other reporters
    @staticmethod
    def _reporter_names(text: str) -> tuple[dict[str, str], list[str]]:
        """'ds = Dana' lines -> {'ds': 'Dana'} (also 'D.S.: Dana', 'ds - Dana', a tab, or 'ds Dana'), and the
        lines that can't be read that way. The initials are written as in My info: 'D. S.' is 'ds'."""
        out, bad = {}, []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r"(.+?)\s*(?:=|:|\t|\s-\s)\s*(.+)", line)
            if not m or not re.fullmatch(r"[a-z]{2,4}", reporter_key(m.group(1))):
                m = re.match(r"((?:[A-Za-z]\.?\s?){2,3})\s+(.+)", line)  # "ds Dana", "D.S. Dana"
            if m and re.fullmatch(r"[a-z]{2,4}", reporter_key(m.group(1))) and m.group(2).strip():
                out[reporter_key(m.group(1))] = m.group(2).strip()
            else:
                bad.append(line)
        return out, bad

    def _save_reporters(self, s: Settings) -> None:
        """Save: each reporter's name from the Names box, with the invoice details kept for them; a reporter with
        details but no line keeps them, without a name. Lines that can't be read are left out, with a warning."""
        names, bad = self._reporter_names(self.r_names.toPlainText())
        s.reporters = {k: replace(self._details.get(k, ReporterProfile()), name=v) for k, v in names.items()}
        for k, d in self._details.items():  # invoice details of a reporter with no line: kept, without a name
            if k not in s.reporters and d.has_details():
                s.reporters[k] = replace(d, name="")
        if bad:
            self._warnings.append(("Reporters", f"These lines under {path('reporters')} were left out (write them "
                                   "as initials = name, e.g. ds = Dana):\n\n" + "\n".join(bad[:10])))

    def _fill_reporters(self) -> None:
        """The reporters listed in the Reporters box, and those with invoice details but no line in it (details
        saved from Whose pages...), for Invoice details...; marked when they have details."""
        names, _ = self._reporter_names(self.r_names.toPlainText())
        keep = self.r_who.currentData()
        listed = {**{k: "" for k, d in self._details.items() if d.has_details()}, **names}
        items = [(f"{k.upper()}" + (f" - {v}" if v else "")
                  + ("  ✓" if self._details.get(k, ReporterProfile()).has_details() else ""), k)
                 for k, v in sorted(listed.items())]
        refill_combo(self.r_who, items, keep)
        self.r_edit.setEnabled(bool(items))

    def _edit_reporter(self) -> None:
        """Invoice details... for the reporter chosen: kept with the settings when they are saved."""
        k = self.r_who.currentData()
        if not k:
            return
        names, _ = self._reporter_names(self.r_names.toPlainText())
        dlg = ReporterDialog(k, replace(self._details.get(k, ReporterProfile()), name=names.get(k, "")), self)
        if dlg.exec() == QDialog.Accepted:
            self._details[k] = dlg.value()
            if self._details[k].name != names.get(k, ""):  # (else the box's line would undo it on Save)
                self._set_reporter_line(k, self._details[k].name)
            self._fill_reporters()

    def _set_reporter_line(self, k: str, name: str) -> None:
        """Writes reporter k's line in the Reporters box as "k = name" (none for a blank name), where it was."""
        lines, done = [], False
        for line in self.r_names.toPlainText().splitlines():
            if k in self._reporter_names(line)[0]:
                if name and not done:
                    lines.append(f"{k} = {name}")
                done = True
            else:
                lines.append(line)
        if name and not done:
            lines.append(f"{k} = {name}")
        self.r_names.setPlainText("\n".join(lines))

    # --- firms you answered
    def _fill_firms(self) -> None:
        """Firms you answered: one line per answer kept, "Smith Law  =  Smith Law Group (Sam Poe)" (same firm) or
        "≠" (not the same), then those given for now only, marked "for now"; rows saved by 2.2.0 (without the
        names) show the keys compared."""
        self.i_firms.clear()
        for r, kept in [(r, True) for r in self._firm_answers] + [(r, False) for r in self.session_answers]:
            a, b = (r[3] or r[0], r[4] or r[1]) if len(r) >= 5 else (r[0], r[1])
            self.i_firms.addItem(f"{a}  {'=' if r[2] else '≠'}  {b}   ({'same firm' if r[2] else 'not the same'}"
                                 f"{'' if kept else ', for now'})")
        if not self._firm_answers and not self.session_answers:
            item = QListWidgetItem("None yet: you're asked when two rows may be one firm")
            item.setFlags(Qt.NoItemFlags)
            self.i_firms.addItem(item)
        self.i_forget.setEnabled(bool(self._firm_answers or self.session_answers))
        self.i_forget_all.setEnabled(bool(self._firm_answers or self.session_answers))

    def _forget_firms(self, everything: bool) -> None:
        """Forget / Forget all: the answers go when Settings are saved (the ones for now too)."""
        rows = {self.i_firms.row(it) for it in self.i_firms.selectedItems()}
        kept = len(self._firm_answers)
        if everything:
            self._firm_answers, self.session_answers = [], []
        else:
            self._firm_answers = [r for n, r in enumerate(self._firm_answers) if n not in rows]
            self.session_answers = [r for n, r in enumerate(self.session_answers) if n + kept not in rows]
        self._fill_firms()

    # --- the start card
    def _recent_jobs_row(self, f: QFormLayout, settings: Settings) -> None:
        """Program → Start card → Recent jobs: whether the start card lists the jobs made lately, how many
        (RECENT_JOBS_MAX at most, so the card stays short) and how lately made (the user, 2026-10-28)."""
        self.o_recent = QCheckBox("List them while nothing is open,")
        self.o_recent.setToolTip("The Recent jobs card at the top of an empty window: click a job to open it again.\n"
                                 "Unticked, the card only says how to begin.")
        self.o_recent.setChecked(settings.recent_jobs_show)
        self.o_recent_count = QSpinBox()
        self.o_recent_count.setRange(1, RECENT_JOBS_MAX)
        self.o_recent_count.setValue(settings.recent_jobs_count)
        self.o_recent_count.setToolTip(f"How many jobs it lists at most ({RECENT_JOBS_MAX} at most).")
        self.o_recent_days = QSpinBox()
        self.o_recent_days.setRange(0, RECENT_JOBS_DAYS_MAX)
        self.o_recent_days.setPrefix("in the last ")  # ("made in the last 30 days", "made at any time")
        self.o_recent_days.setSuffix(" days")
        self.o_recent_days.setSpecialValueText("at any time")  # (0)
        self.o_recent_days.setValue(settings.recent_jobs_days)
        self.o_recent_days.setToolTip("A job made (or made again) longer ago than this isn't listed.\n"
                                      "0: any time.")
        line = QHBoxLayout()
        line.setSpacing(z(6))
        line.addWidget(self.o_recent)
        line.addWidget(QLabel("up to"))
        line.addWidget(self.o_recent_count)
        line.addWidget(QLabel("made"))
        line.addWidget(self.o_recent_days)
        line.addStretch(1)
        self._row(f, "recent_jobs_show", line, self.o_recent,
                  save=lambda s: setattr(s, "recent_jobs_show", self.o_recent.isChecked()))
        self._keep("recent_jobs_count", self.o_recent_count,
                   save=lambda s: setattr(s, "recent_jobs_count", self.o_recent_count.value()))
        self._keep("recent_jobs_days", self.o_recent_days,
                   save=lambda s: setattr(s, "recent_jobs_days", self.o_recent_days.value()))

    # --- index number patterns
    def _index_patterns_rows(self, f: QFormLayout, settings: Settings) -> None:
        """Reading documents → Index numbers: the user's own index number patterns (Settings.index_patterns), one
        per line, tried as well as the app's own (the user, 2026-10-21: they should be the user's to change), what
        is wrong with one as it is typed, and a box to try them on a line of text."""
        self.o_index = QPlainTextEdit("\n".join(settings.index_patterns))
        self.o_index.setPlaceholderText(r"e.g.  CV-(\d{6})-(\d{2})/QU")
        self.o_index.setToolTip(INDEX_PATTERNS_TIP)
        self.o_index.setFixedHeight(z(64))
        self.o_index_try = QLineEdit()
        self.o_index_try.setPlaceholderText("Try them on: a line from a document, e.g. Re: Roe v. Poe, CV-012345-25/QU")
        self.o_index_note = QLabel("")
        self.o_index_note.setWordWrap(True)
        self.o_index_note.setObjectName("muted")
        self.o_index.textChanged.connect(self._index_patterns_check)
        self.o_index_try.textChanged.connect(self._index_patterns_check)
        box = QVBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        for wid in (self.o_index, self.o_index_try, self.o_index_note):
            box.addWidget(wid)
        self._row(f, "index_patterns", box, self.o_index, self.o_index_try,
                  save=lambda s: setattr(s, "index_patterns", self._index_lines()))
        self._index_patterns_check()

    def _index_lines(self) -> list[str]:
        """The patterns typed, one per line, blank lines left out."""
        return [x.strip() for x in self.o_index.toPlainText().splitlines() if x.strip()]

    def _index_patterns_check(self) -> None:
        """Under the patterns: what is wrong with each that can't be used, else what they find in the text to try
        them on (with the app's own: 'Finds 712345/2021'), else, with nothing to try them on, how many there are."""
        from ..extract_regex import RegexExtractor, index_pattern_problem
        from ..ingest import ingest_text
        lines = self._index_lines()
        bad = [f"⚠ line {i}: {why}" for i, x in enumerate(lines, 1) if (why := index_pattern_problem(x))]
        text = self.o_index_try.text().strip()
        if bad:
            note = "\n".join(bad)
        elif text:
            ex = RegexExtractor(index_patterns_=lines).extract(ingest_text(text, "try.txt"))
            found = sorted({c.value for c in ex.fields.get("index_no", [])})
            note = f"Finds {', '.join(found)}" if found else "Finds no index number in it."
        else:
            note = (f"{len(lines)} pattern{'s' if len(lines) != 1 else ''} of yours, tried as well as the app's "
                    "own." if lines else "The app's own patterns only (they read 712345/2021, 712345/21, "
                    "Index No. 712345-21 and the like).")
        self.o_index_note.setText(note)

    # --- Save
    def accept(self):
        """Runs every control's save (in the order they were made, then those that must come after the others:
        the split rule after the invoice text) into the Settings object, saves it to disk and closes. A blank file
        name pattern or invoice number format keeps the old one. Reporter lines that cannot be read are left out,
        with a warning that lists them. An index number pattern that can't be used keeps the window open at its
        page, saying why (it would be lost). The file is written even over a settings file that couldn't be read
        (Settings.save(force=True)); when it can't be written the user is told, and the dialog closes all the
        same. The warnings (those lines, a signature that couldn't be stored) are shown once every setting is in
        and saved, never halfway; only the index number patterns' stops the Save, before anything is changed."""
        from ..extract_regex import index_pattern_problem
        bad = [f"Line {i}: {why}" for i, x in enumerate(self._index_lines(), 1) if (why := index_pattern_problem(x))]
        if bad:
            self.go_to("index_patterns")
            QMessageBox.warning(self, "Index number patterns", "These index number patterns can't be used:\n\n"
                                + "\n".join(bad) + f"\n\nCorrect them or delete them ({path('index_patterns')}).")
            return
        # warnings wait until every setting is in and saved: a box opened halfway lets the window's work go on
        # (a document read, the AI answering) with the settings half changed, and maybe saved so
        self._warnings = []
        s = self.s
        for _key, save in self._saves + self._late:
            save(s)
        s.settings_page = self.current_page()
        try:
            s.save(force=True)  # (the user's own Save: written even over a settings file that couldn't be read)
        except OSError as e:
            # the settings are changed all the same (the window follows them, and they are saved again when
            # it closes): the dialog closes rather than keeping them half applied behind a Cancel
            show_save_error(self, e, "Could not save the settings",
                            "\n\nYour changes are kept for now and saved again when the app closes.")
        for title, text in self._warnings:
            QMessageBox.warning(self, title, text)
        super().accept()
