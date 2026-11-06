"""Page numbers as read from the PDFs, and the Min-U-Script cover that isn't a page (the user, 2026-11-06).

Across real transcripts the reader never missed a printed number: what went wrong was the check after it (every
page read and rising, or the whole day shows 1-N), so a cover before pages 819-936 showed "1–119" and billed 119
pages. Now a Min-U-Script cover is taken out where a PDF is read (takes.without_cover), and the numbers are shown as
read, in the stretches they run in (takes.run_numbers); a run without numbers says its place ("place 1–20", "counted
pages 1–20"), never a bare "1–20". Records made before this count the cover in what they keep by place, so a past job
opened again moves its rows and corrected takes over (batch.settle_old_places). All names and numbers are made up."""
import json
from dataclasses import replace
from datetime import date

import pymupdf
import pytest

from minute_filler.batch import (Doc, Job, _printed_span, _run_words, billed_split_rule, counts_covers, cover_note,
                                 fill_jobs, fixes_without_cover, group, job_from_origin, job_origin, joint_origin,
                                 put_back_orders, read_docs, remerge, settle_old_places)
from minute_filler.deliver import case_snapshot, ledger_for
from minute_filler.excerpts import Day, Run, carve, case_days
from minute_filler.extract_regex import RegexExtractor
from minute_filler.ingest import Ingested, ingest_file
from minute_filler.models import SRC_PDF, SRC_USER, Attorney, Extraction, FieldState
from minute_filler.runsheet import Row, RunSheetOpts, add_takes, rows_from, title_page_texts, title_page_total
from minute_filler.takes import (PageCount, PageFacts, PageMark, count_pages, counted_words, find_takes, numbers_known,
                                 place_words, read_pages, run_numbers, scan_page, scan_pdf, without_cover)

from helpers import CAPTION_DPM, MIN_U_SCRIPT_COVER as COVER, page_numbered_transcript, pat_settings

DAY = date(2026, 6, 3)
ALEX = Attorney(name="Alex B. Counsel", firm="Counsel & Counsel", checked=True)
DANA = Attorney(name="Dana Smith", firm="Smith Law", checked=True)
A, B = ALEX.key(), DANA.key()
PR, DS = "pr", "ds"


@pytest.fixture
def s(tmp_path):
    s = pat_settings()
    s.output_dir = str(tmp_path / "out")
    s.records_dir = str(tmp_path / "records")
    s.save_math = "off"
    s.use_ai = s.open_after = False
    return s


def job_of(s, *paths) -> Job:
    """The one job these PDFs make, read as the window reads them."""
    docs, errors = read_docs([str(p) for p in paths], s)
    assert not errors
    job, = group(docs, s)
    return job


def firms(job: Job) -> Job:
    job.case.attorneys = [replace(ALEX), replace(DANA)]
    job.att_touched = True
    return job


# ------------------------------------------------------------------ the cover isn't a page

def test_a_min_u_script_cover_is_no_page_to_any_reading_of_the_pages(tmp_path, s):
    """Cover + 20 pages printed 819-838 + 4 pages of word index: 20 total pages, shown as printed. It was 21, and
    "1–21"."""
    path = page_numbered_transcript(tmp_path / "Roe.pdf", 20, first=819, cover=COVER, index_pages=4)
    job = job_of(s, path)
    doc = job.docs[0]
    c = doc.ing.count
    assert doc.ing.page_count == 25  # (the PDF's own count stays)
    assert (c.pages, c.cover, c.index_pages, c.first, c.last) == (20, 1, 4, 819, 838)
    assert [m.number for m in doc.ing.marks] == list(range(819, 839))
    assert job.transcript_pages() == job.invoice_pages() == job.own_pages() == job.your_pages() == 20
    assert job.case.get("est_pages") == "20" and job.case.fields["est_pages"].source == SRC_PDF
    assert len(doc.owners()) == 20 and doc.front_pages() == 0 and not job.ownership_problem()
    assert job.ordered_pages()[""] == 20
    rows = job.runsheet_opts(s).rows
    assert [(r.start, r.pages, r.at, r.after_cover) for r in rows] == [(819, 20, 0, True)]
    day, = case_days([job])
    assert day.numbered and day.pages == 20 and day.span(1, 20) == "819–838" and not day.falls()
    assert job.printed_pages() == list(range(819, 839))


def test_the_text_keeps_the_cover_for_the_fields_it_says(tmp_path):
    ing = ingest_file(page_numbered_transcript(tmp_path / "Roe.pdf", 5, cover=COVER))
    assert "Min-U-Script" in ing.text.split("\f")[0] and ing.first_page_no is None


def test_the_line_under_the_field_says_the_cover_was_left_out(tmp_path, s):
    job = job_of(s, page_numbered_transcript(tmp_path / "Roe.pdf", 20, first=819, cover=COVER, index_pages=4))
    assert job.pages_help()[0] == ("Transcript pages 819–838 · excludes the 4 word-index pages after them · without "
                                   "the Min-U-Script cover")
    bare = job_of(s, page_numbered_transcript(tmp_path / "Poe.pdf", 20, first=819, index_pages=4,
                                              caption="JANE ROE v. KIM PARK\nIndex No. 700111/2022\nJune 4, 2026"))
    assert "cover" not in bare.pages_help()[0]


def test_the_line_says_so_when_every_page_is_counted_too():
    """A cover before scanned pages: "every page of the PDF" alone would not be so."""
    doc = Doc(Ingested("Roe.pdf", "pdf", page_count=6, count=PageCount(5, how="pdf", cover=1)),
              Extraction(doc_kind="transcript"), path="Roe.pdf")
    assert Job(docs=[doc]).pages_help()[0] == ("5 total pages: every page of the PDF (no text to find a word index in) "
                                               "· without the Min-U-Script cover")


def test_a_cover_on_a_transcript_of_two_reporters_asks_nothing_and_bills_the_same_as_none(tmp_path, s):
    """Every reading of the pages agrees with the same transcript without its cover: the marks, the owners, the
    masks, the takes and the title pages. One that kept counting it would bill a page off without a word. It no longer
    holds the invoice to ask whose it is."""
    s.profile.initials = "P.R."
    who = [PR] * 8 + [DS] * 12
    covered = job_of(s, page_numbered_transcript(tmp_path / "a.pdf", 20, first=819, initials=who, cover=COVER,
                                                 index_pages=4))
    plain = job_of(s, page_numbered_transcript(tmp_path / "b.pdf", 20, first=819, initials=who, index_pages=4))
    c, p = covered.docs[0], plain.docs[0]
    assert c.ing.marks == p.ing.marks and c.owners() == p.owners() and c.reporters() == p.reporters()
    assert covered.billed_mask(c) == plain.billed_mask(p) and covered.day_mask() == plain.day_mask()
    assert covered.your_mask() == plain.your_mask()
    assert (covered.your_pages(), covered.invoice_pages(), covered.transcript_pages()) == (8, 8, 20)
    assert covered.reporter_pages() == plain.reporter_pages() == {PR: 8, DS: 12}
    assert covered.portion_pages() == plain.portion_pages() == 20
    assert not covered.ownership_problem() and not covered.invoice_hold() and c.front_pages() == 0
    assert title_page_total(c.ing) == title_page_total(p.ing)
    key = lambda rows: [(r.reporter, r.pages, r.start, r.at, r.numbers, r.note) for r in rows]
    assert key(covered.runsheet_opts(s).rows) == key(plain.runsheet_opts(s).rows)
    assert [r.after_cover for r in covered.runsheet_opts(s).rows] == [True, False]
    assert not any(r.after_cover for r in plain.runsheet_opts(s).rows)
    with pymupdf.open(tmp_path / "a.pdf") as doc:
        assert len(scan_pdf(doc)) == 20


FACT = PageFacts(PageMark())
AFTER = PageFacts(PageMark(819, PR), lined=True)


@pytest.mark.parametrize("first, after, dropped", [
    (replace(FACT, branded=True), AFTER, True),
    (FACT, AFTER, False),  # (a plain typed cover)
    (replace(FACT, branded=True, mark=PageMark(number=1)), AFTER, False),  # (a page with its number)
    (replace(FACT, branded=True, mark=PageMark(initials=PR)), AFTER, False),  # (signed)
    (replace(FACT, branded=True, lined=True), AFTER, False),  # (a condensed transcript's first page)
    (replace(FACT, branded=True), replace(AFTER, index=True, lined=False), False),  # (an index left first counts whole)
    (replace(FACT, branded=True), PageFacts(PageMark()), True),  # (the page after it unnumbered: it is still a cover)
])
def test_what_makes_a_cover(first, after, dropped):
    facts, gone = without_cover([first, after])
    assert gone == dropped and facts == ([after] if dropped else [first, after])


def test_a_pdf_of_one_page_keeps_it():
    only = replace(FACT, branded=True)
    assert without_cover([only]) == ([only], 0) and without_cover([]) == ([], 0)


def test_a_plain_typed_cover_still_counts_and_still_asks_whose(tmp_path, s):
    s.profile.initials = "P.R."
    path = page_numbered_transcript(tmp_path / "Roe.pdf", 20, first=819, initials=[PR] * 8 + [DS] * 12,
                                    cover="JANE ROE v. SAM POE\nIndex No. 712345/2021\nJune 3, 2026\nTranscript")
    job = job_of(s, path)
    c = job.docs[0].ing.count
    assert (c.pages, c.cover) == (21, 0) and job.transcript_pages() == 21
    assert "the first page has no reporter's initials" in job.ownership_problem()
    assert "cover" not in job.pages_help()[0]
    job.front_owner[job.docs[0].key()] = PR
    day, = case_days([job])
    assert day.pages == 21 and day.numbered and day.span(1, 21) == "819–838"  # (shown as read, its places 1-21)


def test_a_condensed_transcript_says_min_u_script_on_every_page_and_keeps_them(tmp_path):
    doc = pymupdf.open()
    lines = "\n".join(f"{n:2}  A.  Yes." for n in range(1, 26))
    for _ in range(4):
        doc.new_page().insert_text((60, 80), f"{lines}\nMin-U-Script", fontsize=9)
    doc.save(tmp_path / "Roe condensed.pdf")
    doc.close()
    ing = ingest_file(tmp_path / "Roe condensed.pdf")
    assert ing.count.cover == 0 and ing.count.pages == 4


def test_a_scanned_first_page_is_no_cover(tmp_path):
    """A picture has no text to say so (read_pages asks the text layer only, not OCR)."""
    doc = pymupdf.open()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 40), False)
    pix.clear_with(200)
    doc.new_page().insert_image(pymupdf.Rect(72, 72, 300, 300), pixmap=pix)
    doc.new_page().insert_text((300, 40), "819", fontsize=10)
    assert without_cover(read_pages(doc))[1] == 0
    doc.close()


def test_a_pdf_of_only_a_cover_keeps_its_page(tmp_path):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 200), COVER, fontsize=12)
    doc.save(tmp_path / "cover.pdf")
    doc.close()
    assert ingest_file(tmp_path / "cover.pdf").count.cover == 0


def test_a_cover_before_nothing_but_a_word_index_stays(tmp_path):
    """Taken off, the index would be the PDF's first page, which the first reading never stops at: all of it counted."""
    ing = ingest_file(page_numbered_transcript(tmp_path / "Roe.pdf", 0, cover=COVER, index_pages=3))
    assert ing.count.cover == 0 and ing.count.pages == 1 and ing.count.index_pages == 3


def test_a_cover_then_an_unsigned_title_page_still_asks_about_that_page(tmp_path, s):
    s.profile.initials = "P.R."
    job = job_of(s, page_numbered_transcript(tmp_path / "Roe.pdf", 20, first=819, cover=COVER,
                                             initials=[""] + [PR] * 7 + [DS] * 12))
    assert job.docs[0].ing.count.cover == 1 and job.docs[0].front_pages() == 1
    assert "the first page has no reporter's initials" in job.ownership_problem()


# ------------------------------------------------------------------ the title pages, without the cover
TITLE = "JANE ROE v. SAM POE\nIndex No. 712345/2021\nJune 3, 2026"
COUNSEL = "APPEARANCES\nALEX B. COUNSEL, ESQ.\nAttorneys for the Plaintiff\nDANA SMITH\nSenior Court Reporter"
TALK = "THE COURT:  Good morning."


def ingested(*pages: str, cover: int = 1, marks=()) -> Ingested:
    return Ingested("Roe.pdf", "pdf", text="\n\f\n".join(pages), page_count=len(marks) + cover, marks=list(marks),
                    count=PageCount(len(marks), cover=cover))


def test_the_title_pages_are_counted_without_the_cover():
    """The count with the cover, less one, is wrong where the page after the cover says nothing of counsel: with the
    cover 1, without it 2 (the title, then the appearances), and the first count would leave none."""
    ing = ingested(COVER, TITLE, COUNSEL)
    assert title_page_total(replace(ing, count=PageCount(0))) == 1  # (read with the cover among them)
    assert title_page_total(ing) == 2 and len(title_page_texts(ing)) == 2
    # and when the cover's count, less one, happens to be right
    assert title_page_total(replace(ingested(COVER, COUNSEL, TALK), count=PageCount(0))) == 2
    assert title_page_total(ingested(COVER, COUNSEL, TALK)) == 1


def test_rows_from_goes_by_the_title_pages_without_the_cover(s):
    marks = [PageMark(819, PR, "Title head"), PageMark(820, PR, "Appearances head"), PageMark(821, PR, "Proceedings")]
    row, = rows_from(ingested(COVER, TITLE, COUNSEL, marks=marks), DAY, s)
    assert row.heads == "Proceedings" and row.reporter == "Pat"
    # the reporter named on the second title page is found (Doc.title_names reads the same pages)
    doc = Doc(ingested(COVER, TITLE, COUNSEL, marks=marks), Extraction(doc_kind="transcript"))
    assert doc.title_names() == ["DANA SMITH"]


# ------------------------------------------------------------------ a page printing 0

def page_saying(*at: tuple) -> PageMark:
    """The mark of a page with these texts at (x, y, text)."""
    doc = pymupdf.open()
    page = doc.new_page()
    for x, y, text in at:
        page.insert_text((x, y), text, fontsize=10)
    mark = scan_page(page)
    doc.close()
    return mark


@pytest.mark.parametrize("head, number", [
    ("Proceedings 151", 151), ("DIRECT - SAM POE 151", 151), ("CROSS - MAYA 7", 7),  # (no month: "May" is)
    ("Proceedings", None), ("Proceedings 0", None),
    ("VOLUME 3", None), ("Vol. 3", None), ("PROCEEDINGS - DAY 2", None), ("Part 14", None), ("Session 2", None),
    ("No. 5", None), ("Index 7", None), ("Exhibit 9", None), ("JUNE 3, 2026", None), ("June 3", None),
])
def test_a_page_printing_0_has_its_number_in_its_head_if_anywhere(head, number):
    """Never a line number ("1" in the top margin, which filtering out the 0 would have taken), nor a number that is
    the head's own."""
    mark = page_saying((300, 40, "0"), (60, 28, head), (40, 80, "1"), (80, 300, "A."), (40, 720, "25"))
    assert mark.number == number


def test_a_page_printing_another_number_is_read_as_before():
    assert page_saying((300, 40, "312"), (60, 28, "Proceedings 151"), (40, 80, "1")).number == 312


def test_a_stretch_printing_0_reads_its_numbers_and_lists_its_head_once(tmp_path, s):
    path = page_numbered_transcript(tmp_path / "Roe.pdf", 12, first=151, zero_at=tuple(range(0, 6)), cover=COVER)
    ing = ingest_file(path)
    assert [m.number for m in ing.marks] == list(range(151, 163)) and ing.first_page_no is None
    assert (ing.count.first, ing.count.last, ing.count.cover) == (151, 162, 1)
    take, = find_takes(ing.marks, title_count=0)
    assert take.heads == ["Proceedings"]  # (one head, not one a page: its number is struck off it)
    assert 0 not in take.numbers and take.start == 151


def test_a_0_on_the_first_page_is_no_first_page_number(tmp_path):
    ing = ingest_file(page_numbered_transcript(tmp_path / "Roe.pdf", 6, first=151, zero_at=(0,)))
    assert ing.first_page_no is None and ing.marks[0].number == 151


# ------------------------------------------------------------------ numbers as read, in stretches

@pytest.mark.parametrize("printed, pages, known", [
    ([819, 820, 821], None, True),
    ([819], None, True),
    ([1, 1, 1], None, False),  # (a line number taken for the page's)
    ([154, None, None, None, None, None], None, False),  # (the one number OCR found)
    ([819, None, 821], None, True),
    ([819, None], None, True),
    ([164, 164], None, True),  # (one number, twice: where a reporter changes)
    ([819, 820], 3, False),  # (the wrong length)
    ([], None, False),
    ([None, None], None, False),
])
def test_numbers_known(printed, pages, known):
    assert numbers_known(printed, pages) is known


@pytest.mark.parametrize("printed, text, falls, pp", [
    ([], "", False, ""),
    ([None, None], "", False, ""),
    ([154], "154", False, "p. 154"),
    ([154, None, None], "154", False, "p. 154"),
    ([819, 820, 821], "819–821", False, "pp. 819–821"),
    ([164, 164], "164", False, "p. 164"),
    ([130, 131, 131, 132], "130–132", False, "pp. 130–132"),  # (a number printed twice)
    ([195, 197], "195–197", False, "pp. 195–197"),  # (a jump of 2: a page left out where a reporter changes)
    ([1, 6], "1–6", False, "pp. 1–6"),  # (a jump of SKIP_OK, 5)
    ([1, 7], "1, 7", False, "pp. 1, 7"),  # (over it)
    ([10, 11, 35, 36], "10–11, 35–36", False, "pp. 10–11, 35–36"),  # (a jump of 24 doesn't flag a fall)
    ([100, None, None, None, None, None, None, None, None, None, 110], "100–110", False, "pp. 100–110"),  # (read around)
    ([100, None, 120], "100, 120", False, "pp. 100, 120"),
    ([1, 2, 3, 10, 11, 12, 11, 12, 1, 2], "1–3, 10–12, 11–12, 1–2", True, "pp. 1–3, 10–12, 11–12, 1–2"),
])
def test_run_numbers(printed, text, falls, pp):
    got = run_numbers(printed)
    assert (got.text, got.falls, got.pp()) == (text, falls, pp)


def test_run_numbers_of_some_of_the_pages():
    assert run_numbers([1, 2, 3, 4, 5], 2, 4).text == "2–4"
    assert run_numbers([1, 2, 3], 2).text == "2–3"


def test_the_words_for_a_place():
    assert (place_words(1, 20), place_words(7, 7)) == ("place 1–20", "place 7")
    assert (counted_words(1, 20), counted_words(7, 7)) == ("counted pages 1–20", "counted page 7")


def test_the_printed_span_of_the_count_is_read_from_its_pages_not_worked_out():
    """The word index found from the end gives the count, and the page before it doesn't follow the numbers: "Transcript
    pages 100–110" would be a number printed nowhere."""
    pages = [PageFacts(PageMark(100 + i, PR), lined=True) for i in range(10)]
    pages.append(PageFacts(PageMark(555, PR), lined=True))
    pages += [PageFacts(PageMark(111 + i), index=True) for i in range(4)]
    c = count_pages(pages)
    assert c.pages == 11 and (c.first, c.last) == (None, None)
    c = count_pages(pages[:10] + [PageFacts(PageMark(110, PR), lined=True)] + pages[11:])
    assert c.pages == 11 and (c.first, c.last) == (100, 110)


# ------------------------------------------------------------------ the Page numbers cell, and runs typed in it
TWICE = (list(range(130, 165)) + list(range(164, 196)) + list(range(197, 236)) + list(range(235, 255)) + [256])
FALLS = (list(range(1, 40)) + list(range(10, 30)) + list(range(60, 98)) + list(range(10, 12)) + list(range(100, 112)))


def day_of(printed, read=(), pages=None) -> Day:
    return Day(None, "6/3/2026", len(printed) if pages is None else pages, list(printed), True, list(read))


def test_a_number_printed_twice_where_a_reporter_changes():
    """It showed 1–127 for 130–164, 164–195, 197–235, 235–254, 256."""
    d = day_of(TWICE)
    assert len(TWICE) == 127 and d.numbered and not d.falls() and d.span(1, 127) == "130–256"
    assert d.parse("164") == (35, 36)  # (both pages)
    assert d.parse("130-164") == (1, 36)  # (ends on the second)
    with pytest.raises(ValueError, match="no page of 6/3/2026 has the printed page number 196"):
        d.parse("196")
    assert d.parse("150-196") == (21, 67)
    with pytest.raises(ValueError, match="printed page numbers are 130–256"):
        d.parse("100-140")


def test_a_day_whose_numbers_fall_takes_a_run_only_where_it_can_say_which_pages():
    d = day_of(FALLS)
    assert d.numbered and d.falls() and d.span(1, d.pages) == "1–39, 10–29, 60–97, 10–11, 100–111"
    assert d.span(39, 40) == "39, 10"  # (a run over the place they fall shows both, as read)
    with pytest.raises(ValueError, match="more than one stretch.*place 15-15"):
        d.parse("15")  # (on two pages: the first found would bill the wrong one)
    with pytest.raises(ValueError, match="more than one stretch.*place 35-39"):
        d.parse("35-65")  # (35-39 before they start again, 60-65 after)
    with pytest.raises(ValueError, match="more than one stretch"):
        d.parse("5-12")  # (10-12 are on the next stretch too)
    with pytest.raises(ValueError, match="not all on one stretch.*place 95-97"):
        d.parse("95-99")  # (97 is that stretch's last)
    with pytest.raises(ValueError, match="no page of 6/3/2026 has a printed page number in 40–50"):
        d.parse("40-50")
    assert d.parse("60-70") == (60, 70)
    assert d.parse("35") == (35, 35)
    assert d.parse("100-105") == (100, 105)
    assert d.parse("place 40-44") == (40, 44) and d.parse("PLACE 40") == (40, 40)
    with pytest.raises(ValueError, match="place 1 to place 111"):
        d.parse("place 200")


@pytest.mark.parametrize("text", ["5-24", "10"])
def test_the_tooltip_offers_a_run_the_day_takes(text):
    """Twice the same numbers: the first 20 pages as shown are on two stretches, so the example is by place."""
    d = day_of(list(range(5, 26)) * 2)
    with pytest.raises(ValueError):
        d.parse(text)
    assert d.example() == "place 1–20" and d.parse(d.example()) == (1, 20)


def test_a_page_whose_number_wasnt_read_goes_by_its_place():
    d = day_of([819, None, 821])
    assert d.numbered and d.span(1, 3) == "819–821" and d.span(2, 2) == "place 2"
    with pytest.raises(ValueError, match="printed page number 820.*place 2"):
        d.parse("820")
    assert d.parse("place 2") == (2, 2) and d.parse("819-821") == (1, 3)


def test_a_day_s_numbers_are_as_read_not_counted_on(tmp_path, s):
    """A page whose number wasn't read was given the number after the page before's, which it may not print."""
    job = firms(job_of(s, page_numbered_transcript(tmp_path / "Roe.pdf", 20, first=819)))
    marks = job.docs[0].ing.marks
    marks[5] = replace(marks[5], number=None)
    printed = job.printed_pages()
    assert printed[4:7] == [823, None, 825] and printed == job.page_numbers()
    day, = case_days([job])
    assert day.numbered and day.span(1, 20) == "819–838" and day.span(6, 6) == "place 6"
    assert _run_words(printed, 6, 6) == "counted page 6" and _run_words(printed, 5, 7) == "pp. 823–825"
    job.case.fields["est_pages"] = FieldState("40", SRC_USER, 1.0, [])
    assert job.printed_pages() == []  # (typed in: nothing ties a place in that number to a page read)
    assert case_days([job])[0].read == job.page_numbers()


def test_a_scan_with_one_number_read_shows_its_place():
    printed = [154] + [None] * 5
    d = day_of(printed)
    assert not d.numbered and d.span(1, 6) == "place 1–6" and d.parse("2-3") == (2, 3)
    with pytest.raises(ValueError, match="place 1 to place 6"):
        d.parse("154")
    assert _run_words(printed, 1, 6) == "counted pages 1–6" and _run_words(printed, 1, 1) == "counted page 1"


def test_one_number_on_every_page_is_not_known():
    d = day_of([1, 1, 1])
    assert not d.numbered and d.span(1, 3) == "place 1–3"
    assert _printed_span([1, 1, 1], 1, 3) == "" and _run_words([1, 1, 1], 1, 3) == "counted pages 1–3"


def test_a_run_with_too_few_numbers_of_its_own_shows_its_place():
    d = day_of([819, 820, 821, None, None, None])
    assert d.numbered and d.span(1, 3) == "819–821" and d.span(3, 6) == "place 3–6" and d.span(4, 6) == "place 4–6"
    assert _run_words(d.printed, 4, 6) == "counted pages 4–6"


def test_a_typed_day_shows_the_numbers_read_for_its_whole_run_only():
    """A number typed is the user's count, not a choice of pages: nothing ties a place in it to a page read."""
    d = day_of([], read=range(236, 329), pages=40)
    assert not d.numbered and d.span(1, 40) == "236–328" and d.span(1, 20) == "place 1–20"
    assert d.parse("1-20") == (1, 20) and d.example() == "place 1–20"
    with pytest.raises(ValueError, match="place 1 to place 40"):
        d.parse("236-328")


def test_a_run_out_of_its_day_says_so_by_place():
    d = day_of(range(358, 458))
    runs = carve([Run(d, 1, d.pages, ["a"])], 0, 20, 40)
    with pytest.raises(ValueError, match="6/3/2026 goes from place 1 to place 100"):
        carve(runs, 1, 90, 120)


# ------------------------------------------------------------------ what the invoice and the forms say
def excerpt_job(tmp_path, s, **k) -> Job:
    job = firms(job_of(s, page_numbered_transcript(tmp_path / "Roe.pdf", 20, first=819, cover=COVER, **k)))
    job.portions = [(10, [A]), (20, [A, B])]
    return job


def test_an_invoice_names_the_pages_as_they_are_printed(tmp_path, s):
    job = excerpt_job(tmp_path, s)
    assert [p.span for p in job.invoice_orders()[0].portions] == ["pp. 819–828", "pp. 829–838"]
    job.set_speed(B, "Daily", row=1)
    job.set_speed(A, "Daily", row=0)
    job.set_speed(A, "Regular", row=1)
    day = job.case.get("dates")
    assert job.ordered_speeds()[A] == [("Daily", f"{day} pp. 819–828"), ("Regular", f"{day} pp. 829–838")]
    assert [where for where, *_ in job.runs_ordered()] == [f"{day} pp. 819–828", f"{day} pp. 829–838"]
    fill_jobs([job], s, outputs=["invoice"])
    got = {i.bill_to: i for i in ledger_for(s).invoices()}
    assert got["Dana Smith"].excerpt == f"{day} pp. 829–838"
    # (the bill itself: the cover is on nobody's invoice)
    assert {k: i.pages for k, i in got.items()} == {"Alex B. Counsel": 20, "Dana Smith": 10}
    assert {i.transcript_pages for i in got.values()} == {20}


def test_a_day_without_numbers_says_counted_pages_on_each(tmp_path, s):
    job = firms(job_of(s, page_numbered_transcript(tmp_path / "Roe.pdf", 20, numbered=False)))
    job.portions = [(10, [A]), (20, [A, B])]
    job.set_speed(A, "Daily", row=0)
    job.set_speed(A, "Regular", row=1)
    day = job.case.get("dates")
    assert [p.span for p in job.invoice_orders()[0].portions] == ["counted pages 1–10", "counted pages 11–20"]
    assert job.ordered_speeds()[A] == [("Daily", f"{day} counted pages 1–10"), ("Regular", f"{day} counted pages 11–20")]
    assert [where for where, *_ in job.runs_ordered()] == [f"{day} counted pages 1–10", f"{day} counted pages 11–20"]
    assert job.order_lines()[1].printed == [""]
    fill_jobs([job], s, outputs=["invoice"])
    got = {i.bill_to: i for i in ledger_for(s).invoices()}
    assert got["Dana Smith"].excerpt == f"{day} counted pages 11–20"


def test_the_agreement_names_the_pages_at_each_speed(tmp_path, s):
    from minute_filler.fill import agreement_case, build_values
    job = excerpt_job(tmp_path, s)
    job.set_speed(A, "Daily", row=0)
    job.set_speed(A, "Regular", row=1)
    firm = job.case.attorneys[0]
    case = agreement_case(job.case, firm, job.ordered_pages(), job.ordered_speeds(), s)
    day = job.case.get("dates")
    assert build_values(case, firm, s)["speeds_note"] == (f"Daily $6.50 a page: {day} pp. 819–828; "
                                                          f"Regular $4.30 a page: {day} pp. 829–838")


# ------------------------------------------------------------------ the Who transcribed what card

def test_the_card_shows_each_take_s_numbers_as_read():
    from minute_filler.gui.main_window import take_cells
    cell = lambda numbers, **k: take_cells(Row(DAY, "Pat", len(numbers), numbers[0], numbers=numbers, **k))[2]
    assert cell([819, 820, 821]) == "pp. 819–821"
    assert cell([154] + [None] * 5) == "p. 154"
    assert cell([1, 1, 1]) == "p. 1"  # (no "pp. 1–1")
    assert cell([38, 39, 10, 11]) == "pp. 38–39, 10–11"
    assert cell([130, 131, 131, 133]) == "pp. 130–133"  # (not the count's 130-133 by chance: as read)
    assert take_cells(Row(DAY, "Pat", 3, None, numbers=[None] * 3))[2] == ""


def test_a_scan_s_one_row_shows_only_the_number_on_its_first_page():
    ing = Ingested("Roe.pdf", "pdf", text="154\nx", page_count=6, first_page_no=154, count=PageCount(6, how="pdf"))
    from minute_filler.gui.main_window import take_cells
    row, = rows_from(ing, DAY, pat_settings())
    assert take_cells(row)[2] == "p. 154"


def test_a_take_starts_on_the_first_number_read_in_it():
    takes = find_takes([PageMark(None, PR), PageMark(820, PR), PageMark(None, DS), PageMark(None, DS), PageMark(823, DS)],
                       title_count=0)
    assert [(t.start, t.numbers, t.at) for t in takes] == [(820, [None, 820], 0), (823, [None, None, 823], 2)]


# ------------------------------------------------------------------ the note on a count

def extraction_note(**k) -> str:
    ing = Ingested("Roe transcript.pdf", "pdf", text=CAPTION_DPM, page_count=30, **k)
    return RegexExtractor(pat_settings().profile).extract(ing).fields["est_pages"][0].note


def test_a_short_transcript_with_a_cover_still_finds_its_caption(tmp_path):
    """The text keeps the cover, and the count doesn't: the caption was looked for in as many of the text's pages as
    the count has, and with a cover those stopped short of the title page."""
    path = page_numbered_transcript(tmp_path / "Roe.pdf", 1, first=819, cover="In The Matter Of:\nMin-U-Script®",
                                    index_pages=3, heading="")  # (no heading on the index to find it in instead)
    ing = ingest_file(path)
    assert (ing.count.pages, ing.count.cover, ing.count.index_pages) == (1, 1, 3)
    ex = RegexExtractor(pat_settings().profile).extract(ing)
    assert any("Roe" in c.value and "Poe" in c.value for c in ex.fields.get("case_name", []))


def test_the_note_on_the_count_names_only_numbers_read():
    note = extraction_note(count=PageCount(30, first=819, last=848))
    assert note == "transcript pages 819-848"
    # the numbers don't run on to its last page: it is not worked out from the count
    assert extraction_note(first_page_no=819, count=PageCount(30)) == "starts at page 819"
    assert extraction_note(first_page_no=819) == "starts at page 819"
    assert extraction_note(count=PageCount(26, index_pages=4)) == ("26 total pages, not counting 4 page(s) after the "
                                                                   "transcript (word index)")


# ------------------------------------------------------------------ old records: moving over

def covered_doc(pages: int, path: str = "a.pdf", cover: int = 1, first: int = 819, who=PR) -> Doc:
    """A transcript as read now: `pages` pages after its cover, numbered from `first`."""
    marks = [PageMark(first + i, who) for i in range(pages)]
    return Doc(Ingested(path, "pdf", page_count=pages + cover, marks=marks, count=PageCount(pages, cover=cover)),
               Extraction(doc_kind="transcript"), path=path)


def old_job(rows, *docs, typed=None) -> Job:
    job = Job(docs=list(docs) or [covered_doc(118)], old_places=True, portions=rows)
    job.case.attorneys = [replace(ALEX), replace(DANA)]
    if typed is not None:
        job.case.fields["est_pages"] = FieldState(typed, SRC_USER, 1.0, [])
    return job


@pytest.mark.parametrize("rows, want", [
    ([(20, [A]), (119, [A, B])], [(19, [A]), (118, [A, B])]),
    ([(1, [A]), (119, [A, B])], [(118, [A, B])]),  # (a row of the cover alone goes)
    ([(1, [A]), (119, [B])], [(118, [B])]),  # (and A, who ordered only that, orders nothing)
    ([(119, [A, B])], [(118, [A, B])]),
    ([(20, [A], {A: "Daily"}), (119, [B])], [(19, [A], {A: "Daily"}), (118, [B])]),  # (a run's own speed stays)
])
def test_rows_lose_the_cover_at_or_before_them(rows, want):
    job = old_job(rows)
    settle_old_places(job)
    assert job.portions == want and not job.old_places


def test_the_rows_moved_show_the_same_printed_pages():
    """Old place 20 was the page printed 837 (the cover was place 1, 819 place 2): so is new place 19."""
    job = old_job([(20, [A]), (119, [A, B])])
    settle_old_places(job)
    printed = job.printed_pages()
    assert _printed_span(printed, 1, 19) == "pp. 819–837" and _printed_span(printed, 20, 118) == "pp. 838–936"
    assert not job.portions_problem() and job.portions_fit_pages()


def test_two_volumes_with_covers():
    """59 pages + cover, then 59 + cover: place 61 was the second cover, so a run of it alone goes."""
    job = old_job([(60, [A]), (61, [B]), (120, [A, B])], covered_doc(59, "a.pdf"), covered_doc(59, "b.pdf", first=1))
    settle_old_places(job)
    assert job.portions == [(59, [A]), (118, [A, B])]


def test_a_cover_on_the_second_volume_only():
    job = old_job([(10, [A]), (60, [A, B]), (121, [B])], covered_doc(60, "a.pdf", cover=0), covered_doc(60, "b.pdf"))
    settle_old_places(job)
    assert job.portions == [(10, [A]), (60, [A, B]), (120, [B])]


def test_rows_that_didnt_fit_are_moved_all_the_same_and_stay_held():
    """Checked for fitting first, rows ending one page short would start fitting by accident, and bill wrong."""
    job = old_job([(20, [A]), (118, [A, B])])
    settle_old_places(job)
    assert job.portions == [(19, [A]), (117, [A, B])] and job.portions_problem()


def test_without_a_cover_nothing_moves():
    job = old_job([(20, [A]), (118, [A, B])], covered_doc(118, cover=0))
    settle_old_places(job)
    assert job.portions == [(20, [A]), (118, [A, B])] and not job.old_places


def test_only_once():
    job = old_job([(20, [A]), (119, [A, B])])
    settle_old_places(job)
    settle_old_places(job)
    assert job.portions == [(19, [A]), (118, [A, B])]


def test_not_until_its_transcripts_are_here():
    job = old_job([(20, [A]), (119, [A, B])], Doc(Ingested("e.txt", "email"), Extraction(doc_kind="email")))
    settle_old_places(job)
    assert job.portions == [(20, [A]), (119, [A, B])] and job.old_places
    job.docs.append(covered_doc(118))  # (the transcript dropped, or a read that ended late)
    settle_old_places(job)
    assert job.portions == [(19, [A]), (118, [A, B])] and not job.old_places


def test_a_number_really_typed_keeps_its_rows():
    job = old_job([(10, [A]), (40, [A, B])], typed="40")
    settle_old_places(job)
    assert job.portions == [(10, [A]), (40, [A, B])] and job.case.get("est_pages") == "40"
    assert job.pages_typed() and job.invoice_pages() == 40


def test_the_new_count_typed_keeps_its_rows_and_becomes_the_count(s):
    """118 typed on an old count of 119 was the user's number, its rows in it; that number is the count now."""
    job = old_job([(50, [A]), (118, [A, B])], typed="118")
    remerge(job, s)
    assert job.portions == [(50, [A]), (118, [A, B])]
    assert job.case.fields["est_pages"].source == SRC_PDF and job.case.get("est_pages") == "118"
    assert not job.pages_typed()


def test_the_old_count_kept_as_typed_goes_back_to_the_count(s):
    """A record whose document had moved keeps the count as typed (MainWindow.open_past_job). As a typed number it
    would bill 119, the cover among them."""
    job = old_job([(20, [A]), (119, [A, B])], typed="119")
    remerge(job, s)
    assert job.portions == [(19, [A]), (118, [A, B])]
    assert job.case.fields["est_pages"].source == SRC_PDF and job.case.get("est_pages") == "118"
    assert not job.pages_typed() and job.invoice_pages() == 118


def test_the_old_count_with_no_rows_goes_back_to_the_count_too(s):
    job = old_job(None, typed="119")
    remerge(job, s)
    assert job.portions is None and job.case.get("est_pages") == "118" and not job.pages_typed()


def test_a_job_merging_rows_still_in_old_places_keeps_them_to_move(tmp_path, s):
    """A job opened again, its transcript still to come, joined by a document that links it with another."""
    from minute_filler.batch import ident, make_doc
    a = job_of(s, page_numbered_transcript(tmp_path / "a.pdf", 5, cover=COVER))
    other = Job(portions=[(2, [A]), (6, [A, B])], old_places=True)
    other.case.set("index_no", a.case.get("index_no"))
    other.case.set("dates", a.case.get("dates"))
    fresh = make_doc(a.docs[0].ing, a.docs[0].regex, s, path="b.pdf")
    empty = Job()
    empty.case.set("index_no", a.case.get("index_no"))
    empty.case.set("dates", a.case.get("dates"))
    jobs = group([fresh], s, [empty, other])
    job, = jobs
    assert ident(job.case).index and job.portions == [(1, [A]), (5, [A, B])] and not job.old_places


@pytest.mark.parametrize("fixes, want", [({5: DS}, {4: DS}), ({0: DS}, {}), ({1: DS, 2: PR}, {0: DS, 1: PR}), ({}, {})])
def test_corrected_takes_lose_the_cover(fixes, want):
    assert fixes_without_cover(fixes, 1) == want
    assert fixes_without_cover(fixes, 0) == fixes  # (a marked record, or no cover: as they are)


def test_a_new_record_says_its_places_are_without_the_cover(tmp_path, s):
    job = firms(job_of(s, page_numbered_transcript(tmp_path / "a.pdf", 5, cover=COVER)))
    assert job_origin(job)["job"]["cover_out"] is True and not counts_covers(job_origin(job))
    joint = joint_origin([job], split_rule="")
    assert joint["cover_out"] is True and not counts_covers(joint)
    job.old_places = True  # (a job still to be moved: its rows still count the cover)
    assert "cover_out" not in job_origin(job)["job"] and counts_covers(job_origin(job))
    assert counts_covers({}) and counts_covers({"job": {"parties": 2}}) and counts_covers({"job": "?"})


def test_a_record_without_a_cover_is_as_it_always_was(tmp_path, s):
    """Earlier records are compared by their text (billed_split_rule): nothing is added where nothing changed."""
    job = firms(job_of(s, page_numbered_transcript(tmp_path / "a.pdf", 5)))
    assert "cover_out" not in job_origin(job)["job"] and "cover_out" not in joint_origin([job])


def test_job_from_origin_marks_old_places_by_the_record():
    old = {"sources": ["a.pdf"], "job": {"portions": [[20, [A]], [119, [A, B]]]}}
    assert job_from_origin(old, pat_settings()).old_places is True
    new = {"sources": ["a.pdf"], "job": {"portions": [[19, [A]], [118, [A, B]]], "cover_out": True}}
    assert job_from_origin(new, pat_settings()).old_places is False


def test_a_marked_record_opened_again_isnt_moved(tmp_path, s):
    job = firms(job_of(s, page_numbered_transcript(tmp_path / "a.pdf", 20, first=819, cover=COVER)))
    job.portions = [(10, [A]), (20, [A, B])]
    again = job_from_origin(json.loads(json.dumps({**job_origin(job), "case": case_snapshot(job.case)})), s)
    again.docs = job.docs
    remerge(again, s)
    assert again.portions == [(10, [A]), (20, [A, B])] and not again.portions_problem()


def test_the_rule_a_job_was_billed_by_is_still_found_with_the_mark_in_its_records(tmp_path, s):
    """Its other files' record is the same as its invoice's but for the rule: the mark is in both, and the record
    of the file made before the invoice still finds the invoice's (billed_split_rule)."""
    job = firms(job_of(s, page_numbered_transcript(tmp_path / "a.pdf", 20, first=819, cover=COVER)))
    job.case.set("index_no", "712345/2021")
    fill_jobs([job], s, outputs=["agreement", "invoice"])
    lg = ledger_for(s)
    kinds = {a.kind: a for a in lg.activity()}
    assert '"cover_out": true' in kinds["agreement"].origin and '"cover_out": true' in kinds["invoice"].origin
    assert job.split_rule and billed_split_rule(kinds["agreement"].origin, lg) == job.split_rule
    assert billed_split_rule(kinds["invoice"].origin, lg) == job.split_rule


def test_a_trial_s_rows_are_moved_as_they_come_back(tmp_path, s):
    """Trials never pass through job_from_origin: put_back_orders has the rows of each day."""
    paths = [page_numbered_transcript(tmp_path / "a.pdf", 20, first=819, cover=COVER),
             page_numbered_transcript(tmp_path / "b.pdf", 20, first=839, cover=COVER, caption=TITLE.replace("3", "4"))]
    docs, errors = read_docs([str(p) for p in paths], s)
    assert not errors
    jobs = group(docs, s)
    assert len(jobs) == 2
    first = next(j for j in jobs if j.docs[0].ing.name == "a.pdf")
    for j in jobs:
        j.case.attorneys = [replace(ALEX), replace(DANA)]
    origin = json.loads(json.dumps(joint_origin(jobs)))
    assert not counts_covers(origin)
    row = next(r for r in origin["orders"] if r["dates"] == first.case.get("dates"))

    # a marked record: as they are
    row["portions"] = [[10, [A]], [20, [A, B]]]
    put_back_orders([first], origin, s)
    assert first.portions == [(10, [A]), (20, [A, B])]

    # an older record: the rows lose the cover, and the day's invoice isn't held for it
    del origin["cover_out"]
    row["portions"] = [[11, [A]], [21, [A, B]]]
    put_back_orders([first], origin, s)
    assert first.portions == [(10, [A]), (20, [A, B])] and not first.old_places and not first.portions_problem()


def test_what_a_job_opened_again_says_when_its_count_changed(tmp_path, s):
    doc = covered_doc(118)
    assert cover_note([doc]) == ("A Min-U-Script cover no longer counts as a page: 118 total pages now, 119 when this "
                                 "job was made. What was made then keeps what it says.")
    assert cover_note([covered_doc(118, cover=0)]) == ""
    letter = covered_doc(3)
    letter.regex = Extraction(doc_kind="text")  # (a PDF that isn't the transcript: its first page was never billed)
    assert cover_note([letter]) == ""


# ------------------------------------------------------------------ the window, an old record opened again
def wait(win, until, seconds=20):
    import time

    from PySide6.QtWidgets import QApplication
    end = time.time() + seconds
    while time.time() < end:
        QApplication.processEvents()
        if not win.runner._live and until():
            return
        time.sleep(0.01)
    raise AssertionError("timed out")


@pytest.fixture
def window(tmp_path, monkeypatch, make_window, qt, s):
    monkeypatch.setattr(qt.QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(qt.QMessageBox, "question", lambda *a, **k: qt.QMessageBox.Yes)
    s.outputs = ["invoice"]
    return make_window(s)


def old_record(job: Job) -> dict:
    """What a version before the cover stopped counting kept: places with the cover among the pages, and no mark."""
    origin = json.loads(json.dumps({**job_origin(job), "case": case_snapshot(job.case)}))
    origin["job"].pop("cover_out", None)
    origin["case"]["fields"]["est_pages"][0] = str(job.transcript_pages() + 1)
    return origin


def test_an_old_record_opened_again_bills_the_same_printed_pages(window, tmp_path, s, monkeypatch):
    """The rows and the corrected takes both move. Without the second, the wrong page would change reporter and the
    wrong pages be billed, with no word said."""
    said = []
    monkeypatch.setattr(window, "_toast", said.append)
    s.profile.initials = "P.R."
    path = page_numbered_transcript(tmp_path / "Roe.pdf", 20, first=819, cover=COVER, initials=[PR] * 8 + [DS] * 12)
    job = firms(job_of(s, path))
    origin = old_record(job)
    # (kept then: Dana Smith ordered old places 12-21, printed 829-838; the page in old place 9, printed 826, is Dana's)
    origin["job"]["portions"] = [[11, [A]], [21, [A, B]]]
    origin["job"]["page_fixes"] = {str(path): {"9": DS}}
    assert window.open_past_job(json.dumps(origin)) is True
    wait(window, lambda: window.cur.docs)
    cur = window.cur
    assert cur.transcript_pages() == 20 and cur.case.get("est_pages") == "20"
    assert cur.portions == [(10, [A]), (20, [A, B])] and not cur.portions_problem()
    assert cur.docs[0].fixes == {8: DS} and cur.docs[0].owners()[8] == DS
    assert [p.span for p in cur.invoice_orders()[0].portions] == ["pp. 819–828", "pp. 829–838"]
    assert cur.your_pages() == 8 and not cur.old_places
    assert any("Min-U-Script cover no longer counts" in x and "20 total pages" in x for x in said)
    assert "cover_out" in job_origin(cur)["job"]  # (made again now, its record says so)


def test_a_marked_record_opened_again_says_nothing_and_moves_nothing(window, tmp_path, s, monkeypatch):
    said = []
    monkeypatch.setattr(window, "_toast", said.append)
    path = page_numbered_transcript(tmp_path / "Roe.pdf", 20, first=819, cover=COVER)
    job = firms(job_of(s, path))
    origin = json.loads(json.dumps({**job_origin(job), "case": case_snapshot(job.case)}))
    origin["job"]["portions"] = [[10, [A]], [20, [A, B]]]
    origin["job"]["page_fixes"] = {str(path): {"9": DS}}
    assert window.open_past_job(json.dumps(origin)) is True
    wait(window, lambda: window.cur.docs)
    assert window.cur.portions == [(10, [A]), (20, [A, B])] and window.cur.docs[0].fixes == {9: DS}
    assert not any("cover" in x for x in said)


def test_an_old_record_whose_transcript_moved_is_moved_over_when_it_comes_back(window, tmp_path, s):
    """Its count is kept as typed meanwhile, its rows in old places; dropped back, both are put right, and the count
    typed doesn't bill the cover."""
    path = page_numbered_transcript(tmp_path / "Roe.pdf", 20, first=819, cover=COVER)
    job = firms(job_of(s, path))
    origin = old_record(job)
    origin["job"]["portions"] = [[11, [A]], [21, [A, B]]]
    gone = tmp_path / "gone.pdf"
    path.rename(gone)
    assert window.open_past_job(json.dumps(origin)) is True
    wait(window, lambda: True)
    cur = window.cur
    assert cur.old_places and cur.case.fields["est_pages"].source == SRC_USER and cur.case.get("est_pages") == "21"
    assert "cover_out" not in job_origin(cur)["job"]  # (still in old places)
    gone.rename(path)
    window.add_files([str(path)], same_job=True)
    wait(window, lambda: window.cur.docs)
    assert cur.portions == [(10, [A]), (20, [A, B])] and not cur.old_places
    assert cur.case.fields["est_pages"].source == SRC_PDF and cur.invoice_pages() == 20


def test_a_trial_opened_again_from_an_old_record(window, tmp_path, s, monkeypatch):
    """A joint record: read a job per day, the rows moved by put_back_orders, the fixes in done()."""
    said = []
    monkeypatch.setattr(window, "_toast", said.append)
    a = page_numbered_transcript(tmp_path / "a.pdf", 20, first=819, cover=COVER, initials=[PR] * 8 + [DS] * 12)
    b = page_numbered_transcript(tmp_path / "b.pdf", 20, first=839, cover=COVER, caption=TITLE.replace("3", "4"))
    s.profile.initials = "P.R."
    docs, errors = read_docs([str(a), str(b)], s)
    assert not errors
    jobs = group(docs, s)
    for j in jobs:
        j.case.attorneys = [replace(ALEX), replace(DANA)]
    origin = json.loads(json.dumps(joint_origin(jobs)))
    del origin["cover_out"]
    first = next(j for j in jobs if j.docs[0].ing.name == "a.pdf")
    row = next(r for r in origin["orders"] if r["dates"] == first.case.get("dates"))
    row["portions"] = [[11, [A]], [21, [A, B]]]
    origin["page_fixes"] = {str(a): {"9": DS}}
    assert window.open_past_job(json.dumps(origin)) is True
    wait(window, lambda: len(window.jobs) == 2 and all(j.docs for j in window.jobs))
    day = next(j for j in window.jobs if j.docs[0].ing.name == "a.pdf")
    assert day.portions == [(10, [A]), (20, [A, B])] and not day.portions_problem() and day.docs[0].fixes == {8: DS}
    assert any("40 total pages now, 42 when this job was made" in x for x in said)


# ------------------------------------------------------------------ the run sheet, generated again

def add(case, rows, s, path=None):
    opts = RunSheetOpts(rows, str(path) if path else None)
    add_takes(case, opts, s, [])
    return opts


def test_a_day_on_a_run_sheet_written_with_its_cover_isnt_added_again(tmp_path, s):
    """The first take there: no first page, and one page more. It came back as a new take."""
    s.runsheet_dir = str(tmp_path / "sheets")
    s.profile.initials = "P.R."
    job = job_of(s, page_numbered_transcript(tmp_path / "Roe.pdf", 20, first=819, cover=COVER, initials=[PR] * 8 + [DS] * 12))
    old = add(job.case, [Row(DAY, "Pat", 9, None), Row(DAY, "DS", 12, 827)], s)
    rows = job.runsheet_opts(s).rows
    assert [(r.reporter, r.pages, r.start) for r in rows] == [("Pat", 8, 819), ("DS", 12, 827)]
    again = add(job.case, rows, s, old.path)
    assert (again.added, again.skipped) == (0, 2)


def test_the_same_day_written_after_the_cover_stopped_counting_isnt_added_twice(tmp_path, s):
    s.runsheet_dir = str(tmp_path / "sheets")
    job = job_of(s, page_numbered_transcript(tmp_path / "Roe.pdf", 20, first=819, cover=COVER))
    first = add(job.case, job.runsheet_opts(s).rows, s)
    again = add(job.case, job.runsheet_opts(s).rows, s, first.path)
    assert (first.added, again.added, again.skipped) == (1, 0, 1)


def test_a_take_that_only_looks_like_it_is_still_added():
    new = Row(DAY, "Pat", 20, 819, after_cover=True)
    assert new.same_take(Row(DAY, "Pat", 21, None))
    assert not new.same_take(Row(DAY, "Dana", 21, None))  # (another reporter)
    assert not new.same_take(Row(DAY, "Pat", 22, None))  # (not one page more)
    assert not new.same_take(Row(date(2026, 6, 4), "Pat", 21, None))  # (another day)
    assert not Row(DAY, "Pat", 20, 819).same_take(Row(DAY, "Pat", 21, None))  # (a transcript without a cover)
    assert Row(DAY, "Pat", 21, None).same_take(new)  # (either way round)


def test_a_first_page_of_0_on_a_run_sheet_is_none():
    """What a page printing 0 gave the run sheet before: read as a number, 151-160 didn't overlap 0-9."""
    assert Row(DAY, "Pat", 10, 151).same_take(Row(DAY, "Pat", 10, 0))
    assert Row(DAY, "Pat", 10, 0).same_take(Row(DAY, "Pat", 10, 151))
    assert not Row(DAY, "Dana", 10, 151).same_take(Row(DAY, "Pat", 10, 0))
    assert Row(DAY, "Pat", 10, 151, after_cover=True).same_take(Row(DAY, "Pat", 11, 0))


# ------------------------------------------------------------------ the windows

def excerpts_of(s, job):
    from minute_filler.gui.excerpts import ExcerptsWindow
    w = ExcerptsWindow(s, lambda: None)
    w.load([job])
    return w


def falling_job(tmp_path, s) -> Job:
    """Two volumes of a day, the second numbered back among the first's."""
    job = firms(job_of(s, page_numbered_transcript(tmp_path / "a.pdf", 20, first=101),
                       page_numbered_transcript(tmp_path / "b.pdf", 20, first=111)))
    assert len(job.invoice_days()) == 1
    return job


def test_a_day_whose_numbers_fall_is_warned_about_and_the_warning_stays(qt, tmp_path, s):
    from minute_filler.gui.excerpts import PAGES
    job = falling_job(tmp_path, s)
    w = excerpts_of(s, job)
    assert not w.falling.isHidden() and "start again (101–120, 111–130)" in w.falling.text()
    assert "place 40-44" in w.falling.text()
    assert w.table.item(0, PAGES).text() == "101–120, 111–130"
    assert "e.g. place 1–20" in w.table.item(0, PAGES).toolTip()  # (101–120 would be refused: 111-120 are there twice)
    w.table.item(0, PAGES).setText("115")  # (on two pages)
    assert "more than one stretch" in w.problem.text() and job.portions is None
    w.table.item(0, PAGES).setText("place 5-9")
    assert w.problem.text() == "" and job.portions is not None and [r[0] for r in job.portions] == [4, 9, 40]
    assert not w.falling.isHidden() and "start again" in w.falling.text()  # (the next change doesn't clear it)


def test_no_warning_on_a_day_whose_numbers_rise(qt, tmp_path, s):
    w = excerpts_of(s, firms(job_of(s, page_numbered_transcript(tmp_path / "a.pdf", 20, first=819, cover=COVER))))
    assert w.falling.isHidden() and w.falling.text() == ""
    from minute_filler.gui.excerpts import PAGES
    assert w.table.item(0, PAGES).text() == "819–838"
    assert "e.g. 819–838" in w.table.item(0, PAGES).toolTip()


def test_a_typed_day_s_cell(qt, tmp_path, s):
    from minute_filler.gui.excerpts import PAGES
    job = firms(job_of(s, page_numbered_transcript(tmp_path / "a.pdf", 93, first=236)))
    job.case.fields["est_pages"] = FieldState("40", SRC_USER, 1.0, [])
    w = excerpts_of(s, job)
    assert w.table.item(0, PAGES).text() == "236–328"  # (the whole day: the numbers read)
    w.table.item(0, PAGES).setText("1-20")
    assert [w.table.item(r, PAGES).text() for r in range(w.table.rowCount())] == ["place 1–20", "place 21–40"]
    assert [p.span for p in job.invoice_orders()[0].portions] == ["counted pages 1–20", "counted pages 21–40"]


def correct(window, monkeypatch, row, end):
    """Correct where this take ends, the box answered with `end`: what it offered, and what the "Are you sure?" says."""
    from PySide6 import QtWidgets
    asked, said = [], []

    def exec_box(box):
        said.append(box.text())
        yes = next((b for b in box.buttons() if box.buttonRole(b) == QtWidgets.QMessageBox.AcceptRole), None)
        if yes is not None:
            yes.click()
        return 0
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", exec_box)
    monkeypatch.setattr(QtWidgets.QInputDialog, "getInt", lambda *a, **k: asked.append(a) or (end, True))
    window._fix_take(row)
    return asked, said


def test_correcting_a_take_where_the_numbers_fall_or_arent_read(window, tmp_path, monkeypatch, s):
    """numbers[-1] as the top of the range refused any page on a day whose numbers fall; a None in them raised."""
    s.outputs = ["runsheet"]
    s.profile.initials = "P.R."
    path = page_numbered_transcript(tmp_path / "Roe.pdf", 12, first=50, initials=[PR] * 4 + [DS] * 4 + [PR] * 4)
    window.add_files([str(path)])
    wait(window, lambda: window.cur.docs and bool(window._take_rows))
    doc = window.cur.docs[0]
    numbers = [50, 51, 52, None, 54, None, 56, 57, 58, 3, 4, 5]
    doc.ing.marks = [replace(m, number=n) for m, n in zip(doc.ing.marks, numbers)]
    window._remerge()
    wait(window, lambda: bool(window._take_rows))
    pat, dana = window._take_rows[:2]
    assert (pat.start, pat.numbers) == (50, numbers[:4]) and (dana.start, dana.numbers) == (54, numbers[4:8])
    asked, said = correct(window, monkeypatch, pat, 54)
    # it ends, as read, on 52 (the page after has no number); it can go as low and as high as the pages after it read
    assert "starts on page 50 and ends on page 52" in asked[0][2]
    assert asked[0][3:] == (52, 3, 58)
    assert doc.fixes == {4: PR} and any("page 54" in x and "instead of 52" in x for x in said)


def take_with_numbers(window, tmp_path, s, numbers):
    """A transcript of 12 pages (Pat 4, Dana 4, Pat 4) read with these page numbers, and its takes on the card."""
    s.outputs = ["runsheet"]
    s.profile.initials = "P.R."
    path = page_numbered_transcript(tmp_path / "Roe.pdf", 12, first=50, initials=[PR] * 4 + [DS] * 4 + [PR] * 4)
    window.add_files([str(path)])
    wait(window, lambda: window.cur.docs and bool(window._take_rows))
    doc = window.cur.docs[0]
    doc.ing.marks = [replace(m, number=n) for m, n in zip(doc.ing.marks, numbers)]
    window._remerge()
    wait(window, lambda: bool(window._take_rows))
    return doc


def test_a_number_not_read_is_no_page_to_end_a_take_on(window, tmp_path, monkeypatch, s):
    """Counted on from the page before, a take could be made to end on page 55, which nothing prints."""
    from PySide6 import QtWidgets
    doc = take_with_numbers(window, tmp_path, s, [50, 51, 52, None, 54, None, 56, 57, 58, 59, 60, 61])
    said = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda *a, **k: said.append(a[2]))
    correct(window, monkeypatch, window._take_rows[0], 55)
    assert any("There is no page 55" in x for x in said) and doc.fixes == {}


def test_a_take_joined_up_to_a_last_page_without_a_number_says_the_last_one_read(window, tmp_path, monkeypatch, s):
    """It said "will end on page None"."""
    doc = take_with_numbers(window, tmp_path, s, [50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, None])
    _, said = correct(window, monkeypatch, window._take_rows[0], 57)
    assert any("will end on page 60 instead of 53" in x and "up to page 60, joins it" in x for x in said)
    assert not any("None" in x for x in said) and doc.fixes == {4: PR, 5: PR, 6: PR, 7: PR}


def test_a_take_with_no_number_read_has_nothing_to_go_by(window, tmp_path, monkeypatch, s):
    from PySide6 import QtWidgets
    s.outputs = ["runsheet"]
    s.profile.initials = "P.R."
    path = page_numbered_transcript(tmp_path / "Roe.pdf", 6, first=50, initials=[PR] * 3 + [DS] * 3)
    window.add_files([str(path)])
    wait(window, lambda: window.cur.docs and bool(window._take_rows))
    doc = window.cur.docs[0]
    doc.ing.marks = [replace(m, number=None) if i < 3 else m for i, m in enumerate(doc.ing.marks)]
    window._remerge()
    wait(window, lambda: bool(window._take_rows))
    said = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "information", lambda *a, **k: said.append(a[2]))
    window._fix_take(window._take_rows[0])
    assert any("no printed page numbers to go by" in x for x in said)


def test_help_says_a_cover_is_no_page():
    from minute_filler.help_topics import TOPICS
    text = next(t for t in TOPICS if t.id == "check-pages").html
    assert "Min-U-Script cover" in text and "isn't a page" in text
    assert "place 40-44" in next(t for t in TOPICS if t.id == "exc-table").html
