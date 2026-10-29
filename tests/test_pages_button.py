"""Who ordered's "Who ordered which pages…" (it was "Excerpts…", at the far right of the card's row, hard to find:
the user, 2026-10-28): beside "+ Add attorney" and "Remove selected", outlined in the accent's colour, with a ?
that shows how to use it step by step (gui/excerpts.show_how_to), as the window's own ? does; "More in the manual"
opens the help at its topic. Settings -> Options -> Folders has the box that copies the documents read into an
Inputs folder (off by default). All names are made up."""
import pytest

from minute_filler.settings import Settings

from helpers import pat_settings


@pytest.fixture
def window(make_window, qt):
    s = pat_settings()
    s.use_ai = s.open_after = False
    return make_window(s)


def answer(monkeypatch, qt, button: str) -> list:
    """Every QMessageBox is answered with the button whose text starts with `button`; returns (title, text)
    of each shown."""
    shown = []

    def exec_(box):
        shown.append((box.windowTitle(), box.text()))
        box._picked = next((b for b in box.buttons() if b.text().startswith(button)), None)
        return 0
    monkeypatch.setattr(qt.QMessageBox, "exec", exec_)
    monkeypatch.setattr(qt.QMessageBox, "clickedButton", lambda box: getattr(box, "_picked", None))
    return shown


def row_of(layout, widget):
    """The layout, inside `layout`, that holds `widget` itself (None when none does)."""
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item.widget() is widget:
            return layout
        if item.layout() is not None:
            found = row_of(item.layout(), widget)
            if found is not None:
                return found
    return None


def test_the_button_sits_with_the_row_s_own_buttons_and_stands_out(window, qt):
    b = window.orders_edit
    assert b.text() == "Who ordered which pages…" and b.objectName() == "pages"
    card = window.cards["attorneys"]
    assert card.isAncestorOf(b) and card.isAncestorOf(window.orders_how)
    row = row_of(b.parentWidget().layout(), b)
    texts = [row.itemAt(i).widget().text() for i in range(row.count())
             if row.itemAt(i).widget() is not None and hasattr(row.itemAt(i).widget(), "text")]
    # (in the card's row of buttons, right after them, before the hint: no longer at the far right)
    assert texts[:4] == ["+ Add attorney", "Remove selected", "Who ordered which pages…", "?"]
    from minute_filler.gui.theme import QSS
    assert "QPushButton#pages {" in QSS  # (outlined in the accent's colour)


def test_the_question_mark_shows_the_steps_and_opens_the_manual(window, monkeypatch, qt):
    opened = []
    monkeypatch.setattr(window, "show_help", lambda topic="": opened.append(topic))
    shown = answer(monkeypatch, qt, "Close")
    window.orders_how.click()
    assert shown and shown[0][0] == "Who ordered which pages: how to use it"
    assert "Tick the firms that ordered" in shown[0][1] and "141-170" in shown[0][1]
    assert opened == []
    answer(monkeypatch, qt, "More in the manual")
    window.orders_how.click()
    assert opened == ["exc-table"]


def test_the_window_has_its_own_question_mark(window, monkeypatch, qt):
    from minute_filler.gui.excerpts import ExcerptsWindow
    w = ExcerptsWindow(window.s, lambda: None, window)
    assert w.windowTitle() == "Who ordered which pages" and w.how.text() == "?"
    shown = answer(monkeypatch, qt, "Close")
    w.how.click()
    assert shown and "run of pages" in shown[0][1]
    w.deleteLater()


def test_the_help_topic_is_found_by_its_old_name_and_its_new_one():
    """Searched by its old name, the topic comes first; by the button's new one ("who" and "which" are no words
    to look for: help_search.STOP), among the first two, after the Who ordered card's own topic, which names the
    button. With the word table and by the keywords alone, whichever earlier tests made ready (help_meaning)."""
    from minute_filler import help_meaning
    from minute_filler.help_search import search
    from minute_filler.help_topics import TOPICS
    topic = next(t for t in TOPICS if t.id == "exc-table")
    assert topic.title.startswith("Who ordered which pages…")
    assert "excerpt" in topic.words
    for meaning in (help_meaning.load(TOPICS), False):
        assert search("excerpts", meaning=meaning)[0].topic.id == "exc-table"
        assert "exc-table" in [h.topic.id for h in search("who ordered which pages", meaning=meaning)[:2]]


def test_f1_on_the_button_opens_its_topic(window):
    from minute_filler.gui.help_window import help_topic_of
    assert help_topic_of(window.orders_edit) == "exc-table"


def test_settings_save_the_inputs_box(qt):
    from minute_filler.gui.dialogs import SettingsDialog
    dlg = SettingsDialog(pat_settings())
    assert not dlg.o_save_inputs.isChecked()  # (off by default)
    dlg.o_save_inputs.setChecked(True)
    dlg.accept()
    assert Settings.load().save_inputs is True
