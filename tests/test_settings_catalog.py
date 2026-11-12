"""Every setting has one home and makes one decision (settings_catalog, SETTINGS.md): every field of Settings has an
entry, the Settings window has a control for each entry shown there and none without one, a setting and those it
needs share a page, the window writes no setting it doesn't declare, every "Settings → …" path written in the code,
the help or the README names a page of today's, and Save gives back exactly what the window opened with."""
from __future__ import annotations

import re
from dataclasses import asdict, fields
from pathlib import Path

import pytest

from minute_filler.settings_catalog import (ENTRIES, ENTRY, INTERNAL, PAGE, PAGES, SETTINGS, WINDOW, path, search,
                                            setting_keys, shown_label)

ROOT = Path(__file__).resolve().parents[1]


def test_every_field_has_one_entry():
    """A field added to Settings (or its Profile) without an entry fails here: SETTINGS.md says where it goes."""
    keys = [e.key for e in ENTRIES]
    assert len(keys) == len(set(keys)), [k for k in keys if keys.count(k) > 1]
    assert set(keys) == set(setting_keys()), (set(setting_keys()) - set(keys), set(keys) - set(setting_keys()))


def test_entries_are_whole():
    """Each entry says where it lives and what it decides; a setting shown in Settings is on a page, under one of
    its headings, named once there; what it needs is a setting of the same page (settings that depend on each
    other are seen together); a job's own choice is a Job attribute."""
    from minute_filler.batch import Job
    job_fields = {f.name for f in fields(Job)}
    named = set()
    for e in ENTRIES:
        assert e.home in (SETTINGS, WINDOW, INTERNAL), e
        assert e.decides.strip(), e.key
        if e.home != SETTINGS:
            assert e.where and not e.page and not e.also_in and not e.needs, e.key
            continue
        page = PAGE[e.page]
        assert e.section in page.sections, (e.key, e.section)
        assert e.label or e.row_of, f"{e.key}: no label and not part of another row"
        if e.row_of:
            assert ENTRY[e.row_of].page == e.page and ENTRY[e.row_of].label, e.key
        if e.label:
            assert (e.page, e.section, e.label.lower()) not in named, f"two settings named {e.label!r} there"
            named.add((e.page, e.section, e.label.lower()))
        for need in e.needs:
            assert ENTRY[need].home == SETTINGS and ENTRY[need].page == e.page, (e.key, need)
        if e.job_field:
            assert e.job_field in job_fields, (e.key, e.job_field)


def test_every_page_and_heading_holds_something():
    """No empty page or heading; pages named once; each with a help topic."""
    from minute_filler.help_topics import topic
    assert len({p.title for p in PAGES}) == len(PAGES) and len(PAGE) == len(PAGES)
    for p in PAGES:
        for section in p.sections:
            assert any(e.page == p.key and e.section == section for e in ENTRIES), (p.key, section)
        assert topic(p.help), p.help
        assert p.summary and p.belongs


def test_path_names_where_a_setting_is():
    """settings_catalog.path: the page and the setting's name (its row's, for a part of a row), a page alone, or one
    of a setting's other rows."""
    assert path("invoice_rounding") == "Settings → Invoices → Rounding"
    assert path("invoice_index_threshold") == "Settings → Invoices → Bill an index from"  # (its row's label)
    assert path(page="files") == "Settings → Files and folders"
    assert path("reporters", row="Invoices for") == "Settings → Other reporters → Invoices for"
    assert shown_label("days_regular") == "Regular" and shown_label("tracking_rules") == "Tick boxes and colours"


def test_find_a_setting():
    """Find a setting: words that begin words of a setting's name, page, heading or what it decides; its own name
    first."""
    assert search("judge")[0].key == "invoice_judge_index"
    assert search("judges")[0].key == "invoice_judge_index"
    assert search("dark")[0].key == "theme"
    assert {e.key for e in search("file name")} >= {"filename_pattern", "invoice_filename_pattern",
                                                   "mofr_filename_pattern", "runsheet_filename_pattern"}
    assert {"days_regular", "days_expedited"} <= {e.key for e in search("turnaround days")}
    assert search("email")[0].key in ("profile.email", "invoice_include_email")
    assert search("") == [] and search("zzqx") == []
    assert all(e.home == SETTINGS for e in search("index"))
    assert search("filename")[0].key == "filename_pattern"
    # (a setting set where it acts is found too when asked, after those of Settings: it moved out this release)
    assert search("highlight") == [] and search("highlight", windows=True)[0].key == "takes_highlight_mine"
    assert search("judge", windows=True)[0].key == "invoice_judge_index"
    assert search("signature")[0].key == "signature_image"  # (its heading counts as its name)
    assert [e.key for e in search("colours")].count("tracking_rules") == 0  # (one row for the one editor)
    assert "tracking_boxes" in [e.key for e in search("colours")]


# --- the window

def _texts(widget) -> set[str]:
    """Every text shown in a widget, whole (labels, card headings, tick boxes, buttons), in lower case and without a
    closing colon: a setting's label must be one of them exactly, not a piece of a longer one."""
    from PySide6.QtWidgets import QAbstractButton, QLabel
    found = [w.text() for w in widget.findChildren(QLabel)] + [w.text() for w in widget.findChildren(QAbstractButton)]
    return {t.strip().rstrip(":").lower() for t in found}


def test_the_window_has_a_control_for_every_setting_it_shows(qt):
    """Each entry shown in Settings has its controls on its page, where its name can be read; the window keeps
    no control under a key the catalog doesn't show there."""
    from minute_filler.gui.settings_dialog import SettingsDialog
    from minute_filler.settings import Settings
    d = SettingsDialog(Settings())
    shown = {e.key for e in ENTRIES if e.home == SETTINGS}
    assert set(d.controls) == shown, (shown - set(d.controls), set(d.controls) - shown)
    for key in shown:
        e = ENTRY[key]
        page = d.pages[e.page]
        for w in d.controls[key]:
            assert page.isAncestorOf(w), (key, w)
        if e.label:
            assert e.label.lower() in _texts(page), (key, e.label)
        for row in e.rows:
            assert row.lower() in _texts(page), (key, row)
    d.deleteLater()


def _turn(d, key: str, on: bool) -> None:
    """Turns setting `key` on or off in the window: its tick box, or its yes/no choice."""
    from PySide6.QtWidgets import QCheckBox
    w = d.control(key)
    if isinstance(w, QCheckBox):
        w.setChecked(on)
    else:
        w.setCurrentIndex(w.findData(on))


def test_a_setting_is_greyed_out_while_one_it_needs_is_off(qt):
    """Every `needs` of the catalog: off, the setting's controls and its row's label are greyed out; on, they come
    back. A setting that still counts while the other is off (the index's rows: a job's Peripherals… can bill one)
    needs nothing, and stays as it is."""
    from minute_filler.gui.settings_dialog import SettingsDialog
    from minute_filler.settings import Settings
    d = SettingsDialog(Settings())
    pairs = [(e.key, need) for e in ENTRIES if e.home == SETTINGS for need in e.needs]
    assert ("forms_per_case", "invoice_joint") in pairs and ("case_folder_pattern", "case_folders") in pairs
    for key, need in pairs:
        _turn(d, need, False)
        assert not any(w.isEnabled() for w in d.controls[key]), (key, need)
        assert key not in d._labels or not d._labels[key].isEnabled(), (key, need)
        _turn(d, need, True)
        assert all(w.isEnabled() for w in d.controls[key]), (key, need)
    _turn(d, "invoice_include_index", False)
    assert all(d.control(k).isEnabled() for k in ("invoice_judge_index", "invoice_index_threshold",
                                                   "invoice_index_rule", "invoice_index_shared"))
    d.deleteLater()


def _busy() -> "Settings":
    """Settings with every setting the window shows changed from its default, to values its controls can hold."""
    from minute_filler.settings import ReporterProfile, Settings
    s = Settings()
    p = s.profile
    p.name, p.title, p.address1, p.address2 = "Pat Reporter", "Senior Court Reporter", "1 Court Sq", "Anytown, NY"
    p.phone, p.fax, p.email, p.website, p.initials = "555-0100", "555-0101", "pat@example.com", "example.com", "pr"
    s.sign_reporter = True
    s.reporters = {"ds": ReporterProfile(name="Dana", full_name="Dana Smith", prefix="DS")}
    s.default_court, s.default_county, s.default_copies = "Civil", "Kings", "2"
    s.title_case_names = False
    s.index_patterns = [r"CV-(\d{6})-(\d{2})/QU"]
    s.firm_answers = [["smith law", "smith law group", True, "Smith Law", "Smith Law Group"]]
    s.use_ai, s.ai_for_text, s.ai_ticks = False, False, "never"
    s.ollama_model, s.ollama_host, s.ai_timeout = "gemma4:e4b", "http://localhost:9999", 60
    s.trial_orders, s.invoice_joint, s.forms_per_case, s.batch_combine_dates = "day", False, False, True
    s.agreement_today, s.fill_delivery_date = False, False
    s.days_immediate, s.days_daily, s.days_expedited, s.days_regular = 1, 2, 6, 20
    s.invoice_turnaround = {"Immediate": "At once.", "Daily": "Next day.", "Expedited": "A week.",
                            "Regular": "A month."}
    s.turnaround_business_days, s.turnaround_from = False, "today"
    s.business_day_dating, s.after_hours, s.after_hours_from = False, True, "18:30"
    s.holidays = s.holidays[:3]
    s.holiday_weekend = "none"
    s.invoice_speeds = ["Regular", "Daily"]
    s.agreement_speed_first, s.agreement_speed_fallback = "Daily", "fastest"
    s.split_speeds = "ask"
    s.outputs = ["agreement", "invoice"]
    s.form_choice, s.include_instructions, s.per_email, s.mofr_division = "clean", False, False, "criminal"
    s.invoice_include_email, s.invoice_rounding, s.invoice_include_index = False, "page", False
    s.invoice_index_threshold, s.invoice_index_rule, s.invoice_index_shared = 75, "each", "split"
    s.invoice_judge_index = "off"
    s.invoice_detail_items = ["days", "per_page"]
    s.invoice_detailed_copy = True
    s.invoice_texts = s.invoice_texts[:2]
    s.invoice_number_format = "{yy}-{seq}"
    s.show_math, s.save_math = False, "each"
    s.runsheet_existing, s.runsheet_witness = "add", "blank"
    s.records_colours, s.fuzzy_numbers, s.recaps = False, False, False
    s.records_dir = str(Path.home() / "Records copies")
    s.output_dir = str(Path.home() / "Out")
    s.case_folders, s.case_folder_pattern, s.case_folder_existing = False, "{index} {case}", "add"
    s.save_inputs = True
    s.output_dirs = {"invoice": str(Path.home() / "Invoices")}
    s.filename_pattern, s.mofr_filename_pattern = "Agreement {case}", "MOFR {case}"
    s.invoice_filename_pattern, s.runsheet_filename_pattern = "Invoice {number}", "Run {case}"
    s.preview_before_saving, s.open_after, s.flatten = False, False, True
    s.theme, s.show_yin = "dark", False
    s.recent_jobs_show, s.recent_jobs_count, s.recent_jobs_days = False, 2, 10
    s.check_updates = False
    return s


def test_save_gives_back_what_the_window_opened_with(qt):
    """Settings opened and saved untouched changes nothing, every setting it shows set away from its default: a
    control that doesn't give back what it was given fails here (and with the defaults too)."""
    from minute_filler.gui.settings_dialog import SettingsDialog
    from minute_filler.settings import Settings
    for s in (_busy(), Settings()):
        before = asdict(s)
        d = SettingsDialog(s)
        d.accept()
        after = asdict(s)
        before.pop("settings_page"), after.pop("settings_page")
        changed = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
        assert not changed, changed
        d.deleteLater()
    busy = _busy()
    defaults = asdict(Settings())
    shown = {e.key for e in ENTRIES if e.home == SETTINGS and not e.key.startswith("profile.")}
    same = sorted(k for k in shown if asdict(busy)[k] == defaults[k] and k not in (
        "signature_image", "zoom", "invoice_split_rule", "tracking_boxes", "tracking_rules", "records_count",
        "rate_sheet", "rate_sheets_dir"))
    assert not same, f"_busy() leaves these at their default, so the test misses them: {same}"


def test_it_opens_at_the_page_last_shown(qt):
    """Settings opens where it was last closed (Cancel too), and Save keeps the page for the next start."""
    from minute_filler.gui.settings_dialog import SettingsDialog
    from minute_filler.settings import Settings
    s = Settings()
    d = SettingsDialog(s)
    d.show_page("dates")
    d.reject()
    again = SettingsDialog(s)
    assert again.current_page() == "dates"
    again.show_page("Invoice")  # (the tab's name before 2.18)
    assert again.current_page() == "invoices"
    again.accept()
    assert s.settings_page == "invoices"
    SettingsDialog.last_page = ""
    assert SettingsDialog(s).current_page() == "invoices"
    for old, new in (("Options", "files"), ("Defaults", "rates"), ("Run sheet", "runsheets"), ("Records", "records"),
                     ("AI", "ai"), ("nowhere", PAGES[0].key)):
        again.show_page(old)
        assert again.current_page() == new, old
    SettingsDialog.last_page = ""


def test_find_a_setting_in_the_window(qt, monkeypatch):
    """Typed in Find a setting: what it finds is listed; Enter, or a click, opens the first's page. Enter there
    never saves and closes Settings (its default button), even with nothing found; Escape clears the box first."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from minute_filler.gui.settings_dialog import SettingsDialog
    from minute_filler.settings import Settings
    saved = []
    # (on the class, before the window is made: its Save button holds the method it was given then)
    monkeypatch.setattr(SettingsDialog, "accept", lambda self: saved.append(1))
    monkeypatch.setattr(SettingsDialog, "reject", lambda self: saved.append(0))
    d = SettingsDialog(Settings())
    d.show()
    d.show_page("my_info")
    d.find.setFocus()
    QTest.keyClicks(d.find, "judge")
    assert d.found.count() >= 1 and d.found.item(0).data(Qt.UserRole) == "invoice_judge_index"
    assert d.list.isHidden() and not d.found.isHidden()
    QTest.keyClick(d.find, Qt.Key_Return)
    assert d.current_page() == "invoices" and not saved and d.isVisible()
    QTest.keyClick(d.found, Qt.Key_Enter)
    assert not saved and d.isVisible()
    d.find.setText("nothing like this zzz")
    assert d.found.count() == 1 and not d.found.item(0).data(Qt.UserRole)
    QTest.keyClick(d.find, Qt.Key_Return)
    assert not saved and d.isVisible()
    QTest.keyClick(d.find, Qt.Key_Escape)
    assert d.find.text() == "" and not d.list.isHidden() and d.found.isHidden() and not saved
    d.find.setText("your")  # (Escape in the list clears the search too; Enter on a row of no setting does nothing)
    d.found.setFocus()
    d.show_page("dates")
    row = next(i for i in range(d.found.count()) if not d.found.item(i).data(Qt.UserRole))
    d.found.setCurrentRow(row)
    QTest.keyClick(d.found, Qt.Key_Return)
    assert d.current_page() == "dates" and not saved
    QTest.keyClick(d.found, Qt.Key_Escape)
    assert d.find.text() == "" and not saved and d.isVisible()
    d.find.setText("highlight")  # (moved out of Settings: said where it is, nothing to go to)
    assert d.found.count() == 1 and not d.found.item(0).data(Qt.UserRole)
    assert d.found.item(0).text().startswith("Not in Settings: The Who transcribed what card")
    d.hide()
    SettingsDialog.last_page = ""
    d.deleteLater()


def _run_loop(ms: int) -> None:
    """Runs the event loop for `ms` milliseconds (the window's timers fire)."""
    from PySide6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def test_a_setting_found_is_lit_up_a_moment_then_as_it_was(qt):
    """Found twice in a row (a double-click), the label still gets its own look back after FLASH_MS; closed and
    deleted meanwhile, the window's timers do nothing (no error box)."""
    import sys
    import traceback
    from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
    from minute_filler.gui import settings_dialog
    from minute_filler.settings import Settings
    # (work earlier tests left running answers first: only this window's errors count below)
    QThreadPool.globalInstance().waitForDone(10000)
    QCoreApplication.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    d = settings_dialog.SettingsDialog(Settings())
    label = d._labels["invoice_rounding"]
    own = label.styleSheet()
    d.go_to("invoice_rounding")
    d.go_to("invoice_rounding")
    assert "highlight" in label.styleSheet()
    _run_loop(settings_dialog.FLASH_MS + 300)
    assert label.styleSheet() == own and not d._flashed
    errors = []
    hook = sys.excepthook
    sys.excepthook = lambda kind, e, tb: errors.extend(
        [e] if "settings_dialog" in "".join(traceback.format_tb(tb)) or "already deleted" in str(e) else [])
    try:
        d.go_to("invoice_rounding")
        d.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        _run_loop(settings_dialog.FLASH_MS + 300)
    finally:
        sys.excepthook = hook
    assert not errors
    settings_dialog.SettingsDialog.last_page = ""


# --- what the code says about where settings are

ARROW = re.compile(r"\s*(?:→|->|&rarr;)\s*")
# what may come between "→" and the name it points at: markup (<i>, <b>, Markdown's *), a quote
MARKUP = re.compile(r"(?:<[ib]>|\*|\")*")
OLD_RE = re.compile(r"\b(?:Options|Defaults)\s*(?:→|->|&rarr;)|\b(?:Dates|Invoice|Options|Defaults) tab\b")


def _sources() -> list[Path]:
    """The code, the help and the README (the website follows the release, as its pictures do)."""
    return [f for f in sorted((ROOT / "minute_filler").rglob("*.py")) if f.name != "settings_catalog.py"] + [
        ROOT / "README.md"]


def _after(text: str, at: int, names) -> str | None:
    """The name of `names` (longest first, any case, lines joined) that text starts with at `at`, past markup."""
    at = MARKUP.match(text, at).end()
    # (a path may run on in the next string of the code, or the next line of a comment: "Split "\n "invoices")
    ahead = " ".join(re.sub(r'\bf"|["#]|\\n', " ", text[at:at + 160]).split()).lower()
    return next((n for n in sorted(names, key=len, reverse=True) if n and ahead.startswith(n.lower())), None)


def test_every_settings_path_written_is_a_page_of_today():
    """"Settings → Invoices → Rounding" in a message, a tooltip, the help, a comment or the README: the page is one
    of today's, and what comes after it a heading or a setting's name on that page. A setting moved without its
    paths fails here (messages should use settings_catalog.path, which follows it)."""
    titles = {p.title: p for p in PAGES}
    wrong = []
    for f in _sources():
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(r"Settings(?=\s*(?:→|->|&rarr;))", text):
            line = text.count("\n", 0, m.start()) + 1
            arrow = ARROW.match(text, m.end())
            title = _after(text, arrow.end(), titles)
            if title is None:
                wrong.append(f"{f.relative_to(ROOT)}:{line}: {text[m.start():m.start() + 50]!r}")
                continue
            page = titles[title]
            end = MARKUP.match(text, arrow.end()).end() + len(title)
            nxt = ARROW.match(text, end)
            if nxt is None:
                continue  # ("Settings → Invoices turns it back on")
            names = list(page.sections) + [n for e in ENTRIES if e.page == page.key
                                           for n in (shown_label(e.key),) + e.rows]
            names += [re.sub(r"\s*\(.*?\)", "", n) for n in names]  # ("one for the whole case (every day…)")
            if _after(text, nxt.end(), names) is None:
                wrong.append(f"{f.relative_to(ROOT)}:{line}: {text[m.start():m.start() + 70]!r}")
        for m in OLD_RE.finditer(text):
            wrong.append(f"{f.relative_to(ROOT)}:{text.count(chr(10), 0, m.start()) + 1}: {m.group(0)!r}")
    assert not wrong, "\n".join(wrong)


# the setting a GUI module writes outside Settings, by assignment or MainWindow._set_opt: each must be one the
# catalog keeps there (home WINDOW or INTERNAL) or one it shows in Settings saying where else it is set (also_in).
# (Only the window's own settings, self.s: a copy made for a preview, "s = deepcopy(self.s)", changes nothing.)
WRITE_RE = re.compile(r"\b(?:self\.s|win\.s|window\.s|self\.settings)\.(\w+)\s*(?:=(?!=)|\+=)|"
                      r"_set_opt\(\s*\"(\w+)\"")


def test_the_windows_write_no_setting_they_dont_declare():
    """A window outside Settings that sets a setting shown in Settings says so in its entry's also_in (or the setting
    is the window's own, home WINDOW): one setting, set in two places, is declared, never found by surprise."""
    gui = ROOT / "minute_filler" / "gui"
    keys = set(setting_keys())
    undeclared = []
    for f in sorted(gui.glob("*.py")):
        if f.name == "settings_dialog.py":
            continue
        text = f.read_text(encoding="utf-8")
        for m in WRITE_RE.finditer(text):
            key = m.group(1) or m.group(2)
            if key not in keys:
                continue
            e = ENTRY[key]
            if e.home == SETTINGS and not e.also_in:
                undeclared.append(f"{f.name}:{text.count(chr(10), 0, m.start()) + 1}: {key}")
    assert not undeclared, "\n".join(undeclared)


@pytest.mark.parametrize("key", [e.key for e in ENTRIES if e.also_in])
def test_also_in_says_where(key):
    """Every other place named in also_in says where it is."""
    assert all(w.strip() for w in ENTRY[key].also_in)


def test_settings_md_lists_every_page_as_the_catalog_has_it():
    """SETTINGS.md's table of pages: each page, its rule and its headings, as settings_catalog says them."""
    md = (ROOT / "SETTINGS.md").read_text(encoding="utf-8")
    rows = {line.split("|")[1].strip(): line for line in md.splitlines() if line.startswith("| ")}
    for p in PAGES:
        assert p.title in rows, p.title
        assert p.belongs in rows[p.title] and " · ".join(p.sections) in rows[p.title], p.title
