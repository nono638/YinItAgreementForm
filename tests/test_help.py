"""The help: the manual's topics (help_topics), their links and their made-up names, that every setting and every
shortcut of the windows is in it (so a new one can't go unexplained), that the search finds the right topic for
questions in a reporter's own words (tests/help_questions.py, written without looking at the help), typos and
everyday words, the word table it is helped by (help_meaning) and the keywords alone without it, the Help window
(search, Back, links, highlights; not modal), F1 opening the topic of where you are (the main window, Settings'
tabs, Records), the Help menu, and About linking the website and crediting the word table's model."""
import os
import re

import pytest

from helpers import pat_settings
from help_questions import QUESTIONS

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

WEBSITE = "https://nono638.github.io/YinItAgreementForm/"
TOP3_AT_LEAST = 0.8  # the share of QUESTIONS whose answer the search must put among the first three (87% in 2.8.0)


def _norm(text: str) -> str:
    """Lower case, one space between words, without the ends that change from place to place (…, :)."""
    return " ".join(text.replace("&", "").split()).lower().strip(" :….").replace("...", "")


@pytest.fixture
def window(tmp_path, make_window):
    s = pat_settings()
    s.use_ai = s.open_after = False
    s.output_dir = str(tmp_path / "out")
    s.records_dir = str(tmp_path / "records")
    return make_window(s)


def help_menu(win):
    return next(a.menu() for a in win.menuBar().actions() if a.text() == "&Help")


# --- the topics

def test_the_topics_have_unique_ids_working_links_and_every_chapter():
    from minute_filler.help_topics import CHAPTERS, TOPICS, links, topic
    ids = [t.id for t in TOPICS]
    assert len(ids) == len(set(ids))
    assert {t.chapter for t in TOPICS} == set(CHAPTERS)
    broken = [(t.id, link) for t in TOPICS for link in links(t) if topic(link) is None]
    assert not broken
    for t in TOPICS:
        assert t.title and len(t.text.split()) >= 20, t.id
        assert "<script" not in t.html and "color" not in t.html, t.id  # (no colours: they'd clash in dark mode)


def test_the_topics_use_made_up_names_only():
    """The help is compiled into the app, so it may hold only the made-up names of the examples."""
    from minute_filler.help_topics import TOPICS
    text = " ".join(t.text for t in TOPICS)
    names = set(re.findall(r"\b[A-Z][a-z]+ [A-Z]\. [A-Z][a-z]+\b|\b[A-Z][a-z]+ v\. [A-Z][a-z]+", text))
    assert names <= {"Alex B. Counsel", "Maria T. Alvarez", "Roe v. Sam", "Smith v. Jones"}, names
    assert set(re.findall(r"\b\d{6}/\d{4}\b", text)) <= {"712345/2021", "722222/2025"}


def test_every_setting_is_in_the_help(qt):
    """Each tick box and each row's label of Settings is named in some topic: a setting added without a word in the
    help fails here."""
    from PySide6.QtWidgets import QCheckBox, QFormLayout, QLabel, QTabWidget
    from minute_filler.gui.dialogs import SETTINGS_TOPICS, SettingsDialog
    from minute_filler.help_topics import TOPICS, topic
    from minute_filler.settings import Settings
    text = _norm(" ".join(t.title + " " + t.text for t in TOPICS))
    d = SettingsDialog(Settings())
    tabs = d.findChild(QTabWidget)
    names = {tabs.tabText(i) for i in range(tabs.count())}
    assert names == set(SETTINGS_TOPICS) and all(topic(v) for v in SETTINGS_TOPICS.values())
    labels = [c.text() for c in d.findChildren(QCheckBox)]
    for form in d.findChildren(QFormLayout):
        for row in range(form.rowCount()):
            item = form.itemAt(row, QFormLayout.LabelRole)
            if item is not None and isinstance(item.widget(), QLabel):
                labels.append(item.widget().text())
    # (the speeds' own names, and words that only make sense beside their box)
    skip = {"", "immediate", "daily", "expedited", "regular", "where", "show when", "dated the next day",
            "address", "case", "civil", "criminal"}
    missing = sorted({lab for lab in labels if _norm(lab) not in skip and _norm(lab) not in text})
    d.deleteLater()
    assert not missing, f"not in the help: {missing}"


def test_the_shortcuts_topic_has_the_windows_shortcuts(window):
    """Every key of the main window and the Records window is in the Keyboard shortcuts topic."""
    from PySide6.QtGui import QShortcut
    from minute_filler.gui.records_window import RecordsWindow
    from minute_filler.help_topics import topic
    text = topic("keys").text.replace(" ", "")
    same = {"Return": "Enter", "Ctrl+=": "Ctrl++", "Del": "Delete"}

    def shown(key: str) -> str:
        for a, b in same.items():
            key = key.replace(a, b)
        return key

    records = RecordsWindow(window.s, window)
    keys = {s.key().toString() for w in (window, records) for s in w.findChildren(QShortcut)}
    keys.discard("")
    missing = sorted(k for k in keys if shown(k) not in text and k not in text)
    records.deleteLater()
    assert not missing, f"not in the shortcuts topic: {missing}"


# --- the search

def test_the_questions_name_real_topics():
    from minute_filler.help_topics import topic
    assert len(QUESTIONS) >= 80
    assert not [q for q, ok in QUESTIONS if not ok or any(topic(i) is None for i in ok)]


def test_the_search_finds_the_answers_in_the_first_three():
    """Questions in a reporter's own words ("check came in", "add a holliday") find a topic that answers them among
    the first three, nearly always (the misses are listed when it doesn't)."""
    from minute_filler import help_meaning, help_search
    from minute_filler.help_topics import TOPICS
    meaning = help_meaning.load(TOPICS)
    assert meaning is not None  # (the word table is bundled: data/help_words.bin)
    missed = []
    for q, ok in QUESTIONS:
        got = [h.topic.id for h in help_search.search(q, meaning=meaning)][:3]
        if not set(got) & set(ok):
            missed.append(f"{q!r}: wanted {ok}, got {got}")
    share = 1 - len(missed) / len(QUESTIONS)
    assert share >= TOP3_AT_LEAST, f"{share:.0%} found:\n" + "\n".join(missed)


@pytest.mark.parametrize("question, answer", [
    ("invioce number", "inv-numbers"),        # a typo
    ("lawyer's address", "check-attorneys"),  # everyday words for the help's (SYNONYMS: lawyer -> attorney)
    ("cost per page", "inv-priced"),
    ("day off", "dates-holidays"),            # a phrase (day off -> holiday)
    ("signature", "set-signature"),
])
def test_the_search_forgives_typos_and_knows_everyday_words(question, answer):
    from minute_filler import help_search
    assert answer in [h.topic.id for h in help_search.search(question, meaning=False)][:3]


def test_a_search_of_only_little_words_finds_nothing_and_snippets_bold_the_words():
    from minute_filler import help_search
    from minute_filler.help_topics import topic
    assert help_search.search("how do I", meaning=False) == []
    snip = help_search.snippet(topic("dates-holidays"), "add a holiday")
    assert "<b>" in snip and "holiday" in snip.lower()
    assert help_search.stem("dated") == help_search.stem("dates") == help_search.stem("dating")
    assert help_search.stem("parties") == "party" and help_search.stem("address") == help_search.stem("addresses")


def test_the_word_table_knows_what_words_mean():
    """The table made from EmbeddingGemma 2 puts "bill" nearer "invoice" than "holiday", and "closed" nearer
    "holiday" than "invoice"; its header names the model."""
    from minute_filler import help_meaning
    t = help_meaning.Table()
    assert t.header["model"] == "google/embeddinggemma-2" and t.dims > 0 and len(t.index) > 10000

    def sim(a, b):
        return sum(x * y for x, y in zip(t.vector(a), t.vector(b)))

    assert sim("bill", "invoice") > sim("bill", "holiday")
    assert sim("closed", "holiday") > sim("closed", "invoice")
    assert sim("lawyer", "attorney") > sim("lawyer", "weekend")
    assert t.vector("holidays") is not None and t.vector("zzqxj") is None


def test_a_typo_the_table_lacks_counts_as_the_help_word():
    """"holliday" isn't in the table: its meaning is the help's "holiday" (the keyword search's typo put right), so
    the table doesn't outvote the keywords with the question's other words alone ("add a ...")."""
    from minute_filler import help_meaning, help_search
    from minute_filler.help_topics import TOPICS
    meaning = help_meaning.load(TOPICS)
    assert meaning.table.vector("holliday") is None
    assert meaning.vector("holliday") == meaning.vector("holiday")
    for question, answer in (("add a holliday", "dates-holidays"), ("signiture on the agreement", "set-signature")):
        assert answer in [h.topic.id for h in help_search.search(question, meaning=meaning)][:3], question


def test_without_the_table_the_search_goes_by_keywords(tmp_path):
    from minute_filler import help_meaning, help_search
    from minute_filler.help_topics import TOPICS
    topics = list(TOPICS)  # (another list: load() keeps one Meaning per list of topics)
    assert help_meaning.load(topics, tmp_path / "none.bin") is None
    bad = tmp_path / "bad.bin"
    bad.write_bytes(b"YINW1\n{\"dims\": 4, \"count\": 2, \"words_bytes\": 3}\nab")
    assert help_meaning.load(list(TOPICS), bad) is None
    found = help_search.search("court holidays", topics, meaning=help_meaning.ready(topics))
    assert found[0].topic.id == "dates-holidays"


# --- the window

def test_the_help_window_searches_opens_results_and_goes_back(qt):
    from PySide6.QtCore import QEvent, Qt, QUrl
    from PySide6.QtGui import QKeyEvent
    from minute_filler.gui.help_window import FIRST, HelpWindow
    w = HelpWindow()
    assert not w.isModal() and w.current == FIRST
    w.search.setText("court holidays")
    w.timer.stop()
    w._search()
    assert w.stack.currentWidget() is w.results and w.hits
    assert w.hits[0].topic.id == "dates-holidays"
    w.eventFilter(w.search, QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.NoModifier))
    assert w.chosen == 1
    w.eventFilter(w.search, QKeyEvent(QEvent.KeyPress, Qt.Key_Up, Qt.NoModifier))
    w.eventFilter(w.search, QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
    assert w.current == "dates-holidays"
    assert w.text.extraSelections()  # (the words searched for are highlighted)
    assert "Columbus Day" in w.text.toPlainText()
    w._link(QUrl("topic:set-dates"))
    assert w.current == "set-dates"
    w._go(-1)
    assert w.current == "dates-holidays"
    w._go(-1)
    assert w.current == FIRST and not w.back.isEnabled() and w.forward.isEnabled()
    w.search.clear()
    w._search()
    assert w.stack.currentWidget() is w.tree
    assert not w.show_topic("no-such-topic") and w.current == FIRST
    w.show_topic("start-help")
    assert WEBSITE in w.text.toHtml() and "{website}" not in w.text.toHtml()
    w.deleteLater()


def test_the_help_window_says_when_nothing_is_found(qt):
    from minute_filler.gui.help_window import HelpWindow
    w = HelpWindow()
    w.search.setText("zzqxj vvkkw")
    w._search()
    assert not w.hits and "Nothing found" in w.results.toPlainText()
    w.deleteLater()


def test_f1_opens_the_topic_of_the_field_with_the_focus(window):
    from PySide6.QtGui import QShortcut
    from minute_filler.gui.help_window import FIRST, help_topic_of
    assert help_topic_of(window.rows["est_pages"].edit) == "check-pages"
    assert help_topic_of(window.rows["agreement_date"].edit) == "dates-business-days"
    assert help_topic_of(window.cards["attorneys"]) == "check-attorneys"
    window.show()
    window.activateWindow()
    window.rows["est_pages"].edit.setFocus()
    f1 = next(s for s in window.findChildren(QShortcut) if s.key().toString() == "F1")
    f1.activated.emit()
    win = window._help_window
    assert win.isVisible() and not win.isModal()
    assert win.current == (help_topic_of(window.focusWidget()) or FIRST)
    win.show_topic("keys")
    window.show_help("check-index")
    assert window._help_window is win and win.current == "check-index"  # (one window, reused)
    win.close()


def test_every_part_of_the_window_names_a_real_topic(window):
    from PySide6.QtWidgets import QWidget
    from minute_filler.help_topics import topic
    named = {str(w.property("help_topic")) for w in window.findChildren(QWidget) if w.property("help_topic")}
    assert len(named) >= 10
    assert all(topic(t) for t in named), [t for t in named if not topic(t)]


def test_settings_help_opens_the_tab_shown(qt, monkeypatch):
    from minute_filler.gui import help_window
    from minute_filler.gui.dialogs import SettingsDialog
    from minute_filler.settings import Settings
    opened = []
    monkeypatch.setattr(help_window, "open_help", lambda t="", owner=None: opened.append((t, owner)))
    d = SettingsDialog(Settings())
    d.show_tab("Dates")
    d.show_help()
    assert opened == [("set-dates", d)]
    d.show_tab("Invoice")
    d.show_help()
    assert opened[-1] == ("set-invoice", d)
    d.deleteLater()


def test_records_f1_opens_the_records_topics(window, monkeypatch):
    from minute_filler.gui import help_window
    from minute_filler.gui.records_window import RecordsWindow
    opened = []
    monkeypatch.setattr(help_window, "open_help", lambda t="", owner=None: opened.append((t, owner)))
    r = RecordsWindow(window.s, window)
    r.show_help()
    assert opened == [("rec-overview", window)]
    r.deleteLater()


def test_the_help_menu_opens_the_help_and_the_website(window, monkeypatch):
    import minute_filler.gui.main_window as mw
    assert [a.text() for a in window.menuBar().actions()] == ["&File", "&View", "&Help"]
    actions = {a.text().split("\t")[0]: a for a in help_menu(window).actions() if a.text()}
    assert list(actions)[0] == "&How to use YinItAgreementForm…"
    opened = []
    monkeypatch.setattr(mw, "open_url", opened.append)
    actions["&How to use YinItAgreementForm…"].trigger()
    assert window._help_window.isVisible()
    window._help_window.close()
    next(a for t, a in actions.items() if "website" in t).trigger()
    assert opened == [WEBSITE]


def test_the_windows_keys_include_f1(window):
    from PySide6.QtGui import QKeySequence, QShortcut
    keys = {s.key().toString() for s in window.findChildren(QShortcut)}
    for k in ("F1", "Ctrl+O", "Ctrl+N", "Ctrl+Return", "Ctrl+Shift+Return", "Ctrl+R", "Ctrl+0"):
        assert QKeySequence(k).toString() in keys, k


def test_about_links_the_website_and_credits_the_word_tables_model(qt):
    from PySide6.QtWidgets import QLabel
    from minute_filler.gui.dialogs import COMPONENTS, AboutDialog, WEBSITE_URL
    assert WEBSITE_URL == WEBSITE
    d = AboutDialog()
    assert any(WEBSITE in l.text() for l in d.findChildren(QLabel))
    assert any("EmbeddingGemma" in name and lic == "Apache-2.0" for name, lic, _ in COMPONENTS)
    d.deleteLater()
