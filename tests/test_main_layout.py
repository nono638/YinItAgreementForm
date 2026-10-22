"""The main window laid out as the job goes (the user, 2026-10-22: the cards felt unintuitive): the cards in the
order the work is done, named for what is in them, the field badges quiet unless something needs a look, each
firm marked by its tag and a stripe (not a shade that reads as "check this"), short texts, Generate buttons that
say what they make, the things to check listed where they can be clicked, the invoice's choices in a card of the
form and the Outputs box one row. All names are made up."""
import pytest

from helpers import pat_settings


@pytest.fixture
def window(make_window, tmp_path):
    """A window styled as the app styles it at start."""
    from PySide6.QtWidgets import QApplication
    from minute_filler.gui.theme import apply_theme
    apply_theme(QApplication.instance(), "light")
    s = pat_settings()
    s.use_ai = s.open_after = False
    s.output_dir = str(tmp_path / "out")
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
