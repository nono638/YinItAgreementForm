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

from minute_filler.batch import (Doc, Job, _printed_span, _run_words, _runs_words, billed_split_rule, counts_covers,
                                 cover_note,
                                 documents_not_here, fill_jobs, fixes_without_cover, group, job_from_origin, job_origin,
                                 joint_origin, origin_fixes, put_back_orders, read_docs, record_documents, remerge,
                                 settle_old_places, trial_orders)
from minute_filler.deliver import case_snapshot, ledger_for
from minute_filler.excerpts import Day, Run, carve, case_days
from minute_filler.extract_regex import RegexExtractor
from minute_filler.ingest import Ingested, ingest_file
from minute_filler.models import SRC_PDF, SRC_USER, Attorney, Extraction, FieldState
from minute_filler.runsheet import (Row, RunSheetOpts, add_takes, page_order, rows_from, run_sheet_summary, takes_to_add,
                                    title_page_texts, title_page_total)
from minute_filler.takes import (PageCount, PageFacts, PageMark, _scan, count_pages, counted_words, find_takes,
                                 numbers_known, place_words, read_pages, run_numbers, scan_page, scan_pdf, without_cover)

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
    (replace(FACT, branded=True, caption=True), AFTER, False),  # (a typed title page saying "-against-", "Index No.")
    (replace(FACT, branded=True, zero=True), AFTER, False),  # (it prints something where its number goes: no cover does)
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
    the head's own, even between pages it would go on from."""
    at = int(head.rsplit(" ", 1)[-1]) if head[-1].isdigit() and head != "Proceedings 0" else 100
    doc = pymupdf.open()
    for n in (at - 1, 0, at + 1):
        page = doc.new_page()
        page.insert_text((300, 40), str(n), fontsize=10)
        if not n:
            page.insert_text((60, 28), head, fontsize=10)
        page.insert_text((40, 80), "1", fontsize=10)
        page.insert_text((80, 300), "A.", fontsize=10)
        page.insert_text((40, 720), "25", fontsize=10)
    got = [f.mark.number for f in read_pages(doc)]
    doc.close()
    assert got == [at - 1, number, at + 1]


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
    ([164, 164], None, False),  # (one number, twice: [1, 1] looks the same, so the run goes by its place)
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
    with pytest.raises(ValueError, match="more than one stretch.*place 15$"):
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


def test_a_take_starts_on_the_number_read_on_its_first_page_or_blank():
    """Not the first number read in it: the run sheet's End formula counts on from its Start, and would say a page past
    its last. Nor one counted on from the take before."""
    takes = find_takes([PageMark(None, PR), PageMark(820, PR), PageMark(None, DS), PageMark(None, DS), PageMark(823, DS),
                        PageMark(824, PR)], title_count=0)
    assert [(t.start, t.numbers, t.at) for t in takes] == [(None, [None, 820], 0), (None, [None, None, 823], 2),
                                                           (824, [824], 5)]


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


def test_a_job_merging_rows_still_in_old_places_waits_as_they_did(tmp_path, s):
    """The record's total and documents come with the rows: without them the first transcript read would settle them."""
    from minute_filler.batch import make_doc
    a = job_of(s, page_numbered_transcript(tmp_path / "a.pdf", 5, cover=COVER))
    other = Job(portions=[(2, [A]), (12, [A, B])], old_places=True, old_total=12, old_sources=["a.pdf", "b.pdf"])
    empty = Job()
    for job in (other, empty):
        job.case.set("index_no", a.case.get("index_no"))
        job.case.set("dates", a.case.get("dates"))
    job, = group([make_doc(a.docs[0].ing, a.docs[0].regex, s, path="a.pdf")], s, [empty, other])
    assert job.old_places and job.portions == [(2, [A]), (12, [A, B])] and (job.old_total, job.old_sources) == (
        12, ["a.pdf", "b.pdf"])


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


# ------------------------------------------------------------------ pages printing what they print
LINES = "\n".join(f"{n:2}  {'Q.  And then?' if n % 2 else 'A.  Yes.'}" for n in range(1, 26))


def printed_doc(numbers, who=None, heads=None, caption=CAPTION_DPM):
    """A PDF whose pages print these numbers where the number goes (None: nothing there; 0: a 0), signed as `who` says
    ("" unsigned; "pr" on every page without it), each under its running head when `heads` gives one."""
    doc = pymupdf.open()
    for i, n in enumerate(numbers):
        page = doc.new_page()
        if n is not None:
            page.insert_text((300, 40), str(n), fontsize=10)
        if heads and heads[i]:
            page.insert_text((60, 28), heads[i], fontsize=10)
        page.insert_text((60, 80), caption if i == 0 else LINES, fontsize=9)
        mark = who[i] if who else PR
        if mark:
            page.insert_text((520, page.rect.height - 40), mark, fontsize=10)
    return doc


def printed_pdf(path, numbers, who=None, heads=None, caption=CAPTION_DPM):
    doc = printed_doc(numbers, who, heads, caption)
    doc.save(path)
    doc.close()
    return path


def read_numbers(numbers, heads) -> list:
    """The numbers read_pages reads on these pages, as a PDF is read (the pages around each one to go by)."""
    doc = printed_doc(numbers, heads=heads)
    got = [f.mark.number for f in read_pages(doc)]
    doc.close()
    return got


# ------------------------------------------------------------------ the zero rule goes by the pages around it
@pytest.mark.parametrize("head", ["Proceedings 2026", "Term 2026", "Monday 2026", "Docket 12345", "Courtroom 25",
                                  "Exhibits 5", "Ex. 12", "Juror 9", "Witness 3", "Index No. 712345 2021", "Vol. II 3",
                                  "Nos. 5", "Case 7"])
def test_a_number_in_a_head_that_doesnt_go_on_from_the_pages_around_it_is_no_page_number(head):
    numbers = [100, 101, 102, 103, 104, 0, 106, 107, 108, 109, 110]
    assert read_numbers(numbers, [""] * 5 + [head] + [""] * 5) == numbers[:5] + [None] + numbers[6:]


def test_proceedings_2026_shows_no_year_among_the_page_numbers(tmp_path, s):
    """It gave "pp. 100–104, 2026, 106–110", a warning that the numbers fall, and "100-110" refused."""
    path = printed_pdf(tmp_path / "Roe.pdf", [100, 101, 102, 103, 104, 0, 106, 107, 108, 109, 110],
                       heads=[""] * 5 + ["Proceedings 2026"] + [""] * 5)
    day, = case_days([firms(job_of(s, path))])
    assert not day.falls() and day.span(1, 11) == "100–110" and day.parse("100-110") == (1, 11)
    take, = find_takes(job_of(s, path).docs[0].ing.marks, title_count=0)
    assert take.heads == ["Proceedings 2026"]  # (the head stays as printed: it isn't its number)


@pytest.mark.parametrize("numbers, heads, want", [
    ([104, 0, 106], ["", "Proceedings 105", ""], [104, 105, 106]),
    ([104, 0, 110], ["", "Proceedings 105", ""], [104, 105, 110]),  # (a skip of SKIP_OK after it)
    ([104, 0, 106], ["", "Proceedings 110", ""], [104, None, 106]),  # (past the page after it)
    ([100, 0, 106], ["", "Proceedings 105", ""], [100, 105, 106]),
    ([98, 0, 106], ["", "Proceedings 105", ""], [98, None, 106]),  # (a jump of 7 from the page before)
    ([100, None, 0, 103], ["", "", "Proceedings 102", ""], [100, None, 102, 103]),  # (an unread page between)
    ([100, 101, 0], ["", "", "Proceedings 102"], [100, 101, 102]),  # (the last page: one neighbour is enough)
    ([0, 101, 102], ["Proceedings 100", "", ""], [100, 101, 102]),  # (the first)
    ([0], ["Proceedings 151"], [None]),  # (no neighbour at all)
    ([0, 0, 0], ["Proceedings 151", "Proceedings 152", "Proceedings 153"], [151, 152, 153]),  # (they vouch for each other)
    ([0, 0, 0], ["Proceedings 2026"] * 3, [None, None, None]),  # (the same number on each is the head's)
    ([0, 0, 0, 0, 104], ["Proceedings 100", "Proceedings 101", "Proceedings 102", "Proceedings 103", ""],
     [100, 101, 102, 103, 104]),  # (a stretch printing 0, up to the first page read)
    ([104, 0, 0, 107], ["", "Proceedings 105", "Docket 555", ""], [104, 105, None, 107]),  # (each judged for itself)
    ([164, 0, 166], ["", "Proceedings 164", ""], [164, None, 166]),  # (not a number the page before has)
])
def test_which_numbers_in_a_head_go_on_from_the_pages_around_it(numbers, heads, want):
    assert read_numbers(numbers, heads) == want


def test_a_page_read_alone_has_no_pages_around_it_to_go_by():
    assert page_saying((300, 40, "0"), (60, 28, "Proceedings 151")).number is None


# ------------------------------------------------------------------ a last page printing 0 still counts
@pytest.mark.parametrize("zeros", [1, 2])
def test_a_last_page_printing_0_still_counts(tmp_path, zeros):
    """Unsigned and without its number in its head, it read as nothing, and dropped off the end: 11 pages of 12 billed,
    with no word said."""
    numbers = list(range(100, 112 - zeros)) + [0] * zeros
    ing = ingest_file(printed_pdf(tmp_path / "Roe.pdf", numbers, [PR] * (12 - zeros) + [""] * zeros))
    assert ing.count.pages == 12 and len(ing.marks) == 12 and not ing.count.warning
    assert [m.number for m in ing.marks[-zeros:]] == [None] * zeros


def test_what_keeps_a_page_at_the_end_of_the_first_reading():
    signed = PageFacts(PageMark(100, PR))
    assert len(_scan([signed, PageFacts(PageMark(), lined=True)])) == 1  # (a word index's first page can look lined)
    assert len(_scan([signed, PageFacts(PageMark(), zero=True)])) == 2
    assert len(_scan([signed, PageFacts(PageMark())])) == 1  # (nothing on it to say it is one)
    # (line numbers alone don't make a transcript's pages out of a PDF with nothing else on them: no marks to go by)
    assert _scan([PageFacts(PageMark(), lined=True)] * 3) == []


# ------------------------------------------------------------------ a run ending on a page whose number wasn't read
@pytest.mark.parametrize("printed, typed, places", [
    ([100, None, None, 103, 104, 105], "100-101", "place 1-3"),
    ([100, None, None, 103, 104, 105], "100-102", "place 1-3"),
    ([100, None, None, 103, 104, 105], "101-103", "place 2-4"),
    ([100, None, None, 103, 104, 105], "102-105", "place 2-6"),
    ([100, None, 102, None, 104], "101-103", "place 2-4"),
])
def test_a_run_ending_among_unread_pages_is_refused_and_says_which_places(printed, typed, places):
    """It billed the pages read up to there: "100-102" was one page, with no word said."""
    with pytest.raises(ValueError, match=f"wasn't read.*{places}$"):
        day_of(printed).parse(typed)


@pytest.mark.parametrize("printed, typed, want", [
    ([100, None, None, 103, 104, 105], "100-103", (1, 4)),  # (its ends are read)
    ([100, None, None, 103, 104, 105], "103-105", (4, 6)),
    ([100, None, None, 103, 104, 105], "place 1-2", (1, 2)),
    ([100, 101, 103, 104], "100-102", (1, 2)),  # (no page prints 102, and none is unread: as ever)
    ([100, 101, 103, 104], "102-104", (3, 4)),
])
def test_a_run_whose_ends_are_read_or_skipped_is_taken(printed, typed, want):
    assert day_of(printed).parse(typed) == want


# ------------------------------------------------------------------ one word for several runs, on the form's little room
def agreement_job(numbers) -> Job:
    """A day of these numbers, Alex B. Counsel ordering four runs of 60 pages at two speeds."""
    doc = covered_doc(len(numbers), cover=0)
    doc.ing.marks = [PageMark(n, PR) for n in numbers]
    job = firms(Job(docs=[doc]))
    job.case.set("dates", "6/3/2026")
    job.portions = [(60, [A]), (120, [A]), (180, [A]), (240, [A])]
    for row, speed in enumerate(["Daily", "Regular", "Daily", "Regular"]):
        job.set_speed(A, speed, row=row)
    return job


def test_counted_pages_is_said_once_for_each_speed():
    speeds = agreement_job([None] * 240).ordered_speeds()[A]
    assert speeds == [("Daily", "6/3/2026 counted pages 1–60, 121–180"), ("Regular", "6/3/2026 counted pages 61–120, 181–240")]


def test_pp_is_said_once_for_each_speed():
    speeds = agreement_job(list(range(101, 341))).ordered_speeds()[A]
    assert speeds == [("Daily", "6/3/2026 pp. 101–160, 221–280"), ("Regular", "6/3/2026 pp. 161–220, 281–340")]


def test_a_mix_of_runs_says_each_kind_once():
    """Pages 61-120 without numbers: those by their place, between the numbered ones."""
    numbers = list(range(101, 161)) + [None] * 60 + list(range(221, 341))
    speeds = dict(agreement_job(numbers).ordered_speeds()[A])
    assert speeds["Regular"] == "6/3/2026 counted pages 61–120, pp. 281–340"
    assert speeds["Daily"] == "6/3/2026 pp. 101–160, 221–280"


def test_the_note_on_the_agreement_fits_where_the_old_words_did():
    """Four runs at two speeds: the boxes on the UCS and the original form are about 336 points wide, and "counted
    pages" said on each run came to 384 at the smallest size, cut off."""
    from minute_filler.fill import speeds_note
    from minute_filler.forms import original_map, ucs_map
    from minute_filler.pdfout import fit_size, text_width
    speeds = agreement_job([None] * 240).ordered_speeds()[A]
    note = speeds_note([(sp, {"Daily": "6.50", "Regular": "4.30"}[sp], where) for sp, where in speeds])
    for form in (ucs_map, original_map):
        box = pymupdf.Rect(form.OVERLAYS["speeds_note"])
        assert text_width(note, fit_size(note, box)) <= box.width - 4


def test_one_run_at_a_speed_reads_as_before():
    job = agreement_job(list(range(101, 341)))
    job.portions = [(60, [A]), (240, [A])]
    job.set_speed(A, "Daily", row=0)
    job.set_speed(A, "Regular", row=1)
    assert job.ordered_speeds()[A] == [("Daily", "6/3/2026 pp. 101–160"), ("Regular", "6/3/2026 pp. 161–340")]


# ------------------------------------------------------------------ the line under the Pages field, as read
def read_as(numbers, **k) -> Job:
    doc = covered_doc(len(numbers), cover=0)
    doc.ing.marks = [PageMark(n, PR) for n in numbers]
    doc.ing.count = PageCount(len(numbers), first=numbers[0], last=numbers[-1], **k)
    return Job(docs=[doc])


def test_the_line_shows_numbers_that_start_again_as_they_are_read():
    """It said "Transcript pages 1–111" over the cells' 1–39, 10–29, 60–97, 10–11, 100–111."""
    assert read_as(FALLS).pages_help()[0] == "Transcript pages 1–39, 10–29, 60–97, 10–11, 100–111 (no word index)"
    assert read_as(FALLS, index_pages=4).pages_help()[0] == ("Transcript pages 1–39, 10–29, 60–97, 10–11, 100–111 · "
                                                             "excludes the 4 word-index pages after them")


def test_the_line_reads_as_ever_on_numbers_that_only_rise():
    assert read_as(TWICE).pages_help()[0] == "Transcript pages 130–256 (no word index)"
    assert read_as(list(range(819, 937))).pages_help()[0] == "Transcript pages 819–936 (no word index)"


def test_the_note_on_the_count_shows_numbers_that_start_again_as_read():
    marks = [PageMark(n, PR) for n in FALLS]
    note = extraction_note(count=PageCount(len(FALLS), first=1, last=111), marks=marks)
    assert note == "transcript pages 1–39, 10–29, 60–97, 10–11, 100–111"


# ------------------------------------------------------------------ the index limit counts the cover
def test_a_word_index_at_the_limit_with_a_cover_is_no_warning(tmp_path):
    """Cover + 14 pages + 6 of index: 6 of the PDF's 21 is within a quarter. Without the cover among the PDF's pages, 6
    of 20 was over it, and the count went amber though it was right."""
    c = ingest_file(page_numbered_transcript(tmp_path / "Roe.pdf", 14, cover=COVER, index_pages=6)).count
    assert (c.pages, c.cover, c.index_pages) == (14, 1, 6) and not c.warning and c.confidence == 0.95


def test_a_word_index_over_the_limit_still_warns_and_names_the_pdf_s_pages():
    pages = [PageFacts(PageMark(100 + i, PR), lined=True) for i in range(14)]
    pages += [PageFacts(PageMark(), index=True) for _ in range(7)]
    c = count_pages(pages, cover=1)
    assert "7 of the PDF's 22 total pages" in c.warning and c.confidence == 0.55


# ------------------------------------------------------------------ a caption page is no cover
@pytest.mark.parametrize("words", [
    "JANE ROE,\nPlaintiff,\n-against-\nSAM POE,\nDefendant.",
    "JANE ROE,\nPlaintiff,\n- against -\nSAM POE,\nDefendant.",
    "JANE ROE v. SAM POE\nIndex No. 712345/2021",
    "JANE ROE v. SAM POE\nINDEX NUMBER 712345/2021",
])
def test_a_typed_caption_page_saying_min_u_script_is_a_page(tmp_path, s, words):
    """Taken for a cover, a real title page went unbilled without a word."""
    path = page_numbered_transcript(tmp_path / "Roe.pdf", 20, first=819, cover=f"{words}\nJune 3, 2026\nMin-U-Script")
    c = job_of(s, path).docs[0].ing.count
    assert (c.cover, c.pages) == (0, 21)


def test_the_cover_s_own_words_are_no_caption(tmp_path):
    """"Word Index" isn't "Index No.", nor "Jane Roe v. Sam Poe" the "-against-" of a caption."""
    ing = ingest_file(page_numbered_transcript(tmp_path / "Roe.pdf", 5, cover=COVER))
    assert ing.count.cover == 1


# ------------------------------------------------------------------ numbers known, on a short day
@pytest.mark.parametrize("printed, known", [
    ([1, 1], False), ([164, 164], False), ([1, 1, None], False),
    ([154, None], True),  # (one read of two: as read, and no bill turns on it)
    ([1, 2], True),
])
def test_two_numbers_read_must_be_two_numbers(printed, known):
    assert numbers_known(printed) is known


def test_a_short_day_printing_one_number_is_by_place():
    assert _run_words([1, 1], 1, 2) == "counted pages 1–2" and day_of([1, 1]).span(1, 2) == "place 1–2"


# ------------------------------------------------------------------ the run sheet keeps every take
def sheet_of(opts) -> list:
    from openpyxl import load_workbook
    from minute_filler.runsheet import _read_ours
    return [(r.reporter, r.pages, r.start) for r in _read_ours(load_workbook(opts.path)["Run Sheet"])]


@pytest.fixture
def sheets(tmp_path, s):
    s.runsheet_dir = str(tmp_path / "sheets")
    s.profile.initials = "P.R."
    return s


def test_a_first_page_without_a_number_keeps_both_takes_and_a_blank_start(tmp_path, sheets):
    """Pat's first number read made Pat's take 2..11 and Dana's 11..18: they overlapped, and Dana's was dropped."""
    s = sheets
    job = job_of(s, printed_pdf(tmp_path / "Roe.pdf", [None] + list(range(2, 19)), [PR] * 10 + [DS] * 8))
    rows = job.runsheet_opts(s).rows
    assert [(r.reporter, r.pages, r.start, r.end(), r.at) for r in rows] == [("Pat", 10, None, None, 0),
                                                                             ("DS", 8, 11, 18, 10)]
    assert rows[0].numbers == [None] + list(range(2, 11))  # (what was read still shows)
    made = add(job.case, rows, s)
    assert (made.added, made.skipped) == (2, 0) and sheet_of(made) == [("Pat", 10, None), ("DS", 8, 11)]
    assert "with 2 takes" in run_sheet_summary(made)
    again = add(job.case, job.runsheet_opts(s).rows, s, made.path)
    assert (again.added, again.skipped) == (0, 2)


def test_a_take_whose_first_number_wasnt_read_stays_in_its_place(tmp_path, sheets):
    """Its last take was dropped, and a blank Start sorted it out of the order of the pages."""
    s = sheets
    job = job_of(s, printed_pdf(tmp_path / "Roe.pdf", [1, 2, 3, None, 5, 6, 7, 8], ["ab"] * 3 + ["cd"] * 3 + ["ef"] * 2))
    rows = job.runsheet_opts(s).rows
    assert [(r.reporter, r.pages, r.start) for r in rows] == [("AB", 3, 1), ("CD", 3, None), ("EF", 2, 7)]
    assert [r.numbers for r in rows] == [[1, 2, 3], [None, 5, 6], [7, 8]]  # (never 4, counted on from the page before)
    made = add(job.case, rows, s)
    assert sheet_of(made) == [("AB", 3, 1), ("CD", 3, None), ("EF", 2, 7)]
    assert (add(job.case, job.runsheet_opts(s).rows, s, made.path).added) == 0


def test_a_blank_start_stays_in_its_place_on_the_card_and_on_a_batch_s_run_sheet(tmp_path, sheets):
    from minute_filler.batch import takes_of, unit_sheet
    s = sheets
    job = job_of(s, printed_pdf(tmp_path / "Roe.pdf", [1, 2, 3, None, 5, 6, 7, 8], ["ab"] * 3 + ["cd"] * 3 + ["ef"] * 2))
    assert [r.reporter for r in takes_of([job], s)] == ["AB", "CD", "EF"]
    assert [r.reporter for r in unit_sheet([job], s, []).rows] == ["AB", "CD", "EF"]


def test_a_number_printed_twice_where_the_reporter_changes_keeps_every_take(tmp_path, sheets):
    s = sheets
    who = [PR] * 35 + [DS] * 32 + [PR] * 39 + [DS] * 20 + [PR]
    job = job_of(s, printed_pdf(tmp_path / "Roe.pdf", TWICE, who))
    made = add(job.case, job.runsheet_opts(s).rows, s)
    assert made.added == 5 and sum(p for _, p, _ in sheet_of(made)) == 127
    assert [start for *_, start in sheet_of(made)] == [130, 164, 197, 235, 256]
    assert add(job.case, job.runsheet_opts(s).rows, s, made.path).added == 0


def test_a_day_whose_numbers_fall_keeps_every_take(tmp_path, sheets):
    s = sheets
    who = [PR] * 39 + [DS] * 20 + [PR] * 38 + [DS] * 2 + [PR] * 12
    job = job_of(s, printed_pdf(tmp_path / "Roe.pdf", FALLS, who))
    made = add(job.case, job.runsheet_opts(s).rows, s)
    assert made.added == 5 and sum(p for _, p, _ in sheet_of(made)) == 111
    assert add(job.case, job.runsheet_opts(s).rows, s, made.path).added == 0


def test_a_take_an_older_run_sheet_lost_to_a_number_printed_twice_is_added(tmp_path, sheets):
    """An earlier version dropped Dana's takes from this sheet: they only share the number printed twice with Pat's."""
    s = sheets
    who = [PR] * 35 + [DS] * 32 + [PR] * 39 + [DS] * 20 + [PR]
    job = job_of(s, printed_pdf(tmp_path / "Roe.pdf", TWICE, who))
    old = add(job.case, [Row(DAY, "Pat", 35, 130), Row(DAY, "Pat", 39, 197), Row(DAY, "Pat", 1, 256)], s)
    again = add(job.case, job.runsheet_opts(s).rows, s, old.path)
    assert (again.added, again.skipped) == (2, 3)
    assert sheet_of(again) == [("Pat", 35, 130), ("DS", 32, 164), ("Pat", 39, 197), ("DS", 20, 235), ("Pat", 1, 256)]


@pytest.mark.parametrize("zero_at, written", [
    (0, [("Pat", 0), ("DS", 161), ("Pat", 171)]),  # (its first take: the last take's Start is a formula on the sheet)
    (10, [("Pat", 151), ("DS", 0), ("Pat", 171)]),  # (a take under it starting by a number of its own)
    (20, [("Pat", 151), ("DS", 161), ("Pat", 0)]),
])
def test_a_zero_file_on_an_older_run_sheet_adds_nothing(tmp_path, sheets, zero_at, written):
    """A take starting on a page printing 0 wrote a first page of 0 there, and the takes under it their numbers."""
    s = sheets
    numbers = list(range(151, 181))
    numbers[zero_at] = 0
    heads = [""] * 30
    heads[zero_at] = f"Proceedings {151 + zero_at}"
    job = job_of(s, printed_pdf(tmp_path / "Roe.pdf", numbers, [PR] * 10 + [DS] * 10 + [PR] * 10, heads))
    # (takes of one transcript: all three reach the sheet, as an earlier version wrote them)
    old = add(job.case, [Row(DAY, who, 10, start, doc="old.pdf", at=i * 10) for i, (who, start) in enumerate(written)], s)
    assert old.added == 3
    assert add(job.case, job.runsheet_opts(s).rows, s, old.path).added == 0


@pytest.mark.parametrize("a, b, same", [
    (Row(DAY, "Pat", 10, 2, doc="a.pdf", at=0), Row(DAY, "DS", 8, 11, doc="a.pdf", at=10), False),  # (one transcript)
    (Row(DAY, "Pat", 10, 2, doc="a.pdf", at=0), Row(DAY, "Pat", 10, 2, doc="a.pdf", at=0), True),  # (the very take)
    (Row(DAY, "Pat", 10, 2, doc="a.pdf", at=0), Row(DAY, "Pat", 10, 2, doc="b.pdf", at=0), True),  # (dropped twice)
    (Row(DAY, "Pat", 5, 164, doc="a.pdf", at=0), Row(DAY, "Pat", 5, 164), True),  # (on the run sheet: no document)
    (Row(DAY, "DS", 32, 164), Row(DAY, "Pat", 35, 130), False),  # (only the number printed twice in common)
    (Row(DAY, "Pat", 35, 130), Row(DAY, "DS", 32, 164), False),
    (Row(DAY, "DS", 1, 164), Row(DAY, "Pat", 35, 130), False),  # (a take of that one page)
    (Row(DAY, "Dana", 1, 164), Row(DAY, "DS", 1, 164), True),  # (the same page under another name)
    (Row(DAY, "Dana", 32, 164), Row(DAY, "DS", 32, 164), True),  # (the same pages under another name)
    (Row(DAY, "Dana", 32, 164), Row(DAY, "DS", 30, 165), True),  # (more than the one number in common: as ever)
    (Row(DAY, "Pat", 32, 164), Row(DAY, "Pat", 35, 130), True),  # (one reporter's: as ever)
    # the last number read, not the count: 195, 197, 198 ends on 198 (the formula's 197 would miss the page shared)
    (Row(DAY, "Pat", 3, 195, numbers=[195, 197, 198]), Row(DAY, "Pat", 3, 198), True),
    (Row(DAY, "Pat", 3, None, numbers=[None, 5, 6]), Row(DAY, "Casey", 3, 4), True),  # (a Start counted on, on a sheet)
    (Row(DAY, "Pat", 3, None, numbers=[None, 5, 6]), Row(DAY, "Pat", 3, None), True),  # (no numbers there: by the count)
    (Row(DAY, "Pat", 3, None, numbers=[None, None, None]), Row(DAY, "Pat", 3, 40), True),  # (none read here)
    # a scan's row has the one number on its first page: reporter typed in on the sheet since, it is still that take
    (Row(DAY, "", 6, 154, numbers=[154]), Row(DAY, "Pat", 6, 154), True),
    (Row(DAY, "", 6, 154, numbers=[154]), Row(DAY, "Pat", 6, 200), False),
    (Row(DAY, "", 6, 154, numbers=[154]), Row(DAY, "", 6, 156), True),  # (its six pages reach it, not its one number)
    # one number read of a take's six, from the same first page, under another name: that take
    (Row(DAY, "Pat", 6, 154, numbers=[154] + [None] * 5), Row(DAY, "Casey", 6, 154), True),
    (Row(date(2026, 6, 4), "Pat", 10, 2), Row(DAY, "Pat", 10, 2), False),
])
def test_what_is_the_same_take(a, b, same):
    assert a.same_take(b) is same


def test_correcting_a_take_with_a_blank_start(window, tmp_path, monkeypatch, s):
    doc = take_with_numbers(window, tmp_path, s, [None, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61])
    pat = window._take_rows[0]
    assert pat.start is None and pat.numbers[:2] == [None, 51]
    asked, _ = correct(window, monkeypatch, pat, 54)
    assert "starts on page 51 and ends on page 53" in asked[0][2] and doc.fixes == {4: PR}


# ------------------------------------------------------------------ the reporter's label changed since the old sheet
CAPTION_NAMING = CAPTION_DPM + "\n\n    DANA SMITH\n    Senior Court Reporter"


def test_a_first_take_written_under_its_initials_isnt_added_again_under_its_name(tmp_path, sheets):
    """The old count stopped at the cover, so the old sheet says DS; the title page after it names Dana now. Added
    again, Dana's 8 pages counted as 15."""
    s = sheets
    path = page_numbered_transcript(tmp_path / "Roe.pdf", 12, first=100, initials=[DS] * 7 + [PR] * 5, cover=COVER,
                                    caption=CAPTION_NAMING)
    job = job_of(s, path)
    rows = job.runsheet_opts(s).rows
    assert [(r.reporter, r.pages, r.start, r.after_cover) for r in rows] == [("Dana", 7, 100, True), ("Pat", 5, 107, False)]
    old = add(job.case, [Row(DAY, "DS", 8, None), Row(DAY, "Pat", 5, 107)], s)
    again = add(job.case, rows, s, old.path)
    assert (again.added, again.skipped) == (0, 2)


def test_another_reporter_s_initials_are_no_match():
    new = Row(DAY, "Dana", 7, 100, initials=DS, after_cover=True)
    assert new.same_take(Row(DAY, "DS", 8, None)) and not new.same_take(Row(DAY, "KP", 8, None))


# ------------------------------------------------------------------ Split, on a day typed in or whose numbers fall
def split_with(w, monkeypatch, answer):
    """Split run… on the table's first run, answered with `answer` (None: the number offered): (the question, what it
    offered)."""
    from minute_filler.gui import excerpts as window_of_excerpts
    asked = []

    def get_text(_parent, _title, label, _echo, offered):
        asked.append((label, offered))
        return (offered if answer is None else answer), True
    monkeypatch.setattr(window_of_excerpts.QInputDialog, "getText", get_text)
    w.table.selectRow(0)
    w._split()
    return asked[0]


def test_split_on_a_typed_day_asks_for_a_place(qt, tmp_path, s, monkeypatch):
    """Pages typed 300, numbers read 100-399: "after which page number?" and 150 typed cut at place 150, not at the
    page printed 150 (place 51)."""
    job = firms(job_of(s, page_numbered_transcript(tmp_path / "a.pdf", 300, first=100)))
    job.case.fields["est_pages"] = FieldState("280", SRC_USER, 1.0, [])
    w = excerpts_of(s, job)
    label, offered = split_with(w, monkeypatch, "150")
    assert "after which place?" in label and "page number" not in label and "1–280 of 280 pages typed" in label
    assert offered == "place 140"
    assert [r[0] for r in job.portions] == [150, 280]


def test_split_on_a_typed_day_takes_the_place_it_offers(qt, tmp_path, s, monkeypatch):
    job = firms(job_of(s, page_numbered_transcript(tmp_path / "a.pdf", 30, first=100)))
    job.case.fields["est_pages"] = FieldState("20", SRC_USER, 1.0, [])
    w = excerpts_of(s, job)
    split_with(w, monkeypatch, None)
    assert [r[0] for r in job.portions] == [10, 20]


def test_split_s_offer_on_a_day_whose_numbers_fall_is_taken(qt, tmp_path, s, monkeypatch):
    """The middle page's number can be on two stretches: offered as it was, it was refused."""
    job = falling_job(tmp_path, s)  # (101-120, 111-130: the middle page prints 120, the 21st 111)
    day, = case_days([job])
    assert day.as_typed(15, 15) == "place 15"  # (115: on both stretches)
    with pytest.raises(ValueError):
        day.parse(day.span(15, 15))
    job.portions = [(30, [A, B]), (40, [A, B])]  # (the first run, its middle at place 15)
    w = excerpts_of(s, job)
    label, offered = split_with(w, monkeypatch, None)
    assert offered == "place 15" and "page number" in label  # (its runs still go by their numbers)
    assert w.problem.text() == "" and [r[0] for r in job.portions] == [15, 30, 40]


def test_split_on_a_day_of_rising_numbers_asks_as_before(qt, tmp_path, s, monkeypatch):
    job = firms(job_of(s, page_numbered_transcript(tmp_path / "a.pdf", 20, first=819)))
    w = excerpts_of(s, job)
    label, offered = split_with(w, monkeypatch, None)
    assert label == "Cut the run 819–838 after which page number?" and offered == "828"
    assert [r[0] for r in job.portions] == [10, 20]


@pytest.mark.parametrize("a, b, want", [
    (1, 20, "819–838"), (5, 5, "823"),
])
def test_a_run_as_it_can_be_typed(a, b, want):
    assert day_of(range(819, 939)).as_typed(a, b) == want


def test_a_run_whose_shown_numbers_mean_other_pages_is_offered_by_place():
    d = day_of(TWICE)
    assert d.as_typed(35, 35) == "place 35"  # (164 is both pages 35 and 36)
    assert d.as_typed(35, 36) == "164"  # (a run in a day known: typed, 164 is those two pages)
    assert d.example() == "130–149"


# ------------------------------------------------------------------ an old record: all its transcripts first
def old_two_volumes(tmp_path, s):
    """A day of two transcripts as an older version kept it: a.pdf (a cover and 20 pages from 100), b.pdf (10 from
    200), 31 pages counted. Alex B. Counsel alone ordered 100-104 (old places 2-6)."""
    a = page_numbered_transcript(tmp_path / "a.pdf", 20, first=100, cover=COVER)
    b = page_numbered_transcript(tmp_path / "b.pdf", 10, first=200)
    origin = old_record(firms(job_of(s, a, b)))
    origin["job"]["portions"] = [[6, [A]], [31, [A, B]]]
    assert origin["case"]["fields"]["est_pages"][0] == "31"
    return a, b, origin


def drop_back(window, path, count):
    window.add_files([str(path)], same_job=True)
    wait(window, lambda: len(window.cur.docs) == count)


def assert_moved_over(cur):
    assert not cur.old_places and cur.portions == [(5, [A]), (30, [A, B])] and not cur.portions_problem()
    assert [d.ing.name for d in cur.transcripts()] == ["a.pdf", "b.pdf"]  # (as the record counted them)
    assert cur.case.fields["est_pages"].source == SRC_PDF and cur.case.get("est_pages") == "30"
    assert not cur.pages_typed() and cur.invoice_pages() == 30
    assert [(p.pages, p.span) for p in cur.invoice_orders()[0].portions] == [(5, "pp. 100–104"), (25, "pp. 105–119, 200–209")]


def test_a_day_waits_for_all_its_transcripts_before_it_moves(window, tmp_path, s, monkeypatch):
    """b.pdf moved. Settled when a.pdf was read, 31 stayed typed against the 30 total pages when b.pdf came back: 31
    billed, the rows in old places, Alex billed 6 pages "counted pages 1–6", with no word said."""
    said = []
    monkeypatch.setattr(window, "_toast", said.append)
    a, b, origin = old_two_volumes(tmp_path, s)
    gone = tmp_path / "gone.pdf"
    b.rename(gone)
    assert window.open_past_job(json.dumps(origin)) is True
    wait(window, lambda: window.cur.docs)
    cur = window.cur
    assert cur.old_places and cur.portions == [(6, [A]), (31, [A, B])]
    assert cur.case.get("est_pages") == "31" and cur.case.fields["est_pages"].source == SRC_USER
    # (what it would say of the documents read so far is not so, while Pages still shows the record's 31)
    assert not any("total pages now" in x for x in said)
    gone.rename(b)
    drop_back(window, b, 2)
    assert_moved_over(cur)
    assert any("30 total pages now, 31 when this job was made" in x for x in said)


def test_the_document_with_the_cover_coming_back_last_is_counted_where_it_was(window, tmp_path, s):
    """The cover was at place 1 as the record counted them, though a.pdf comes back after b.pdf."""
    a, b, origin = old_two_volumes(tmp_path, s)
    gone = tmp_path / "gone.pdf"
    a.rename(gone)
    assert window.open_past_job(json.dumps(origin)) is True
    wait(window, lambda: window.cur.docs)
    cur = window.cur
    assert cur.old_places and [d.ing.name for d in cur.docs] == ["b.pdf"]
    gone.rename(a)
    drop_back(window, a, 2)
    assert_moved_over(cur)


def test_a_document_dropped_back_from_another_folder_is_known_by_its_name(window, tmp_path, s):
    a, b, origin = old_two_volumes(tmp_path, s)
    (tmp_path / "elsewhere").mkdir()
    moved = tmp_path / "elsewhere" / "a.pdf"
    a.rename(moved)
    assert window.open_past_job(json.dumps(origin)) is True
    wait(window, lambda: window.cur.docs)
    drop_back(window, moved, 2)
    assert_moved_over(window.cur)


def test_a_document_back_under_another_name_holds_the_rows_for_a_look(window, tmp_path, s):
    """Which order the record counted it in can't be told, so nor can where its cover was: the rows are not moved, they
    don't end on its pages, and the invoice waits. Never moved by a guess."""
    a, b, origin = old_two_volumes(tmp_path, s)
    renamed = tmp_path / "renamed.pdf"
    a.rename(renamed)
    assert window.open_past_job(json.dumps(origin)) is True
    wait(window, lambda: window.cur.docs)
    drop_back(window, renamed, 2)
    cur = window.cur
    assert not cur.old_places and cur.transcript_pages() == 30 and cur.case.fields["est_pages"].source == SRC_PDF
    assert cur.portions == [(6, [A]), (31, [A, B])] and "rows don't end on" in cur.portions_problem()


def test_a_letter_that_moved_doesnt_keep_the_rows_waiting(tmp_path, s):
    """Its transcript is here and the pages add up to the record's: nothing is missing that counts."""
    path = page_numbered_transcript(tmp_path / "Roe.pdf", 20, first=819, cover=COVER)
    job = job_from_origin({"sources": [str(path), str(tmp_path / "letter.pdf")],
                           "job": {"portions": [[11, [A]], [21, [A, B]]]},
                           "case": {"fields": {"est_pages": ["21", SRC_USER, 1.0]}, "attorneys": [ALEX.to_dict(), DANA.to_dict()]}},
                          s)
    assert (job.old_total, job.old_sources) == (21, [str(path), str(tmp_path / "letter.pdf")])
    job.docs += read_docs([str(path)], s)[0]
    remerge(job, s)
    assert job.portions == [(10, [A]), (20, [A, B])] and not job.old_places and job.case.get("est_pages") == "20"


def test_all_its_documents_read_settles_a_transcript_that_got_shorter(tmp_path, s):
    """Every document of the record is here: nothing more will come, so the rows move, and are held for not fitting."""
    path = page_numbered_transcript(tmp_path / "Roe.pdf", 20, first=819, cover=COVER)
    job = job_from_origin({"sources": [str(path)], "job": {"portions": [[11, [A]], [31, [A, B]]]},
                           "case": {"fields": {"est_pages": ["31", SRC_PDF, 0.95]}, "attorneys": [ALEX.to_dict(), DANA.to_dict()]}},
                          s)
    job.docs += read_docs([str(path)], s)[0]
    remerge(job, s)
    assert job.portions == [(10, [A]), (30, [A, B])] and not job.old_places and job.portions_problem()


def test_a_shorter_transcript_back_from_another_folder_is_known_by_its_name(tmp_path, s):
    """Its pages never add up to the record's, so only its name can say it is the document the record counted."""
    (tmp_path / "elsewhere").mkdir()
    moved = page_numbered_transcript(tmp_path / "elsewhere" / "Roe.pdf", 20, first=819, cover=COVER)
    job = job_from_origin({"sources": [str(tmp_path / "Roe.pdf")], "job": {"portions": [[11, [A]], [31, [A, B]]]},
                           "case": {"fields": {"est_pages": ["31", SRC_PDF, 0.95]}, "attorneys": [ALEX.to_dict(), DANA.to_dict()]}},
                          s)
    job.docs += read_docs([str(moved)], s)[0]
    remerge(job, s)
    assert job.portions == [(10, [A]), (30, [A, B])] and not job.old_places and job.portions_problem()


def test_rows_cut_again_on_the_pages_here_are_no_longer_in_old_places(tmp_path, s):
    """Cut in the window while a document is still away, the Pages field cleared: they are by the pages read."""
    from minute_filler.excerpts import store
    a, b, origin = old_two_volumes(tmp_path, s)
    job = job_from_origin(origin, s)
    job.docs += read_docs([str(a)], s)[0]
    remerge(job, s)
    assert job.old_places and not job.pages_typed()  # (the record's count, not typed: the rows just don't fit)
    day, = case_days([job])
    store(day, [Run(day, 1, 5, [A]), Run(day, 6, 20, [A, B])], job.case.attorneys)
    assert not job.old_places and job.portions == [(5, [A]), (20, [A, B])]


def test_rows_cut_in_a_number_kept_as_typed_still_wait(tmp_path, s):
    """They count pages of the record's 31, the cover among them: still to be moved."""
    from minute_filler.excerpts import store
    a, b, origin = old_two_volumes(tmp_path, s)
    job = job_from_origin(origin, s)
    job.case.fields["est_pages"].source = SRC_USER
    job.docs += read_docs([str(a)], s)[0]
    remerge(job, s)
    day, = case_days([job])
    assert job.pages_typed() and day.pages == 31
    store(day, [Run(day, 1, 11, [A]), Run(day, 12, 31, [A, B])], job.case.attorneys)
    assert job.old_places


def test_a_trial_s_day_waits_for_its_transcripts_too(window, tmp_path, s):
    """a.pdf (10 pages) moved, b.pdf (a cover and 20): the cover was at place 11, not 1. Taken at 1 the rows became
    [4, 30], fitted when a.pdf came back, and Alex was billed 4 pages for 5, with no word said."""
    a = page_numbered_transcript(tmp_path / "a.pdf", 10, first=100)
    b = page_numbered_transcript(tmp_path / "b.pdf", 20, first=110, cover=COVER)
    job = firms(job_of(s, a, b))
    origin = json.loads(json.dumps(joint_origin([job])))
    del origin["cover_out"]
    origin["orders"][0]["portions"] = [[5, [A]], [31, [A, B]]]
    gone = tmp_path / "gone.pdf"
    a.rename(gone)
    assert window.open_past_job(json.dumps(origin)) is True
    wait(window, lambda: window.cur.docs)
    cur = window.cur
    assert cur.old_places and cur.portions == [(5, [A]), (31, [A, B])] and cur.portions_problem()
    gone.rename(a)
    window.add_files([str(a)])
    wait(window, lambda: len(window.cur.docs) == 2)
    assert not cur.old_places and cur.portions == [(5, [A]), (30, [A, B])] and not cur.portions_problem()
    assert [d.ing.name for d in cur.transcripts()] == ["a.pdf", "b.pdf"]
    assert [(p.pages, p.span) for p in cur.invoice_orders()[0].portions] == [(5, "pp. 100–104"), (25, "pp. 105–129")]


def test_a_trial_whose_other_day_is_away_moves_the_day_that_is_all_here(tmp_path, s):
    """The record's documents are of every day; this day's own pages add up, and that is what it waits for."""
    a = page_numbered_transcript(tmp_path / "a.pdf", 20, first=819, cover=COVER)
    job = firms(job_of(s, a))
    origin = json.loads(json.dumps(joint_origin([job])))
    del origin["cover_out"]
    origin["sources"].append(str(tmp_path / "another day.pdf"))
    origin["orders"][0]["portions"] = [[11, [A]], [21, [A, B]]]
    put_back_orders([job], origin, s)
    assert job.portions == [(10, [A]), (20, [A, B])] and not job.old_places


# ------------------------------------------------------------------ an old own count kept as typed
def own_count_record(path, est, source=SRC_USER, front=PR, rows=None) -> dict:
    return json.loads(json.dumps({"sources": [str(path)],
                                  "job": {"front_owner": {str(path): front}, "att_touched": True, "portions": rows},
                                  "case": {"fields": {"est_pages": [est, source, 1.0]},
                                           "attorneys": [ALEX.to_dict(), DANA.to_dict()]}}))


def shared_with_cover(tmp_path, s):
    s.profile.initials = "P.R."
    return page_numbered_transcript(tmp_path / "Roe.pdf", 20, first=100, initials=[PR] * 8 + [DS] * 12, cover=COVER)


def test_an_old_own_count_kept_as_typed_goes_back_to_the_count(tmp_path, s):
    """The cover was the user's (front_owner), so 9 was the count of the user's pages, 8 now. Kept as a number typed it
    billed the cover, and the agreement counted 9 of the 20 total pages."""
    path = shared_with_cover(tmp_path, s)
    job = job_from_origin(own_count_record(path, "9", rows=[[5, [A]], [21, [A, B]]]), s)
    job.docs += read_docs([str(path)], s)[0]
    remerge(job, s)
    assert not job.pages_typed() and job.own_pages() == job.invoice_pages() == 8
    assert job.case.fields["est_pages"].source == SRC_PDF and job.case.get("est_pages") == "20"
    assert job.ordered_pages()[A] == 20
    assert job.portions == [(4, [A]), (20, [A, B])]  # (it was the count, so the rows counted the cover)


def test_an_own_count_whose_cover_was_someone_else_s_is_the_count_too(tmp_path, s):
    """The cover was Dana's: the old count of the user's pages was 8, as it is now, and the rows counted the cover."""
    path = shared_with_cover(tmp_path, s)
    job = job_from_origin(own_count_record(path, "8", front=DS, rows=[[5, [A]], [21, [A, B]]]), s)
    job.docs += read_docs([str(path)], s)[0]
    remerge(job, s)
    assert not job.pages_typed() and job.invoice_pages() == 8 and job.portions == [(4, [A]), (20, [A, B])]


@pytest.mark.parametrize("typed, front", [("9", DS), ("10", PR), ("7", PR)])
def test_a_number_that_was_never_an_old_count_stays_typed(tmp_path, s, typed, front):
    path = shared_with_cover(tmp_path, s)
    job = job_from_origin(own_count_record(path, typed, front=front), s)
    job.docs += read_docs([str(path)], s)[0]
    remerge(job, s)
    assert job.pages_typed() and job.invoice_pages() == int(typed)


def test_a_typed_0_is_the_user_s_even_when_none_of_the_pages_are_billed(tmp_path, s):
    """No invoice for the day, as ever: it was never the count, though the user's pages of this transcript are none."""
    s.profile.initials = "K.P."
    path = shared_with_cover(tmp_path, s)
    s.profile.initials = "K.P."
    job = job_from_origin(own_count_record(path, "0", front=DS), s)
    job.docs += read_docs([str(path)], s)[0]
    remerge(job, s)
    assert job.own_pages() == 0 and job.pages_typed() and job.case.get("est_pages") == "0"


def test_whose_cover_it_was_goes_by_who_is_billed():
    """Billed the whole transcript or a reporter of its own: the old count had the cover, whoever's initials follow."""
    doc = covered_doc(5, who=PR)
    assert Job(docs=[doc], own=(PR,))._cover_billed(doc) is True  # (one reporter, the user)
    shared = covered_doc(5)
    shared.ing.marks = [PageMark(100, PR), PageMark(101, PR), PageMark(102, DS), PageMark(103, DS), PageMark(104, DS)]
    key = shared.key()
    assert Job(docs=[shared], own=(PR,), front_owner={key: PR})._cover_billed(shared) is True
    assert Job(docs=[shared], own=(PR,), front_owner={key: DS})._cover_billed(shared) is False
    assert Job(docs=[shared], own=(PR,))._cover_billed(shared) is False  # (nobody said)
    assert Job(docs=[shared], own=(PR,), front_owner={key: PR}, page_basis={key: "*"})._cover_billed(shared) is True
    assert Job(docs=[shared], own=(PR,), front_owner={key: DS}, page_basis={key: DS})._cover_billed(shared) is True


# ------------------------------------------------------------------ a record is all one way of counting
def test_a_trial_part_moved_over_is_kept_all_in_the_old_way(tmp_path, s):
    """Day X moved over, day Y still waiting (only an e-mail back). One mark can't say both: without it X's rows and
    corrected takes were moved again when the record was opened, {4: ds} to {3: ds}, [5, 20] to [4, 19], with no word
    said. So the record counts the covers everywhere, as an older one does, and nothing moves twice."""
    x = firms(job_of(s, page_numbered_transcript(tmp_path / "x.pdf", 20, first=100, cover=COVER)))
    x.portions = [(5, [A]), (20, [A, B])]
    x.docs[0].fixes = {4: DS}
    y = Job(old_places=True, portions=[(10, [A])])
    y.case.set("dates", "6/4/2026")
    origin = json.loads(json.dumps(joint_origin([x, y])))
    assert counts_covers(origin)
    assert origin["page_fixes"] == {str(tmp_path / "x.pdf"): {"5": DS}}
    assert origin["orders"][0]["portions"] == [[6, [A]], [21, [A, B]]]
    assert origin["orders"][1]["portions"] == [[10, [A]]]  # (still as the older record had them)

    assert fixes_without_cover(origin_fixes(origin)[str(tmp_path / "x.pdf")], 1) == {4: DS}
    again = job_of(s, tmp_path / "x.pdf")
    put_back_orders([again], origin, s)
    assert again.portions == [(5, [A]), (20, [A, B])] and not again.old_places and not again.portions_problem()


def test_a_trial_all_moved_over_keeps_its_places_and_the_mark(tmp_path, s):
    x = firms(job_of(s, page_numbered_transcript(tmp_path / "x.pdf", 20, first=100, cover=COVER)))
    x.portions = [(5, [A]), (20, [A, B])]
    x.docs[0].fixes = {4: DS}
    origin = json.loads(json.dumps(joint_origin([x])))
    assert not counts_covers(origin) and origin["page_fixes"] == {str(tmp_path / "x.pdf"): {"4": DS}}
    assert origin["orders"][0]["portions"] == [[5, [A]], [20, [A, B]]]


def test_rows_in_a_number_typed_arent_given_the_cover_back(tmp_path, s):
    """They count pages of that number, and were never moved."""
    x = firms(job_of(s, page_numbered_transcript(tmp_path / "x.pdf", 20, first=100, cover=COVER)))
    x.case.fields["est_pages"] = FieldState("40", SRC_USER, 1.0, [])
    x.portions = [(10, [A]), (40, [A, B])]
    y = Job(old_places=True, portions=[(10, [A])])
    origin = json.loads(json.dumps(joint_origin([x, y])))
    assert origin["orders"][0]["portions"] == [[10, [A]], [40, [A, B]]]


@pytest.mark.parametrize("docs, rows", [
    ([(20, 1)], [(1, [A]), (20, [A, B])]),
    ([(20, 1)], [(19, [A]), (20, [A, B])]),
    ([(10, 0), (20, 1)], [(10, [A]), (11, [A]), (30, [A, B])]),
    ([(59, 1), (59, 1)], [(59, [A]), (60, [A]), (118, [A, B])]),
    ([(59, 1), (59, 0), (10, 1)], [(59, [A]), (118, [B]), (119, [A]), (128, [A, B])]),
])
def test_rows_given_their_covers_back_come_back_the_same(docs, rows):
    """What a record of a part-moved trial writes, opened again, is the rows the job had."""
    job = old_job(list(rows), *[covered_doc(n, f"{i}.pdf", cover=c) for i, (n, c) in enumerate(docs)])
    job.old_places = False
    job.portions = [r for _, r in enumerate(rows)]
    other = Job(old_places=True)
    orders = trial_orders([job, other], with_covers=True)
    job.portions = [tuple(r) for r in orders[0]["portions"]]
    job.old_places = True
    settle_old_places(job)
    assert job.portions == rows and not job.old_places


def test_a_job_still_waiting_keeps_its_corrected_takes_in_the_old_way_too(tmp_path, s):
    """Its takes moved as the transcript was read, its rows not yet: a record of both must say one thing."""
    a, b, origin = old_two_volumes(tmp_path, s)
    job = job_from_origin(origin, s)
    job.docs += read_docs([str(a)], s)[0]
    remerge(job, s)
    assert job.old_places
    job.docs[0].fixes = {4: DS}
    kept = json.loads(json.dumps(job_origin(job)))["job"]
    assert kept["page_fixes"] == {str(a): {"5": DS}} and "cover_out" not in kept
    assert kept["portions"] == [[6, [A]], [31, [A, B]]]


# ------------------------------------------------------------------ the help, on whose pages
def test_the_help_s_examples_say_whose_pages():
    from minute_filler.help_topics import TOPICS
    text = " ".join(t.html for t in TOPICS)
    assert "40 pages" not in text and "(10 pages, no index)" not in text
    assert "50 by both attorneys" not in text


def test_the_help_says_what_a_flat_save_to_has_inside_it():
    from minute_filler.help_topics import TOPICS
    text = " ".join(" ".join(t.html.split()) for t in TOPICS)
    assert "no folders inside it but the <b>Math</b> folder" not in text
    assert "and the <b>Inputs</b> folder when that is on" in text


# ------------------------------------------------------------------ a record's own list of documents and its count
def record_of(job: Job) -> dict:
    """What a Generate would keep of this job now."""
    return json.loads(json.dumps({**job_origin(job), "case": case_snapshot(job.case)}))


def toasts(window, monkeypatch) -> list:
    said = []
    monkeypatch.setattr(window, "_toast", said.append)
    return said


def open_with_away(window, origin, path, gone):
    """Opens this record with the document at `path` moved to `gone`; the job on screen once what is there is read."""
    path.rename(gone)
    return open_again(window, origin)


def open_again(window, origin):
    assert window.open_past_job(json.dumps(origin)) is True
    wait(window, lambda: window.cur.docs)
    return window.cur


def test_a_generate_while_a_document_is_away_keeps_what_the_record_said(window, tmp_path, s, monkeypatch):
    """b.pdf away. The record made then named a.pdf alone, so opening it settled at once: 31 stayed typed against 30 total
    pages when b.pdf came back, the rows in old places, Alex billed 6 "counted pages 1–6", with no word said."""
    said = toasts(window, monkeypatch)
    a, b, origin = old_two_volumes(tmp_path, s)
    gone = tmp_path / "gone.pdf"
    first = open_with_away(window, origin, b, gone)
    made = record_of(first)
    assert made["sources"] == [str(a)]  # (what was read: a trial day's list would read other days' documents in)
    assert made["job"]["old_sources"] == [str(a), str(b)] and made["job"]["old_count"] == 31
    assert "cover_out" not in made["job"] and made["job"]["portions"] == [[6, [A]], [31, [A, B]]]
    said.clear()
    cur = open_again(window, made)
    assert cur.old_places and cur.portions == [(6, [A]), (31, [A, B])] and cur.case.get("est_pages") == "31"
    assert cur.old_count == 31 and cur.old_sources == [str(a), str(b)]
    assert any(x.startswith("1 document of this job is no longer where it was") for x in said)
    gone.rename(b)
    drop_back(window, b, 2)
    assert_moved_over(cur)


def test_a_document_back_in_its_place_is_read_when_the_record_made_without_it_is_opened(window, tmp_path, s, monkeypatch):
    """The record named b.pdf as away. Back where it was by the time the record is opened, it was never read, and the
    window said it was no longer there."""
    said = toasts(window, monkeypatch)
    a, b, origin = old_two_volumes(tmp_path, s)
    gone = tmp_path / "gone.pdf"
    made = record_of(open_with_away(window, origin, b, gone))
    gone.rename(b)
    said.clear()
    assert window.open_past_job(json.dumps(made)) is True
    wait(window, lambda: len(window.cur.docs) == 2)
    assert_moved_over(window.cur)
    assert not any("no longer where" in x for x in said), said


def test_a_record_of_a_record_made_while_a_document_was_away_says_the_same(window, tmp_path, s):
    """Made again and again while it stays away, the list and the count stay the first record's."""
    a, b, origin = old_two_volumes(tmp_path, s)
    gone = tmp_path / "gone.pdf"
    made = record_of(open_with_away(window, origin, b, gone))
    again = record_of(open_again(window, made))
    assert again["job"]["old_sources"] == made["job"]["old_sources"] and again["job"]["old_count"] == 31
    gone.rename(b)
    cur = open_again(window, again)
    drop_back(window, b, 2)
    assert_moved_over(cur)


def test_a_number_typed_over_the_record_s_count_meanwhile_stays_the_user_s(window, tmp_path, s):
    a, b, origin = old_two_volumes(tmp_path, s)
    gone = tmp_path / "gone.pdf"
    first = open_with_away(window, origin, b, gone)
    first.case.fields["est_pages"] = FieldState("40", SRC_USER, 1.0, [])
    cur = open_again(window, record_of(first))
    assert cur.old_count == 31 and cur.old_total == 31
    gone.rename(b)
    drop_back(window, b, 2)
    assert cur.pages_typed() and cur.invoice_pages() == 40 and not cur.old_places


def test_a_trial_s_record_made_while_a_day_s_document_is_away_says_the_same(window, tmp_path, s):
    """a.pdf (10 pages) away, b.pdf a cover and 20. The record named b.pdf alone: the cover taken at place 1 for 11, rows
    [4, 30], Alex billed 4 "pp. 110–113" for 5 "pp. 100–104", with no word said."""
    a = page_numbered_transcript(tmp_path / "a.pdf", 10, first=100)
    b = page_numbered_transcript(tmp_path / "b.pdf", 20, first=110, cover=COVER)
    job = firms(job_of(s, a, b))
    origin = json.loads(json.dumps(joint_origin([job])))
    del origin["cover_out"]
    origin["orders"][0]["portions"] = [[5, [A]], [31, [A, B]]]
    gone = tmp_path / "gone.pdf"
    first = open_with_away(window, origin, a, gone)
    made = json.loads(json.dumps(joint_origin([first])))
    assert made["sources"] == [str(b)] and made["orders"][0]["old_sources"] == [str(a), str(b)]
    cur = open_again(window, made)
    assert cur.old_places and cur.portions == [(5, [A]), (31, [A, B])]
    gone.rename(a)
    window.add_files([str(a)])
    wait(window, lambda: len(window.cur.docs) == 2)
    assert not cur.old_places and cur.portions == [(5, [A]), (30, [A, B])] and not cur.portions_problem()
    assert [d.ing.name for d in cur.transcripts()] == ["a.pdf", "b.pdf"]
    assert [(p.pages, p.span) for p in cur.invoice_orders()[0].portions] == [(5, "pp. 100–104"), (25, "pp. 105–129")]


def test_nothing_new_in_a_record_once_every_document_is_here(tmp_path, s):
    """Earlier records are compared by their text (billed_split_rule): a job with all its documents writes as it did."""
    a, b, origin = old_two_volumes(tmp_path, s)
    job = job_from_origin(origin, s)
    job.docs += read_docs([str(a), str(b)], s)[0]
    remerge(job, s)
    assert not job.old_places and job.old_count == 0
    kept = record_of(job)
    assert "old_sources" not in kept["job"] and "old_count" not in kept["job"]
    assert "old_sources" not in json.loads(json.dumps(joint_origin([job])))["orders"][0]


def test_the_rule_a_job_was_billed_by_is_still_found_with_a_document_away(tmp_path, s):
    """What a record keeps meanwhile is in the invoice's record and its other files' alike (billed_split_rule)."""
    a, b, origin = old_two_volumes(tmp_path, s)
    job = job_from_origin(origin, s)
    job.docs += read_docs([str(a)], s)[0]
    job.case.set("index_no", "712345/2021")
    remerge(job, s)
    assert job.old_places
    job.portions = None  # (the rows have their own check: this is about the record)
    fill_jobs([job], s, outputs=["agreement", "invoice"])
    lg = ledger_for(s)
    kinds = {x.kind: x for x in lg.activity()}
    assert '"old_sources"' in kinds["agreement"].origin and '"old_sources"' in kinds["invoice"].origin
    assert job.split_rule and billed_split_rule(kinds["agreement"].origin, lg) == job.split_rule


@pytest.mark.parametrize("kept", ["31", True, -1, None, 0, [31]])
def test_a_record_s_kept_count_that_isn_t_one_is_left_out(kept):
    job = job_from_origin({"sources": ["a.pdf"], "job": {"old_count": kept}}, pat_settings())
    assert job.old_count == 0 and job.old_total == 0


@pytest.mark.parametrize("kept", ["a.pdf", 3, None, {"a": 1}, []])
def test_a_record_s_kept_list_that_isn_t_one_is_left_out(kept):
    origin = {"sources": ["a.pdf"], "job": {"old_sources": kept}, "orders": [{"old_sources": kept}, "?"]}
    assert job_from_origin(origin, pat_settings()).old_sources == ["a.pdf"]
    assert record_documents(origin) == ["a.pdf"]


def test_the_documents_a_record_says_it_was_made_from():
    assert record_documents({"sources": ["x\\a.pdf"], "job": {"old_sources": ["w\\a.pdf", "x\\b.pdf"]}}) == [
        "x\\a.pdf", "x\\b.pdf"]  # (a.pdf back from another folder is the one read)
    days = [{"old_sources": ["a.pdf", "b.pdf", "c.pdf"]}, {"old_sources": ["a.pdf", "b.pdf", "c.pdf"]}]
    assert record_documents({"sources": ["b.pdf"], "joint": True, "orders": days}) == ["b.pdf", "a.pdf", "c.pdf"]
    assert record_documents({"sources": ["a.pdf"], "job": "?", "orders": "?"}) == ["a.pdf"]
    assert record_documents({}) == []


def test_a_record_s_kept_list_follows_a_folder_renamed(tmp_path, s):
    from minute_filler.batch import follow_moves
    from minute_filler.records import moved_origin
    old, new = tmp_path / "old", tmp_path / "new"
    data = {"sources": [str(old / "a.pdf")], "job": {"old_sources": [str(old / "a.pdf"), str(old / "b.pdf")]},
            "orders": [{"dates": "6/3/2026", "old_sources": [str(old / "b.pdf"), "elsewhere.pdf"]}]}
    assert moved_origin(data, old, new) is True
    assert data["job"]["old_sources"] == [str(new / "a.pdf"), str(new / "b.pdf")]
    assert data["orders"][0]["old_sources"] == [str(new / "b.pdf"), "elsewhere.pdf"]
    job = Job(old_sources=[str(old / "a.pdf"), str(tmp_path / "c.pdf")])
    follow_moves([job], [(old, new)])
    assert job.old_sources == [str(new / "a.pdf"), str(tmp_path / "c.pdf")]


def test_a_document_taken_out_of_the_job_is_no_longer_waited_for(window, tmp_path, s):
    """The user took it out: nothing says it will come back, and a record made now doesn't say it is away."""
    a, b, origin = old_two_volumes(tmp_path, s)
    cur = open_again(window, origin)
    wait(window, lambda: len(cur.docs) == 2)
    assert "old_sources" not in record_of(cur)["job"]
    window._remove_doc(cur, next(d for d in cur.docs if d.ing.name == "b.pdf"))
    assert cur.old_sources == [str(a)] and "old_sources" not in record_of(cur)["job"]


@pytest.mark.parametrize("named, here, away", [
    (["x\\a.pdf", "x\\b.pdf"], ["x\\a.pdf"], ["x\\b.pdf"]),
    (["x\\a.pdf"], ["y\\A.PDF"], []),  # (back from another folder: by its name)
    (["am\\t.pdf", "pm\\t.pdf"], ["am\\t.pdf"], ["pm\\t.pdf"]),  # (one name, two documents: one back isn't both)
    (["am\\t.pdf", "pm\\t.pdf"], ["pm\\t.pdf"], ["am\\t.pdf"]),
    (["am\\t.pdf", "pm\\t.pdf"], ["y\\t.pdf"], ["pm\\t.pdf"]),
    (["am\\t.pdf", "pm\\t.pdf"], ["y\\t.pdf", "z\\t.pdf"], []),
    (["am\\t.pdf", "pm\\t.pdf"], ["pm\\t.pdf", "y\\t.pdf"], []),
    ([], ["a.pdf"], []),
])
def test_which_of_a_record_s_documents_arent_here(named, here, away):
    assert documents_not_here(named, here) == away


def same_name_volumes(tmp_path, s):
    """A day of two transcripts of one file name: AM (a cover and 20 pages from 100), PM (10 from 200), rows as an older
    version kept them."""
    (tmp_path / "AM").mkdir()
    (tmp_path / "PM").mkdir()
    am = page_numbered_transcript(tmp_path / "AM" / "Transcript.pdf", 20, first=100, cover=COVER)
    pm = page_numbered_transcript(tmp_path / "PM" / "Transcript.pdf", 10, first=200)
    origin = old_record(firms(job_of(s, am, pm)))
    origin["job"]["portions"] = [[6, [A]], [31, [A, B]]]
    return am, pm, origin


def assert_same_names_moved_over(cur):
    assert not cur.old_places and cur.portions == [(5, [A]), (30, [A, B])] and not cur.portions_problem()
    assert not cur.pages_typed() and cur.invoice_pages() == 30
    assert [(p.pages, p.span) for p in cur.invoice_orders()[0].portions] == [(5, "pp. 100–104"), (25, "pp. 105–119, 200–209")]


def test_two_documents_of_one_name_wait_for_each_other(window, tmp_path, s):
    """AM back, PM away: its name was on the record, so it took the day as all back. PM dropped later: 31 typed, rows
    [6, 31], "counted pages 1–6"."""
    am, pm, origin = same_name_volumes(tmp_path, s)
    gone = tmp_path / "gone.pdf"
    cur = open_with_away(window, origin, pm, gone)
    assert cur.old_places and cur.portions == [(6, [A]), (31, [A, B])]
    gone.rename(pm)
    drop_back(window, pm, 2)
    assert_same_names_moved_over(cur)


def test_two_documents_of_one_name_go_by_their_paths_whichever_comes_first(window, tmp_path, s):
    """PM back first, AM after: in the order they came, Alex was billed pp. 200–205."""
    am, pm, origin = same_name_volumes(tmp_path, s)
    gone = tmp_path / "gone.pdf"
    cur = open_with_away(window, origin, am, gone)
    gone.rename(am)
    drop_back(window, am, 2)
    assert [d.path for d in cur.transcripts()] == [str(am), str(pm)]
    assert_same_names_moved_over(cur)


def test_two_documents_of_one_name_read_at_once_in_the_other_order(tmp_path, s):
    am, pm, origin = same_name_volumes(tmp_path, s)
    job = job_from_origin(origin, s)
    job.docs += read_docs([str(pm), str(am)], s)[0]
    remerge(job, s)
    assert [d.path for d in job.transcripts()] == [str(am), str(pm)]
    assert_same_names_moved_over(job)


def test_two_documents_of_one_name_back_from_other_folders_hold_the_rows(tmp_path, s):
    """Nothing says which is which, so nor where the cover was: never moved by a guess, and the rows don't fit."""
    am, pm, origin = same_name_volumes(tmp_path, s)
    (tmp_path / "X").mkdir()
    (tmp_path / "Y").mkdir()
    x, y = am.rename(tmp_path / "X" / "Transcript.pdf"), pm.rename(tmp_path / "Y" / "Transcript.pdf")
    job = job_from_origin(origin, s)
    job.docs += read_docs([str(x), str(y)], s)[0]
    remerge(job, s)
    assert not job.old_places and job.portions == [(6, [A]), (31, [A, B])] and job.portions_problem()


def test_two_documents_of_one_name_one_from_another_folder_is_told_by_the_other_s_path(tmp_path, s):
    am, pm, origin = same_name_volumes(tmp_path, s)
    (tmp_path / "X").mkdir()
    x = pm.rename(tmp_path / "X" / "Transcript.pdf")
    job = job_from_origin(origin, s)
    job.docs += read_docs([str(x), str(am)], s)[0]
    remerge(job, s)
    assert [d.path for d in job.transcripts()] == [str(am), str(x)]
    assert_same_names_moved_over(job)


def marked_two_volumes(tmp_path, s, *cover):
    """A day of a.pdf (20 pages from 100, after a cover when `cover` says) and b.pdf (10 from 200), as a record of now
    keeps it: Alex alone ordered 100-104."""
    a = page_numbered_transcript(tmp_path / "a.pdf", 20, first=100, cover=cover[0] if cover else "")
    b = page_numbered_transcript(tmp_path / "b.pdf", 10, first=200)
    job = firms(job_of(s, a, b))
    job.portions = [(5, [A]), (30, [A, B])]
    return a, b, record_of(job)


def test_on_a_record_that_says_the_cover_is_out_the_first_document_back_goes_first(window, tmp_path, s):
    """It came last: [b, a], no hold, Alex billed "pp. 200–204" for "pp. 100–104". A record with no cover sorted right,
    so the newer record did worse than the older."""
    a, b, origin = marked_two_volumes(tmp_path, s, COVER)
    assert origin["job"]["cover_out"] is True
    gone = tmp_path / "gone.pdf"
    cur = open_with_away(window, origin, a, gone)
    assert [d.ing.name for d in cur.docs] == ["b.pdf"]
    gone.rename(a)
    drop_back(window, a, 2)
    assert_moved_over(cur)


def test_so_on_a_record_with_no_cover_at_all(window, tmp_path, s):
    a, b, origin = marked_two_volumes(tmp_path, s)
    assert "cover_out" not in origin["job"]
    gone = tmp_path / "gone.pdf"
    cur = open_with_away(window, origin, a, gone)
    gone.rename(a)
    drop_back(window, a, 2)
    assert_moved_over(cur)


def test_a_generate_while_the_first_document_is_away_keeps_its_place_on_a_marked_record(window, tmp_path, s):
    a, b, origin = marked_two_volumes(tmp_path, s, COVER)
    gone = tmp_path / "gone.pdf"
    made = record_of(open_with_away(window, origin, a, gone))
    assert made["sources"] == [str(b)] and made["job"]["old_sources"] == [str(a), str(b)]
    # (the document with the cover is the one away: without the mark, rows that had lost the cover would lose it again)
    assert made["job"]["cover_out"] is True
    cur = open_again(window, made)
    gone.rename(a)
    drop_back(window, a, 2)
    assert_moved_over(cur)


def test_a_document_new_to_the_job_goes_after_those_the_record_names(tmp_path, s):
    a, b, origin = marked_two_volumes(tmp_path, s, COVER)
    c = page_numbered_transcript(tmp_path / "c.pdf", 5, first=300)
    job = job_from_origin(origin, s)
    job.docs += read_docs([str(c), str(b), str(a)], s)[0]
    remerge(job, s)
    assert [d.ing.name for d in job.transcripts()] == ["a.pdf", "b.pdf", "c.pdf"]


def test_a_trial_s_day_goes_by_its_own_documents_on_a_marked_record_too(tmp_path, s):
    a, b, _ = marked_two_volumes(tmp_path, s, COVER)
    day = firms(job_of(s, b))
    origin = json.loads(json.dumps(joint_origin([firms(job_of(s, a, b))])))
    origin["orders"][0]["portions"] = [[5, [A]], [30, [A, B]]]
    put_back_orders([day], origin, s)
    assert day.old_sources == [str(a), str(b)] and not day.old_places
    day.docs += read_docs([str(a)], s)[0]
    remerge(day, s)
    assert [d.ing.name for d in day.transcripts()] == ["a.pdf", "b.pdf"]


def test_a_trial_s_day_doesn_t_wait_for_the_documents_of_its_other_days(tmp_path, s):
    """Read into their own days, they are no documents of this one: a day's corrected transcript can settle by its own."""
    x = page_numbered_transcript(tmp_path / "x.pdf", 15, first=100, cover=COVER)
    y = page_numbered_transcript(tmp_path / "y.pdf", 20, first=200, caption=TITLE.replace("3", "4"))
    docs, errors = read_docs([str(x), str(y)], s)
    assert not errors
    jobs = group(docs, s)
    assert len(jobs) == 2
    day = next(j for j in jobs if j.docs[0].ing.name == "x.pdf")
    for j in jobs:
        j.case.attorneys = [replace(ALEX), replace(DANA)]
    origin = json.loads(json.dumps(joint_origin(jobs)))
    del origin["cover_out"]
    row = next(r for r in origin["orders"] if r["dates"] == day.case.get("dates"))
    row["portions"] = [[6, [A]], [21, [A, B]]]  # (it was a cover and 20 then)
    put_back_orders(jobs, origin, s)
    assert day.old_sources == [str(x)] and not day.old_places
    assert day.portions == [(5, [A]), (20, [A, B])] and day.portions_problem()


def own_count_two_volumes(tmp_path, s, est, source=SRC_USER, rows=None):
    """a.pdf (a cover and 20: Pat's first 8) and b.pdf (10: Pat's first 5), the record's Pages holding `est`."""
    s.profile.initials = "P.R."
    a = page_numbered_transcript(tmp_path / "a.pdf", 20, first=100, initials=[PR] * 8 + [DS] * 12, cover=COVER)
    b = page_numbered_transcript(tmp_path / "b.pdf", 10, first=200, initials=[PR] * 5 + [DS] * 5)
    origin = json.loads(json.dumps({"sources": [str(a), str(b)],
                                    "job": {"front_owner": {str(a): PR}, "att_touched": True, "portions": rows},
                                    "case": {"fields": {"est_pages": [est, source, 1.0]},
                                             "attorneys": [ALEX.to_dict(), DANA.to_dict()]}}))
    return a, b, origin


def test_an_own_count_across_two_documents_waits_for_both(tmp_path, s):
    """14 was 8, the cover and 5. a.pdf's 21 pages were more than 14, so it settled on a.pdf alone: b.pdf back, it billed
    14 of the 13 of Pat's, no rows so no hold."""
    a, b, origin = own_count_two_volumes(tmp_path, s, "14")
    job = job_from_origin(origin, s)
    assert job.old_count == 0 and job.old_sources == [str(a), str(b)]
    job.docs += read_docs([str(a)], s)[0]
    remerge(job, s)
    assert job.old_places and job.case.get("est_pages") == "14" and job.pages_typed()
    job.docs += read_docs([str(b)], s)[0]
    remerge(job, s)
    assert not job.old_places and not job.pages_typed() and job.invoice_pages() == job.own_pages() == 13


def test_an_own_count_with_rows_cut_in_it_waits_for_both_too(tmp_path, s):
    """Its rows end on 14 too: the pages here being more than that says nothing either."""
    a, b, origin = own_count_two_volumes(tmp_path, s, "14", rows=[[5, [A]], [14, [A, B]]])
    job = job_from_origin(origin, s)
    job.docs += read_docs([str(a)], s)[0]
    remerge(job, s)
    assert job.old_places and job.pages_typed()
    job.docs += read_docs([str(b)], s)[0]
    remerge(job, s)
    assert not job.old_places and not job.pages_typed() and job.invoice_pages() == 13


def test_an_own_count_with_rows_counted_in_the_old_total_moves_them(tmp_path, s):
    a, b, origin = own_count_two_volumes(tmp_path, s, "14", rows=[[5, [A]], [31, [A, B]]])
    job = job_from_origin(origin, s)
    assert job.old_total == 31
    job.docs += read_docs([str(a)], s)[0]
    remerge(job, s)
    assert job.old_places
    job.docs += read_docs([str(b)], s)[0]
    remerge(job, s)
    assert not job.old_places and job.portions == [(4, [A]), (30, [A, B])] and job.invoice_pages() == 13


def test_a_number_really_typed_over_two_documents_stays(tmp_path, s):
    a, b, origin = own_count_two_volumes(tmp_path, s, "50")
    job = job_from_origin(origin, s)
    job.docs += read_docs([str(a)], s)[0]
    remerge(job, s)
    assert job.old_places and job.invoice_pages() == 50
    job.docs += read_docs([str(b)], s)[0]
    remerge(job, s)
    assert not job.old_places and job.pages_typed() and job.invoice_pages() == 50


def test_a_typed_count_of_exactly_the_pages_here_needs_no_more(tmp_path, s):
    """A letter may be away for good: the pages adding up to exactly the number say nothing is missing."""
    path = page_numbered_transcript(tmp_path / "Roe.pdf", 20, first=819, cover=COVER)
    job = job_from_origin({"sources": [str(path), str(tmp_path / "letter.pdf")], "job": {},
                           "case": {"fields": {"est_pages": ["21", SRC_USER, 1.0]}}}, s)
    job.docs += read_docs([str(path)], s)[0]
    remerge(job, s)
    assert not job.old_places and not job.pages_typed() and job.case.get("est_pages") == "20"


@pytest.mark.parametrize("pages, count", [(15, 25), (35, 45)])
def test_a_corrected_transcript_with_another_document_away_goes_back_to_the_count(window, tmp_path, s, pages, count):
    """a.pdf reissued shorter or longer, b.pdf away, then back. 31 stayed typed against 25 or 45 total pages, and the
    rows fitted it: no hold, the old count billed, with no word said."""
    a, b, origin = old_two_volumes(tmp_path, s)
    gone = tmp_path / "gone.pdf"
    b.rename(gone)
    a.unlink()
    page_numbered_transcript(a, pages, first=100, cover=COVER)
    cur = open_again(window, origin)
    gone.rename(b)
    drop_back(window, b, 2)
    assert not cur.old_places and not cur.pages_typed() and cur.case.get("est_pages") == str(count)
    assert cur.portions == [(5, [A]), (30, [A, B])] and "rows don't end on" in cur.portions_problem()


@pytest.mark.parametrize("pages, count", [(15, 25), (35, 45)])
def test_so_on_a_record_with_no_cover(window, tmp_path, s, pages, count):
    a, b, origin = marked_two_volumes(tmp_path, s)
    gone = tmp_path / "gone.pdf"
    b.rename(gone)
    a.unlink()
    page_numbered_transcript(a, pages, first=100)
    cur = open_again(window, origin)
    gone.rename(b)
    drop_back(window, b, 2)
    assert not cur.pages_typed() and cur.case.get("est_pages") == str(count) and cur.portions_problem()


@pytest.mark.parametrize("pages, count", [(15, 25), (35, 45)])
def test_so_on_a_record_that_says_the_cover_is_out(window, tmp_path, s, pages, count):
    """Nothing to move there, but its count is held all the same: rows as they are, and they don't fit."""
    a, b, origin = marked_two_volumes(tmp_path, s, COVER)
    assert origin["job"]["cover_out"] is True
    gone = tmp_path / "gone.pdf"
    b.rename(gone)
    a.unlink()
    page_numbered_transcript(a, pages, first=100, cover=COVER)
    cur = open_again(window, origin)
    gone.rename(b)
    drop_back(window, b, 2)
    assert not cur.pages_typed() and cur.case.get("est_pages") == str(count)
    assert cur.portions == [(5, [A]), (30, [A, B])] and cur.portions_problem()


def test_one_transcript_back_under_another_name_has_no_order_to_tell(window, tmp_path, s):
    """Its rows were left where they were, for a look: with one transcript nothing is in doubt."""
    path = page_numbered_transcript(tmp_path / "Roe.pdf", 20, first=819, cover=COVER)
    origin = old_record(firms(job_of(s, path)))
    origin["job"]["portions"] = [[11, [A]], [21, [A, B]]]
    renamed = tmp_path / "Roe corrected.pdf"
    path.rename(renamed)
    assert window.open_past_job(json.dumps(origin)) is True
    window.add_files([str(renamed)], same_job=True)
    wait(window, lambda: window.cur.docs)
    cur = window.cur
    assert not cur.old_places and cur.portions == [(10, [A]), (20, [A, B])] and not cur.portions_problem()
    assert cur.invoice_pages() == 20


def test_a_longer_transcript_with_a_letter_away_for_good_needs_no_letter(tmp_path, s):
    """More pages than the count the record read: a transcript got longer. The count goes, the rows are held for a look."""
    path = page_numbered_transcript(tmp_path / "Roe.pdf", 30, first=819, cover=COVER)
    job = job_from_origin({"sources": [str(path), str(tmp_path / "letter.pdf")], "job": {"portions": [[11, [A]], [21, [A, B]]]},
                           "case": {"fields": {"est_pages": ["21", SRC_PDF, 0.95]}, "attorneys": [ALEX.to_dict(), DANA.to_dict()]}},
                          s)
    job.case.fields["est_pages"].source = SRC_USER  # (as the window keeps it, the letter being a PDF away)
    job.docs += read_docs([str(path)], s)[0]
    remerge(job, s)
    assert not job.old_places and not job.pages_typed() and job.case.get("est_pages") == "30"
    assert job.portions == [(10, [A]), (20, [A, B])] and job.portions_problem()


def test_a_record_that_says_the_cover_is_out_counted_no_cover(tmp_path, s):
    """Its 30 are 29 and 1, the cover no page: a.pdf's 29 and its cover aren't all of them."""
    a = page_numbered_transcript(tmp_path / "a.pdf", 29, first=100, cover=COVER)
    b = page_numbered_transcript(tmp_path / "b.pdf", 1, first=200)
    origin = record_of(firms(job_of(s, a, b)))
    assert origin["job"]["cover_out"] is True and origin["case"]["fields"]["est_pages"][0] == "30"
    job = job_from_origin(origin, s)
    job.case.fields["est_pages"].source = SRC_USER
    job.docs += read_docs([str(a)], s)[0]
    remerge(job, s)
    assert job.old_count == 30 and job.case.get("est_pages") == "30" and job.pages_typed()
    job.docs += read_docs([str(b)], s)[0]
    remerge(job, s)
    assert job.old_count == 0 and not job.pages_typed() and job.invoice_pages() == 30


@pytest.mark.parametrize("record", [["21", SRC_USER, 1.0], ["20", SRC_PDF, 0.95]])
def test_a_marked_record_doesn_t_take_a_number_as_its_old_count(tmp_path, s, record):
    """Without covers among its count a number one more than the pages is the user's, on a job that has a cover: as the
    record's, or typed over the count it read."""
    a = page_numbered_transcript(tmp_path / "a.pdf", 20, first=100, cover=COVER)
    job = job_from_origin({"sources": [str(a)], "job": {"cover_out": True},
                           "case": {"fields": {"est_pages": record}}}, s)
    job.case.fields["est_pages"] = FieldState("21", SRC_USER, 1.0, [])
    job.docs += read_docs([str(a)], s)[0]
    remerge(job, s)
    assert job.pages_typed() and job.invoice_pages() == 21


def test_a_job_taking_rows_from_a_job_opened_again_takes_what_its_record_said(tmp_path, s):
    """A marked record: not moved, and still in the record's order."""
    from minute_filler.batch import make_doc
    a = job_of(s, page_numbered_transcript(tmp_path / "a.pdf", 5))
    other = Job(portions=[(2, [A]), (15, [A, B])], old_total=15, old_count=15, old_sources=["a.pdf", "b.pdf"])
    empty = Job()
    for job in (other, empty):
        job.case.set("index_no", a.case.get("index_no"))
        job.case.set("dates", a.case.get("dates"))
    job, = group([make_doc(a.docs[0].ing, a.docs[0].regex, s, path="a.pdf")], s, [empty, other])
    assert not job.old_places and job.portions == [(2, [A]), (15, [A, B])]
    assert (job.old_total, job.old_count, job.old_sources) == (15, 15, ["a.pdf", "b.pdf"])


def merged(tmp_path, s, mine: Job, other: Job) -> Job:
    """`mine`, of the case of a new transcript, joined by it with `other`."""
    from minute_filler.batch import make_doc
    a = job_of(s, page_numbered_transcript(tmp_path / "a.pdf", 5))
    for job in (mine, other):
        job.case.set("index_no", a.case.get("index_no"))
        job.case.set("dates", a.case.get("dates"))
    job, = group([make_doc(a.docs[0].ing, a.docs[0].regex, s, path="a.pdf")], s, [mine, other])
    return job


def test_a_job_with_its_own_rows_and_record_keeps_them(tmp_path, s):
    job = merged(tmp_path, s, Job(portions=[(5, [A])], old_sources=["a.pdf"]),
                 Job(portions=[(2, [A]), (15, [A, B])], old_total=15, old_count=15, old_sources=["b.pdf"]))
    assert job.portions == [(5, [A])] and job.old_sources == ["a.pdf"] and job.old_count == 0


def test_a_job_opened_again_joined_by_a_new_one_keeps_what_its_record_said(tmp_path, s):
    job = merged(tmp_path, s, Job(old_sources=["a.pdf", "b.pdf"], old_total=15, old_count=15), Job())
    assert job.old_sources == ["a.pdf", "b.pdf"] and (job.old_total, job.old_count) == (15, 15)


def test_what_a_record_said_goes_with_the_rows_it_kept(tmp_path, s):
    """They count the pages in that record's order."""
    job = merged(tmp_path, s, Job(old_sources=["a.pdf"]),
                 Job(portions=[(2, [A]), (15, [A, B])], old_total=15, old_count=15, old_sources=["b.pdf", "a.pdf"]))
    assert job.portions == [(2, [A]), (15, [A, B])] and job.old_sources == ["b.pdf", "a.pdf"]


def test_a_trial_s_own_count_is_its_rows_and_never_typed(tmp_path, s):
    """A day's record has no count: its rows end on the day's pages, which a longer transcript passes."""
    a = page_numbered_transcript(tmp_path / "a.pdf", 25, first=819, cover=COVER)
    job = firms(job_of(s, a))
    origin = json.loads(json.dumps(joint_origin([job])))
    del origin["cover_out"]
    origin["sources"].append(str(tmp_path / "another day.pdf"))
    origin["orders"][0]["portions"] = [[11, [A]], [21, [A, B]]]
    put_back_orders([job], origin, s)
    assert not job.old_places and job.portions == [(10, [A]), (20, [A, B])] and job.portions_problem()


# ------------------------------------------------------------------ what a job bills while a document is away
HOLDS_31 = ("⚠ Pages still holds this job's count from its record, 31 total pages, until b.pdf is back: it counts any "
            "Min-U-Script cover and every reporter's pages")


def test_pages_says_it_holds_the_record_s_count_while_a_document_is_away(window, tmp_path, s):
    """31 billed for the 30 there are, under "Typed by you", which nobody did."""
    a, b, origin = old_two_volumes(tmp_path, s)
    gone = tmp_path / "gone.pdf"
    cur = open_with_away(window, origin, b, gone)
    assert cur.invoice_pages() == 31 and cur.pages_typed() and not cur.invoice_hold()  # (a warning, no hold)
    line, warning = cur.pages_help()
    assert warning == HOLDS_31 and "Typed by you" not in line
    assert line.startswith("From this job's record · the transcript has 20 total pages")
    window._show_job()
    assert window.pages_warn.text() == HOLDS_31
    assert any(p.text == HOLDS_31 for p in window._problems())
    gone.rename(b)
    drop_back(window, b, 2)
    assert cur.pages_help()[1] == "" and window.pages_warn.text() == ""


def test_so_it_says_on_a_transcript_of_two_reporters(tmp_path, s):
    """The user's invoice bills every reporter's pages meanwhile: 31 for Pat's 8 here, 13 once b.pdf is back."""
    a, b, origin = own_count_two_volumes(tmp_path, s, "31", SRC_PDF)
    job = job_from_origin(origin, s)
    job.case.fields["est_pages"].source = SRC_USER  # (as the window keeps it: MainWindow.open_past_job)
    job.docs += read_docs([str(a)], s)[0]
    remerge(job, s)
    assert job.invoice_pages() == 31 and job.own_pages() == 8 and job.pages_help()[1] == HOLDS_31
    job.docs += read_docs([str(b)], s)[0]
    remerge(job, s)
    assert job.invoice_pages() == job.own_pages() == 13 and job.pages_help()[1] == ""


def test_it_names_every_pdf_away(tmp_path, s):
    a = page_numbered_transcript(tmp_path / "a.pdf", 5, first=100)
    job = job_from_origin({"sources": [str(a), str(tmp_path / "b.pdf"), str(tmp_path / "c.pdf"), str(tmp_path / "d.eml")],
                           "job": {}, "case": {"fields": {"est_pages": ["31", SRC_PDF, 0.95]}}}, s)
    job.case.fields["est_pages"].source = SRC_USER
    job.docs += read_docs([str(a)], s)[0]
    remerge(job, s)
    assert "31 total pages, until b.pdf and c.pdf are back:" in job.pages_help()[1]


def test_a_record_that_says_the_cover_is_out_says_nothing_of_a_cover_here(window, tmp_path, s):
    a, b, origin = marked_two_volumes(tmp_path, s, COVER)
    gone = tmp_path / "gone.pdf"
    cur = open_with_away(window, origin, b, gone)
    assert cur.pages_help()[1] == ("⚠ Pages still holds this job's count from its record, 30 total pages, until b.pdf is "
                                   "back: it counts every reporter's pages")


def test_a_number_really_typed_is_said_to_be_typed(tmp_path, s):
    a, b, origin = own_count_two_volumes(tmp_path, s, "50")
    job = job_from_origin(origin, s)
    job.docs += read_docs([str(a)], s)[0]
    remerge(job, s)
    line, warning = job.pages_help()
    assert line.startswith("Typed by you ·") and warning == ""


def test_a_number_typed_over_the_record_s_count_is_said_to_be_typed(window, tmp_path, s):
    a, b, origin = old_two_volumes(tmp_path, s)
    gone = tmp_path / "gone.pdf"
    cur = open_with_away(window, origin, b, gone)
    cur.case.fields["est_pages"] = FieldState("40", SRC_USER, 1.0, [])
    line, warning = cur.pages_help()
    assert line.startswith("Typed by you ·") and warning == ""


def test_its_own_warning_keeps_the_pdf_s_after_it(window, tmp_path, s):
    a, b, origin = old_two_volumes(tmp_path, s)
    gone = tmp_path / "gone.pdf"
    cur = open_with_away(window, origin, b, gone)
    cur.docs[0].ing.count.warning = "⚠ 30 of the PDF's 96 total pages were taken for the word index"
    assert cur.pages_help()[1] == HOLDS_31 + "\n30 of the PDF's 96 total pages were taken for the word index"


def test_an_old_own_count_back_from_another_folder_goes_back_to_the_count(tmp_path, s):
    """Whose pages... keeps the first pages' owner by the path it was at: not found, 9 stayed a number typed, and billed
    the cover."""
    old_path = tmp_path / "Roe.pdf"
    (tmp_path / "x").mkdir()
    moved = shared_with_cover(tmp_path / "x", s)
    job = job_from_origin(own_count_record(old_path, "9"), s)
    job.docs += read_docs([str(moved)], s)[0]
    remerge(job, s)
    assert not job.pages_typed() and job.invoice_pages() == job.own_pages() == 8


def test_whose_cover_it_was_goes_by_the_document_s_name_only_when_its_path_says_nothing():
    shared = covered_doc(5, path="x\\Roe.pdf")
    shared.ing.name = "Roe.pdf"
    shared.ing.marks = [PageMark(100, PR), PageMark(101, PR), PageMark(102, DS), PageMark(103, DS), PageMark(104, DS)]
    assert Job(docs=[shared], own=(PR,), front_owner={"y\\Roe.pdf": PR})._cover_billed(shared) is True
    assert Job(docs=[shared], own=(PR,), front_owner={"y\\Roe.pdf": DS})._cover_billed(shared) is False
    assert Job(docs=[shared], own=(PR,), front_owner={"y\\Other.pdf": PR})._cover_billed(shared) is False
    # (its own path first)
    assert Job(docs=[shared], own=(PR,), front_owner={"y\\Roe.pdf": PR, "x\\Roe.pdf": DS})._cover_billed(shared) is False


# ------------------------------------------------------------------ what is already on a run sheet
FALLS_WHO = [PR] * 39 + [DS] * 20 + [PR] * 38 + [DS] * 2 + [PR] * 12


def test_a_falling_day_on_an_older_run_sheet_gets_the_takes_it_lost(tmp_path, sheets):
    """An earlier version kept Pat's three takes. Dana's overlap them by more than one number, so "already has these
    takes: nothing was added": 89 of the 111 total pages on the sheet, with no word said."""
    s = sheets
    job = job_of(s, printed_pdf(tmp_path / "Roe.pdf", FALLS, FALLS_WHO))
    old = add(job.case, [Row(DAY, "Pat", 39, 1), Row(DAY, "Pat", 38, 60), Row(DAY, "Pat", 12, 100)], s)
    again = add(job.case, job.runsheet_opts(s).rows, s, old.path)
    assert (again.added, again.skipped) == (2, 3)
    assert sum(p for _, p, _ in sheet_of(again)) == 111
    assert add(job.case, job.runsheet_opts(s).rows, s, old.path).added == 0


def test_two_volumes_each_numbered_from_1_keep_their_takes_on_a_new_sheet(tmp_path, sheets):
    """Pat 1-20 of AM.pdf, Dana 1-15 of PM.pdf: "with 1 take. (1 take was on it already.)"."""
    s = sheets
    job = job_of(s, printed_pdf(tmp_path / "AM.pdf", list(range(1, 21)), [PR] * 20),
                 printed_pdf(tmp_path / "PM.pdf", list(range(1, 16)), [DS] * 15))
    made = add(job.case, job.runsheet_opts(s).rows, s)
    assert (made.added, made.skipped) == (2, 0) and sorted(p for _, p, _ in sheet_of(made)) == [15, 20]
    assert add(job.case, job.runsheet_opts(s).rows, s, made.path).added == 0


def test_two_volumes_of_one_reporter_each_numbered_from_1_too(tmp_path, sheets):
    s = sheets
    job = job_of(s, printed_pdf(tmp_path / "AM.pdf", list(range(1, 21)), [PR] * 20),
                 printed_pdf(tmp_path / "PM.pdf", list(range(1, 16)), [PR] * 15))
    made = add(job.case, job.runsheet_opts(s).rows, s)
    assert (made.added, made.skipped) == (2, 0) and sum(p for _, p, _ in sheet_of(made)) == 35


def test_one_file_under_two_paths_is_one_take(tmp_path, sheets):
    s = sheets
    (tmp_path / "copy").mkdir()
    a = printed_pdf(tmp_path / "Roe.pdf", list(range(1, 21)), [PR] * 20)
    b = printed_pdf(tmp_path / "copy" / "Roe.pdf", list(range(1, 21)), [PR] * 20)
    made = add(job_of(s, a).case, job_of(s, a, b).runsheet_opts(s).rows, s)
    assert (made.added, made.skipped) == (1, 1)


@pytest.mark.parametrize("a, b, among, same", [
    # the row there is another reporter's of this run, starting apart: not this take, however many numbers they share
    (Row(DAY, "DS", 20, 10), Row(DAY, "Pat", 39, 1), {"ds", "pat"}, False),
    (Row(DAY, "DS", 2, 10), Row(DAY, "Pat", 39, 1), {"ds", "pat"}, False),
    # its own reporter under another name: "DS" isn't among those of this run
    (Row(DAY, "Dana", 32, 164), Row(DAY, "DS", 30, 165), {"dana", "pat"}, True),
    # from the same page: a take corrected to another reporter, the same take
    (Row(DAY, "DS", 32, 164), Row(DAY, "Pat", 32, 164), {"ds", "pat"}, True),
    # so with its end moved: the sheet is the user's to put right, and added it would count those pages twice
    (Row(DAY, "DS", 15, 165, corrected=True), Row(DAY, "Pat", 50, 130), {"ds", "pat"}, True),
    (Row(DAY, "Pat", 39, 1), Row(DAY, "Pat", 39, 1), {"ds", "pat"}, True),
    # no first number here to say it starts apart
    (Row(DAY, "CD", 3, None, numbers=[None, 5, 6]), Row(DAY, "AB", 5, 1), {"cd", "ab"}, False),
])
def test_what_is_the_same_take_among_a_run_s_reporters(a, b, among, same):
    assert a.same_take(b, among) is same


@pytest.mark.parametrize("a, b, same", [
    (Row(DAY, "Pat", 20, 1, doc="a.pdf", at=0), Row(DAY, "DS", 15, 1, doc="b.pdf", at=0), False),
    (Row(DAY, "Pat", 20, 1, doc="a.pdf", at=0), Row(DAY, "Pat", 15, 1, doc="b.pdf", at=0), False),
    (Row(DAY, "Pat", 20, 1, doc="a.pdf", at=0), Row(DAY, "Pat", 20, 2, doc="b.pdf", at=0), False),
    (Row(DAY, "Pat", 20, 1, doc="a.pdf", at=0), Row(DAY, "PAT", 20, 1, doc="b.pdf", at=5), True),
    (Row(DAY, "Pat", 20, 1, doc="a.pdf", at=0), Row(DAY, "Pat", 20, 1), True),  # (on the run sheet: no document)
])
def test_rows_of_two_documents_are_one_take_only_when_all_alike(a, b, same):
    assert a.same_take(b) is same


@pytest.mark.parametrize("a, b, same", [
    # a Start of 0 or none on the sheet: only the reporter and the count to go by, the reporter under its initials too
    (Row(DAY, "Kim Park", 27, 114, initials="kp"), Row(DAY, "KP", 27, 0), True),
    (Row(DAY, "Kim Park", 27, 114, initials="kp"), Row(DAY, "KP", 27, None), True),
    (Row(DAY, "KP", 27, 0), Row(DAY, "Kim Park", 27, 114, initials="kp"), True),
    (Row(DAY, "Kim Park", 27, 114, initials="kp"), Row(DAY, "DS", 27, 0), False),
    (Row(DAY, "Kim Park", 27, 114, initials="kp"), Row(DAY, "KP", 26, 0), False),
    # a first page not read, under another label: one number in common is no fall, it has no first number to differ
    (Row(DAY, "Casey", 2, None, numbers=[None, 5], initials="cd"), Row(DAY, "CD", 2, 4), True),
    (Row(DAY, "CD", 2, 4), Row(DAY, "Casey", 2, None, numbers=[None, 5], initials="cd"), True),
])
def test_what_is_the_same_take_without_numbers_to_go_by(a, b, same):
    assert a.same_take(b) is same


def test_a_blank_label_is_nobody_s_initials():
    """A take of no initials on the sheet with no reporter yet isn't the take of a reporter whose initials aren't known."""
    assert not Row(DAY, "Pat", 27, 114).same_take(Row(DAY, "", 27, 0))
    assert not Row(DAY, "", 27, 0).same_take(Row(DAY, "Pat", 27, 114))
    assert Row(DAY, "", 27, 114).same_take(Row(DAY, "", 27, 0))


def covered_three_takes(tmp_path, s, later=25):
    """A cover, then Pat 24 pages, Dana 27, Pat `later`, numbered from 1."""
    pages = 24 + 27 + later
    return job_of(s, page_numbered_transcript(tmp_path / "Roe.pdf", pages, first=1, cover=COVER,
                                              initials=[PR] * 24 + [DS] * 27 + [PR] * later))


def test_a_lost_take_as_long_as_a_first_take_and_its_cover_is_put_back(tmp_path, sheets):
    """An earlier version's first row: no Start, 25 pages, the cover and 24. Its lost third take is 25 pages by the same
    reporter, so it counted as that row and was never put back: the sheet stayed 25 short, with no word said."""
    s = sheets
    job = covered_three_takes(tmp_path, s)
    old = add(job.case, [Row(DAY, "Pat", 25, None), Row(DAY, "DS", 27, 25)], s)
    assert old.added == 2
    again = add(job.case, job.runsheet_opts(s).rows, s, old.path)
    assert (again.added, again.skipped) == (1, 2)
    assert ("Pat", 25, 52) in sheet_of(again) and sum(p for _, p, _ in sheet_of(again)) == 77
    assert add(job.case, job.runsheet_opts(s).rows, s, old.path).added == 0


def test_the_takes_on_a_sheet_of_blank_starts_are_still_found_each_for_its_own(tmp_path, sheets):
    """One blank Start and the formulas under it read as no number at all: each row still answers for one take."""
    s = sheets
    job = covered_three_takes(tmp_path, s)
    old = [Row(DAY, "Pat", 25, None), Row(DAY, "DS", 27, None), Row(DAY, "Pat", 25, None)]
    assert takes_to_add(job.runsheet_opts(s).rows, old) == []
    assert [r.start for r in takes_to_add(job.runsheet_opts(s).rows, old[:2])] == [52]


def test_a_row_with_a_number_can_still_be_many_takes(tmp_path, sheets):
    """Overlapping numbers aren't used up: one row there of a stretch now cut in two is both."""
    new = [Row(DAY, "Pat", 10, 100), Row(DAY, "Pat", 10, 110)]
    assert takes_to_add(new, [Row(DAY, "Pat", 20, 100)]) == []


def test_a_row_with_no_number_goes_to_the_take_with_a_number_only_when_no_number_answers(tmp_path, sheets):
    new = [Row(DAY, "Pat", 25, 52)]
    assert takes_to_add(new, [Row(DAY, "Pat", 25, None), Row(DAY, "Pat", 25, 52)]) == []
    first = Row(DAY, "Pat", 25, 1)
    assert takes_to_add([first, *new], [Row(DAY, "Pat", 25, None), Row(DAY, "Pat", 25, 52)]) == []


def test_a_take_written_with_a_start_of_0_under_its_initials_isnt_added_again(tmp_path, sheets):
    """The old count read no names on its title page, the new one does, so the labels differ, and the take there with a
    first page of 0 was added a second time: 27 pages counted twice."""
    s = sheets
    job = job_of(s, page_numbered_transcript(tmp_path / "Roe.pdf", 12, first=100, initials=[PR] * 7 + [DS] * 5,
                                             caption=CAPTION_NAMING))
    rows = job.runsheet_opts(s).rows
    assert [(r.reporter, r.pages, r.start) for r in rows] == [("Pat", 7, 100), ("Dana", 5, 107)]
    old = add(job.case, [Row(DAY, "Pat", 7, 100), Row(DAY, "DS", 5, 0)], s)
    assert add(job.case, rows, s, old.path).added == 0


def test_a_label_changed_on_a_first_page_not_read_isnt_added_again(tmp_path, sheets, monkeypatch):
    """"CD" there from 4 for 2 pages, "Casey" here reading None and 5: added again, Casey counted twice."""
    s = sheets
    monkeypatch.setattr(s, "reporter_names", lambda: {"cd": "Casey"})
    job = job_of(s, printed_pdf(tmp_path / "Roe.pdf", [1, 2, 3, None, 5, 6, 7], ["ab"] * 3 + ["cd"] * 2 + ["ef"] * 2))
    rows = job.runsheet_opts(s).rows
    assert [(r.reporter, r.numbers) for r in rows][1] == ("Casey", [None, 5])
    old = add(job.case, [Row(DAY, "AB", 3, 1), Row(DAY, "CD", 2, 4), Row(DAY, "EF", 2, 6)], s)
    assert add(job.case, rows, s, old.path).added == 0


def test_their_own_sheet_goes_by_the_same_rules(tmp_path, sheets):
    """A sheet this app didn't make: Dana's take is added, Pat's isn't."""
    from openpyxl import Workbook, load_workbook
    s = sheets
    wb = Workbook()
    ws = wb.active
    ws.append(["Date", "Weekday", "Reporter", "Day's Take", "Running Take", "Pages written", "Starting Page No.",
               "Ending Page No."])
    ws.append([DAY, "Wednesday", "Pat", 1, 1, 39, 1, 39])
    ws.append([DAY, "Wednesday", "Pat", 2, 2, 38, 60, 97])
    ws.append([DAY, "Wednesday", "Pat", 3, 3, 12, 100, 111])
    path = tmp_path / "theirs.xlsx"
    wb.save(path)
    job = job_of(s, printed_pdf(tmp_path / "Roe.pdf", FALLS, FALLS_WHO))
    opts = add(job.case, job.runsheet_opts(s).rows, s, path)
    assert (opts.added, opts.skipped) == (2, 3)
    ws = load_workbook(path).active
    assert sum(ws.cell(r, 6).value for r in range(2, ws.max_row + 1)) == 111


# ------------------------------------------------------------------ takes in the order of the pages
def test_a_take_with_no_number_read_stays_in_its_place(tmp_path, sheets):
    """It went first on the card and last on the sheet: an earlier version counted on from the page before, so it was in
    order."""
    from minute_filler.batch import takes_of, unit_sheet
    s = sheets
    job = job_of(s, printed_pdf(tmp_path / "Roe.pdf", [1, 2, 3, None, None, None, 7, 8], ["ab"] * 3 + ["cd"] * 3 + ["ef"] * 2))
    want = ["AB", "CD", "EF"]
    assert [r.reporter for r in job.runsheet_opts(s).rows] == want
    assert [r.reporter for r in takes_of([job], s)] == want
    assert [r.reporter for r in unit_sheet([job], s, []).rows] == want
    assert [who for who, *_ in sheet_of(add(job.case, job.runsheet_opts(s).rows, s))] == want


def test_a_falling_day_s_takes_stay_in_the_order_of_its_pages(tmp_path, sheets):
    """Sorted by their numbers, Dana's second take came straight after the first, out of the order of the pages."""
    from minute_filler.batch import takes_of, unit_sheet
    s = sheets
    job = job_of(s, printed_pdf(tmp_path / "Roe.pdf", FALLS, FALLS_WHO))
    want = [("Pat", 1), ("DS", 10), ("Pat", 60), ("DS", 10), ("Pat", 100)]
    assert [(r.reporter, r.start) for r in job.runsheet_opts(s).rows] == want
    assert [(r.reporter, r.start) for r in takes_of([job], s)] == want
    assert [(r.reporter, r.start) for r in unit_sheet([job], s, []).rows] == want
    assert [(who, start) for who, _, start in sheet_of(add(job.case, job.runsheet_opts(s).rows, s))] == want


def test_a_day_s_transcripts_go_by_the_first_number_read_in_each(tmp_path, sheets):
    """Each one whole: the second's numbers fall among the first's, and they no longer mix. Given in the other order, or
    with an unread first page, the same."""
    s = sheets
    a = printed_pdf(tmp_path / "a.pdf", [None] + list(range(102, 121)), [PR] * 10 + [DS] * 10)
    b = printed_pdf(tmp_path / "b.pdf", list(range(111, 131)), [PR] * 20)
    for paths in ((a, b), (b, a)):
        job = job_of(s, *paths)
        assert [(r.reporter, r.start) for r in job.runsheet_opts(s).rows] == [("Pat", None), ("DS", 111), ("Pat", 111)]


def test_two_volumes_from_one_number_stay_in_the_order_given_and_whole(tmp_path, sheets):
    s = sheets
    job = job_of(s, printed_pdf(tmp_path / "AM.pdf", list(range(1, 21)), [PR] * 10 + [DS] * 10),
                 printed_pdf(tmp_path / "PM.pdf", list(range(1, 16)), [DS] * 5 + [PR] * 10))
    assert [(r.doc[-6:], r.at) for r in job.runsheet_opts(s).rows] == [("AM.pdf", 0), ("AM.pdf", 10), ("PM.pdf", 0),
                                                                        ("PM.pdf", 5)]


def test_takes_of_no_transcript_go_by_their_own_numbers():
    rows = [Row(DAY, "B", 5, 20), Row(date(2026, 6, 4), "C", 5, 1), Row(DAY, "A", 5, 10), Row(DAY, "D", 5, None)]
    assert [r.reporter for r in sorted(rows, key=page_order(rows))] == ["D", "A", "B", "C"]
    assert [r.reporter for r in sorted(rows, key=page_order(rows, float("inf")))] == ["A", "B", "D", "C"]


# ------------------------------------------------------------------ a page of the word index isn't kept for its line numbers
INDEX_ENTRIES = "\n".join(f"{n} [2] {n}:{n + 1};{n + 3}:{n + 2}" for n in range(1, 10))
REFERENCES = "\n".join(f"word{k} (2)\n    {10 + k}:{k % 25 + 1};{20 + k}:{(k * 3) % 25 + 1}" for k in range(18))


def pages_pdf(path, pages) -> str:
    """A PDF of (number, body) pages signed "pr" where they have a number: None for no number, a body of None for 25
    numbered lines."""
    doc = pymupdf.open()
    for number, body in pages:
        page = doc.new_page()
        if number is not None:
            page.insert_text((300, 40), str(number), fontsize=10)
            page.insert_text((520, page.rect.height - 40), PR, fontsize=10)
        page.insert_text((60, 80), LINES if body is None else body, fontsize=9)
    doc.save(path)
    doc.close()
    return str(path)


def test_the_first_page_of_a_word_index_is_no_page_of_the_transcript(tmp_path):
    """Unnumbered and unsigned, its entries "1 [2] ..." to "9" with no 10-19 read as line numbers: 21 billed at 0.95, with
    no word said, for the 20 and a warning the other readings give."""
    pages = [(i, None) for i in range(1, 21)] + [(None, INDEX_ENTRIES)] + [(None, REFERENCES)] * 3
    c = ingest_file(pages_pdf(tmp_path / "Roe.pdf", pages)).count
    assert c.pages == 20 and c.confidence == 0.55 and "check the count" in c.warning
    only = [(i, None) for i in range(1, 21)] + [(None, INDEX_ENTRIES)]  # (with nothing after it)
    assert ingest_file(pages_pdf(tmp_path / "Poe.pdf", only)).count.pages == 20


# ------------------------------------------------------------------ the number in a head must be the one the pages imply
@pytest.mark.parametrize("numbers, heads, want", [
    ([10, 11, 0], ["", "", "Juror 15"], [10, 11, None]),  # (within a skip of the page before, but not what it implies)
    ([10, 11, 0], ["", "", "Juror 12"], [10, 11, 12]),
    ([0, 11, 12], ["Juror 7", "", ""], [None, 11, 12]),
    ([0, 11, 12], ["Proceedings 10", "", ""], [10, 11, 12]),
    ([10, None, 0, 15], ["", "", "Juror 13", ""], [10, None, None, 15]),  # (10 implies 12, 15 implies 14)
    ([10, None, 0, 14], ["", "", "Proceedings 12", ""], [10, None, 12, 14]),  # (either side will do)
    ([10, None, 0, 15], ["", "", "Proceedings 14", ""], [10, None, 14, 15]),
])
def test_a_head_s_number_must_be_the_one_the_pages_around_it_imply(numbers, heads, want):
    """[10, 11, 0 under "Juror 15"] gave 15: within SKIP_OK of the page before, so it read as a skip. All 107 real numbers
    in heads are exactly what the pages around them imply."""
    assert read_numbers(numbers, heads) == want


# ------------------------------------------------------------------ a typed title page is no cover, however it says so
@pytest.mark.parametrize("words", [
    "JANE ROE,\nPlaintiff,\n-v-\nSAM POE,\nDefendant.",
    "JANE ROE\n-v.-\nSAM POE",
    "JANE ROE\n-vs-\nSAM POE",
    "JANE ROE,\n\nagainst\n\nSAM POE",
    "JANE ROE, Plaintiff, and SAM POE",
    "JANE ROE v. SAM POE, Defendants",
    "JANE ROE v. SAM POE\nInd. No. 712345/2021",
    "JANE ROE v. SAM POE\nIndex: 712345/2021",
    "JANE ROE v. SAM POE\nIndex # 712345/2021",
])
def test_nor_is_a_typed_title_page_in_other_words(tmp_path, s, words):
    path = page_numbered_transcript(tmp_path / "Roe.pdf", 20, first=819, cover=f"{words}\nJune 3, 2026\nMin-U-Script")
    c = job_of(s, path).docs[0].ing.count
    assert (c.cover, c.pages) == (0, 21)


@pytest.mark.parametrize("words", ["JANE ROE\n– against –\nSAM POE", "JANE ROE\n—against—\nSAM POE", "ROE\n– v. –\nPOE"])
def test_nor_with_the_dashes_a_typist_uses(words):
    """(The test PDFs' font has no such dashes: as read from a PDF that has them.)"""
    from minute_filler.takes import _CAPTION
    assert _CAPTION.search(words)


@pytest.mark.parametrize("words", [
    "In The Matter Of:\nJane Roe v. Sam Poe\nProceedings\nJune 3, 2026\nQueens Supreme Court\nMin-U-Script® with Word Index",
    "In The Matter Of:\nJANE ROE vs. SAM POE\nTrial Day 3\nJune 3, 2026\nSupreme Court of the State of New York\n"
    "Min-U-Script® with Word Index",
    "In The Matter Of:\nPeople v. Sam Poe\nProceedings\nMin-U-Script\nWord Index: 12 pages",  # (no index number after it)
    "In The Matter Of:\nJane Against All Odds, Inc. v. Sam Poe\nMin-U-Script® with Word Index",
])
def test_what_a_cover_says_is_still_a_cover(tmp_path, words):
    assert ingest_file(page_numbered_transcript(tmp_path / "Roe.pdf", 5, cover=words)).count.cover == 1


# ------------------------------------------------------------------ a run inside a day whose numbers are known
def test_a_run_of_one_number_printed_twice_shows_that_number():
    """"Two numbers read must be two numbers" is a test of a day, not of a run in a day known: 164 printed twice showed
    "place 35–36", and the invoice "pp. 130–134, counted pages 35–36", though typing 164 gives those two pages."""
    d = day_of(TWICE)
    assert d.span(35, 36) == "164" and d.parse("164") == (35, 36) and d.as_typed(35, 36) == "164"
    assert _run_words(TWICE, 35, 36) == "p. 164" and _printed_span(TWICE, 35, 36) == "p. 164"
    assert _runs_words(TWICE, [(1, 5), (35, 36)]) == "pp. 130–134, 164"
    assert d.span(34, 36) == "163–164" and _run_words(TWICE, 34, 36) == "pp. 163–164"


@pytest.mark.parametrize("printed, a, b, shown", [
    ([1, 1], 1, 2, "place 1–2"),  # (a day of one number stays by place)
    ([1, 1, 1], 1, 2, "place 1–2"),
    ([154, None], 1, 2, "154"),  # (one read of two is half)
    ([100, 101, 102, None, None, None], 3, 6, "place 3–6"),  # (too few of its own)
    ([100, 101, 102, None, None, None], 3, 4, "102"),
])
def test_what_a_run_shows_as_its_numbers(printed, a, b, shown):
    assert day_of(printed).span(a, b) == shown


# ------------------------------------------------------------------ what a refused run says
@pytest.mark.parametrize("printed, typed, hint", [
    ([100, None, 102, 103, None, 105], "104", "place 5"),  # (it said place 2, the page between 100 and 102)
    ([100, None, None, 103, None, 105], "104", "place 5"),
    ([100, None, 102, 103, None, 105], "101", "place 2"),
    ([1, 2, None, 4, 5, 6, 7, 8, 1, 2, None, 4], "3", None),  # (a gap on each stretch: nothing says which)
])
def test_a_hint_names_the_gap_the_number_could_be_in(printed, typed, hint):
    with pytest.raises(ValueError) as refused:
        day_of(printed).parse(typed)
    if hint:
        assert str(refused.value).endswith(f"goes by its place: {hint})")
        d = day_of(printed)
        place = int(hint.split()[1])
        assert d.parse(hint) == (place, place) and d.printed[place - 1] is None
    else:
        assert "goes by its place" not in str(refused.value)


def test_no_hint_where_no_page_was_unread_around_the_number():
    with pytest.raises(ValueError) as refused:
        day_of([None, 100, 101, 103]).parse("102")  # (the unread page is before 100)
    assert "place" not in str(refused.value)


def test_a_hint_gives_the_whole_gap():
    d = day_of([100, None, None, 103, 104, 105, 106, 107])
    with pytest.raises(ValueError, match=r"goes by its place: place 2–3\)$"):
        d.parse("101")
    with pytest.raises(ValueError, match=r"goes by its place: place 2–3\)$"):
        d.parse("101-102")
    assert d.parse("place 2–3") == (2, 3)


def test_a_place_of_one_page_is_said_as_one():
    with pytest.raises(ValueError, match=r"e\.g\. place 15$"):
        day_of(FALLS).parse("15")
    assert day_of(FALLS).parse("place 15") == (15, 15)


def test_a_cell_typed_again_as_it_shows_is_told_its_place():
    """It said "e.g. 141-170", which no page of this day prints."""
    d = day_of(FALLS)
    with pytest.raises(ValueError, match=r"e\.g\. place 1-59$"):
        d.parse("1–39, 10–29")
    with pytest.raises(ValueError, match=r"e\.g\. place 1-111$"):
        d.parse(d.span(1, 111))
    with pytest.raises(ValueError, match=r"e\.g\. place 1-59$"):
        d.parse(" 1-39 ,  10 - 29 ")
    assert d.parse("place 1-59") == (1, 59)


def test_several_numbers_that_arent_a_run_shown_get_the_day_s_example():
    with pytest.raises(ValueError, match=r"first-last page, e\.g\. place 1–20$"):
        day_of(FALLS).parse("3, 5, 7")
    with pytest.raises(ValueError, match=r"first-last page, e\.g\. 819–838$"):
        day_of(range(819, 939)).parse("819, 820, 821")
    with pytest.raises(ValueError, match=r"first-last page, e\.g\. place 1–6$"):
        day_of([None] * 6).parse("")
    with pytest.raises(ValueError, match=r"first-last page, e\.g\. place 1–6$"):
        day_of([154] + [None] * 5).parse("1, 2, 3")
    with pytest.raises(ValueError, match=r"first-last page, e\.g\. 141-170$"):
        day_of([]).parse("")  # (no pages to give an example of)
