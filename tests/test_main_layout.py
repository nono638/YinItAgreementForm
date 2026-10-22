"""The main window laid out as the job goes (the user, 2026-10-22: the cards felt unintuitive): the cards in the
order the work is done, named for what is in them, the field badges quiet unless something needs a look, each
firm marked by its tag and a stripe (not a shade that reads as "check this"), short texts, Generate buttons that
say what they make, the things to check listed where they can be clicked, the invoice's choices in a card of the
form and the Outputs box one row. All names are made up."""
import pytest

from helpers import pat_settings


@pytest.fixture
def window(make_window, tmp_path, monkeypatch, qt):
    """A window styled as the app styles it at start, making agreements and invoices; message boxes and the
    questions before Generate answered at once."""
    from minute_filler.gui.dialogs import ClarifyDialog
    from minute_filler.gui.theme import apply_theme
    monkeypatch.setattr(qt.QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(ClarifyDialog, "exec", lambda self: qt.QDialog.Accepted)
    apply_theme(qt.QApplication.instance(), "light")
    s = pat_settings()
    s.use_ai = s.open_after = False
    s.output_dir, s.records_dir = str(tmp_path / "out"), str(tmp_path / "records")
    s.outputs = ["agreement", "invoice"]
    return make_window(s)


def card_order(win) -> list[str]:
    """The keys of the form's folding cards, top to bottom."""
    lay = win.form_scroll.widget().layout()
    return sorted(win.cards, key=lambda k: lay.indexOf(win.cards[k]))


def test_the_cards_follow_the_job_and_say_what_is_in_them(window):
    """Who ordered first (Attorneys right under the case), then the speed, pages and dates; the invoice's cards
    with what was ordered before what it costs, and the trial's report last."""
    assert card_order(window) == ["case", "attorneys", "details", "orders", "pays", "takes"]
    titles = {k: c.heading.text() for k, c in window.cards.items()}
    assert titles == {"case": "Case", "attorneys": "Attorneys: tick who ordered", "details": "Speed, pages and dates",
                      "orders": "Who ordered what", "pays": "Who pays what", "takes": "Who transcribed what"}
    assert window.orders_edit.text() == "Excerpts…"


def test_a_badge_is_a_pill_only_for_a_value_to_look_at(window):
    """Where a value came from is said quietly ("found", "PDF", "default"...: grey, no pill); a value the AI or the
    records gave, or one the reader wasn't sure of, keeps a coloured pill, as its field is marked to look at."""
    from minute_filler.gui.theme import QSS
    from minute_filler.models import FieldState
    court = window.rows["court"]
    for st, loud in [(FieldState("Supreme", "regex", 0.9), False), (FieldState("Supreme", "default", 1.0), False),
                     (FieldState("Supreme", "you", 1.0), False), (FieldState("Supreme", "regex", 0.5), True),
                     (FieldState("Supreme", "AI", 0.9), True), (FieldState("Supreme", "records", 0.9), True)]:
        court.set_state(st)
        assert court.badge.property("loud") is loud, st
        assert court.badge.text()
    base = next(line for line in QSS.splitlines() if line.startswith("QLabel#badge {"))
    assert "border: 1px solid transparent" in base and "font-weight" not in base
    assert 'QLabel#badge[src="regex"]' not in QSS  # (a source's colour is the loud pill's only)


def test_a_folded_who_pays_what_shows_its_warning(window, qt, tmp_path):
    """Nothing to bill because something needs fixing (three speeds on the same pages): folded, Who pays what's
    line starts with the ⚠ its card shows, as the other cards' lines do."""
    from test_sweep_270 import A, B, C, counsel, one_day, poe, smith
    job = one_day(window, qt, tmp_path, [counsel(), smith(), poe()])
    job.speeds = {A: "Daily", B: "Immediate", C: "Regular"}
    window._update_status()
    assert "⚠" in window.pays.text()
    window._fold_card(window.cards["pays"], True)
    assert window.cards["pays"].summary.text().startswith("⚠ Nothing to bill yet")
    job.speeds = {A: "Daily", B: "Daily", C: "Daily"}
    window._update_status()
    window._card_summaries()
    assert window.cards["pays"].summary.text().startswith("3 invoices: ")
