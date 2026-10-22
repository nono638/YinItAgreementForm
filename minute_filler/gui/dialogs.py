"""The app's dialogs: Settings (with its invoice text editor; the Dates tab's court holidays are
gui/holiday_editor.py, the Records tab's tick boxes and colours gui/tracking_editor.py), the "please clarify"
questions before filling, the speed the agreement form names when an e-mail asks for another (SpeedDialog), the
speed each firm of a split order ordered at (SplitSpeedsDialog), the run sheet choice, a job's invoice Peripherals
(for that job only), granular detail and whose pages of a transcript of several reporters to bill, another
reporter's invoice details (ReporterDialog), the Ollama setup help (with a model download) and About. The preview
before saving, the math and the first-run welcome are in preview.py; the Excerpts window (who ordered which pages)
is gui/excerpts.py; the Help window (the manual, F1) is gui/help_window.py."""
from __future__ import annotations

import re
from dataclasses import replace

from PySide6.QtCore import QSignalBlocker, QThread, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QRadioButton, QScrollArea, QSpinBox, QTabWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from .. import __version__, courthouses
from ..models import Attorney, FIELD_LABELS
from ..settings import (AGREEMENT_FALLBACKS, AI_TICKS, CASE_FOLDER_EXISTING, CASE_FOLDER_PATTERN, DETAIL_ITEMS,
                        INDEX_RULES, INDEX_SHARED, MATH_SAVES, OUTPUT_FOLDERS, OUTPUTS, ROUNDINGS, SPEEDS,
                        TURNAROUND_FROM, ReporterProfile,
                        TEXT_PLACEHOLDERS, TEXT_PLACES, TEXT_WHEN, Settings, clean_folder_pattern,
                        default_invoice_texts, reporter_key)
from ..tracking import box_rows, rule_rows
from .widgets import check_row, open_path, open_url, refill_combo, rounded, show_save_error
from .zoom import z


def _form(parent: QWidget) -> QFormLayout:
    """A form layout with the label alignment, spacing and margins used by every settings tab."""
    f = QFormLayout(parent)
    f.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    f.setHorizontalSpacing(14)
    f.setVerticalSpacing(9)
    f.setContentsMargins(18, 18, 18, 18)
    return f


# The help topic (help_topics) of each Settings tab, opened by its Help button and F1
SETTINGS_TOPICS = {"My info": "set-my-info", "Defaults": "set-defaults", "Options": "set-options",
                   "Dates": "set-dates", "Invoice": "set-invoice", "Records": "set-records",
                   "Run sheet": "set-run-sheet", "AI": "set-ai"}


class SettingsDialog(QDialog):
    """The Settings window: tabs for My info, Defaults, Options, Dates (business days and the court holidays:
    gui/holiday_editor.py), Invoice, Records (the Records window's tick boxes and colours: gui/tracking_editor.py),
    Run sheet and AI.

    Nothing is stored until Save (accept), which copies every control back into the Settings object
    and saves it to disk. Cancel leaves the settings, and a picked but unsaved signature image,
    untouched.
    """
    def __init__(self, settings: Settings, parent=None, session_answers: list | None = None):
        """settings: the Settings object to edit in place. session_answers: the window's answers about rows that
        may be one firm given for now only (Remember unticked), listed under Firms you answered marked "for now";
        after Save, `self.session_answers` holds those not forgotten."""
        super().__init__(parent)
        self.s = settings
        self.session_answers = [list(r) for r in session_answers or []]
        self.setWindowTitle("Settings")
        self.setMinimumWidth(z(560))
        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)

        # --- My info
        w = QWidget()
        f = _form(w)
        p = settings.profile
        self.p_name = QLineEdit(p.name)
        self.p_title = QLineEdit(p.title)
        self.p_addr1 = QLineEdit(p.address1)
        self.p_addr1.setPlaceholderText("e.g. Supreme Court, 123 Courthouse Plaza, Room 100")
        self.p_addr2 = QLineEdit(p.address2)
        self.p_addr2.setPlaceholderText("e.g. Anytown, NY 10000")
        self.p_phone = QLineEdit(p.phone)
        self.p_fax = QLineEdit(p.fax)
        self.p_email = QLineEdit(p.email)
        self.p_web = QLineEdit(p.website)
        self.p_web.setPlaceholderText("optional, shown on invoices")
        self.p_initials = QLineEdit(p.initials)
        self.p_initials.setPlaceholderText("as you put them at the foot of your transcript pages, e.g. pr")
        self.p_initials.setToolTip("Run sheets and invoices: the pages with these initials are yours (an invoice "
                                   "of a transcript several reporters\nwrote bills yours, unless Whose pages… says "
                                   "otherwise).\n"
                                   "Blank = the first letters of your first and last name.")
        for label, wid in (("Name", self.p_name), ("Title", self.p_title), ("Address", self.p_addr1),
                           ("", self.p_addr2), ("Telephone", self.p_phone), ("Fax", self.p_fax),
                           ("Email", self.p_email), ("Website", self.p_web), ("Initials", self.p_initials)):
            f.addRow(label, wid)
        # Signature picture: shown as it will appear on the form; stored on Save
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
        row.addWidget(self.p_sig, 1)
        row.addWidget(pick)
        row.addWidget(self.p_sig_remove)
        f.addRow("Signature", row)
        self.p_sign = QCheckBox("Sign the court reporter line on every form")
        self.p_sign.setToolTip("With your signature picture if you chose one, otherwise your name is typed.")
        self.p_sign.setChecked(settings.sign_reporter)
        f.addRow("", self.p_sign)
        self._show_signature(settings.signature_image)
        self.tabs.addTab(w, "My info")

        # --- Defaults
        w = QWidget()
        f = _form(w)
        self.d_court = QLineEdit(settings.default_court)
        self.d_county = QLineEdit(settings.default_county)
        self.d_copies = QLineEdit(settings.default_copies)
        f.addRow("Court", self.d_court)
        f.addRow("County", self.d_county)
        f.addRow("Copies", self.d_copies)

        # Rate sheets
        self.d_sheet = QComboBox()
        self._sheet_dir = settings.rate_sheets_dir
        self._load_sheet_names()
        f.addRow("Rate sheet", self.d_sheet)
        row = QHBoxLayout()
        self.d_dir = QLineEdit(settings.rate_sheets_dir)
        from ..rates import default_dir
        self.d_dir.setPlaceholderText(str(default_dir()))
        pick = QPushButton("Browse...")
        pick.clicked.connect(self._pick_sheet_dir)
        open_btn = QPushButton("Open folder")
        open_btn.clicked.connect(self._open_sheet_dir)
        row.addWidget(self.d_dir, 1)
        row.addWidget(pick)
        row.addWidget(open_btn)
        f.addRow("Sheets folder", row)
        help_lbl = QLabel("Rate sheets are CSV files (open them in Excel). To add one, e.g. city rates, copy "
                          "\"Rate Sheet TEMPLATE.csv\" in that folder, rename it, and fill in the prices. "
                          "An optional Days column sets each speed's turnaround.")
        help_lbl.setWordWrap(True)
        help_lbl.setObjectName("muted")
        f.addRow("", help_lbl)

        self.days = {}
        row = QHBoxLayout()
        for label in reversed(SPEEDS):  # fastest first
            attr = f"days_{label.lower()}"
            spin = QSpinBox()
            spin.setRange(0, 120)
            spin.setValue(getattr(settings, attr))
            self.days[attr] = spin
            row.addWidget(QLabel(label))
            row.addWidget(spin)
            row.addSpacing(8)
        row.addStretch(1)
        f.addRow("Turnaround days", row)
        note = QLabel("Used when a rate sheet has no Days column. Business days (weekends and court holidays not "
                      "counted) unless the Dates tab says calendar days.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        f.addRow("", note)
        self.tabs.addTab(w, "Defaults")

        # --- Options
        w = QWidget()
        f = _form(w)
        self.o_per_email = QCheckBox("Write \"per email\" in the attorney signature spot")
        self.o_flat = QCheckBox("Flatten the PDF (fields no longer editable)")
        self.o_flat.setToolTip("Applies to minute agreements, MOFRs and invoices: they are locked as they are made.\n"
                               "Unticked, they stay fillable; File → Lock finished PDFs locks a copy later.")
        self.o_open = QCheckBox("Open the PDF after saving")
        self.o_preview = QCheckBox("Show a preview before saving (Generate, Generate all)")
        self.o_preview.setToolTip("Generate and Generate all first show the files as pictures, with the math of the "
                                  "invoices;\nnothing is saved until you click Save.")
        self.o_tc = QCheckBox("Convert ALL-CAPS names to Title Case")
        self.o_yin = QCheckBox("Show the yin-yang (working / done / stumped pictures)")
        for cb, val in ((self.o_per_email, settings.per_email), (self.o_flat, settings.flatten),
                        (self.o_open, settings.open_after), (self.o_preview, settings.preview_before_saving),
                        (self.o_tc, settings.title_case_names),
                        (self.o_yin, settings.show_yin)):
            cb.setChecked(val)
            f.addRow("", cb)
        from ..fill import FORMS
        self.o_form = QComboBox()
        for key, (_, label) in FORMS.items():
            self.o_form.addItem(label, key)
        self.o_form.setCurrentIndex(max(0, self.o_form.findData(settings.form_choice)))
        f.addRow("Form", self.o_form)
        make, self.o_outputs = check_row(OUTPUTS, settings.outputs)
        make.addStretch(1)
        f.addRow("Make by default", make)
        self.o_division = QComboBox()
        self.o_division.addItem("Civil", "civil")
        self.o_division.addItem("Criminal", "criminal")
        self.o_division.setCurrentIndex(max(0, self.o_division.findData(settings.mofr_division)))
        f.addRow("MOFR case", self.o_division)
        self.o_instr = QCheckBox("Include the instructions page (UCS form page 2)")
        self.o_instr.setToolTip("Unticked: the saved PDF has the form page only.")
        self.o_instr.setChecked(settings.include_instructions)
        f.addRow("", self.o_instr)
        self.o_combine = QCheckBox("Batches: put all days of the same case on one form")
        self.o_combine.setToolTip("Off: documents about the same case make one form per day of proceedings.")
        self.o_combine.setChecked(settings.batch_combine_dates)
        f.addRow("", self.o_combine)
        self.o_per_case = QCheckBox("Minute agreements and MOFRs: one for the whole case (every day on its invoice)")
        self.o_per_case.setToolTip(
            "Generate all, when the days of a case share an invoice (Settings → Invoice → Days of one case):\n"
            "one minute agreement per attorney, listing the days it ordered and every page it ordered on them,\n"
            "whoever wrote them (its invoice bills only your pages of them), and one MOFR for all the days.\n"
            "Off: an agreement per attorney and a MOFR for each day, as before.\n"
            "\"Generate this job\" always makes the forms of the day shown alone.")
        self.o_per_case.setChecked(settings.forms_per_case)
        f.addRow("", self.o_per_case)
        self._folders(f, settings)
        self.o_pattern = QLineEdit(settings.filename_pattern)
        self.o_pattern.setToolTip("Placeholders:\n{case}  {index}  {attorney}\n"
                                  "{date} - date of the minutes\n{today} - the date the form is dated (today, or "
                                  "the next business day: Dates tab)")
        f.addRow("File name", self.o_pattern)
        self.o_mofr_pattern = QLineEdit(settings.mofr_filename_pattern)
        self.o_mofr_pattern.setToolTip(self.o_pattern.toolTip())
        f.addRow("MOFR file name", self.o_mofr_pattern)
        self.o_theme = QComboBox()
        self.o_theme.addItems(["system", "light", "dark"])
        self.o_theme.setCurrentText(settings.theme)
        f.addRow("Theme", self.o_theme)
        from .zoom import MAX, MIN, zoom
        self.o_zoom = QSpinBox()
        self.o_zoom.setRange(round(MIN * 100), round(MAX * 100))
        self.o_zoom.setSingleStep(10)
        self.o_zoom.setSuffix(" %")
        self.o_zoom.setValue(round(zoom() * 100))
        self.o_zoom.setToolTip("How big everything in the window is drawn, on top of Windows' own display scaling.\n"
                               "Also Ctrl + and Ctrl − in the window, or Ctrl and the mouse wheel;\n"
                               "Ctrl 0 goes back to 100 %.")
        f.addRow("Zoom", self.o_zoom)
        self._index_patterns_rows(f, settings)
        self.o_fuzzy_numbers = QCheckBox("Fuzzy search matches numbers loosely too")
        self.o_fuzzy_numbers.setToolTip("Records → the search box's Fuzzy box. Ticked: numbers are matched like words, "
                                        "so \"2026-0001\" also finds 2026-0002.\nUnticked: a word with a digit in "
                                        "it (an invoice or index number, a date) must be found as typed;\n"
                                        "names and other words still forgive a typo.")
        self.o_fuzzy_numbers.setChecked(settings.fuzzy_numbers)
        f.addRow("Records search", self.o_fuzzy_numbers)
        self.o_recaps = QCheckBox("Show a recap of last month (and last year) when Records is first opened")
        self.o_recaps.setToolTip("\"Last month you made $870.00 with 243 pages\": once a month, and once a year for "
                                 "the year before.")
        self.o_recaps.setChecked(settings.recaps)
        f.addRow("Recaps", self.o_recaps)
        self.o_math = QCheckBox("Show the math of each invoice")
        self.o_math.setToolTip("How each amount is reached (pages × rate, the copies, the split between parties):\n"
                               "the preview's first tab, The math, or, with previews off, a window after saving\n"
                               "that can copy it or save it as a PDF. For Generate and Generate all.\n"
                               "(Generate also saves it with the invoices: Invoice tab → Save the math.)")
        self.o_math.setChecked(settings.show_math)
        f.addRow("Invoice math", self.o_math)
        self.o_updates = QCheckBox("Look for a newer version once a day")
        self.o_updates.setToolTip("The only time the app goes online: it asks GitHub for the number of the latest "
                                  "version\nand shows an Update button at the top of the window when there is a "
                                  "newer one. Nothing about you, your "
                                  "computer or your cases is sent,\nand nothing is installed by itself.")
        self.o_updates.setChecked(settings.check_updates)
        f.addRow("New versions", self.o_updates)
        scroll = QScrollArea()  # a long tab: scrolls on small screens
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(w)
        self.tabs.addTab(scroll, "Options")
        self._dates_tab(settings)

        # --- Invoice
        w = QWidget()
        f = _form(w)
        intro = QLabel("Invoices bill a transcript's pages (or the pages typed in Est. number of pages), priced from "
                       "the rate sheet. The invoice offers several speeds, each at its own price; the minute "
                       "agreement form names one speed at one rate per page.")
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        f.addRow(intro)
        from ..rates import speed_key
        offered = {speed_key(x) for x in settings.invoice_speeds}
        speeds, self.i_speeds = check_row({n: n for n in SPEEDS}, [n for n in SPEEDS if speed_key(n) in offered],
                                          self._show_agreement_speed, spacing=12)
        speeds.addStretch(1)
        f.addRow("Speeds offered", speeds)
        hint = QLabel("The attorney chooses one. With one ticked the invoice bills that speed alone. "
                      "The same boxes are under the rate sheet in the main window (Speed, pages and dates).")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        f.addRow("", hint)
        # the one speed the minute agreement form names, out of those offered (Settings.agreement_speed)
        first = QHBoxLayout()
        self.i_first = QComboBox()
        names = list(SPEEDS)
        if settings.agreement_speed_first and not any(speed_key(n) == speed_key(settings.agreement_speed_first)
                                                      for n in names):
            names.append(settings.agreement_speed_first)  # a sheet's own spelling ("Expedite"): kept, not Regular
        for n in names:
            self.i_first.addItem(n, n)
        self.i_first.setCurrentIndex(max(0, next((i for i, n in enumerate(names)
                                                  if speed_key(n) == speed_key(settings.agreement_speed_first)), 0)))
        self.i_fallback = QComboBox()
        for k, label in AGREEMENT_FALLBACKS.items():
            self.i_fallback.addItem(label, k)
        self.i_fallback.setCurrentIndex(max(0, self.i_fallback.findData(settings.agreement_speed_fallback)))
        first.addWidget(self.i_first)
        first.addWidget(QLabel("when it is offered; otherwise"))
        first.addWidget(self.i_fallback)
        first.addStretch(1)
        f.addRow("Agreement form speed", first)
        self.i_agreement_note = QLabel("")
        self.i_agreement_note.setObjectName("muted")
        self.i_agreement_note.setWordWrap(True)
        f.addRow("", self.i_agreement_note)
        self.i_first.currentIndexChanged.connect(self._show_agreement_speed)
        self.i_fallback.currentIndexChanged.connect(self._show_agreement_speed)
        self._show_agreement_speed()
        shows = QGridLayout()
        shows.setHorizontalSpacing(16)
        shows.setVerticalSpacing(6)
        self.i_items: dict[str, QCheckBox] = {}
        for i, (key, label) in enumerate(DETAIL_ITEMS.items()):
            cb = QCheckBox(label)
            cb.setChecked(key in settings.invoice_detail_items)
            self.i_items[key] = cb
            shows.addWidget(cb, i // 2, i % 2)
        f.addRow("Granular detail shows", shows)
        self.i_detailed_copy = QCheckBox("Also save a detailed copy of each invoice")
        self.i_detailed_copy.setToolTip("Next to each invoice, a copy with the granular detail above (the same number, "
                                        "\"... (detailed).pdf\"),\nready for when someone asks how the amount was "
                                        "reached. A job whose invoice already shows the detail gets none.")
        self.i_detailed_copy.setChecked(settings.invoice_detailed_copy)
        f.addRow("", self.i_detailed_copy)
        self.i_save_math = QComboBox()
        for key, label in MATH_SAVES.items():
            self.i_save_math.addItem(label, key)
        self.i_save_math.setCurrentIndex(max(0, self.i_save_math.findData(settings.save_math)))
        self.i_save_math.setToolTip("How each amount was reached, saved as PDFs next to the invoices when Generate "
                                    "makes them:\neach firm's own (\"... - the math.pdf\", only what that firm owes, "
                                    "to send it) and everyone's in one\n(every firm's amounts, to look back at the "
                                    "job). The same choice is under the math itself, in the preview and its window.")
        f.addRow("Save the math", self.i_save_math)
        self.i_email = QCheckBox("Each party also gets an e-mailed copy (Email column of the rate sheet)")
        self.i_email.setChecked(settings.invoice_include_email)
        f.addRow("", self.i_email)
        idx = QHBoxLayout()
        self.i_index = QCheckBox("Add an index (and one for the judge) from")
        self.i_index.setChecked(settings.invoice_include_index)
        self.i_threshold = QSpinBox()
        self.i_threshold.setRange(1, 10000)
        self.i_threshold.setValue(settings.invoice_index_threshold)
        self.i_threshold.setSuffix(" pages")
        self.i_threshold.setFixedWidth(z(110))
        tip = ("Counted on the whole transcript, every reporter's pages, though each invoice charges the index on\n"
               "its own pages (your 45 of an 83-page transcript get one). A job's Peripherals… can say yes or no\n"
               "for that job.")
        self.i_index.setToolTip(tip)
        self.i_threshold.setToolTip(tip)
        idx.addWidget(self.i_index)
        idx.addWidget(self.i_threshold)
        idx.addStretch(1)
        f.addRow("", idx)
        self.i_rule = QComboBox()
        for key, label in INDEX_RULES.items():
            self.i_rule.addItem(label, key)
        self.i_rule.setCurrentIndex(max(0, self.i_rule.findData(settings.invoice_index_rule)))
        self.i_rule.setToolTip("For an invoice covering several days. Every page of a day's transcripts counts,\n"
                               "whoever wrote them. A job's Peripherals… can still turn the index on or off for\n"
                               "that job.")
        f.addRow("Index on several days", self.i_rule)
        self.i_shared = QComboBox()
        for key, label in INDEX_SHARED.items():
            self.i_shared.addItem(label, key)
        self.i_shared.setCurrentIndex(max(0, self.i_shared.findData(settings.invoice_index_shared)))
        self.i_shared.setToolTip("When several attorneys ordered the same pages: each pays an index of the pages it\n"
                                 "ordered (100 pages, B orders 10 of them: A pays an index of 100 pages, B of 10),\n"
                                 "or one index is split between them like the original. The judge's index is\n"
                                 "always split, page by page (A pays 95 pages of it, B 5).")
        f.addRow("Index on shared pages", self.i_shared)
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
                                "(and the judge's index). Each always pays its own copies at its own speed, and its\n"
                                "own index too unless Index on shared pages splits it. Point at a choice in the list\n"
                                "to see how it works. The invoice's note on such pages (Invoice text) follows the\n"
                                "choice, unless you have reworded it. A job invoiced already keeps the way it was\n"
                                "billed, made again or opened again from Records.")
        if rules:
            f.addRow("Split invoices", self.i_split)
        self.i_rounding = QComboBox()
        for key, label in ROUNDINGS.items():
            self.i_rounding.addItem(label, key)
        self.i_rounding.setCurrentIndex(max(0, self.i_rounding.findData(settings.invoice_rounding)))
        self.i_rounding.setToolTip("When a firm's price a page comes to part of a cent (four firms sharing Immediate:\n"
                                   "$6.6125 a page).\n"
                                   "Exact: every fraction of a cent is kept, and the amount is rounded up to the cent\n"
                                   "once, at the end (1,000 pages: $6,612.50).\n"
                                   "The price a page, to the cent: rounded to the nearest cent first, as most people\n"
                                   "do by hand ($6.61 × 1,000 = $6,610.00; $6.6175 a page would be $6.62). It can\n"
                                   "come out either way.\n"
                                   "The math (Show the math) says which was used.")
        f.addRow("Rounding", self.i_rounding)
        self.i_joint = QComboBox()
        self.i_joint.addItem("One joint invoice for all the days of a case", True)
        self.i_joint.addItem("An invoice for each day", False)
        self.i_joint.setCurrentIndex(0 if settings.invoice_joint else 1)
        self.i_joint.setToolTip("When several days of one case are generated together (Generate all).\n"
                                "A single day selected and generated on its own is always billed alone.\n"
                                "With a joint invoice, the minute agreements and the MOFR are made once for the\n"
                                "whole case too, unless Settings → Options says otherwise.")
        f.addRow("Days of one case", self.i_joint)
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
        f.addRow("Firms you answered", box)
        self._fill_firms()
        self.i_turn: dict[str, QLineEdit] = {}
        for name in SPEEDS:
            e = QLineEdit(settings.turnaround(name))
            self.i_turn[name] = e
            f.addRow(f"{name} turnaround", e)
        self.i_texts = InvoiceTextEditor(settings.invoice_texts, self._preview_invoice)
        f.addRow("Invoice text", self.i_texts)
        self.i_number = QLineEdit(settings.invoice_number_format)
        self.i_number.setToolTip("{year} and {seq} (the count this year, {seq:04} = 0007); {yy} = 26")
        f.addRow("Invoice numbers", self.i_number)
        self.i_pattern = QLineEdit(settings.invoice_filename_pattern)
        self.i_pattern.setToolTip("Placeholders: {number} {case} {index} {attorney} {date} {today}")
        f.addRow("File name", self.i_pattern)
        row = QHBoxLayout()
        self.i_records = QLineEdit(settings.records_dir)
        self.i_records.setPlaceholderText(str(settings.records_folder()))
        rb = QPushButton("Browse...")
        rb.clicked.connect(lambda: self._pick_into(self.i_records, "Folder for the records (CSV copies)"))
        row.addWidget(self.i_records)
        row.addWidget(rb)
        f.addRow("Records folder", row)
        scroll = QScrollArea()  # a long tab: scrolls on small screens
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(w)
        self.tabs.addTab(scroll, "Invoice")

        # --- Records: the tick boxes of the Records window's invoices and the colour of its rows
        from .tracking_editor import TrackingEditor
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(18, 18, 18, 18)
        self.k_track = TrackingEditor(settings.boxes(), settings.rules(), settings.records_colours,
                                      settings.records_count)
        v.addWidget(self.k_track)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(w)
        self.tabs.addTab(scroll, "Records")

        # --- Run sheet
        w = QWidget()
        f = _form(w)
        intro = QLabel("A run sheet lists who wrote which pages of a trial, take by take, from the initials at the "
                       "foot of each transcript page. There is one per case; a transcript's takes are added to it.")
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        f.addRow(intro)
        where = QLabel("The run sheets' folder is under Options → Folders.")
        where.setObjectName("muted")
        f.addRow("Folder", where)
        self.r_existing = QComboBox()
        for key, label in (("ask", "Ask whether to add to it or start a new one"),
                           ("add", "Add to it without asking"), ("new", "Always start a new run sheet")):
            self.r_existing.addItem(label, key)
        self.r_existing.setCurrentIndex(max(0, self.r_existing.findData(settings.runsheet_existing)))
        self.r_existing.setToolTip("A run sheet is the case's when it has the same index number or the same case "
                                   "name\n(a trial with several index numbers is billed together).")
        f.addRow("When the case has one", self.r_existing)
        self.r_pattern = QLineEdit(settings.runsheet_filename_pattern)
        self.r_pattern.setToolTip("Placeholders: {month} {year} (of the first day)  {case}  {index}  {date}")
        f.addRow("File name", self.r_pattern)
        self.r_names = QPlainTextEdit("\n".join(f"{k} = {v}" for k, v in sorted(settings.reporter_names().items())))
        self.r_names.setPlaceholderText("ds = Dana\nkl = Kim")
        self.r_names.setFixedHeight(z(110))
        f.addRow("Reporters", self.r_names)
        help_lbl = QLabel("Initials = the name for the Reporter column, one reporter per line. Without a line, the "
                          "first name of the reporter listed on the transcript's title page is used (and yours "
                          "for your own initials, under My info); failing that, the initials.")
        help_lbl.setWordWrap(True)
        help_lbl.setObjectName("muted")
        f.addRow("", help_lbl)
        # the details on the invoices made for another reporter's pages (Whose pages... ticks them)
        from copy import deepcopy
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
        self.r_names.textChanged.connect(self._fill_reporters)
        self._fill_reporters()
        self.tabs.addTab(w, "Run sheet")

        # --- AI
        w = QWidget()
        f = _form(w)
        self.a_use = QCheckBox("Use a local AI model (Ollama) to help read documents")
        self.a_use.setChecked(settings.use_ai)
        self.a_text = QCheckBox("Also ask the AI about e-mails and pasted text (slower, better for informal text)")
        self.a_text.setChecked(settings.ai_for_text)
        self.a_model = QComboBox()
        self.a_model.setEditable(True)
        self.a_model.setToolTip("Choose one of the two, or any other model Ollama has (you can type its name).")
        self._fill_models([])
        self.a_model.setCurrentText(settings.ollama_model)
        from ..extract_llm import MODELS
        a_note = QLabel("<br>".join(f"<b>{name}</b>: {what}." for name, what in MODELS.items())
                        + "<br>Not installed yet? The button below downloads the one chosen.")
        a_note.setObjectName("muted")
        a_note.setWordWrap(True)
        self.a_host = QLineEdit(settings.ollama_host)
        self.a_timeout = QSpinBox()
        self.a_timeout.setRange(10, 900)
        self.a_timeout.setValue(settings.ai_timeout)
        self.a_timeout.setSuffix(" s")
        test = QPushButton("Test connection")
        self.a_status = QLabel("")
        self.a_status.setObjectName("muted")
        self.a_status.setWordWrap(True)
        test.clicked.connect(self._test_ai)
        self.a_ticks = QComboBox()
        for key, label in AI_TICKS.items():
            self.a_ticks.addItem(label, key)
        self.a_ticks.setCurrentIndex(max(0, self.a_ticks.findData(settings.ai_ticks)))
        self.a_ticks.setToolTip("A transcript lists who appeared, not who ordered, so the AI's tick is trusted only\n"
                                "from e-mails and pasted text unless you say otherwise.")
        f.addRow("", self.a_use)
        f.addRow("", self.a_text)
        f.addRow("The AI may tick who ordered:", self.a_ticks)
        f.addRow("Model", self.a_model)
        f.addRow("", a_note)
        f.addRow("Ollama URL", self.a_host)
        f.addRow("Timeout", self.a_timeout)
        f.addRow(test, self.a_status)
        guide = QPushButton("How to install Ollama + gemma…")
        guide.clicked.connect(lambda: OllamaHelpDialog(self.a_model.currentText().strip() or Settings.ollama_model,
                                                       self.a_host.text().strip(), self).exec())
        f.addRow("", guide)
        self.tabs.addTab(w, "AI")
        self._load_models()

        for i in range(self.tabs.count()):  # (what Help and F1 open: help_window.help_topic_of)
            self.tabs.widget(i).setProperty("help_topic", SETTINGS_TOPICS.get(self.tabs.tabText(i), ""))
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel | QDialogButtonBox.Help)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.helpRequested.connect(self.show_help)
        lay.addWidget(buttons)
        QShortcut(QKeySequence("F1"), self, activated=self.show_help)

    def show_help(self):
        """Help and F1: the help topic of the tab shown (SETTINGS_TOPICS), in a Help window of this dialog's own (a
        modal dialog blocks the main window's)."""
        from .help_window import help_topic_of, open_help
        focus = self.focusWidget()
        topic = help_topic_of(focus) if focus is not None and self.tabs.isAncestorOf(focus) else ""
        open_help(topic or help_topic_of(self.tabs.currentWidget()), self)

    # --- signature picture
    def _show_signature(self, path: str):
        """Shows the signature picture at `path` scaled to the row, or a hint if there is none, and enables
        Remove accordingly."""
        from pathlib import Path
        from PySide6.QtGui import QPixmap
        pix = QPixmap(path) if path and Path(path).is_file() else QPixmap()
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
        from PySide6.QtWidgets import QMessageBox
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

    def _store_signature(self):
        """Applies a pick or removal made in this dialog: moves the prepared picture to signature.png (or
        deletes it) and records it in the settings. Does nothing if the signature was not touched, and leaves
        the settings as they were (saying so) if the file cannot be moved or deleted.
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
            QMessageBox.warning(self, "Signature", "The signature picture couldn't be "
                                f"{'stored' if self._sig_new else 'removed'}, so the one you had stays.\n\n{e}")
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
            f"With {ticked} ticked, every agreement form says {pick}{why}. A speed you choose for one job under "
            "Speed, pages and dates comes first; when an e-mail asks for another speed, you are asked which.")

    def _pick_sheet_dir(self):
        """Lets the user choose another rate sheets folder and reloads the sheet list from it."""
        d = QFileDialog.getExistingDirectory(self, "Rate sheets folder", self.d_dir.text() or self.d_dir.placeholderText())
        if d:
            self.d_dir.setText(d)
            self._sheet_dir = d
            self._load_sheet_names()

    def _open_sheet_dir(self):
        """Opens the rate sheets folder (the one typed in, or the default) in Explorer."""
        from ..rates import sheets_dir
        open_path(sheets_dir(self.d_dir.text().strip()))

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
        import copy
        import tempfile
        from pathlib import Path
        from ..invoice import sample_invoice
        s = copy.deepcopy(self.s)
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

    def _folders(self, f: QFormLayout, settings: Settings) -> None:
        """The Folders rows of the Options tab: "Save to" (every output), then a row for each output (a key of
        OUTPUTS, so an output added later gets one too) to give it a folder of its own."""
        head = QLabel("Folders")
        head.setObjectName("section")
        f.addRow(head)
        self.o_dir = QLineEdit(settings.output_dir)
        self.o_dir.setPlaceholderText("The folder of the dropped file")
        f.addRow("Save to", self._folder_row(self.o_dir, "Save the outputs to", None))
        self._case_folder_rows(f, settings)
        self.o_dirs: dict[str, QLineEdit] = {}
        for key, label in OUTPUTS.items():
            e = QLineEdit(settings.output_dirs.get(key, ""))
            builtin = OUTPUT_FOLDERS.get(key)
            e.setPlaceholderText(str(Settings().folder_for(key)) if builtin else "Same as Save to")
            e.setToolTip(f"Where {label.lower()}s are saved. Blank = "
                         + (f"{Settings().folder_for(key)}" if builtin else "the Save to folder above") + ".")
            self.o_dirs[key] = e
            f.addRow(f"{label}s", self._folder_row(e, f"Folder for {label.lower()}s", key))
        hint = QLabel("Give an output a folder of its own, or leave it blank to save it with the others.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        f.addRow("", hint)

    def _case_folder_rows(self, f: QFormLayout, settings: Settings) -> None:
        """The Folders rows about a folder for each case inside Save to (Settings.case_folders): the box, the
        folder's name (a pattern of placeholders; the characters Windows forbids can't be typed) with an example
        from a made-up case, and what to do when the folder is already there (Settings.case_folder_existing). The
        last two are greyed out while the box is unticked."""
        from PySide6.QtCore import QRegularExpression
        from PySide6.QtGui import QRegularExpressionValidator

        from ..models import CaseInfo
        from ..pdfout import CASE_FOLDER_PLACES, FOLDER_FORBIDDEN, case_folder_name
        self.o_case_folders = QCheckBox("A folder for each case, inside Save to")
        self.o_case_folders.setToolTip("Each case's minute agreements, MOFR, invoices and their math go into a "
                                       "folder of its own, named as below\n(\"...\\Minute Agreements\\712345-2021\")."
                                       " An output with a folder of its own below, and the run sheet, keep theirs."
                                       "\nWhen your documents already sit in a folder of that name, it is used as "
                                       "it is (no \"712345-2021\" inside it).")
        self.o_case_folders.setChecked(settings.case_folders)
        f.addRow("", self.o_case_folders)
        self.o_case_pattern = QLineEdit(settings.case_folder_pattern)
        self.o_case_pattern.setPlaceholderText(CASE_FOLDER_PATTERN)
        # (none of the characters Windows forbids in a folder name can be typed or pasted: \ / : * ? " < > | and
        # the control characters, Tab among them)
        self.o_case_pattern.setValidator(QRegularExpressionValidator(
            QRegularExpression(r'[^<>:"/\\|?*\x00-\x1f]*'), self.o_case_pattern))
        places = " ".join("{" + p + "}" for p in CASE_FOLDER_PLACES)
        self.o_case_pattern.setToolTip(f"The case folder's name. Placeholders: {places}\n"
                                       "({index} 712345-2021, {case} the short caption, {date} the first day, "
                                       "{dates} \"6-3-2026 to 6-4-2026\").\n"
                                       f"Not allowed in a folder name, so they can't be typed: "
                                       f"{' '.join(FOLDER_FORBIDDEN)}")
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
                                     f"Not allowed in a folder name: {' '.join(FOLDER_FORBIDDEN)}")
        self.o_case_pattern.textChanged.connect(show_example)
        show_example()
        f.addRow("Case folder name", self.o_case_pattern)
        f.addRow("", self.o_case_hint)
        self.o_case_existing = QComboBox()
        for key, label in CASE_FOLDER_EXISTING.items():
            self.o_case_existing.addItem(label, key)
        self.o_case_existing.setCurrentIndex(max(0, self.o_case_existing.findData(settings.case_folder_existing)))
        self.o_case_existing.setToolTip("When Generate finds the case's folder already there with files in it "
                                        "(the case made before, or another with the same name)")
        f.addRow("If it's already there", self.o_case_existing)
        for w in (self.o_case_pattern, self.o_case_existing, self.o_case_hint):
            self.o_case_folders.toggled.connect(w.setEnabled)
            w.setEnabled(settings.case_folders)

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

    def _pick_into(self, edit: QLineEdit, title: str):
        """Asks for a folder, starting at the one in `edit`, and puts the choice into `edit`."""
        d =QFileDialog.getExistingDirectory(self, title, edit.text() or edit.placeholderText())
        if d:
            edit.setText(d)

    def _fill_firms(self) -> None:
        """Invoice → Firms you answered: one line per answer kept, "Smith Law  =  Smith Law Group (Sam Poe)"
        (same firm) or "≠" (not the same), then those given for now only, marked "for now"; rows saved by 2.2.0
        (without the names) show the keys compared."""
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

    def _dates_tab(self, settings: Settings) -> None:
        """The Dates tab (workdays.py): the two dates filled in, the business days (forms and invoices made on a
        weekend or a court holiday dated the next business day, the turnaround counted in business days and from
        which day, made after the evening hour dated the next day) and the court holidays (HolidayEditor)."""
        from PySide6.QtCore import QTime
        from PySide6.QtWidgets import QTimeEdit
        from .holiday_editor import HolidayEditor
        w = QWidget()
        f = _form(w)
        f.addRow(_tip("Minute agreement forms and invoices are dated on the court's business days, and turnaround "
                      "days counted in them: weekends and the court holidays below are skipped. The main window "
                      "says so under the dates whenever one was moved."))
        self.o_today = QCheckBox("Fill in the date of agreement (today, or the next business day as below)")
        self.o_today.setChecked(settings.agreement_today)
        f.addRow("Date of agreement", self.o_today)
        self.o_deldate = QCheckBox("Fill in the estimated delivery date from the turnaround days")
        self.o_deldate.setToolTip("The days of each speed: the rate sheet's Days column, else Defaults → "
                                  "Turnaround days.")
        self.o_deldate.setChecked(settings.fill_delivery_date)
        f.addRow("Est. delivery date", self.o_deldate)
        self.t_dating = QCheckBox("Date forms and invoices on a business day")
        self.t_dating.setToolTip(
            "One made on a weekend or a court holiday is dated the next business day: made on Sunday 10/11/2026,\n"
            "with Columbus Day on the Monday, it is dated Tuesday 10/13/2026. The invoice's number (its year), the\n"
            "records and {today} in the file names go by that date too.")
        self.t_dating.setChecked(settings.business_day_dating)
        f.addRow("Business days", self.t_dating)
        self.t_business = QCheckBox("Count turnaround days as business days")
        self.t_business.setToolTip(
            "Ticked: 5 days from Tuesday 10/13/2026 is Tuesday 10/20/2026 (weekends and court holidays not "
            "counted).\nUnticked: calendar days; a last day on a weekend or a court holiday moves to the next "
            "business day.")
        self.t_business.setChecked(settings.turnaround_business_days)
        f.addRow("", self.t_business)
        self.t_from = QComboBox()
        for key, label in TURNAROUND_FROM.items():
            self.t_from.addItem(label, key)
        self.t_from.setCurrentIndex(max(0, self.t_from.findData(settings.turnaround_from)))
        self.t_from.setToolTip("Made on Sunday 10/11/2026 (dated Tuesday 10/13), 5 business days are Tuesday 10/20 "
                               "from the date on the form,\nor Monday 10/19 from the day you make it.")
        f.addRow("Count the turnaround from", self.t_from)
        row = QHBoxLayout()
        self.t_after = QCheckBox("Made after")
        self.t_after.setChecked(settings.after_hours)
        self.t_time = QTimeEdit(QTime.fromString(settings.after_hours_from, "HH:mm"))
        self.t_time.setDisplayFormat("h:mm AP")
        self.t_time.setEnabled(settings.after_hours)
        self.t_after.toggled.connect(self.t_time.setEnabled)
        row.addWidget(self.t_after)
        row.addWidget(self.t_time)
        row.addWidget(QLabel(": dated the next day"), 1)
        tip = ("Off at first. A form or an invoice made in the evening is dated as if made the next morning: the next "
               "business day,\nwhen Date forms and invoices on a business day is ticked (made Friday at 6 PM: "
               "Monday).")
        for x in (self.t_after, self.t_time):
            x.setToolTip(tip)
        f.addRow("Evening", row)
        heading = QLabel("Court holidays")
        heading.setObjectName("section")
        f.addRow(heading)
        self.t_holidays = HolidayEditor(settings.holidays, settings.holiday_weekend)
        f.addRow(self.t_holidays)
        scroll = QScrollArea()  # a long tab: scrolls on small screens
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(w)
        self.tabs.addTab(scroll, "Dates")

    def show_tab(self, name: str) -> None:
        """Opens at the tab of that name ("Records"); an unknown name leaves the first."""
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == name:
                self.tabs.setCurrentIndex(i)
                return

    def _index_patterns_rows(self, f: QFormLayout, settings: Settings) -> None:
        """Options -> Index numbers: the user's own index number patterns (Settings.index_patterns), one per line,
        tried as well as the app's own (the user, 2026-10-21: they should be the user's to change), what is wrong
        with one as it is typed, and a box to try them on a line of text."""
        self.o_index = QPlainTextEdit("\n".join(settings.index_patterns))
        self.o_index.setPlaceholderText(r"e.g.  Docket\s*#?\s*(\d{5,7})\s*/\s*(\d{2,4})")
        self.o_index.setToolTip(INDEX_PATTERNS_TIP)
        self.o_index.setFixedHeight(z(64))
        self.o_index_try = QLineEdit()
        self.o_index_try.setPlaceholderText("Try them on: a line from a document, e.g. Docket # 712345/21")
        self.o_index_note = QLabel("")
        self.o_index_note.setWordWrap(True)
        self.o_index_note.setObjectName("muted")
        self.o_index.textChanged.connect(self._index_patterns_check)
        self.o_index_try.textChanged.connect(self._index_patterns_check)
        box = QVBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        for wid in (self.o_index, self.o_index_try, self.o_index_note):
            box.addWidget(wid)
        f.addRow("Index numbers", box)
        self._index_patterns_check()

    def _index_lines(self) -> list[str]:
        """The patterns typed, one per line, blank lines left out."""
        return [x.strip() for x in self.o_index.toPlainText().splitlines() if x.strip()]

    def _index_patterns_check(self) -> None:
        """Under the patterns: what is wrong with each that can't be used, else what they find in the text to try
        them on (with the app's own: 'Finds 712345/2021')."""
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
                    "own." if lines else "The app's own patterns only (they read 712345/2021, 712345-21, "
                    "Index No. 712345/21 and the like).")
        self.o_index_note.setText(note)

    def accept(self):
        """Copies every control into the Settings object, saves it to disk and closes. A blank file name
        pattern or invoice number format keeps the old one. Reporter lines that cannot be read are left out,
        with a warning that lists them. An index number pattern that can't be used keeps the window open, saying
        why (it would be lost). The file is written even over a settings file that couldn't be read
        (Settings.save(force=True)); when it can't be written the user is told, and the dialog closes all the
        same."""
        from ..extract_regex import index_pattern_problem
        bad = [f"Line {i}: {why}" for i, x in enumerate(self._index_lines(), 1) if (why := index_pattern_problem(x))]
        if bad:
            self.tabs.setCurrentIndex(next(i for i in range(self.tabs.count()) if self.tabs.tabText(i) == "Options"))
            QMessageBox.warning(self, "Index number patterns", "These index number patterns can't be used:\n\n"
                                + "\n".join(bad) + "\n\nCorrect them or delete them (Options → Index numbers).")
            return
        s, p = self.s, self.s.profile
        s.index_patterns = self._index_lines()
        p.name, p.title = self.p_name.text().strip(), self.p_title.text().strip()
        p.address1, p.address2 = self.p_addr1.text().strip(), self.p_addr2.text().strip()
        p.phone, p.fax, p.email = self.p_phone.text().strip(), self.p_fax.text().strip(), self.p_email.text().strip()
        p.website = self.p_web.text().strip()
        p.initials = self.p_initials.text().strip().lower().replace(".", "").replace(" ", "")
        s.default_court, s.default_county = self.d_court.text().strip(), self.d_county.text().strip()
        s.agreement_speed_first = self.i_first.currentData() or s.agreement_speed_first
        s.agreement_speed_fallback = self.i_fallback.currentData() or s.agreement_speed_fallback
        s.default_copies = self.d_copies.text().strip()
        s.rate_sheet = self.d_sheet.currentData() or s.rate_sheet
        s.rate_sheets_dir = self.d_dir.text().strip()
        for attr, spin in self.days.items():
            setattr(s, attr, spin.value())
        s.fill_delivery_date = self.o_deldate.isChecked()
        s.per_email, s.sign_reporter = self.o_per_email.isChecked(), self.p_sign.isChecked()
        self._store_signature()
        s.agreement_today, s.flatten = self.o_today.isChecked(), self.o_flat.isChecked()
        s.business_day_dating, s.turnaround_business_days = self.t_dating.isChecked(), self.t_business.isChecked()
        s.turnaround_from = self.t_from.currentData() or s.turnaround_from
        s.after_hours, s.after_hours_from = self.t_after.isChecked(), self.t_time.time().toString("HH:mm")
        s.holidays, s.holiday_weekend = self.t_holidays.rows(), self.t_holidays.weekend()
        s.open_after, s.title_case_names = self.o_open.isChecked(), self.o_tc.isChecked()
        s.form_choice = self.o_form.currentData()
        s.include_instructions = self.o_instr.isChecked()
        s.batch_combine_dates = self.o_combine.isChecked()
        s.forms_per_case = self.o_per_case.isChecked()
        s.output_dir, s.filename_pattern = self.o_dir.text().strip(), self.o_pattern.text().strip() or s.filename_pattern
        s.theme = self.o_theme.currentText()
        s.zoom = self.o_zoom.value() / 100
        s.fuzzy_numbers = self.o_fuzzy_numbers.isChecked()
        s.preview_before_saving = self.o_preview.isChecked()
        s.recaps, s.check_updates = self.o_recaps.isChecked(), self.o_updates.isChecked()
        s.show_math, s.invoice_detailed_copy = self.o_math.isChecked(), self.i_detailed_copy.isChecked()
        s.save_math = self.i_save_math.currentData()
        s.outputs = [k for k, cb in self.o_outputs.items() if cb.isChecked()]
        s.mofr_division = self.o_division.currentData()
        s.mofr_filename_pattern = self.o_mofr_pattern.text().strip() or s.mofr_filename_pattern
        # speeds named otherwise on a rate sheet (ticked under Speeds offered) have no box here: they stay
        from ..rates import speed_key
        keep = [x for x in s.invoice_speeds if speed_key(x) not in {speed_key(n) for n in SPEEDS}]
        s.invoice_speeds = keep + [k for k, cb in self.i_speeds.items() if cb.isChecked()]
        s.invoice_include_email, s.invoice_include_index = self.i_email.isChecked(), self.i_index.isChecked()
        s.invoice_index_threshold = self.i_threshold.value()
        s.invoice_index_rule = self.i_rule.currentData()
        s.invoice_index_shared = self.i_shared.currentData()
        s.invoice_rounding = self.i_rounding.currentData()
        s.invoice_joint = bool(self.i_joint.currentData())
        s.invoice_detail_items = [k for k, cb in self.i_items.items() if cb.isChecked()]
        s.invoice_turnaround = {k: e.text().strip() for k, e in self.i_turn.items()}
        s.invoice_texts = self.i_texts.rows()
        split = self.i_split.currentData() or ""
        rules = courthouses.split_rules()
        if not s.invoice_split_rule and rules and split == rules[0].key:
            split = ""  # (the default left as it was: "" follows the courthouse's default, should it change)
        s.use_split_rule(split)  # (after the text: it may reword the note on such pages)
        s.firm_answers = [list(r) for r in self._firm_answers]
        s.invoice_number_format = self.i_number.text().strip() or s.invoice_number_format
        s.invoice_filename_pattern = self.i_pattern.text().strip() or s.invoice_filename_pattern
        s.records_dir = self.i_records.text().strip()
        s.tracking_boxes = box_rows(self.k_track.boxes())
        s.tracking_rules = rule_rows(self.k_track.rules())
        s.records_colours = self.k_track.colours_on()
        s.records_count = self.k_track.count_name()
        s.output_dirs = {k: e.text().strip() for k, e in self.o_dirs.items() if e.text().strip()}
        s.case_folders = self.o_case_folders.isChecked()
        # (the box refuses those characters typed or pasted, but not in the pattern it started with: a settings
        # file edited by hand)
        s.case_folder_pattern = clean_folder_pattern(self.o_case_pattern.text())
        s.case_folder_existing = self.o_case_existing.currentData()
        s.runsheet_existing = self.r_existing.currentData()
        s.runsheet_filename_pattern = self.r_pattern.text().strip() or s.runsheet_filename_pattern
        names, bad = self._reporter_names(self.r_names.toPlainText())
        s.reporters = {k: replace(self._details.get(k, ReporterProfile()), name=v) for k, v in names.items()}
        for k, d in self._details.items():  # invoice details of a reporter with no line: kept, without a name
            if k not in s.reporters and d.has_details():
                s.reporters[k] = replace(d, name="")
        if bad:
            QMessageBox.warning(self, "Reporters", "These lines under Run sheet → Reporters were left out (write "
                                "them as initials = name, e.g. ds = Dana):\n\n" + "\n".join(bad[:10]))
        s.show_yin = self.o_yin.isChecked()
        s.use_ai, s.ai_for_text = self.a_use.isChecked(), self.a_text.isChecked()
        s.ai_ticks = self.a_ticks.currentData() or s.ai_ticks
        s.ollama_model, s.ollama_host = self.a_model.currentText().strip(), self.a_host.text().strip()
        s.ai_timeout = self.a_timeout.value()
        try:
            s.save(force=True)  # (the user's own Save: written even over a settings file that couldn't be read)
        except OSError as e:
            # the settings are changed all the same (the window follows them, and they are saved again when
            # it closes): the dialog closes rather than keeping them half applied behind a Cancel
            show_save_error(self, e, "Could not save the settings",
                            "\n\nYour changes are kept for now and saved again when the app closes.")
        super().accept()


class InvoiceTextEditor(QWidget):
    """Settings -> Invoice -> Invoice text: the invoice's own text as rows. Each row says where it goes
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
    "Each finds the number and the year as two groups in parentheses, in that order (or named\n"
    "(?P<number>...) and (?P<year>...)). Capitals don't matter. A number found by one of yours counts as\n"
    "surely as one after \"Index No.\".\n\n"
    "Docket\\s*#?\\s*(\\d{5,7})\\s*/\\s*(\\d{2,4})   finds  Docket # 712345/21\n"
    "CV-(\\d{6})-(\\d{2})/QU   finds  CV-012345-25/QU")


class SplitSpeedsDialog(QDialog):
    """Asks the speed each firm of a split order ordered at (firms that ordered the same pages commit to one:
    courthouses.speed_upfront), for the firms whose speed isn't set yet (batch.speeds_to_ask): the case's name
    above its days, then a row per day and firm, with who it ordered the pages with ("(its speed on its other
    pages)" for a firm asked because it has a speed on some pages only) and a box of the rate sheet's speeds, set to
    the speed it starts from (the firm's on its other pages of the case, else the agreement form's), matched
    loosely ("Expedited" is "Expedite"). MainWindow._ask_split_speeds keeps the answers (Job.speeds); "Go back"
    makes nothing."""

    def __init__(self, asks: list, speeds: list[tuple[str, str]], button: str = "Generate", parent=None,
                 marks: dict | None = None):
        """asks: batch.SpeedAsk each; speeds: the rate sheet's, (label, name) each, cheapest first; button: the
        button pressed ("Generate", "Generate all"), named on OK ("Generate all with these speeds"); marks: each
        firm's mark by its key (batch.trial_marks), its tag before its name."""
        from .badges import badge_html
        super().__init__(parent)
        self.setWindowTitle("Which speed did each firm order?")
        self.setMinimumWidth(z(620))
        lay = QVBoxLayout(self)
        intro = QLabel("These firms ordered the same pages, so each one commits to a speed and is billed that "
                       "speed alone (a firm ordering by itself can still choose from its invoice). At different "
                       "speeds, the original is divided as Settings → Invoice → Split invoices says, and each "
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
            for c, text in enumerate((a.job.case.get("dates") or "(no date)", a.name,
                                      a.shared_with or "(its speed on its other pages)")):
                lab = QLabel(text)
                lab.setTextFormat(Qt.PlainText)
                if c == 1 and (marks or {}).get(a.key) is not None:
                    lab.setTextFormat(Qt.RichText)
                    lab.setText(badge_html(marks[a.key], text))
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
        lay.addWidget(_tip("The speeds are kept with each day: change them later in the \"Who ordered what\" card "
                           "or in the Excerpts window."))
        buttons = QDialogButtonBox()
        buttons.addButton(f"{button} with these speeds", QDialogButtonBox.AcceptRole)
        buttons.addButton("Go back", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def chosen(self) -> list[str]:
        """The speed chosen for each row, in order."""
        return [cb.currentData() or "" for cb in self.combos]


DEFAULTS_TIP = "Your defaults for every invoice are in Settings → Invoice."
# Peripherals... changes one job only: said at the top and the bottom of it, as it was taken for the settings
JOB_ONLY_TIP = ("These choices are for this job only. New jobs start from Settings → Invoice, where the {n} pages "
                "of the automatic index are set.")


def _tip(text: str) -> QLabel:
    """A small grey note."""
    label = QLabel(text)
    label.setObjectName("muted")
    label.setWordWrap(True)
    return label


def _invoice_buttons(dlg: QDialog, on_defaults, label: str = "Use my defaults") -> QDialogButtonBox:
    """OK, Cancel and "Use my defaults" (or `label`), which calls on_defaults and closes the window with OK."""
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    reset = buttons.addButton(label, QDialogButtonBox.ResetRole)
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
        lay.addWidget(QLabel("Index for this job (and one for the judge):"))
        t = s.invoice_index_threshold
        self.index = QButtonGroup(self)
        self.on_typed_box = None
        if typed:
            n, whole = typed
            self.on_typed_box = QCheckBox(f"Judge it on the {n:,} pages you typed, not the transcript's {whole:,}")
            self.on_typed_box.setToolTip("Your answer when Generate asked (Est. number of pages typed below the\n"
                                         "transcript's count). Not asked yet: Generate asks. Same as Settings\n"
                                         "has it ask again.")
            self.on_typed_box.setChecked(bool(on_typed))
        for key, label in (("auto", f"Auto: when the whole transcript has {t} pages or more"),
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
        lay.addWidget(_invoice_buttons(self, self._defaults, "Same as Settings"))

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
        lay.addWidget(_tip("\"Pages for each day\" is shown when the invoice covers several days. " + DEFAULTS_TIP))
        lay.addWidget(_invoice_buttons(self, self._defaults))

    def _defaults(self):
        """Use my defaults: the boxes as Settings say, and the window closes with OK (values() gives None)."""
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
            except OSError:
                pass

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
            parts = [f"{x.upper()}{' (you)' if x in self.own else ''}: {self._count(owners, {x}, front)} pp."
                     for x in found]
            unknown = sum(1 for o in owners if not o and front in (None, "none"))  # (Nobody: still no initials)
            if unknown:
                parts.append(f"no initials: {unknown} pp.")
            item["count"].setText(f"{len(owners)} pages · " + " · ".join(parts))
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
<p><b>Which model?</b> Settings → AI → Model offers two. <b>gemma4:e2b</b> is smaller and faster, and the usual
choice. <b>gemma4:e4b</b> is larger and more accurate, but much slower on a laptop without a graphics card
(GPU). Choose the model there first: this window downloads the one chosen.</p>

<h4>3. Check it</h4>
<p>Close this window and click <b>Test connection</b> in Settings → AI. The main window shows "● AI ready" at the
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
            client = ollama.Client(host=self.host or None, timeout=None)
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

    The download keeps going if the dialog is closed (see accept).
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

    def _pull(self):
        """Starts the model download on a background thread and shows the progress bar."""
        self.pull_btn.setEnabled(False)
        self.bar.setVisible(True)
        self.bar.setRange(0, 0)
        self.status.setText("Starting download…")
        self.thread = _PullThread(self.model, self.host)
        self.thread.progress.connect(self._progress)
        self.thread.finished_ok.connect(self._done)
        self.thread.start()

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
        """Escape or the window's close button behaves like Close."""
        self.accept()

    def accept(self):
        """Closes the dialog. A download still running is handed to _BACKGROUND so it is not cut off."""
        if self.thread and self.thread.isRunning():
            _BACKGROUND.append(self.thread)  # keep the download alive after the dialog closes
        super().accept()


# Downloads that outlive their dialog. Qt aborts the program if a QThread is destroyed while it still runs,
# so a reference is kept here for as long as the app is open.
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
