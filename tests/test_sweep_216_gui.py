"""The window's half of the 2.16 sweep (2026-10-30): a firm renamed while Generate's preview is open is the firm
the files invoiced (not one still to bill); midnight or the evening hour coming while Generate all runs is no
change to its days (a date typed meanwhile is); an AI question sent before the AI was turned off doesn't hold up
Generate, and the box that says to wait names the button pressed; Save in a preview waits for a read still going;
the Records window offers neither Mark paid nor Mark not paid on a void invoice, keeps an Undo that failed, and
chooses the newest backup copy that can be read; Settings lists the rate sheets of a sheets folder typed in;
Details... in Whose pages... says when the settings couldn't be saved; the model download reaches Ollama directly
and isn't started twice; the About box credits what HTTPX and ollama-python bring along. Pat Reporter ("pr") is
the user; all names and numbers are made up."""
import os
import re
import threading
from datetime import date, datetime, time, timedelta

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from minute_filler.models import Attorney, FieldState, SRC_USER  # noqa: E402

from helpers import pat_settings  # noqa: E402
from test_gui_batch import wait  # noqa: E402
from test_races_batch import Held, told, two_days, window  # noqa: E402,F401  (fixture)
from test_races_window import boxes, previewing, settings  # noqa: E402,F401  (fixtures)
from test_tracking import inv  # noqa: E402

NEW_FIRM = "Brand New Firm LLP"


# ------------------------------------------------------------------ 1: a firm renamed while Generate's preview is up
def renamed_meanwhile(win, monkeypatch):
    """While the preview is open, an AI answer's remerge fills in the ticked attorney's firm (another
    Attorney.key(), the same firm): returns (the key as shown, the key now)."""
    from minute_filler.gui.preview import PreviewDialog
    job = win.cur
    old = next(a for a in job.case.attorneys if a.checked).key()

    def exec_(dlg):
        a = next(a for a in job.case.attorneys if a.key() == old)
        a.firm = NEW_FIRM
        job.rename_in_portions(old, a.key())
        win._show_case()
        return PreviewDialog.Accepted
    monkeypatch.setattr(PreviewDialog, "exec", exec_)
    return old, Attorney(firm=NEW_FIRM).key()


def test_a_firm_renamed_while_the_preview_is_open_is_the_firm_invoiced(previewing, monkeypatch):
    """The firm was only renamed: the day is invoiced and made (Generate all doesn't bill the firm again under
    its new name), and the Saved box doesn't say the day changed."""
    job = previewing.cur
    old, new = renamed_meanwhile(previewing, monkeypatch)
    previewing.fill()
    assert job.ticked_keys() == [new] and job.saved
    assert job.made and job.invoiced and previewing._to_generate() == []
    assert "changed while the files were made" not in previewing.said[-1]


def test_a_firm_renamed_while_the_preview_is_open_is_kept_invoiced_when_saving_fails(previewing, monkeypatch):
    """Generate stops with an error after the firm's invoice was made: the attorney kept as invoiced is the firm
    under its new name, so trying again doesn't bill it twice."""
    from minute_filler.gui import main_window as mw
    job = previewing.cur
    old, new = renamed_meanwhile(previewing, monkeypatch)
    real, calls = mw.generate, []

    def generate(case, s, out_dir, outputs, opts, invoiced=None, **kw):
        calls.append(1)
        if len(calls) == 1:  # (the preview's)
            return real(case, s, out_dir, outputs, opts, invoiced=invoiced, **kw)
        invoiced.append(old)  # (its invoice made, under the name the preview showed)
        raise RuntimeError("the agreement could not be written")
    monkeypatch.setattr(mw, "generate", generate)
    monkeypatch.setattr(mw, "show_save_error", lambda *a, **k: None)
    previewing.fill()
    assert len(calls) == 2 and job.error and not job.invoiced
    assert job.invoiced_keys == [new] and job.billed_keys() == [new]


# ------------------------------------------------------------------ 2: the day turning while Generate all runs
def tomorrow(monkeypatch):
    """The clock at 10 AM tomorrow, and the window's minute timer catching up (_redate)."""
    from minute_filler import workdays
    monkeypatch.setattr(workdays, "now", lambda: datetime.combine(date.today() + timedelta(days=1), time(10)))


def test_midnight_while_generate_all_runs_is_no_change(window, tmp_path, monkeypatch):
    """Midnight comes while the batch is made: the window dates its days' default dates for the new day, which
    is no change to them, so they are marked made (the next Generate all doesn't make them again)."""
    day1, day2 = two_days(window, tmp_path)
    said = told(window, monkeypatch)
    held = Held(window, monkeypatch)
    window.fill_all_jobs()
    shown = day1.case.get("agreement_date")
    tomorrow(monkeypatch)
    window._redate()
    assert day1.case.get("agreement_date") != shown  # (the window's date did move)
    held.run()
    assert day1.made and day2.made and "changed while the files were made" not in said[-1]


def test_midnight_while_generate_alls_preview_is_open_is_no_change(window, tmp_path, monkeypatch):
    from minute_filler.gui.preview import PreviewDialog
    window.s.preview_before_saving = True
    day1, day2 = two_days(window, tmp_path)
    said = told(window, monkeypatch)
    held = Held(window, monkeypatch)

    def later(dlg):
        tomorrow(monkeypatch)
        window._redate()
        return PreviewDialog.Accepted
    monkeypatch.setattr(PreviewDialog, "exec", later)
    window.fill_all_jobs()
    held.run()  # the preview
    held.run()  # the batch saved
    assert day1.made and day2.made and "changed while the files were made" not in said[-1]


def test_a_date_typed_while_generate_all_runs_is_still_a_change(window, tmp_path, monkeypatch):
    """A date the user typed meanwhile isn't the day's default: that day is made again next time."""
    day1, day2 = two_days(window, tmp_path)
    said = told(window, monkeypatch)
    held = Held(window, monkeypatch)
    window.fill_all_jobs()
    tomorrow(monkeypatch)
    window._redate()
    day1.case.fields["agreement_date"] = FieldState("6/10/2026", SRC_USER, 1.0, [])
    held.run()
    assert not day1.made and day2.made and "changed while the files were made" in said[-1]


# ------------------------------------------------------------------ 3: the AI turned off; the button pressed
def test_an_ai_question_sent_before_the_ai_was_turned_off_doesnt_hold_generate(previewing, boxes, monkeypatch):
    """Its answer is dropped when it comes (_maybe_ai), so Generate doesn't wait for it."""
    from minute_filler.gui.preview import PreviewDialog
    monkeypatch.setattr(PreviewDialog, "exec", lambda dlg: PreviewDialog.Accepted)
    previewing.ai_pending = 1
    previewing.s.use_ai = False
    previewing.fill()
    assert not boxes and previewing.cur.saved
    previewing.ai_pending = 0


def test_the_wait_box_names_the_button_pressed(window, tmp_path, monkeypatch, boxes):
    """Generate for one day of a case reads "Generate 6/3/2026 only": the box says to press that again."""
    two_days(window, tmp_path)
    window.work = 1
    try:
        window.fill()
    finally:
        window.work = 0
    assert boxes and re.search(r"Press Generate \d+/\d+/\d{4} only again", boxes[-1][1]), boxes
    assert f"Press {window._one_words(window.cur)} again" in boxes[-1][1]


# ------------------------------------------------------------------ 4: Save in a preview while a read goes on
def reading_at_first_save(win, monkeypatch, then=None):
    """The preview's Save pressed while a file dropped meanwhile is read; the box that says to wait answered,
    the read ends and the preview is shown again: Save (or then(), the second answer). Returns the calls made."""
    from minute_filler.gui.preview import PreviewDialog
    calls = []

    def exec_(dlg):
        calls.append(win.work)
        if len(calls) == 1:
            win.work += 1  # (the read started while the preview was made, still going)
            return PreviewDialog.Accepted
        win.work -= 1  # (the read ended while the wait box was up)
        return then if then is not None else PreviewDialog.Accepted
    monkeypatch.setattr(PreviewDialog, "exec", exec_)
    return calls


def test_save_in_generate_alls_preview_waits_for_a_read(tmp_path, monkeypatch, make_window, qt, boxes):
    """The user, 2026-10-30: "you can't generate as things are still being read and there should just be a
    pop-up saying please wait for reads to finish". The box says to wait, nothing is saved, the preview stays
    for Save again; the batch starts once the read is done."""
    from minute_filler.gui import dialogs
    monkeypatch.setattr(qt.QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(dialogs.ClarifyDialog, "exec", lambda self: 0)
    s = settings(tmp_path)
    s.save_math = "off"
    win = make_window(s, preview=True)
    two_days(win, tmp_path)
    calls = reading_at_first_save(win, monkeypatch)
    started = []
    run_batch = win._run_batch
    monkeypatch.setattr(win, "_run_batch", lambda *a, **k: (started.append(win.work), run_batch(*a, **k)))
    win.fill_all_jobs()
    wait(win, lambda: len(calls) == 2 and not win.filling)
    assert boxes and boxes[0][0] == "Please wait for the reading to finish" and "Press Save again" in boxes[0][1]
    assert started == [0] and all(j.saved for j in win.jobs)


def test_go_back_after_waiting_for_a_read_saves_nothing(tmp_path, monkeypatch, make_window, qt, boxes):
    from minute_filler.gui import dialogs
    from minute_filler.gui.preview import PreviewDialog
    monkeypatch.setattr(qt.QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(dialogs.ClarifyDialog, "exec", lambda self: 0)
    s = settings(tmp_path)
    s.save_math = "off"
    win = make_window(s, preview=True)
    two_days(win, tmp_path)
    calls = reading_at_first_save(win, monkeypatch, then=PreviewDialog.Rejected)
    win.fill_all_jobs()
    wait(win, lambda: len(calls) == 2 and not win.filling)
    assert boxes and not any(j.saved for j in win.jobs) and not win.filling


def test_save_in_generates_preview_waits_for_a_read(previewing, monkeypatch, boxes):
    """One job: the same."""
    calls = reading_at_first_save(previewing, monkeypatch)
    previewing.fill()
    assert len(calls) == 2 and "Press Save again" in boxes[0][1] and previewing.cur.saved


# ------------------------------------------------------------------ 5-7: the Records window
@pytest.fixture
def records(qt, tmp_path, monkeypatch):
    """The Records window with a made-up 2026-0001 invoice void and 2026-0002 open; menus are caught (shown,
    one would wait for a click): win.menu holds the last one's action texts."""
    from minute_filler.deliver import ledger_for
    from minute_filler.gui import records_window as rw
    s = pat_settings()
    s.records_dir = str(tmp_path / "records")
    lg = ledger_for(s)
    lg.add_invoice(inv("2026-0001"))
    lg.add_invoice(inv("2026-0002", firm="Counsel & Counsel"))
    lg.void("2026-0001")
    win = rw.RecordsWindow(s)
    win.reload()
    win.i_year.setCurrentIndex(0)
    win.menu = []

    class Menu(rw.QMenu):
        def exec(self, *a):
            win.menu[:] = [x.text() for x in self.actions() if x.text()]

    monkeypatch.setattr(rw, "QMenu", Menu)
    yield win, lg
    win.close()
    win.deleteLater()


def menu_of(win, no):
    from test_tracking import cell
    win.show()
    t = win.inv_table
    win._invoice_menu(t.visualItemRect(cell(win, no, "no")).center())
    return win.menu


def test_a_void_invoice_is_neither_marked_paid_nor_not_paid(records, monkeypatch):
    """Mark paid... on a void invoice used to take its void away without a word (Restore (not void) is for
    that)."""
    from minute_filler.gui import records_window as rw
    win, lg = records
    assert "Mark paid…" not in menu_of(win, "2026-0001") and "Mark not paid" not in win.menu
    assert "Restore (not void)" in win.menu
    assert "Mark paid…" in menu_of(win, "2026-0002")
    monkeypatch.setattr(rw.PaidDialog, "exec", lambda self: rw.QDialog.Accepted)
    win._set_paid("2026-0001", True)  # (the Paid cell, say)
    assert lg.invoice("2026-0001").status == "void"
    win._set_paid("2026-0002", True)
    assert lg.invoice("2026-0002").status == "paid"


def test_an_undo_that_fails_can_be_tried_again(records, monkeypatch):
    from minute_filler.gui import records_window as rw
    win, lg = records
    monkeypatch.setattr(rw.QMessageBox, "warning", lambda *a, **k: None)
    win.delete("invoices", [lg.invoice("2026-0002")], ask=False)
    assert lg.invoice("2026-0002").deleted and len(win.undo_stack) == 1
    real = win.ledger.restore

    def locked(*a, **k):
        raise PermissionError("the records are open in another program")
    monkeypatch.setattr(win.ledger, "restore", locked)
    win.undo()
    assert len(win.undo_stack) == 1 and win.undo_btn.isEnabled()  # (kept, to try again)
    monkeypatch.setattr(win.ledger, "restore", real)
    win.undo()
    assert win.undo_stack == [] and not lg.invoice("2026-0002").deleted and not win.undo_btn.isEnabled()


def test_backups_choose_the_newest_copy_that_can_be_read(records, monkeypatch):
    from PySide6.QtCore import Qt
    from minute_filler.deliver import backup_folder
    from minute_filler.gui import records_window as rw
    win, lg = records
    folder = backup_folder(win.s)
    folder.mkdir(parents=True, exist_ok=True)
    lg.backup(folder, force=True)
    (folder / "records 2099-01-01.db").write_bytes(b"not a records database")  # (the newest, unreadable)
    dlg = rw.BackupsDialog(win.s, lg, win)
    assert dlg.list.count() == 2 and "can't be read" in dlg.list.item(0).text()
    assert dlg.list.currentRow() == 1 and dlg.restore_btn.isEnabled()
    dlg.list.setCurrentRow(0)  # (by the keyboard, say)
    assert not dlg.restore_btn.isEnabled()
    asked = []
    monkeypatch.setattr(rw.QMessageBox, "question", lambda *a, **k: asked.append(1) or rw.QMessageBox.No)
    dlg.restore()
    assert not asked and not dlg.restored
    dlg.list.setCurrentRow(1)
    assert dlg.restore_btn.isEnabled() and bool(dlg.list.currentItem().flags() & Qt.ItemIsEnabled)
    dlg.deleteLater()


# ------------------------------------------------------------------ 9-11: Settings, Whose pages..., Ollama, About
def sheets_folders(tmp_path):
    """Settings using "County Rates" of a first sheets folder, and another folder with "City Rates" (made-up
    prices)."""
    first, other = tmp_path / "first sheets", tmp_path / "other sheets"
    for folder, name in ((first, "County Rates"), (other, "City Rates")):
        folder.mkdir()
        (folder / f"{name}.csv").write_text("Speed,Original,Copy\nRegular,5.00,1.00\n", encoding="utf-8")
    s = pat_settings()
    s.rate_sheets_dir, s.rate_sheet = str(first), "County Rates"
    return s, other


def sheet_names(d) -> list[str]:
    return [d.d_sheet.itemText(i) for i in range(d.d_sheet.count())]


def test_a_sheets_folder_typed_in_lists_its_sheets(qt, tmp_path, monkeypatch):
    """Only Browse... used to list the sheets of another folder: Save then kept a sheet of the old folder with
    the new one."""
    from minute_filler.gui import dialogs
    monkeypatch.setattr(dialogs.QMessageBox, "warning", lambda *a, **k: None)
    s, other = sheets_folders(tmp_path)
    d = dialogs.SettingsDialog(s)
    assert "County Rates" in sheet_names(d) and "City Rates" not in sheet_names(d)
    d.d_dir.setText(str(other))
    d.d_dir.editingFinished.emit()  # (Enter, or the box left)
    assert "City Rates" in sheet_names(d) and "County Rates" not in sheet_names(d)
    d.d_sheet.setCurrentIndex(sheet_names(d).index("City Rates"))
    d.accept()
    assert s.rate_sheets_dir == str(other) and s.rate_sheet == "City Rates"


def test_a_sheets_folder_typed_and_saved_at_once(qt, tmp_path, monkeypatch):
    from minute_filler.gui import dialogs
    monkeypatch.setattr(dialogs.QMessageBox, "warning", lambda *a, **k: None)
    s, other = sheets_folders(tmp_path)
    d = dialogs.SettingsDialog(s)
    d.d_dir.setText(str(other))
    d.accept()  # (no focus left the box first)
    assert s.rate_sheets_dir == str(other) and s.rate_sheet != "County Rates"
    from minute_filler.rates import list_sheets
    assert s.rate_sheet in [x.name for x in list_sheets(str(other))[0]]


def test_whose_pages_details_say_when_the_settings_cant_be_saved(qt, monkeypatch):
    from minute_filler.gui import dialogs
    from minute_filler.settings import ReporterProfile
    s = pat_settings()
    dlg = dialogs.PagesOwnerDialog([("k", "Roe.pdf", ["pr", "pr", "ds"])], {"pr"}, {"k": ["me", "ds"]}, {},
                                   settings=s)
    monkeypatch.setattr(dialogs.ReporterDialog, "exec", lambda self: dialogs.ReporterDialog.Accepted)
    monkeypatch.setattr(dialogs.ReporterDialog, "value", lambda self: ReporterProfile(name="Dana",
                                                                                      full_name="Dana Q. Smith"))

    def locked(*a, **k):
        raise PermissionError("settings.json is open in another program")
    monkeypatch.setattr(s, "save", locked)
    logged, warned = [], []
    monkeypatch.setattr(dialogs, "log_error", lambda what, e: logged.append(what))
    monkeypatch.setattr(dialogs.QMessageBox, "warning", lambda parent, title, text: warned.append(text))
    dlg._details("ds")
    assert s.reporter("ds").full_name == "Dana Q. Smith"  # (kept for now)
    assert logged == ["could not save the settings"] and "saved again when the app closes" in warned[0]
    dlg.deleteLater()


def test_the_model_download_reaches_ollama_on_this_computer_directly(qt, monkeypatch):
    """As every other Ollama client: a proxy set up in Windows may not pass "localhost" on."""
    import ollama
    from minute_filler.gui import dialogs
    made = []

    class Client:
        def __init__(self, **kw):
            made.append(kw)

        def pull(self, model, stream=True):
            return iter(())
    monkeypatch.setattr(ollama, "Client", Client)
    t = dialogs._PullThread("llama-test", "")
    said = []
    t.finished_ok.connect(said.append)
    t.run()  # (here, not on a thread)
    assert made == [{"host": None, "timeout": None, "trust_env": False}] and said == ["✓ llama-test is installed."]


def test_the_ollama_help_opened_again_doesnt_start_a_second_download(qt, monkeypatch):
    """The help closed during a download and opened again: Download stays off until the first one ends."""
    from minute_filler.gui import dialogs
    monkeypatch.setattr(dialogs, "_BACKGROUND", [])
    release = threading.Event()
    monkeypatch.setattr(dialogs._PullThread, "run", lambda self: release.wait(10))
    first = dialogs.OllamaHelpDialog("llama-test", "")
    first._pull()
    try:
        again = dialogs.OllamaHelpDialog("llama-test", "")
        assert not again.pull_btn.isEnabled() and "started before" in again.status.text()
        assert again.thread is first.thread
    finally:
        release.set()
        assert first.thread.wait(5000)
    wait_for = 50
    while wait_for and not again.pull_btn.isEnabled():
        qt.QApplication.processEvents()
        threading.Event().wait(0.02)
        wait_for -= 1
    assert again.pull_btn.isEnabled()  # (the download over: offered again)
    third = dialogs.OllamaHelpDialog("llama-test", "")
    assert third.pull_btn.isEnabled()
    for d in (first, again, third):
        d.deleteLater()


def test_the_about_box_credits_what_httpx_and_ollama_bring_along(qt):
    from minute_filler.gui.dialogs import COMPONENTS
    names = {name: lic for name, lic, _ in COMPONENTS}
    assert names["certifi (used by HTTPX)"] == "MPL-2.0"
    assert names["Pydantic (used by ollama-python)"] == "MIT"
    assert any(n.startswith("httpcore, h11, anyio, idna") for n in names)
