"""Extraction tests against the fictional samples in tests/samples (a transcript's cover page, an invoice, two
e-mails), with the merge of one of them, the AI's answers checked against the text, Title Case and parts.

Real documents go in samples_internal/ (git-ignored) and are covered by test_private_samples.py.
"""

from minute_filler.extract_regex import RegexExtractor, smart_title
from minute_filler.ingest import Ingested, ingest_text
from minute_filler.merge import merge
from minute_filler.settings import Settings

from helpers import PAT as PROFILE, SAMPLES, best


def run(name, as_pdf=False, **pdf):
    """Extract from a sample; as_pdf pretends the text came from a PDF's text layer."""
    text = (SAMPLES / name).read_text()
    ing = Ingested(name.replace(".txt", ".pdf"), "pdf", text=text, **pdf) if as_pdf else ingest_text(text, name)
    return RegexExtractor(PROFILE).extract(ing)


def test_transcript_cover_page():
    """A transcript PDF's cover page gives every field, its page count, and one entry per firm (not the reporter)."""
    ex = run("transcript_cover.txt", as_pdf=True, page_count=30, first_page_no=101)
    assert best(ex, "index_no") == "712345/2021"
    assert best(ex, "court") == "Supreme"
    assert best(ex, "county") == "Queens"
    assert best(ex, "part") == "14"
    assert best(ex, "judge") == "Maria T. Alvarez"
    assert best(ex, "dates") == "6/3/2026"
    assert best(ex, "case_name") == ("Jane Roe v. X.Y. Holding Corporation and Acme Widget Metal & Glass Corp.")
    assert ex.proc_types.get("Trial", 0) >= 0.6
    assert best(ex, "est_pages") == "30"
    names = {a.name for a in ex.attorneys}  # one entry per firm, naming all its attorneys
    assert names == {"Samuel R. Advocate, Dana White", "Alex B. Counsel"}  # not the reporter
    counsel = next(a for a in ex.attorneys if a.name == "Alex B. Counsel")
    assert counsel.firm == "Counsel & Counsel"
    assert counsel.party == "Defendants"
    assert counsel.address == "500 Sample Road\nLake Town, New York 10002"


def test_invoice():
    """An invoice gives the case, and its To: line the firm that ordered, ticked."""
    ex = run("invoice.txt")
    assert best(ex, "index_no") == "712222/2024"
    assert best(ex, "part") == "53"
    assert best(ex, "judge") == "Lopez"
    assert best(ex, "dates") == "5/22/2026"
    assert best(ex, "case_name") == "Smith v. Jones"
    [a] = ex.attorneys
    assert a.firm == "Example Firm LLP" and a.email == "billing@examplefirm.com" and a.checked
    # the reporter's own e-mail on the invoice must not become an attorney
    assert all("preporter" not in x.email for x in ex.attorneys)


def test_informal_email():
    """An informal e-mail gives the case, two days, the speed and copies, and its sender's signature, ticked."""
    ex = run("email_informal.txt")
    assert best(ex, "index_no") == "812345/2023"
    assert best(ex, "part") == "19"
    assert best(ex, "judge") == "Rodriguez"
    assert best(ex, "dates") == "9/14/2026, 9/15/2026"
    assert best(ex, "delivery") == "Expedited"
    assert best(ex, "copies") == "1"
    assert "Garcia v. Metro Transit" in best(ex, "case_name")
    [a] = ex.attorneys
    assert (a.name, a.firm, a.phone, a.fax) == ("John Doe", "Doe & Roe, LLP", "(212) 555-1212", "(212) 555-1313")
    assert a.checked  # the sender is the one ordering


def test_lowercase_email():
    """A short e-mail written all in lower case still gives the index number, part, judge and caption."""
    ex = run("email_short.txt")
    assert best(ex, "index_no") == "700123/2025"
    assert best(ex, "part") == "7"
    assert best(ex, "judge") == "Lopez"
    assert best(ex, "case_name") == "Smith v. Jones"


def test_merge_defaults_and_derived():
    """Merging fills the court from the defaults and works out the speed, rate and delivery date."""
    s = Settings()
    s.profile = PROFILE
    case = merge([run("email_informal.txt")], s)
    assert case.get("court") == "Supreme" and case.fields["court"].source == "default"
    assert case.get("delivery") == "Expedite"  # the rate sheet's spelling
    assert case.get("rate") == "5.40"
    assert case.get("delivery_date")
    assert len(case.attorneys) == 1 and case.attorneys[0].checked


def test_smart_title():
    """ALL CAPS becomes Title Case, keeping initials, LLP/PLLC, small words, Mc and O'."""
    assert smart_title("X.Y. HOLDING CORPORATION and ACME CORP.") == "X.Y. Holding Corporation and Acme Corp."
    assert smart_title("SMITH JONES & BROWN PLLC") == "Smith Jones & Brown PLLC"
    assert smart_title("JOHN MCDONALD O'BRIEN") == "John McDonald O'Brien"


def test_ai_answers_are_checked_against_the_text():
    """Invented values from a small model (e.g. a county the e-mail never mentions) are dropped."""
    from minute_filler.extract_llm import OllamaExtractor
    x = OllamaExtractor(Settings())
    src = "can I get the transcript for smith v jones 10/1/2026, index 700123-2025, judge lopez"
    ex = x._to_extraction({"county": "Bronx", "court": "Family", "judge": "Lopez", "case_name": "Smith v Jones",
                           "index_number": "700123-2025", "attorneys": [
                               {"name": "Invented Person", "firm": "Nowhere LLP", "address": "", "phone": "",
                                "email": "", "party": "", "is_requester": True}]}, src)
    assert "county" not in ex.fields and "court" not in ex.fields
    assert best(ex, "judge") == "Lopez" and best(ex, "index_no") == "700123/2025"
    assert ex.attorneys == []


def test_part_letters_and_numbers():
    """A court document's 'PART MDP', 'PART 25', 'Part: TAP-A' and 'IAS PART 12' are parts; 'part of the record'
    and 'PART OF THE RECORD' are not."""
    from minute_filler.models import Extraction
    x = RegexExtractor(PROFILE)
    for text, want in [("COUNTY OF QUEENS:  CIVIL TERM:  PART MDP \n", "MDP"),
                       ("COUNTY OF QUEENS: CIVIL TERM: PART 25\n", "25"),
                       ("Part: TAP-A\n", "TAP-A"),
                       ("Judge: Lopez\nPart: 53\n", "53"),
                       ("SUPREME COURT, IAS PART 12\n", "12")]:
        ex = Extraction()
        x._part(text, text, ex)
        assert best(ex, "part") == want, text
    ex = Extraction()
    x._part("that is part of the record. PART OF THE RECORD", "", ex)
    assert "part" not in ex.fields


STACKED_CAPTION = """                                                                  386
 1   SUPREME COURT OF THE STATE OF NEW YORK
     COUNTY OF QUEENS : CIVIL TERM : PART 14
 2   ----------------------------------------X
     J.R., an infant by her mother and natural
 3   Guardian, JANE ROE, and JANE ROE, Individually,
 4                                              Index No.
                               Plaintiff,       712345/21
 5
              -against-
 6                                              JURY TRIAL
 7   SAM POE, M.D.,
 8                             Defendant.
     ----------------------------------------X
 9                             Supreme Courthouse
                               88-11 Sutphin Boulevard
10                             Jamaica, New York  11435
                               October 20, 2026
"""


def test_an_index_number_under_its_label_with_a_short_year():
    """'Index No.' on one line, the number on the next after 'Plaintiff,', and a two-digit year (712345/21): read
    as labelled (the user's transcript of 2026-10-21 got none: the label wasn't next to it, and a number without
    one needed a four-digit year). The courthouse's ZIP code on the same page is no index number."""
    ex = RegexExtractor(PROFILE).extract(Ingested("t.pdf", "pdf", text=STACKED_CAPTION))
    assert best(ex, "index_no") == "712345/2021"
    assert max(c.confidence for c in ex.fields["index_no"]) >= 0.9
    lone = RegexExtractor(PROFILE).extract(ingest_text("The minutes of 712345/21, please.", "e.txt"))
    assert best(lone, "index_no") == "712345/2021"  # (unlabelled, the year short: still read, less surely)
    for no in ("Call 555-1234/21 today.", "On 10/21/2026 at 2:30.", "Box 12345-21."):
        assert not RegexExtractor(PROFILE).extract(ingest_text(no, "e.txt")).fields.get("index_no"), no


def test_index_number_patterns_of_the_users_own():
    """Settings -> Options -> Index numbers (the user, 2026-10-21: the patterns should be the user's to change):
    a pattern of theirs finds what the app's own don't, as surely as a labelled number; one that can't be used
    (not a regular expression, no number and year groups) is left out and says why."""
    from minute_filler.extract_regex import index_pattern_problem, index_patterns
    text = "Re: Roe v. Poe, CV-012345-25/QU, the minutes of 6/3."
    assert not RegexExtractor(PROFILE).extract(ingest_text(text, "e.txt")).fields.get("index_no")
    ex = RegexExtractor(PROFILE, index_patterns_=[r"CV-(\d{6})-(\d{2})/QU"]).extract(ingest_text(text, "e.txt"))
    assert best(ex, "index_no") == "12345/2025" and ex.fields["index_no"][0].confidence == 0.95
    named = RegexExtractor(PROFILE, index_patterns_=[r"(?P<year>\d{2})/QU-(?P<number>\d{5})"])
    assert best(named.extract(ingest_text("File 25/QU-54321.", "e.txt")), "index_no") == "54321/2025"
    assert index_pattern_problem(r"CV-(\d{6})-(\d{2})") == ""
    assert index_pattern_problem(r"CV-(\d{6}").startswith("not a regular expression")
    assert index_pattern_problem(r"CV-\d{6}-(\d{2})") == "it needs two groups in parentheses: the number, then the year"
    assert len(index_patterns(["(", r"(\d+)/(\d+)", "", 5])) == 1


PATTERN = r"CV-(\d{6})-(\d{2})/QU"  # (a pattern of the user's: Civil Court's docket numbers)


def test_index_number_patterns_in_the_settings_window(qt, monkeypatch):
    """Options -> Index numbers: what is wrong with a pattern as it is typed, what they find in a line to try them
    on, a pattern that can't be used keeping the window open (it would be lost), and the good ones saved."""
    from minute_filler.gui.dialogs import SettingsDialog
    warned = []
    monkeypatch.setattr(qt.QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
    dlg = SettingsDialog(Settings.load())
    assert "The app's own patterns only" in dlg.o_index_note.text()
    dlg.o_index.setPlainText(PATTERN + "\n" + r"Docket (\d+")
    assert dlg.o_index_note.text().startswith("⚠ line 2: not a regular expression")
    dlg.accept()
    assert warned and "Line 2" in warned[0] and Settings.load().index_patterns == []
    dlg.o_index.setPlainText(PATTERN + "\n\n")
    dlg.o_index_try.setText("the minutes of CV-012345-25/QU, please")
    assert dlg.o_index_note.text() == "Finds 12345/2025"
    dlg.accept()
    assert Settings.load().index_patterns == [PATTERN]
    assert SettingsDialog(Settings.load()).o_index.toPlainText() == PATTERN
