"""The options of each output, one function per output (courthouses.OutputSpec.panel): panel(win, form) adds its
rows to a form MainWindow made, and keeps its widgets on the window (win.form_choice, win.inv_parties...), where
the window's refresh code finds them. An output with a card (OutputSpec.card: the invoice's choices are this job's)
has its form in that card of the window's form; the others' are panels of the Outputs row's Options ▾ (standing
choices, kept for every job). An output without one has no options.

These are Queens Supreme Court's four, moved here from MainWindow._build (MIGRATION.md, Release A); what they
show as the job changes is still worked out by the window (MainWindow._refresh_outputs and the methods it calls).
Each is named by its OutputSpec as "minute_filler.gui.panels:<name>" and imported by name, so the build can't see
the import: YinItAgreementForm.spec lists this module among its hidden imports (Courthouse.modules).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox, QWidget

from .main_window import PARTIES_TIP, WHOSE_TIP, _who_splits


def agreement(win, ag: QFormLayout) -> None:
    """The Minute agreement's options: which form, "per email" and signing, and the one speed the form names."""
    from ..fill import FORMS
    win.form_choice = QComboBox()
    for key, (_, label) in FORMS.items():
        win.form_choice.addItem(label, key)
    win.form_choice.setCurrentIndex(max(0, win.form_choice.findData(win.s.form_choice)))
    win.form_choice.currentIndexChanged.connect(
        lambda _: win._set_opt("form_choice", win.form_choice.currentData()))
    ag.addRow("Form:", win.form_choice)
    win.per_email = QCheckBox("\"Per email\" on attorney signature")
    win.per_email.setToolTip("Writes \"per email\" in the attorney's signature spot")
    win.per_email.setChecked(win.s.per_email)
    win.per_email.toggled.connect(lambda v: win._set_opt("per_email", v))
    ag.addRow("Signing:", win.per_email)
    win.sign_rep = QCheckBox("Sign as court reporter")
    win.sign_rep.setToolTip("Puts your signature picture on the court reporter line - or types your name,\n"
                            "if no picture is chosen in Settings → My info.")
    win.sign_rep.setChecked(win.s.sign_reporter)
    win.sign_rep.toggled.connect(lambda v: win._set_opt("sign_reporter", v))
    ag.addRow("", win.sign_rep)
    win.ag_speed = QLabel("")  # the speed and rate the forms name (MainWindow._form_speed_text)
    win.ag_speed.setObjectName("muted")
    win.ag_speed.setToolTip("The speed and rate per page the minute agreement forms name (the MOFR names the\n"
                            "speed too): set under Speed, pages and dates → Speed. A firm whose speed\n"
                            "is set in Who ordered what gets its own, and the MOFR ticks every speed ordered.")
    ag.addRow("Speed:", win.ag_speed)


def invoice(win, inv: QFormLayout) -> None:
    """The Invoice card's rows (this job's invoice): parties and Excerpts..., whose pages are billed, what it
    includes (Peripherals...), granular detail, the prices and the math. (The speeds it offers are under the rate
    sheet, in the window's Speed, pages and dates card.)"""
    win.inv_parties = QSpinBox()
    win.inv_parties.setRange(1, 20)
    win.inv_parties.setToolTip(PARTIES_TIP.format(**_who_splits(win.s)))
    win.inv_parties.valueChanged.connect(win._invoice_parties_changed)
    parties = QHBoxLayout()
    parties.setSpacing(8)
    parties.addWidget(win.inv_parties)
    win.inv_who = QPushButton("Excerpts…")
    win.inv_who.clicked.connect(lambda: win._who_ordered())
    parties.addWidget(win.inv_who)
    parties.addStretch(1)
    inv.addRow("Parties:", parties)
    # a transcript of several reporters: whose pages are billed (shown only for such a transcript)
    win.inv_pages_row = QHBoxLayout()
    win.inv_pages_row.setSpacing(8)
    win.inv_pages_info = QLabel("")  # (its lines broken by _lines)
    win.inv_pages_info.setObjectName("muted")
    win.inv_pages_row.addWidget(win.inv_pages_info)
    win.inv_whose = QPushButton("Whose pages…")
    win.inv_whose.setToolTip(WHOSE_TIP)
    win.inv_whose.clicked.connect(lambda: win._whose_pages(win.cur))
    win.inv_pages_row.addWidget(win.inv_whose, 0, Qt.AlignTop)
    win.inv_pages_row.addStretch(1)  # (the button by its line, not at the far side of the card)
    inv.addRow("Billed:", win.inv_pages_row)
    inv.setRowVisible(win.inv_pages_row, False)  # until a transcript of several reporters is loaded
    win.inv_form = inv

    def with_button(w: QWidget, text: str, tip: str, slot) -> QHBoxLayout:
        """[widget] [button…] on one row."""
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(w)
        b = QPushButton(text)
        b.setToolTip(tip)
        b.clicked.connect(slot)
        row.addWidget(b)
        row.addStretch(1)
        return row

    # what it includes besides the original and the copies (and why: "index (83 total pages, 50 or more)");
    # Peripherals... changes it for this job only. Its lines are broken as the Billed row's are.
    includes = QHBoxLayout()
    includes.setSpacing(8)
    win.inv_peripherals_info = QLabel("")
    win.inv_peripherals_info.setObjectName("muted")
    includes.addWidget(win.inv_peripherals_info)
    win.inv_peripherals = QPushButton("Peripherals…")
    win.inv_peripherals.setToolTip("The e-mailed copy and the index, for this job's invoice only\n"
                                   "(new jobs start from Settings → Invoice)")
    win.inv_peripherals.clicked.connect(win._invoice_peripherals)
    includes.addWidget(win.inv_peripherals, 0, Qt.AlignTop)
    includes.addStretch(1)
    inv.addRow("Includes:", includes)
    win.inv_detail = QCheckBox("Show granular detail")
    win.inv_detail.setToolTip("For this job's invoice only (off for every new job): also show what Customize…\n"
                              "lists, such as the page count, the price per page and the charges in each amount.\n"
                              "Unticked, the invoice shows each speed's turnaround and amount only.")
    win.inv_detail.toggled.connect(win._invoice_detail_changed)
    inv.addRow("", with_button(
        win.inv_detail, "Customize…", "What granular detail shows on this job's invoice\n"
        "(your defaults are in Settings → Invoice)", win._invoice_show))
    win.inv_info = QLabel("")
    win.inv_info.setObjectName("muted")
    inv.addRow("Prices:", win.inv_info)
    # the whole math of the invoices priced, as under Who pays what (shown while there are prices)
    win.inv_math = QLabel('<a href="math">How these amounts are worked out…</a>')
    win.inv_math.setToolTip("The math of each invoice, charge by charge, as things stand now")
    win.inv_math.linkActivated.connect(win._show_live_math)
    inv.addRow("", win.inv_math)
    inv.setRowVisible(win.inv_math, False)


def mofr(win, mo: QFormLayout) -> None:
    """The MOFR's options: the Civil or Criminal box."""
    win.mofr_division = QComboBox()
    win.mofr_division.addItem("Civil", "civil")
    win.mofr_division.addItem("Criminal", "criminal")
    win.mofr_division.setToolTip("Which box is ticked on the MOFR (civil cases also get the case's own title\n"
                                 "instead of the printed \"People v.\")")
    win.mofr_division.setCurrentIndex(max(0, win.mofr_division.findData(win.s.mofr_division)))
    win.mofr_division.currentIndexChanged.connect(
        lambda _: win._set_opt("mofr_division", win.mofr_division.currentData()))
    mo.addRow("Case:", win.mofr_division)


def runsheet(win, rs: QFormLayout) -> None:
    """The Run sheet's options: what to do when the case has one already, a warning without a transcript,
    and the link to the run sheets folder (under the options: usable while it is unticked)."""
    win.rs_existing = QComboBox()
    for key, label in (("ask", "Ask me"), ("add", "Add to it"), ("new", "Start a new one")):
        win.rs_existing.addItem(label, key)
    win.rs_existing.setToolTip("When the case already has a run sheet (the same index number or case name)")
    win.rs_existing.setCurrentIndex(max(0, win.rs_existing.findData(win.s.runsheet_existing)))
    win.rs_existing.currentIndexChanged.connect(
        lambda _: win._set_opt("runsheet_existing", win.rs_existing.currentData()))
    rs.addRow("If one exists:", win.rs_existing)
    win.rs_info = QLabel("")
    win.rs_info.setObjectName("muted")
    win.rs_info.setVisible(False)
    rs.addRow(win.rs_info)
    # under the options, not among them: the folder can be opened while Run sheet is unticked too
    win.rs_folder = QLabel('<a href="open">Open the run sheets folder</a>')
    win.rs_folder.setToolTip("Opens the folder the run sheets are kept in (Settings → Options → Folders)")
    win.rs_folder.linkActivated.connect(lambda _: win._open_run_sheets_folder())
    col = win.option_panels["runsheet"].layout()
    col.insertWidget(col.count() - 1, win.rs_folder)  # above the stretch
