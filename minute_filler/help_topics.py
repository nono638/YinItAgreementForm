"""The in-app manual (Help → How to use, F1): short topics, each answering one question, grouped in chapters.

Each Topic has an id (what F1 and the links between topics use: <a href="topic:dates-holidays">), the chapter it is
listed under, a title, extra search words (synonyms a reporter might type that the text doesn't use; never shown)
and its text as simple HTML (<p>, <ul>, <b>, <i>, <table>; no colours, so it reads in light and dark).
help_search finds topics in it; gui/help_window shows them. "{website}" is replaced by the website's address when
shown. Examples use made-up names only (Pat Reporter, Dana Smith, Jane Roe, 712345/2021)."""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Topic:
    """One page of the manual. words: extra search terms (not shown); html: its text (without the title)."""
    id: str
    chapter: str
    title: str
    words: str
    html: str
    text: str = field(default="", compare=False)  # the plain text, worked out once (see below)

    def __post_init__(self):
        # (the tags inside a line go without a trace, so a result's line reads "the Court, County", not "the
        # Court , County"; the others, paragraphs and list items, part words)
        inline = re.sub(r"</?(?:b|i|a|code|em|strong|small|span|u)\b[^>]*>", "", self.html)
        plain = html.unescape(re.sub(r"<[^>]+>", " ", inline))
        object.__setattr__(self, "text", " ".join(plain.split()))


START = "Getting started"
INPUT = "What you can put in"
CHECK = "Checking what was read"
MAKE = "What it makes"
INVOICE = "Invoices"
EXCERPTS = "Pages ordered and speeds"
RECORDS = "Records"
DATES = "Dates and business days"
RATES = "Rate sheets"
RUNSHEET = "Run sheet"
BATCH = "Batches"
SETTINGS = "Settings"
AI = "The AI helper"
TROUBLE = "If something goes wrong"
KEYS = "Keyboard shortcuts"
CHAPTERS = (START, INPUT, CHECK, MAKE, INVOICE, EXCERPTS, RECORDS, DATES, RATES, RUNSHEET, BATCH, SETTINGS, AI,
            TROUBLE, KEYS)

T = Topic
TOPICS: list[Topic] = [
    # ------------------------------------------------------------------------------------------ Getting started
    T("start-overview", START, "What the app does", "about purpose introduction overview privacy offline internet",
      """
<p>YinItAgreementForm reads the documents of an order (a transcript, an invoice, a photo of a court paper, an
e-mail), finds the court, part, judge, case, index number, dates and attorneys, and shows them for you to check.
Then it makes the paperwork:</p>
<ul>
<li>the <b>minute agreement form</b>, one for each attorney who ordered (<a href="topic:make-agreement">more</a>);</li>
<li>the <b>invoice</b>, priced from your rate sheet and the transcript's pages (<a href="topic:inv-priced">more</a>);</li>
<li>the <b>MOFR</b>, the Minute Order Form/Receipt (<a href="topic:make-mofr">more</a>);</li>
<li>the <b>run sheet</b> of a shared trial: who wrote which pages (<a href="topic:run-overview">more</a>).</li>
</ul>
<p>Every file it makes is listed in <a href="topic:rec-overview">Records</a>, with what you billed and what was
paid.</p>
<p><b>Everything stays on this computer.</b> Photos are read by the text recognition built into Windows, and the
optional <a href="topic:ai-what">AI helper</a> runs on this computer too. The only time the app goes online is to
ask GitHub, once a day, whether there is a newer version. Nothing about you or your cases is sent, and
Settings → Options → <i>Look for a newer version once a day</i> turns it off.</p>
"""),
    T("start-first-time", START, "The first time: your details and defaults",
      "setup begin new install name address phone email initials signature first launch welcome",
      """
<p>The first time the app starts, it asks for your name, address, rate sheet and where to save files. All of it
can be changed later in <b>Settings</b> (File → Settings…):</p>
<ul>
<li><b>My info</b>: your name, title, address, phone, fax, e-mail, website, initials and
<a href="topic:set-signature">signature</a>. They go on every form and invoice.</li>
<li><b>Defaults</b>: the court, county, number of copies and the <a href="topic:rates-sheets">rate sheet</a> new
jobs start with.</li>
<li><b>Options → Folders</b>: where the files are saved (<a href="topic:make-folders">more</a>).</li>
<li><b>Invoice</b>: your payment details and the text of your invoices (<a href="topic:inv-text">more</a>).</li>
</ul>
<p>Your <b>initials</b> matter on shared trials: the app finds your pages by the initials at the foot of each page.
Put them in My info if they aren't the first letters of your name.</p>
"""),
    T("start-steps", START, "Step by step: from an order to the paperwork",
      "how to use workflow steps begin quick start tutorial",
      """
<ol>
<li><b>Add the order.</b> Drop the documents anywhere in the window, click <b>Browse…</b>, press Ctrl+O, or paste an
e-mail or a screenshot (<a href="topic:input-documents">what it reads</a>).</li>
<li><b>Check the fields.</b> Amber fields are guesses; the badge on each says where its value came from
(<a href="topic:check-badges">more</a>). The status at the top right counts what still needs a look.</li>
<li><b>Tick who ordered</b> in the <i>Who ordered</i> card. A transcript lists everyone who appeared, not who
ordered. In a trial, one tick is the whole trial, at the speed shown (<a href="topic:check-attorneys">more</a>).</li>
<li><b>Check the speed and the rate sheet</b> (<a href="topic:inv-speeds">more</a>).</li>
<li><b>Check Who pays what</b>, the card under the Invoice card (<a href="topic:inv-who-pays">more</a>).</li>
<li><b>Tick what to make</b> in the Outputs box and click <b>Generate</b> (Ctrl+Enter), or <b>Generate all</b>
(Ctrl+Shift+Enter) for every ticked job (<a href="topic:make-outputs">more</a>).</li>
<li><b>Look at the preview</b> and click <b>Save</b>, or <b>Go back</b> to change something: nothing is saved until
then (<a href="topic:make-preview">more</a>).</li>
</ol>
"""),
    T("start-window", START, "The main window at a glance",
      "layout screen parts each part what for drop zone job list form cards status records button yin yang recent "
      "jobs",
      """
<ul>
<li><b>The drop zone</b> (top left): drop documents on it, or anywhere in the window. Once a document is read it
becomes one slim row (<i>Drop more here, or Browse…</i>).</li>
<li><b>The job list</b> (left): each job's case, date and day, total pages and your pages, with ✓ for a job already made and ⚠ for
one with something to check (<a href="topic:batch-job-list">more</a>).</li>
<li><b>The form</b> (right): its cards follow the job, top to bottom: <i>Case</i>, <i>Who ordered</i> (who
ordered, what and at what speed), <i>Pages and dates</i>, then, when an invoice is to be made, <i>Invoice</i> and
<i>Who pays what</i>, and for a trial <i>Who transcribed what</i>. Each folds to one line that sums it up
(<a href="topic:start-room">more</a>). While nothing is open, a <b>Recent jobs</b> card at the top of the form lists
the jobs made lately (3 at first, made in the last 30 days: Settings → Options → <i>Recent jobs</i>): click one to open
it again. <i>Recent documents ▾</i> on it lists the documents you opened lately.</li>
<li><b>The status</b> (top right): what still needs a look, such as <i>⚠ 1 missing, 2 to check</i>. Its tooltip
lists them, and a click goes to the first one.</li>
<li><b>Records</b> (top right, next to New job and Settings): your invoices and every file made
(<a href="topic:rec-overview">more</a>).</li>
<li><b>The Outputs box</b> (bottom): what to make, with <b>Generate</b> (<a href="topic:make-outputs">more</a>).</li>
</ul>
<p>The yin-yang in the drop zone swirls while documents are read, settles when the form is ready and cracks when
something required is missing. View → <i>Show the yin-yang</i> hides it.</p>
"""),
    T("start-room", START, "Short of room on a laptop: folding, the divider, zoom and theme",
      "small screen laptop space fold collapse hide bigger smaller text size font dark mode light theme scaling "
      "divider",
      """
<ul>
<li>The <b>Outputs box</b> at the bottom is one row, so the form has the room; in a narrow window its Generate
buttons go on a row of their own under it.</li>
<li><b>Drag the divider</b> between the job list and the paste box.</li>
<li><b>Fold a card</b> of the form to one line that sums it up, with a ⚠ when something in it needs a look; click its
heading. View → <i>Fold all cards</i> and <i>Unfold all cards</i>.</li>
<li><b>Zoom</b>: Ctrl++ and Ctrl+- (or Ctrl and the mouse wheel), Ctrl+0 for 100%; also View → Zoom in, Zoom out and
Actual size, and Settings → Options → Zoom. The window also follows Windows' display scaling (125%, 150%).</li>
<li><b>Theme</b>: View → Theme switches between light, dark and as Windows is.</li>
</ul>
<p>The divider, the folds and the zoom are remembered.</p>
"""),
    T("start-one-window", START, "One window at a time", "second copy open with twice launch again",
      """
<p>Only one window runs at a time. Starting the app again, or opening a PDF with <i>Open with</i>, brings the open
window forward and adds the documents there. (Two windows could each save over the other's settings and run
sheets.)</p>
<p>Several files opened together are added as one drop. While a question is on screen, they wait until it is
answered.</p>
"""),
    T("start-help", START, "Finding help: search, F1 and tooltips", "help manual guide search find question ask tips",
      """
<ul>
<li><b>Search</b>: type a few words in the box at the top left of this window, such as <i>holiday</i> or
<i>bill a lawyer by email</i>. It also finds words that mean the same, and forgives a typo.</li>
<li><b>F1</b> opens the topic for where you are: on the Dates tab of Settings, the dates; in Records, the
records.</li>
<li><b>Tooltips</b>: rest the mouse on a field, a button or a heading to see what it does.</li>
<li>The <a href="{website}">website</a> shows the app with pictures and has the latest version.</li>
</ul>
"""),
    # -------------------------------------------------------------------------------------- What you can put in
    T("input-documents", INPUT, "The documents it reads",
      "pdf transcript invoice photo picture image scan email word docx txt html web page msg outlook file types",
      """
<ul>
<li><b>Transcript PDFs</b>: the best input. The case details come from the title page. The transcript's total pages (every
reporter's) are counted, and the invoice bills your pages (your own, when several reporters wrote it).</li>
<li><b>Other PDFs</b>: an invoice, a scanned order, a printed e-mail. Scans are read by Windows' text
recognition.</li>
<li><b>Photos and screenshots</b>: JPG, PNG, iPhone HEIC, TIFF, BMP, WebP (<a href="topic:input-photos">more</a>).</li>
<li><b>E-mails</b>: paste the text, or drop a saved <code>.eml</code> (<a href="topic:input-email">more</a>).</li>
<li><b>Word</b> (<code>.docx</code>), <code>.txt</code> and saved web pages.</li>
<li><b>A whole folder</b>: File → Open a folder of documents (batch)… (<a href="topic:batch-folder">more</a>).</li>
</ul>
<p>Outlook <code>.msg</code> files can't be read: copy the e-mail's text and paste it instead.</p>
<p>Files this app made (agreements, MOFRs, invoices) are recognised and skipped, so its output can live next to your
documents.</p>
"""),
    T("input-email", INPUT, "E-mails and pasted text", "paste email message text extract outlook eml clipboard",
      """
<p>Paste the e-mail into the text box and click <b>Extract from text</b>. A saved <code>.eml</code> file can be
dropped like a document. Once a document is read the box is one line, <i>Paste an e-mail or notes…</i>, so the job
list has the room: click in it (or paste) to open it again.</p>
<p>The sender of an e-mail is ticked as ordering (a transcript's attorneys are not: it lists who appeared). A page
count read from an e-mail is shown, but not billed until you type it in <i>Est. number of pages</i>.</p>
<p>When an e-mail asks for another speed ("please send a daily copy"), the <i>Who ordered</i> card asks
which speed to use, and so does Generate. A speed an e-mail mentions is never applied by itself.</p>
"""),
    T("input-photos", INPUT, "Photos, scans and screenshots",
      "picture image camera iphone heic jpg png screenshot ocr text recognition paste ctrl+v scan",
      """
<p>Drop a photo or a scan, or paste a screenshot with <b>Ctrl+V</b>. The text is read by the text recognition built
into Windows, on this computer.</p>
<p>A photo of a court paper lists who appeared, not who ordered, so tick the attorneys yourself.</p>
<p>If photos come out blank, see <a href="topic:trouble-photos">Photos come out blank</a>.</p>
"""),
    T("input-several", INPUT, "Several documents for one order",
      "combine add more documents together merge remove document move job of its own show extracted text",
      """
<p>Add as many documents for one order as you like: a transcript, the e-mail ordering it, a photo of the order.
What they say is combined.</p>
<p>A job of several documents lists them under it in the job list. Right-click one to:</p>
<ul>
<li><b>Show extracted text</b>: see what was read from it;</li>
<li><b>Move to a job of its own</b>: when it belongs to another case or day;</li>
<li><b>Remove from job</b>.</li>
</ul>
<p>When the documents of a job have index numbers that don't match, the app says so before making anything
(<a href="topic:check-index">more</a>).</p>
"""),
    # ------------------------------------------------------------------------------------ Checking what was read
    T("check-badges", CHECK, "Where each value came from: the badges and amber fields",
      "badge found pdf records ai default worked out you guess amber yellow highlighted more alternatives "
      "other readings pick choose",
      """
<p>Each field has a badge saying where its value came from:</p>
<ul>
<li><b>found</b>: found in the document;</li>
<li><b>PDF</b>: counted from the transcript PDF itself (the total page count, every reporter's pages);</li>
<li><b>records</b>: a case name an earlier job with the same index number has in your records. It is a suggestion,
always highlighted, and Generate asks you to confirm it;</li>
<li><b>AI</b>: suggested by the <a href="topic:ai-what">AI helper</a>;</li>
<li><b>default</b>: from your settings;</li>
<li><b>worked out</b>: from the other details (the delivery date from the speed, say);</li>
<li><b>you</b>: typed by you. A value you type is never changed by the app.</li>
</ul>
<p>The badge is small grey text, so that the ones to look at stand out: <b>amber fields are guesses</b> (the AI's, the
records', or a value the app wasn't sure of), and their badge is an amber pill. Check them. When the documents read
a field more than one way, a button beside it says how many (<i>2 more ▾</i>) and lists them to pick from.</p>
"""),
    T("check-status", CHECK, "What still needs a look", "status warning missing check review required top right ⚠ problems "
      "before you generate list everything still to do fix",
      """
<p>The status at the top right of the window counts what the job on screen still needs and names the first, such
as <i>⚠ 1 missing, 2 to check: Index Number is missing ›</i>:</p>
<ul>
<li><b>missing</b>: a required field is blank;</li>
<li><b>to check</b>: the job's own checks (nobody ticked, two rows that may be one firm, a speed to choose,
Whose pages… or Who ordered which pages… to decide) and the warnings under the fields (a total page count to check, a date on a weekend
or a court holiday);</li>
<li><b>to review</b>: guesses (amber fields).</li>
</ul>
<p>Its tooltip lists them, and a click goes to the first one: the field gets the cursor, or the button to press
lights up. The <b>Before you generate</b> box at the top of the form lists them all, each a link to its place. The
job list shows the same with a ⚠ on the job (<a href="topic:batch-job-list">more</a>).</p>
"""),
    T("check-pages", CHECK, "The total page count (Est. number of pages)",
      "pages count number of pages word index min-u-script estimate typed amber warning concordance",
      """
<p><i>Est. number of pages</i> is counted from the transcript PDF when there is one: every page, whoever wrote it,
without the word index printed after the transcript. The line under the field says which pages
("Transcript pages 378–460 · excludes the 13 word-index pages after them").</p>
<p>The count is read four ways: the pages up to the word index, the pages with line numbers, the printed page
numbers, and the index found from the end. When two of them agree on another count, or the index would take more
than a quarter of the PDF, the field turns amber and a warning under it says so: check the count (the other count
is in the ▾ list).</p>
<p><b>A number you type</b> stays. It is what your invoice bills, and the day's pages on every agreement. Typed below
the transcript's own count, when the two would decide the <a href="topic:inv-index">index</a> differently, Generate
asks whether to include one.</p>
<p>Without a transcript, type the pages yourself (<a href="topic:inv-no-transcript">more</a>). Several transcripts in
one job, such as the days of a trial, are added up.</p>
"""),
    T("check-index", CHECK, "Index numbers checked", "index number missing mismatch don't match different keep together "
      "move job of its own case number not read didn't extract wasn't found blank empty pattern regex regular expression docket slash dash own format",
      """
<p>A document with no index number gets a note under the job list, and a ⚠ on its row when its job has several
documents.</p>
<p>When the documents of one job have index numbers that don't match ("a.txt has 712345/2021; b.txt has
722222/2025"), the note says so and <b>Generate asks before making anything</b>:</p>
<ul>
<li><i>Generate anyway</i> (or <i>Keep them together</i> in the note) keeps them as one job;</li>
<li>or go back and right-click a document → <i>Move to a job of its own</i>.</li>
</ul>
<p>A title page listing several index numbers (cases tried together) is fine: a document with one of them belongs
with it.</p>
<p><b>Your own patterns.</b> The app reads index numbers written with a slash or a dash and a four-digit year,
labelled or not ("712345/2021", "712345-2021"); with a two-digit year after a label, or with a slash ("Index No.
712345-21", "712345/21"); and under an <i>Index No.</i> label on the line above. A two-digit year is of this century
up to next year, else of the last ("712345/99" is 1999). For another way of writing them, add a pattern of your own
in Settings → Options → <b>Index numbers</b>, one per line: a regular expression that finds the number and the year
as two groups in parentheses, in that order, and no other groups (<code>(?:...)</code> groups without one).
<code>CV-(\\d{6})-(\\d{2})/QU</code> finds "CV-012345-25/QU" (12345/2025). Yours are tried as well as the app's
own, and count as surely as a number after "Index No."; one that takes more than a second on a document is stopped
there. The box under them says what is wrong with one as you type it, and what they find in a line you paste to try
them on.</p>
"""),
    T("check-suggestions", CHECK, "Suggestions as you type",
      "autocomplete autofill complete suggest court part judge attorney firm name typing remember",
      """
<p>Court, Part and Judge suggest what your records hold as you type, from any part of the name ("alv" offers
<i>Maria T. Alvarez</i>). So do an attorney's name and firm in the attorney details.</p>
"""),
    T("check-attorneys", CHECK, "Who ordered: tick each firm that ordered",
      "attorney lawyer firm counsel who ordered tick party appearances address phone fax email details row whole "
      "trial every day all days standing order half ticked only this day what speed pages colour color square "
      "stripe side plaintiff defense",
      """
<p>A transcript lists everyone who appeared, not who ordered: in the <b>Who ordered</b> card, <b>tick each firm that
ordered</b>. Each one ticked gets a minute agreement and an invoice. The app ticks only the sender of an e-mail, the
firm an invoice is addressed to, and the one attorney when only one appeared.</p>
<p><b>In a trial</b> (days of one case), the card lists every firm of every day, whichever day is shown, and <b>a
tick is the whole trial</b>: every day of it, and the days you drop in later, at one speed. That is how most trials
are ordered. A box half filled is a firm that ordered some days or pages only.</p>
<ul>
<li><b>What</b>: <i>The whole trial (4 days)</i>; <i>Only 6/4/2026</i>, the day shown; or <i>Some days or
pages…</i>, which opens <a href="topic:exc-table">Who ordered which pages…</a>, the table of every day and every firm. A firm that
ordered some days says which: <i>6/3/2026 and 6/5/2026</i>, <i>part of 6/4/2026</i>.</li>
<li><b>Speed</b>: the speed the firm is billed, by name (<a href="topic:inv-who-ordered">more</a>).</li>
<li><b>Your pages</b>: the pages its invoice bills: <i>412</i>, or <i>300 of 412 total</i> when some are another
reporter's.</li>
<li>Clicking a half-filled box makes it the whole trial; the next click, none; the next puts back the days it
had.</li>
</ul>
<p>The line under the table says it in words, <i>Counsel &amp; Counsel and Smith Law: the whole trial (4 days), at
Expedite.</i>, then what Generate all bills.</p>
<p>The table has <b>one row per firm</b> (or city office, or a party without an attorney). Every attorney of the firm
on the title page is named in its row ("Alex B. Counsel, Dana Smith"), with the firm's address and whom it
represents. A firm is one party: one agreement and one invoice, however many of its attorneys appeared. A firm
another day names, but not the day shown, is in italics: tick it and it orders the day shown too.</p>
<p>Click a row to see and change all its details under the table: address (one line per line), phone, fax and
e-mail. In a trial they are the firm's on every day.</p>
<p><b>Each firm has a colour</b>: a small square of it before the firm's name and a thin stripe of it at the
left. The plaintiffs' firms get warm colours, the defense firms cool ones, any others grey or green; point at a
firm's square here, or at its column's heading in Who ordered which pages…, to see which side it is. A firm keeps its colour on
every day of a trial, here, in Who pays what and Who ordered which pages…, so you can tell the firms apart at a glance.</p>
<p>To tick each day on its own instead, Settings → Options → <i>A firm you tick orders</i>: <i>Only the day
shown</i>. Two rows that may be one firm are asked about (<a href="topic:check-same-firm">more</a>).</p>
"""),
    T("check-same-firm", CHECK, "Are these one firm?", "same firm not the same duplicate merge join forget remember "
      "firms you answered twice shows up two rows",
      """
<p>When two rows only <i>may</i> be one firm ("Smith Law" and "Smith Law Group", or "Mr. Smith" and Dana Smith of
Smith Law), they are not joined without asking. The Who ordered card asks <i>Are these one firm?</i>: <b>Same
firm</b> or <b>Not the same</b>. Generate asks too, before it makes anything.</p>
<p>With <i>Remember</i> ticked (the default), your answer is kept for later documents. Unticked, it holds until you
close the app.</p>
<p>Settings → Invoice → <i>Firms you answered</i> lists the answers (those for now are marked so). <b>Forget</b> one,
or <b>Forget all</b>: after Save, the jobs open now are read again and you're asked again.</p>
"""),
    T("check-copies", CHECK, "No. of copies", "copies number of copies parties ordering parties count",
      """
<p><i>No. of copies</i> is the number of ordering parties, as the invoice counts them: the firms ticked, or the
<i>Parties</i> number of the Invoice card when you change it. It follows every change of who is ticked, unless you
typed a number.</p>
<p>On a day split under <a href="topic:exc-table">Who ordered which pages…</a>, it is the firms that ordered pages.</p>
"""),
    # ------------------------------------------------------------------------------------------------ What it makes
    T("make-outputs", MAKE, "The Outputs box: choosing what to make, and Generate",
      "outputs generate make create produce tick minute agreement invoice mofr run sheet count files button",
      """
<p>The <b>Outputs</b> box at the bottom of the window is one row: a box for each of <i>Minute agreement</i>,
<i>Invoice</i>, <i>MOFR</i> and <i>Run sheet</i>. Tick the ones to make. Beside each, how many files Generate makes
of it as you tick attorneys (<i>(2)</i>; its tooltip says it in words, <i>Will generate 2 minute agreement
forms</i>, and with several jobs <i>(2 · all 6)</i> counts what Generate all makes too).</p>
<ul>
<li><b>Options ▾</b> holds each output's standing choices, kept for every job: which agreement form and how it is signed,
the MOFR's Civil or Criminal box, what to do when the case has a run sheet already.</li>
<li>The invoice's choices are this job's own: they are in the <b>Invoice</b> card of the form, above Who pays what
(<a href="topic:inv-panel">more</a>).</li>
<li><b>Generate</b> (Ctrl+Enter), the big button at the right of the row, makes the job on screen. For a day of a
case it says which, <i>Generate 6/4/2026 only</i>.</li>
<li><b>Generate all</b> (Ctrl+Shift+Enter) makes every ticked job in the list on the left, and says how many,
<i>Generate all 3 days</i> (<a href="topic:batch-generate-all">more</a>).</li>
</ul>
<p>Each button's tooltip lists the files it makes (<i>2 minute agreement forms, 2 invoices, 3 PDFs of the
math</i>).</p>
<p>While documents are still being read (the bar at the top), both wait, and so does <i>Save</i> in the preview: a
box asks you to press again once the reading is done.</p>
<p>Both show a <a href="topic:make-preview">preview</a> first. Your choices are remembered, except <i>Show granular
detail</i>, which is set for each job. Settings → Options → <i>Make by default</i> says what new jobs start with.
<i>Run sheet</i> ticks itself when two or more reporters wrote a case's transcripts; click it to decide
yourself.</p>
"""),
    T("make-agreement", MAKE, "The minute agreement form",
      "minute agreement form ucs court reporter private party transaction one per attorney pages ordered per email "
      "re-typeset original 1999 scan instructions page dates range",
      """
<p>The UCS <b>Court Reporter Minute Agreement Form</b> is made <b>once for each ticked attorney</b>, with the pages
that attorney ordered, whoever wrote them: firm A ordering a day of 150 pages and firm B an excerpt of 80 of them
get agreements for 150 and 80 pages.</p>
<p>The Outputs box's <i>Options ▾</i>, under <i>Minute agreement</i>, chooses:</p>
<ul>
<li><b>Form</b>: the court's own fillable UCS form (the default), a clean <i>re-typeset</i> version of it (with room
for a long case name, fax and e-mail), or the <i>original 1999 scan</i>;</li>
<li><b>"Per email" on attorney signature</b>: writes "per email" on the attorney's signature line, as minutes are
often ordered by e-mail;</li>
<li><b>Sign as court reporter</b>: puts your <a href="topic:set-signature">signature</a> on the court reporter
line.</li>
</ul>
<p>The days of a case made together with Generate all get <b>one agreement per attorney for the whole case</b>
(<a href="topic:inv-several-days">more</a>). Three or more days in a row are written as a range
("9/28/2026–10/2/2026"), and dates too wide for the line go on a second line.</p>
<p>The rate and speed on the form: see <a href="topic:inv-speeds">Speeds</a>. The dates: see
<a href="topic:dates-business-days">Dated on a business day</a>. Settings → Options → <i>Include the instructions
page (UCS form page 2)</i> adds the form's second page.</p>
"""),
    T("make-mofr", MAKE, "The MOFR (Minute Order Form/Receipt)",
      "mofr minute order form receipt civil criminal reporter section",
      """
<p>The MOFR gets the reporter's parts only: county, Civil or Criminal, title, your name and location, index number,
part, judge, dates, total copies, the type of order and the page count (the pages anyone ordered, whoever wrote
them). The judge's, counsel's, clerk's and auditor's sections are left blank.</p>
<p>Choose <b>Civil</b> or <b>Criminal</b> under <i>Case</i> in the Outputs box's <i>Options ▾</i>, under MOFR (Settings →
Options → <i>MOFR case</i> sets the default). On a civil form the printed "PEOPLE V" is covered, so the full caption
fits.</p>
<p>The days of a trial made together with Generate all, on one invoice, get one MOFR listing all of them. It ticks
every speed ordered.</p>
"""),
    T("make-preview", MAKE, "The preview before saving",
      "preview look check before save go back tabs side by side files list don't show previews zoom",
      """
<p>Generate and Generate all first show each PDF as it will be saved, a tab for each file, each kind of file in its
own colour. With invoices among them, the first tab, <a href="topic:inv-math">The math</a>, shows how each amount is
reached.</p>
<ul>
<li><b>Save</b> saves them. <b>Go back</b> saves nothing, takes no invoice number and records nothing.</li>
<li>With many files, the arrows at the end of the tabs scroll them, <b>Files ▾</b> lists every file, and Ctrl+Tab /
Ctrl+Shift+Tab (or Ctrl+PgDn / Ctrl+PgUp) go to the next one and back.</li>
<li><b>Side by side</b> shows every file at once; scroll across with the bar at the bottom or Shift and the mouse
wheel.</li>
<li>Ctrl++ and Ctrl+- (or Ctrl and the mouse wheel) zoom.</li>
</ul>
<p>The run sheet, a spreadsheet, is not shown. <b>Don't show previews anymore</b> saves at once from then on;
Settings → Options → <i>Show a preview before saving (Generate, Generate all)</i> turns it back on.</p>
"""),
    T("make-saved", MAKE, "After saving: opening and printing", "print printer open after saving saved message box",
      """
<p>After saving, a box says what was saved and where. After Generate (not Generate all) it can <b>print</b> them:
they go to the printer you pick, every page, at their actual size (a form is not shrunk). The run sheet is a
workbook: print it from Excel.</p>
<p>Settings → Options → <i>Open the PDF after saving</i> opens each PDF when it is saved.</p>
<p>Later, print from <a href="topic:rec-overview">Records</a>: right-click → <i>Print 1 invoice…</i>.</p>
"""),
    T("make-folders", MAKE, "Where the files go: a folder for each case",
      "folder save to location where saved case folder directory path already there add new beside subfolder "
      "invoices math trial runs minute agreements mofr inputs copy documents transcripts rename folder name days "
      "characters",
      """
<p>The PDFs and the case's run sheet are saved in a folder for the case, named by its index number, its days and
its caption ("234567-2026 10-13,14,15-2026 Jones v USA Hauling"), next to your document or inside the <i>Save to</i>
folder chosen in Settings → Options → Folders. Inside it, each kind of file has a folder of its own: <b>Minute
Agreements</b>, <b>MOFR</b>, <b>Invoices</b> (with their detailed copies), <b>Math</b> (how the invoices were added
up) and <b>Trial Runs</b> (the run sheet).</p>
<ul>
<li><b>Case folder name</b>: <code>{index}</code>, <code>{days}</code> (the days, "10-13,14,15-2026"),
<code>{case}</code>, <code>{date}</code>, <code>{dates}</code>, <code>{court}</code>, <code>{county}</code>,
<code>{part}</code>, <code>{judge}</code> and words of your own. A folder's name keeps only letters, digits, spaces
and - , _ ( ): anything else is taken out ("Jones v. USA Hauling" is "Jones v USA Hauling"), so the folder can go
to any computer or cloud drive.</li>
<li>The days of a trial made together share one folder. A day made <b>later</b> renames the case's folder to name it
too ("...10-13,14,15,16-2026..."), folders made by earlier versions ("712345-2021") too, and Records follows. When
a file in it is open and Windows won't rename it, the new files go into it as it is, and it is renamed next
time (the Saved box says so). A day that was made by mistake and deleted since (in Records) leaves the name.</li>
<li><b>If it's already there</b>: when a folder of the very same name has files in it, Generate asks whether to add
to it or make a new one beside it ("712345-2021 10-13-2026 Roe v Poe (2)"), or does one of them without asking if
you prefer. A later day joins the case's folder without asking, the folder renamed for its days; with <i>Make a new
one beside it</i>, it gets a folder of its own instead. The same job generating again uses its folder without
asking.</li>
<li>When your document already sits in the case's folder (one whose name starts with its index number, "712345-2021
Roe"), that folder is used as it is: no other case folder inside it, and a later day doesn't rename it (your
documents are read from it). Another folder in <i>Save to</i> that only starts with the index number ("712345-2021
Transcripts from the clerk") is not renamed or filled.</li>
<li><b>Copy the documents read into an "Inputs" folder beside the files</b> (off at first): the transcripts,
e-mails and photos the files were made from, and pasted text as a .txt file, are copied into an <b>Inputs</b>
folder in the case's folder (in <i>Save to</i> without case folders), to look back at should a file come out
wrong. It keeps a second copy of every transcript; a document already in the case's folder isn't copied, and none
is copied twice.</li>
<li>Untick <i>A folder for each case, inside Save to</i> to save them all in one folder, with no folders
inside it.</li>
<li>Minute agreements, MOFRs, invoices and run sheets can each have <b>a folder of their own</b> (same place). An
output with its own folder keeps it.</li>
</ul>
"""),
    T("make-file-names", MAKE, "File names", "file name pattern rename change placeholders today date attorney number",
      """
<p>Each kind of file is named by a pattern of placeholders, which you can change:</p>
<ul>
<li>Minute agreements: Settings → Options → <i>File name</i>, at first
<i>Minute Agreement - {case} - {index} - {attorney} - {today}</i>;</li>
<li>MOFRs: Settings → Options → <i>MOFR file name</i>;</li>
<li>Invoices: Settings → Invoice → <i>File name</i>, at first <i>Invoice {number} - {case} - {attorney}</i>;</li>
<li>Run sheets: Settings → Run sheet → <i>File name</i>.</li>
</ul>
<p><code>{date}</code> is the date of the minutes. <code>{today}</code> is the date the form is dated: today, or the
next business day (or the next day, in the evening, when Settings → Dates says so:
<a href="topic:dates-business-days">more</a>). A case of several days names the first and last
("Jane Roe v. Sam Poe (9-28-2026 to 10-2-2026)"). Rest the mouse on each box for its placeholders.</p>
"""),
    T("make-fix-lock", MAKE, "Fixing a PDF afterwards, and locking it",
      "edit change correct pdf fillable fields flatten lock final read only no more changes",
      """
<p>The PDFs stay fillable: every value the app typed in, invoice amounts included, is a field you can still change
in a PDF viewer, and a blank one can be typed into.</p>
<p>When a PDF is final, <b>File → Lock finished PDFs (no more changes)…</b> saves a locked copy, which works in any
PDF viewer. Or tick Settings → Options → <i>Flatten the PDF (fields no longer editable)</i> to lock every PDF as it is
made.</p>
<p>Corrected an invoice's amount in the PDF? Tell <a href="topic:rec-change">Records</a> too, so the totals
agree.</p>
"""),
    # ------------------------------------------------------------------------------------------------------ Invoices
    T("inv-priced", INVOICE, "How an invoice is priced",
      "price cost amount charge original copy emailed copy index judge's index split share parties per page rate "
      "bill total",
      """
<p>An invoice is made for each ticked attorney who ordered pages. It bills the transcript's pages (your own pages,
when several reporters wrote it) at the prices of your <a href="topic:rates-sheets">rate sheet</a>. For each speed,
per page:</p>
<table cellpadding="3" border="1" cellspacing="0">
<tr><th align="left">Line</th><th align="left">Charged</th></tr>
<tr><td>Original</td><td>Once, split between the parties</td></tr>
<tr><td>Copy</td><td>One for each party</td></tr>
<tr><td>E-mailed copy</td><td>One for each party (optional)</td></tr>
<tr><td>Index</td><td>One for each party, on the pages it ordered, when the transcript is long enough
(<a href="topic:inv-index">more</a>)</td></tr>
<tr><td>Judge's index</td><td>Once, with the index, split between the parties</td></tr>
</table>
<p>Each party pays its share, rounded up to the cent so the shares cover the total: $319.30 three ways is $106.44
each (with Rounding at <i>Exact</i>, as at first). When firms ordered different pages, each pays for the stretches it ordered: a stretch it ordered alone in
full, a stretch shared with others split (<a href="topic:exc-table">more</a>). How a fraction of a cent is rounded:
<a href="topic:inv-rounding">Rounding</a>.</p>
<p>Like most reporters' invoices, it shows only each speed's amount, with your turnaround and payment details.
<a href="topic:inv-granular">Granular detail</a> adds your pages billed and the prices. <a href="topic:inv-math">The math</a>
spells out every charge.</p>
"""),
    T("inv-no-transcript", INVOICE, "An invoice without a transcript",
      "no transcript caption title page email estimate pages typed bill without pdf",
      """
<p>No transcript yet (only a caption or title page, or an e-mail)? Type the pages to bill in <i>Est. number of
pages</i>: the invoice bills them. A number read from an e-mail is shown on the forms but not billed until you type
it.</p>
<p>The run sheet still needs a transcript.</p>
"""),
    T("inv-speeds", INVOICE, "Speeds: what the invoice offers and the agreement names",
      "speed delivery regular expedited expedite daily immediate turnaround offered agreement form speed rate per "
      "page choose",
      """
<p>Every speed is chosen in the <b>Who ordered</b> card:</p>
<ul>
<li><b>Speed</b>, at its top: the speed the minute agreement forms name, at one rate per page: Expedited when you
offer it, else the slowest offered (Settings → Invoice → <i>Agreement form speed</i> changes the rule). Choose
another for the job: in a trial it is every day's. ↺ goes back to the rule.</li>
<li><b>Speeds offered</b>, beside it: what the invoice of a firm ordering alone offers, each at its own price, so
the attorney can choose. Tick one to bill that speed alone.</li>
<li>Each firm's row has its own <b>Speed</b>, by name (<a href="topic:inv-who-ordered">more</a>). A firm whose
speed is chosen there gets it on its own agreement and invoice.</li>
<li>When an e-mail asks for another speed, an amber line asks you to choose (<i>Keep</i> keeps the one shown), and
Generate asks too.</li>
<li>Once a firm's speed is chosen in its row, the <i>Speeds offered</i> boxes are greyed: they only list the speeds
for a firm that chooses from its invoice, and a click asks before changing them.</li>
</ul>
<p>The rate (under <i>Pages and dates</i>), the delivery box and the <a href="topic:dates-turnaround">estimated
delivery date</a> follow the speed.</p>
"""),
    T("inv-panel", INVOICE, "The Invoice card", "Invoice card parties prices billed includes line options this job",
      """
<p>The <b>Invoice</b> card of the form, under <i>Pages and dates</i> and above <i>Who pays what</i> (shown while
<i>Invoice</i> is ticked in the Outputs box), shows the prices before you generate, and holds this job's choices
for its invoice:</p>
<ul>
<li><b>Parties</b>: the number of ordering parties (who ordered which pages is <a href="topic:exc-table">Who ordered which pages…</a>,
in Who ordered);</li>
<li><b>Whose pages…</b>, on a transcript several reporters wrote (<a href="topic:inv-reporters">more</a>);</li>
<li><b>Peripherals…</b>: the e-mailed copy and the index for this job (<a href="topic:inv-peripherals">more</a>);</li>
<li><b>Show granular detail</b> and <b>Customize…</b> (<a href="topic:inv-granular">more</a>);</li>
<li>the <b>Prices</b> line, the <b>Billed</b> line ("You wrote 45 of 83 total pages") and the <b>Includes</b> line
(<i>E-mailed copy, index (83 total pages, 50 or more)</i>), and a link to the math.</li>
</ul>
<p>The speeds the invoice offers are ticked in Who ordered, beside the Speed (<a href="topic:inv-speeds">more</a>).
With Settings → Invoice → <i>Firms ordering the same pages</i> set to ask, a firm sharing pages without a speed
chosen is priced at the agreement form's speed with a question mark (<i>Dana Smith: Expedite? $98.00</i>) until
Generate asks. Your defaults for every invoice are in
<a href="topic:set-invoice">Settings → Invoice</a>.</p>
"""),
    T("inv-peripherals", INVOICE, "Peripherals…: the e-mailed copy and the index for one job",
      "peripherals emailed copy email index yes no auto this job skip",
      """
<p><b>Peripherals…</b> in the Invoice card sets, for this job only:</p>
<ul>
<li><b>the e-mailed copy</b> for each party (some attorneys skip it to save money);</li>
<li><b>the index</b>: <i>Auto</i> (when the whole transcript has 50 total pages or more), <i>Yes, for this job</i> (a short
transcript too) or <i>No, for this job</i>.</li>
</ul>
<p>New jobs start from Settings → Invoice. The <i>Includes</i> line says what this job's invoice gets and why.</p>
"""),
    T("inv-index", INVOICE, "When there is an index",
      "index word index concordance threshold 50 pages judge's index several days shared pages no index price",
      """
<p>An index is charged when the <b>whole transcript</b> has 50 total pages or more (every reporter's pages), though
each invoice charges it on its own pages: your 45 pages of 83 total pages get one, charged on your 45.</p>
<ul>
<li>The 50 is Settings → Invoice → <i>Add an index (and one for the judge) from</i>.</li>
<li><b>Index on several days</b>: by default, once any day of a case reaches it, every day gets an index; it can be
each day on its own, or the days together.</li>
<li><b>Index on shared pages</b>: each firm pays its own (the default), or one index split between the firms.</li>
<li><a href="topic:inv-peripherals">Peripherals…</a> says yes or no for one job.</li>
<li>A page count you typed below the transcript's total pages, when the two would decide differently: Generate asks.</li>
<li>A rate sheet with no index price for the speeds offered: no index can be charged, and Generate says so.</li>
</ul>
"""),
    T("inv-granular", INVOICE, "Granular detail and the detailed copy",
      "granular detail customize breakdown itemized page count price per page charges split detailed copy",
      """
<p>Without granular detail, the invoice lists each speed with its turnaround and the amount due. Tick
<b>Show granular detail</b> in the Invoice card (for this job; it starts unticked for every new job) to add what
<b>Customize…</b> chooses: your page count, your pages of each day, the price per page, the charges that make up each
amount and the split between the parties.</p>
<p>Settings → Invoice → <i>Also save a detailed copy of each invoice</i> saves "… (detailed).pdf" next to each
invoice: the same invoice, with the same number, with the granular detail. It isn't opened, printed or recorded
again: it's there for when someone asks. An invoice that already shows the granular detail gets none.</p>
"""),
    T("inv-numbers", INVOICE, "Invoice numbers", "invoice number numbering sequence format 2026-0001 year next skip",
      """
<p>Invoices are numbered 2026-0001, 2026-0002, … The pattern is Settings → Invoice → <i>Invoice numbers</i>:
<code>{year}</code> and <code>{seq}</code> (the count this year; <code>{seq:04}</code> = 0007), <code>{yy}</code> =
26.</p>
<p>Each number is taken from the records when its invoice is made, and claimed at once: two copies of the app making
an invoice at the same moment never get the same number. A number is never given to another invoice, even when its
invoice is deleted. Going back from the preview takes no number.</p>
<p>The year is the year the invoice is dated: made on the evening of 12/31/2026 with <i>Made after 5:00 PM</i>
ticked (Settings → Dates), it is dated 1/4/2027 and numbered 2027-0001 (<a href="topic:dates-evening">more</a>). Invoices for another reporter's pages have numbers of their
own (DS-2026-0001).</p>
"""),
    T("inv-who-pays", INVOICE, "Who pays what", "who pays what card each firm share amount per page alone shared",
      """
<p>The <b>Who pays what</b> card, under the Invoice card, sums up each firm's invoice: its pages billed (yours), how it ordered them
(<i>70 alone + 50 shared by 2</i>) and what it pays at each speed offered, in all and per page, for every day
ticked in the job list. It follows every tick at once: days, attorneys, speeds, Parties, Peripherals… and
Who ordered which pages…. With more than one invoice (a day invoiced already beside one still to bill, or several cases), each has
its own heading; one made already says <i>invoiced already ✓</i>.</p>
<p><i>How these amounts are worked out…</i> opens the whole <a href="topic:inv-math">math</a>.</p>
"""),
    T("inv-who-ordered", INVOICE, "Who ordered a trial: what each firm ordered, at which speed",
      "who ordered what card day pages speed also ordered rows excerpts whole trial they choose firms ordering the "
      "same pages billed asked one speed several",
      """
<p>Each firm's row in the <b>Who ordered</b> card says what it ordered and at what speed, over every day ticked in
the job list, whichever day is shown (<a href="topic:check-attorneys">ticking who ordered</a>):</p>
<ul>
<li><b>What</b>: <i>The whole trial (4 days)</i>, a list of days, or <i>part of 6/4/2026</i> for some pages. Change
it there: the whole trial, only the day shown, or <i>Some days or pages…</i> (<a href="topic:exc-table">Who ordered which pages…</a>).</li>
<li><b>Speed</b>, by name. Firms that ordered the same pages are each billed one speed: while none is chosen for a
firm, it is the Speed of the forms at the top of the card (<i>Expedite</i>), and that is what is billed. A firm
ordering alone shows <i>They choose: Regular or Expedite</i>: its invoice lists each speed offered. Choose a speed
in the row and it is the firm's for every day of the trial; <i>Several (set in Who ordered which pages…)</i> when its days or
pages differ.</li>
<li><b>Your pages</b>: how many of its pages are billed: on a transcript of several reporters only yours; <i>0 of 40
total: no invoice</i> when none of them are; <i>(typed)</i> when it is the Pages field's number.</li>
</ul>
<p>The line under the table says who orders what at which speed, then what Generate all bills: the days invoiced
already (✓), those unticked in the job list, a day nobody ordered (no invoice for the case until someone does) and
a day waiting for a choice.</p>
<p>Firms that ordered the same pages split the original and the judge's index; each pays its own copies and index.
Generate bills the speeds shown without asking. Settings → Invoice → <i>Firms ordering the same pages</i>: <i>Ask me
each firm's speed at Generate</i> asks first, one line per firm for the whole trial.</p>
"""),
    T("inv-several-days", INVOICE, "Several days of one case: one invoice, one agreement",
      "trial several days multiple days joint invoice one invoice per attorney whole case mofr generate all",
      """
<p>When you generate the days of a case together with <b>Generate all</b>, each ordering attorney gets <b>one
invoice</b> for all its days, billed only for the days it ordered, and only for the pages it ordered. A firm ticked
in Who ordered orders every day (<a href="topic:check-attorneys">more</a>).</p>
<p>The <b>minute agreements and the MOFR are made once</b> for those days too: one agreement per attorney, listing
only the days it ordered, and one MOFR listing every day. The estimated delivery date is the latest of them. A trial
of 4 days ordered by 4 firms makes 4 invoices, 4 agreements, one MOFR and a run sheet, when all four outputs are
ticked.</p>
<ul>
<li>A day once invoiced is not billed again by Generate all. It stays in the cards, with the invoice that billed it;
new documents for it make it billable again.</li>
<li><i>Generate 6/4/2026 only</i> (the button names the day shown) makes that day alone; <i>Generate all 4 days</i>
makes them all. Each button's tooltip lists the files it makes.</li>
<li>Settings → Invoice → <i>Days of one case</i>: <i>An invoice for each day</i>. Settings → Options →
<i>Minute agreements and MOFRs: one for the whole case</i>: untick for forms for each day.</li>
<li>Opened again from Records, a trial comes back with who ordered each day, as it was made.</li>
</ul>
<p>A day that still waits for a choice: <a href="topic:inv-undecided">A day not decided yet</a>.</p>
"""),
    T("inv-undecided", INVOICE, "A day not decided yet", "undecided go back and decide go on anyway nobody ticked held "
      "not invoiced",
      """
<p>When Generate all includes a day whose invoice waits for a choice (Who ordered which pages… to check, Whose pages… to answer,
or a firm's speed to change in Who ordered), or a case with a day nobody is ticked on, it says which
first:</p>
<ul>
<li><b>Go back and decide</b> (the default) makes nothing and shows the first day to decide;</li>
<li><b>Go on anyway</b> makes everything else. Those days get no invoice for now; the other days of their case are
invoiced without them, and the undecided days can be invoiced on their own later.</li>
</ul>
<p>A case with a day nobody is ticked on gets no invoice at all until you tick who ordered that day.</p>
"""),
    T("inv-reporters", INVOICE, "Several reporters on one transcript: whose pages",
      "several reporters shared trial initials my pages your pages whose pages other reporter invoices for billed "
      "line whole transcript total pages difference count every reporter's",
      """
<p>When reporters take turns on a trial, the initials at the foot of the pages change, and your invoice bills
<b>your own pages</b> only: of a 150-page transcript where 65 pages carry your initials, the invoice is for 65. The
<i>Billed</i> line says "You wrote 65 of 150 total pages". The minute agreements still count every page an attorney
ordered.</p>
<p><b>Whose pages…</b> (Invoice card) has a box for <i>My pages</i>, each other reporter's pages ("DS's pages") and
<i>The whole transcript</i>. Each other reporter you tick gets invoices of their own for their pages: in their name,
with their address and how to pay them (Settings → Run sheet → <i>Invoices for</i>, or <b>Details…</b>), numbered
apart from yours (DS-2026-0001). They are theirs, so Records leaves them out of your totals and lists them only
when you click <i>Show them</i> there (<a href="topic:rec-overview">more</a>).</p>
<p>The app asks when it can't tell: when none of the pages carry your initials, or the transcript begins with pages
nobody's initials are on. A transcript with no initials at all is billed in full. Put your initials in Settings →
My info if they aren't the first letters of your name.</p>
"""),
    T("inv-text", INVOICE, "Your own invoice text", "invoice text wording note message payment details footer "
      "conditions placeholders preview zelle check terms",
      """
<p>Settings → Invoice → <i>Invoice text</i> is a list of short texts, each with:</p>
<ul>
<li><b>Where</b> it goes: at the top, under the transcript details, under the amounts, payment, or the small print at
the foot;</li>
<li><b>Show when</b>: always, or only when it applies: more than one party ordered, one speed or several are
offered, it covers several days, the attorney ordered an excerpt, and more.</li>
</ul>
<p>Texts can use placeholders such as <code>{case}</code>, <code>{index}</code>, <code>{pages}</code> (your pages
billed), <code>{total_pages}</code> (total pages, every reporter's),
<code>{parties}</code> and <code>{bill_to}</code>; <code>{transcript} {is}</code> gives "transcript is" or
"transcripts are". By default they are the notes the invoice always had, such as <i>The transcript is delivered once
every party has paid</i> when several parties ordered, and your payment details. <b>Preview…</b> shows a made-up
invoice with your text; <b>Restore defaults</b> brings back the first ones.</p>
"""),
    T("inv-math", INVOICE, "The math: how each amount is reached",
      "math calculation breakdown explain how worked out copy all save as pdf by invoice firms side by side "
      "the math pdf who pays what a page different speeds stretch each side",
      """
<p><b>The math</b> shows how each amount is reached, in tables:</p>
<ul>
<li><b>By invoice</b>: a row for each charge, with its pages billed, rate and cost, how it is paid and what this firm pays
(<i>Original | 59 | $5.40 | $318.60 | Each firm splits this cost (÷ 4) | $79.65</i>);</li>
<li><b>Firms side by side</b>: a column for each firm.</li>
</ul>
<p>When firms ordered the same pages at <a href="topic:exc-speeds">different speeds</a>, <b>Who pays what a page</b>
follows, a table for each set of those pages: what each firm on them pays a page of each charge and in all, as its
invoice bills it, and the firms together (<i>Alex B. Counsel · Daily · Original $3.25 · Copy $1.25 · E-mailed copy
$1.25 · $5.75 a page</i>).</p>
<p>It is the first tab of the preview, and behind the links under Who pays what and in the Invoice card. With
previews off it comes in a window after saving: <b>Copy all</b>, <b>Save as PDF…</b> (for an attorney who asks) or
<b>Don't show this anymore</b> (Settings → Options → <i>Show the math of each invoice</i> turns it back on).</p>
<p><b>Generate saves it</b> as PDFs in the case's <b>Math</b> folder (next to the invoices when you save
without a folder for each case, or when the invoices have a folder of their own): each firm's own ("… - the
math.pdf", to send that firm), which shows only what that firm owes, and everyone's in one, every firm's
amounts, to look back at the job. Which is saved (both, either or none) is chosen under the math itself and in Settings → Invoice → <i>Save the
math</i>. <b>Save as PDF…</b> in the math's window does the same: everyone's, or only one firm's.</p>
"""),
    T("inv-rounding", INVOICE, "Rounding", "rounding round cents fraction of a cent exact price a page by hand calculator",
      """
<p>A share can come to part of a cent a page: four firms sharing Immediate pay $6.6125 a page. Settings → Invoice →
<i>Rounding</i>:</p>
<ul>
<li><b>Exact</b> (the default) keeps every fraction of a cent and rounds the amount up to the cent once, at the end:
$6,612.50 for 1,000 pages.</li>
<li><b>The price a page, to the cent</b> works it out as by hand: the price a page is rounded to the nearest cent
first, then multiplied, $6.61 × 1,000 = $6,610.00, so a firm checking it with a calculator gets the same.</li>
</ul>
<p>The math says which was used (<i>$6.6125 a page, rounded to $6.61, × 1,000 pages</i>). With granular detail,
the charges of an invoice split evenly end with what each party pays (<i>= $26,450.00, split 4 ways: $6,610.00
each</i>). The prices in <a href="topic:exc-table">Who ordered which pages…</a> are rounded the same way. The
<a href="topic:inv-spreadsheet">spreadsheet template</a> always rounds as Exact does.</p>
"""),
    T("inv-spreadsheet", INVOICE, "The invoice spreadsheet template", "spreadsheet excel google sheets template workbook "
      "manual invoice",
      """
<p>Prefer a spreadsheet? <b>File → Save the invoice spreadsheet template…</b> gives you an Excel or Google Sheets
workbook that prices invoices the same way when every party orders every page (it has no excerpts). Fill in
<i>Setup</i> once, then <i>Job</i> for each invoice, and print the <i>Invoice</i> tab.</p>
<p>The workbook always rounds as <b>Exact</b> does: each party's amount up to the cent, once, at the end. With
<a href="topic:inv-rounding">Rounding</a> set to the price a page, its amounts can differ from the app's by up to
half a cent a page ($6,612.50 there, $6,610.00 here, for 1,000 pages).</p>
"""),
    # ------------------------------------------------------------------------------- Pages ordered and speeds
    T("exc-table", EXCERPTS, "Who ordered which pages…: a firm that ordered some pages only (an excerpt)",
      "excerpt excerpts part of the transcript some pages runs page range split run remove run partial order firm "
      "ordered only how to use steps button pages ordered each firm",
      """
<p>When one firm ordered the whole trial and others only some pages (an excerpt), open <b>Who ordered which
pages…</b> (the button under the firms in Who ordered, or
<i>Some days or pages…</i> in a firm's <i>What</i>). It is one table for every day of the case on that invoice (every day ticked, as a rule):</p>
<ul>
<li>each row is a <b>run of pages</b> of a day, typed in its <b>Page numbers</b> cell in the transcript's own
printed page numbers (<i>141-170</i>); the rows around a run you type make room for it. A job of several days is
ordered whole: its cell shows the page numbers printed on its transcripts;</li>
<li>each firm has a box: <b>tick the firms that ordered the run</b>. At first every ticked firm ordered every
page;</li>
<li><b>Split run</b> cuts a run in two. <b>Remove run</b> (or the Delete key, or a right-click) gives its pages to the
run next to it, so every page stays in a run;</li>
<li><b>Remove this day's excerpts</b> and <b>Remove all excerpts</b> go back to whole days.</li>
</ul>
<p>For each run it counts <a href="topic:exc-your-pages">your pages and every reporter's</a> and shows what each
firm pays; under it, what each group of firms ordering
together pays and each firm's invoice, as you type. Pages ordered together split the original and the judge's
index; each firm pays its own copy, e-mailed copy and index. A run nobody ticks is billed to nobody.</p>
<p>The <b>?</b> beside the button, and the one at the top of the window, show these steps in short.
The window stays open beside the main window and follows what you change there. When the day's total page count changes
so that the rows no longer end on its last page, the <i>Prices</i> line says <i>Who ordered which pages… needs checking</i> and no
invoice is made for that day until you fix them.</p>
<p>Example (no index): with $4.30 originals and $1.00 copies and e-mailed copies, 40 pages ordered by Dana Smith
alone and 50 by both attorneys cost Dana Smith 40 × $6.30 + 50 × ($2.15 + $2.00) = $459.50, and the other attorney 50 × $4.15 =
$207.50.</p>
"""),
    T("exc-your-pages", EXCERPTS, "Your pages and every reporter's, in Who ordered which pages…",
      "your pages billed transcribed total every reporter count columns hide only your pages filter clear mine",
      """
<p>On a transcript several reporters wrote, <b>Who ordered which pages…</b> counts each run's pages four ways:</p>
<ul>
<li><b>Your pages billed</b>: your pages of the run that your invoice bills (as Whose pages… says); 0 when no firm
ordered the run;</li>
<li><b>Your pages transcribed</b>: the pages of the run with your initials, ordered or not;</li>
<li><b>Total pages transcribed</b>: every reporter's pages of the run;</li>
<li><b>Total pages billed</b>: every reporter's pages of the run, when a firm ordered it.</li>
</ul>
<p>Under the table, each group of firms ordering together says both counts too: <i>43 of your pages billed
(93 total pages)</i>.</p>
<p><b>Columns ▾</b> (or a right-click on the table's headings) hides the counts you don't need. A <i>?</i> means
which pages are yours can't be told yet: set your initials in Settings → My info, or say whose the first pages are
under Whose pages….</p>
<p>Tick <b>Only your pages</b> to see only the runs with pages of yours, billed or not; <b>Clear filter</b> shows
every run again.</p>
"""),
    T("exc-speeds", EXCERPTS, "Firms ordering the same pages at different speeds",
      "split order shared pages different speeds daily immediate faster slower fastest commit speed which speed "
      "did each firm order split invoices",
      """
<p>When firms order the same pages, each one <b>commits to a speed</b> and is billed that speed alone. Only a firm
ordering by itself gets the invoice that lists every speed to choose from.</p>
<ul>
<li>Each firm's speed is in its row of <a href="topic:inv-who-ordered">Who ordered</a>, by name: the forms' speed
while none is chosen. Choose another there, or, for one run, by right-clicking the firm's box in Who ordered which pages…
(<i>Dana Smith on this run at… ▸</i>). The boxes above its table set the speed of all a firm's pages.</li>
<li>Generate bills the speeds shown. With Settings → Invoice → <i>Firms ordering the same pages</i> set to ask, it
asks <i>Which speed did each firm order?</i> first, one line per firm for the whole trial.</li>
</ul>
<p>At different speeds, the one original is divided as Settings → Invoice → <b>Split invoices</b> says. By
default, it is billed at the <b>fastest</b> speed ordered. Each slower firm pays its share as if every firm had
ordered its speed, and the fastest pays the rest. The judge's index is divided the same way. Each pays its own copies
at its own speed, and its own index too (unless Settings → Invoice → <i>Index on shared pages</i> is <i>Split between
the firms</i>).</p>
<p>Example (10 pages, no index): one firm orders Daily, one Immediate. The original is billed at Immediate, $7.60 a
page. The Daily firm pays $6.50 ÷ 2 = $3.25 of it plus its own copies: $57.50. The Immediate firm pays the rest,
$4.35, plus its own: $72.50.</p>
<p>The math of an invoice says how it was divided, and what each firm on those pages pays a page. A trial is
billed one way throughout: once a day of it is invoiced, every later day of the same index number is divided the
same way, and a job made again or opened again from Records is billed as it was, whatever Split invoices says by
then.</p>
<p>Every party on such pages must be named. When <i>Parties</i> counts more than the firms ticked and they ordered
different speeds, the app can't tell what the others pay: no invoice is made for that day until you tick the missing
firm (with its speed) or change Parties, and Generate lights up the Parties box to show where.</p>
<p>A firm whose speeds differ by day gets an agreement ticking both speeds, with <i>see below</i> on the rate line.
For now, at most two different speeds may share the same pages: a run with three holds the invoice, with the reason
shown.</p>
"""),
    # ------------------------------------------------------------------------------------------------------- Records
    T("rec-overview", RECORDS, "Records: what you billed and what was paid",
      "records history dashboard invoices list totals billed paid outstanding owed filter year month firm status "
      "everything made log ctrl+r colleague another reporter invoices hidden not listed show them",
      """
<p><b>Records</b> (Ctrl+R, the Records button, or File → Records (invoices and history)…) has two tabs:</p>
<ul>
<li><b>Invoices</b>: totals billed, paid and outstanding, filters by year, month, firm and status, and the
<i>By firm</i> and <i>By month</i> breakdowns.</li>
<li><b>Everything made</b>: every minute agreement, MOFR and invoice, and every run sheet takes were added to.
Double-click to open the file.</li>
</ul>
<p>Records lists your own invoices. Those you made for a colleague's pages (<a href="topic:inv-reporters">Whose
pages…</a>) are theirs: they are never in your totals, and aren't listed until you ask. A line under the filters
says how many the filters match ("Not listed: 2 invoices made in a colleague's name"); click <b>Show them</b> to list
them, with their initials under <i>For reporter</i> (their files in <i>Everything made</i> too), and <b>Hide
them</b> to hide them. The next time you open Records they are hidden again.</p>
<p>Right-click an invoice to open the PDF, show it in its folder, print it, <a href="topic:rec-reopen">open its job
again</a>, mark it paid, <a href="topic:rec-change">void it or change its amounts</a>, add a note or delete it.</p>
<p>More: <a href="topic:rec-paid">marking paid</a> · <a href="topic:rec-boxes">tick boxes, status and colours</a> ·
<a href="topic:rec-notes">notes</a> · <a href="topic:rec-search">searching</a> · <a href="topic:rec-columns">the
columns</a> · <a href="topic:rec-button">the count on the Records button</a> · <a href="topic:rec-undo">Undo</a> ·
<a href="topic:rec-delete">the trash</a> · <a href="topic:rec-export">exporting</a>.</p>
<p>The records are kept in <code>%APPDATA%\\YinItAgreementForm\\records.db</code>, and copied to
<code>invoices.csv</code> and <code>activity.csv</code> in <i>Documents\\YinIt Records</i> after every change, so you
can always open them in Excel. Text Excel would take for a formula (<i>- left a message</i>, <i>=1+1</i>)
starts with an apostrophe there, so it opens as text; Excel shows the apostrophe.</p>
"""),
    T("rec-paid", RECORDS, "Marking an invoice paid", "paid payment received mark paid not paid which speed amount date "
      "check cleared",
      """
<p>Tick <b>Paid</b> on an invoice when it is paid (or right-click → <i>Mark paid…</i>). You're asked which speed they
paid for, the amount and the date. Untick it, or right-click → <i>Mark not paid</i>, to take it back.</p>
"""),
    T("rec-boxes", RECORDS, "Tick boxes, status and colours",
      "track tracking transcribed transcript sent invoice sent proofread status column colour color rows orange green "
      "blue yellow teal purple sent not paid ready to send done custom boxes workflow",
      """
<p>Use as much or as little of it as you like: most people tick Paid alone, which is all that's on at first, and
nothing pops up or reminds you.</p>
<p>In Settings → <b>Records</b> (or <i>Tick boxes and colours…</i> under <b>Columns…</b>), switch on <b>Invoice
sent</b>, <b>Transcribed</b> or <b>Transcript sent</b>, or add boxes of your own (<i>Proofread</i>):</p>
<ul>
<li>each is a column after Paid, ticked with a click (several invoices selected: right-click → <i>Tick
Transcribed</i>), and Undo takes a tick back;</li>
<li>each box has a word for ticked and one for not ticked, which the <b>Status</b> column puts together ("Paid,
Transcribed, Not sent");</li>
<li><b>Transcribed</b> is about the transcript, not the firm: ticked on one firm's invoice, it is ticked on the
other firms' invoices of the same transcript (same index number, days and reporter). An invoice made later for
that transcript (another firm orders a copy) starts ticked, with the same date. Paid and the other boxes are each
firm's own, and start unticked (unless you set one of them to <i>Whole transcript</i> in Settings →
Records).</li>
</ul>
<p><b>Colours</b>: each row takes the first colour in the list that matches it, and you can change them. The list,
first to last: sent but not paid purple; sent green; <b>ready to send</b> orange (transcribed, and every firm that
ordered those days has paid); transcribed but not paid by every firm blue; paid but not transcribed yellow; not paid
and not transcribed teal. With Transcript sent but not Transcribed: sent but not paid purple, sent green, ready to
send orange once every firm has paid, paid and waiting on other firms blue, not paid teal. With Paid alone, as at
first (or with Invoice sent, or boxes of your own): paid green, not paid teal. Untick <i>Colour the rows</i> for
none.</p>
<p>Example: four firms ordered the 6/3/2026 transcript of <i>Jane Roe v. X.Y. Holding Corporation</i>. Tick
Transcribed once and all four are ticked; each turns orange once all four have paid, and green once you tick it
sent. The Status filter lists the colours too (<i>Ready to send</i>).</p>
"""),
    T("rec-notes", RECORDS, "Notes on an invoice", "note notes comment remark memo type",
      """
<p>Double-click a <b>Notes</b> cell (or press F2) to type a note in place; Enter keeps it. Or right-click →
<i>Notes…</i>. Search finds the words of a note too.</p>
"""),
    T("rec-search", RECORDS, "Searching the records",
      "search find look up filter firm case index number invoice number judge regex fuzzy misspelled typo",
      """
<p>Type in the search box of either tab to see only the records that match: a firm ("Smith Law"), an attorney, a
case, an index number (712345/2021 or 712345-2021), an invoice number, a judge, a file name. Every word you type
must be found somewhere in the record, in any order.</p>
<ul>
<li><b>Regex</b> reads what you type as a regular expression (<code>^Smith</code>, <code>2026-00(1|2)</code>). The
box turns amber while it is incomplete.</li>
<li><b>Fuzzy</b> also finds near misses and misspellings ("Counsle" finds "Counsel &amp; Counsel"). It treats numbers
the same way, so "2026-0001" also finds 2026-0002; untick Settings → Options → <i>Fuzzy search matches numbers
loosely too</i> to have numbers found only as typed.</li>
</ul>
"""),
    T("rec-columns", RECORDS, "Choosing the columns", "columns show hide add sort heading pages speed ordered excerpt",
      """
<p>Click <b>Columns…</b> (or right-click a column heading) to choose what each table shows; the choice is remembered.
Invoices can show the court, part, judge and dates, the firm and e-mail, your pages billed, your pages transcribed and
the total pages transcribed (every reporter's), who wrote how many ("PR 65, DS 85"), the excerpt ordered, the parties, the speeds offered, the
<b>speed ordered</b> (the one paid for), the e-mailed copy and index, the amounts, the status and payment, notes and
the file.</p>
<p><i>Everything made</i> shows the <i>Pages on the file</i> (what each file counts: the pages ordered on a minute
agreement or MOFR, those billed on an invoice), your pages transcribed and the total pages transcribed.</p>
<p>Click a heading to sort by it. <i>Back to the usual columns</i> resets them.</p>
"""),
    T("rec-reopen", RECORDS, "Opening a job again", "reopen open again corrected invoice another day past job previous "
      "redo recent jobs start card how many hide days old",
      """
<p>Right-click an invoice, or a file under <i>Everything made</i>, and choose <b>Open this job again</b>: the case
comes back into the main window as you left it (the fields, who was ticked, Peripherals… and Who ordered which pages…). The
documents it was read from are read again when they are still where they were. Use it for a corrected invoice, or to
add another day of the case.</p>
<p>An empty main window also lists your recent jobs: click one to open it again. How many it lists (3 at first, 5 at most),
how lately made (30 days at first) and whether it lists them at all are under Settings → Options → <i>Recent
jobs</i>. File → Open recent lists the documents and folders you opened lately.</p>
"""),
    T("rec-change", RECORDS, "Correcting an invoice: Change amounts… and Void",
      "change amounts corrected amount void cancel cancelled wrong invoice mistake not counted",
      """
<ul>
<li><b>Change amounts…</b> (right-click): when you corrected an amount in the invoice PDF, tell the records too, so the
totals agree. The records keep the amounts it was made with until you do.</li>
<li><b>Void (cancelled, not counted)</b>: the invoice stays listed but is left out of the totals. <i>Restore (not
void)</i> takes it back.</li>
</ul>
<p>To make a corrected invoice, <a href="topic:rec-reopen">open the job again</a>.</p>
"""),
    T("rec-undo", RECORDS, "Undo in Records", "undo ctrl+z take back mistake revert",
      """
<p><b>Undo</b> (or Ctrl+Z) takes back the last change made in the Records window: paid or not paid, a box ticked or
unticked, void, changed amounts, a note, a delete or a restore. It goes back up to 30 changes, until the app is
closed or a backup is restored.</p>
"""),
    T("rec-summary", RECORDS, "Summary and monthly recaps",
      "summary recap month year total income earnings how much made average per page report",
      """
<p><b>Summary…</b> sums up this or last month, this or last year, or all time: invoices made, your pages billed, billed,
paid, still owed, payments received in the period, the average per page and per invoice, and the firms billed most.
<b>Copy</b> puts it on the clipboard.</p>
<p>The first time you open Records in a month, a box says what last month came to ("Last month (September 2026) you
made $870.00 with 243 of your pages billed (5 invoices)."), and the first time in a year, last year too. <i>Don't show me monthly or
annual recaps anymore</i> stops them; Settings → Options → <i>Recaps</i> turns them back on.</p>
"""),
    T("rec-backups", RECORDS, "Backups of your records", "backup restore copy lost records go back daily",
      """
<p>Each day you open the app, a copy of the records is saved in <i>Documents\\YinIt Records\\Backups</i>. The last 10
days' copies are kept, and the last 5 made with <i>Back up now</i> or before a restore.</p>
<p><b>Backups…</b> lists them, makes one now (<i>Back up now</i>), and <b>restores</b> one: the records go back to
what they were that day, after a copy of how they are now is made, so you can come back. Only the records are in a
backup, not the PDF files. Invoice numbers given since stay taken.</p>
"""),
    T("rec-delete", RECORDS, "Deleting records, and the trash", "delete remove trash restore deleted permanently "
      "for good",
      """
<p>Select records and press <b>Delete</b> (or right-click → <i>Delete</i>): they go to the <b>🗑 Trash</b> for 30
days, where you can restore them, and are then deleted for good. Only the records are deleted, never the PDF files,
and an invoice's number is never given to another invoice.</p>
"""),
    T("rec-export", RECORDS, "Exporting: a report, Excel or CSV",
      "export report html excel xlsx csv spreadsheet accountant taxes records folder",
      """
<p>The buttons at the bottom of Records export:</p>
<ul>
<li><b>Report (HTML)…</b>: a report of the invoices shown, opened in your browser;</li>
<li><b>Excel…</b>: the invoices, everything made, and sheets by firm and by month;</li>
<li><b>CSV…</b>: <code>invoices.csv</code> and <code>activity.csv</code>.</li>
</ul>
<p>The CSV copies in <i>Documents\\YinIt Records</i> are also kept up to date after every change (<b>Open records
folder</b>). <code>invoices.csv</code> has a column for each tick box in use besides Paid, with the day it was ticked
(<i>Transcribed: 6/10/2026</i>).</p>
"""),
    T("rec-button", RECORDS, "The count on the Records button", "records button count ready to send not paid number "
      "badge",
      """
<p>The <b>Records</b> button in the main window counts the invoices of one status as you work, such as
<i>Records · Ready to send: 3</i>. Choose which (or <i>Nothing</i>, to turn the count off) under <i>Count on the
Records button</i> in Settings → Records. It never pops up. With Paid alone no invoice is ever ready to send
(that takes Transcribed or Transcript sent), so the button counts the invoices <i>Not paid</i> instead until you
switch one of them on. It counts only the invoices for your own pages, as Records' totals do (those you
make for a colleague's pages are theirs).</p>
"""),
    # ------------------------------------------------------------------------------------- Dates and business days
    T("dates-business-days", DATES, "Dated on a business day",
      "date dated weekend saturday sunday holiday next business day monday tuesday moved postdated post-date why "
      "date of agreement invoice date",
      """
<p>A minute agreement form or an invoice made on a weekend or a court holiday is dated the <b>next business
day</b>. Made on Sunday 10/11/2026, with Columbus Day on the Monday, it says Tuesday 10/13/2026. So do the invoice
number's year, its date in Records and <code>{today}</code> in the file names.</p>
<p>A line under the <i>Date of agreement</i> says when it was moved and why: <i>Dated Tue 10/13/2026, the next
business day: today is a Sunday and Mon 10/12 is Columbus Day.</i> The message after saving says it too.</p>
<p>The date shown in the preview is the date saved, even if the clock passes midnight while the preview is open. A
window left open past midnight moves the dates it filled in to the new day; a date you typed stays.</p>
<p>Settings → <b>Dates</b> → <i>Date forms and invoices on a business day</i> turns it off: then a form made on
Sunday is dated Sunday. See also <a href="topic:dates-holidays">the holidays</a> and
<a href="topic:dates-evening">forms made in the evening</a>.</p>
"""),
    T("dates-turnaround", DATES, "The estimated delivery date and turnaround days",
      "estimated delivery date turnaround days business days calendar days due date when transcript due 5 15 "
      "expedited regular quick buttons today tomorrow week month",
      """
<p>The <i>Est. delivery date</i> is worked out from the speed's turnaround days, counted in <b>business days</b>
(weekends and court holidays don't count), from the day the form is dated (a date of agreement you type doesn't change
it). Expedited's 5 days from Tuesday 10/13/2026 is
Tuesday 10/20/2026. A line under the date says how: <i>5 business days from Tue 10/13/2026</i>. A holiday on the
way is named: Regular's 15 days end on Wednesday 11/4/2026, <i>(Election Day on Tue 11/3 not counted)</i>.</p>
<ul>
<li>The days come from the rate sheet's <i>Days</i> column, or else Settings → Defaults → <i>Turnaround days</i>
(at first Expedited 5, Regular 15: one and three working weeks). The line under the date ends <i>(the rate sheet's
Days column)</i> when the sheet gave them.</li>
<li>A rate sheet filled in before version 2.8.0 may still say 7 and 21 days, which were calendar days then (a week and
three weeks). Counted as business days they come out about 9 and 30 calendar days, so the app asks once whether to
change them to 5 and 15, which keeps the dates you had. <i>Keep 7 and 21</i> is remembered for that sheet, and
<i>Not now</i> asks again the next time you start the app; you can still change the numbers in the sheet yourself
(<a href="topic:rates-columns">the sheet's columns</a>).</li>
<li>Settings → Dates → <i>Count turnaround days as business days</i>: untick for calendar days (a last day on a
weekend or a holiday still moves to the next business day).</li>
<li>Settings → Dates → <i>Count the turnaround from</i>: <i>the date on the form</i>, or <i>the day you make
it</i>.</li>
<li>With firms at two speeds, the form gives the later date.</li>
</ul>
<p>The buttons under the date fill in the form's date, or a day, 1–3 weeks or a month from it (from today, when the
turnaround counts from the day you make it); a weekend or a court holiday becomes the next business day (rest the mouse on one to see the date it gives). The 📅 picks a day from a
month, with the court holidays in red.</p>
"""),
    T("dates-holidays", DATES, "Court holidays: the list and how to change it",
      "holidays court closed day off new york list add remove change rules thanksgiving christmas election day "
      "lincoln juneteenth columbus veterans restore weekend friday before monday after",
      """
<p>The list starts with New York's court holidays: New Year's Day, Martin Luther King Jr. Day, Lincoln's Birthday,
Washington's Birthday, Memorial Day, Juneteenth, Independence Day, Labor Day, Columbus Day, Election Day, Veterans
Day, Thanksgiving Day and Christmas Day. Change it in Settings → <b>Dates</b>:</p>
<ul>
<li>each holiday is a rule in plain words, so the list holds every year: "January 1", "3rd Monday of January",
"last Monday of May", "Tuesday after the 1st Monday of November";</li>
<li>a date with a year, such as "12/24/2026", is a one-off closing;</li>
<li>the <i>Next</i> column shows when each falls next; "⚠ not understood" means a rule it can't read (rest the mouse
on it for examples);</li>
<li><b>Add</b> and <b>Remove</b> change the list; <b>Restore the court's holidays</b> brings back the first one.</li>
</ul>
<p><b>A holiday on a weekend</b> is closed the Friday before (Saturday) or the Monday after (Sunday), as New York's
courts do; or choose <i>not moved (no day off)</i>. The line under the list names the holidays coming up.</p>
<p>The day after Thanksgiving, Christmas Eve and New Year's Eve are not court holidays in New York: add them if your
office closes.</p>
"""),
    T("dates-typed", DATES, "A date you type or pick", "type date pick calendar weekend holiday warning never moved "
      "red calendar",
      """
<p>A date you type or pick is <b>never moved</b>. When it falls on a weekend or a court holiday, a line under it
points it out: <i>⚠ 11/11/2026 is Veterans Day, a court holiday.</i></p>
<p>The 📅 beside the date picks a day from a month, with the court holidays in red; rest the mouse on one for its
name.</p>
"""),
    T("dates-evening", DATES, "Forms made in the evening", "evening after hours 5 pm late night after 5:00 tomorrow next "
      "day cut-off time",
      """
<p>Settings → Dates → <i>Made after 5:00 PM: dated the next day</i> (off at first) dates what you make after that
hour the next day, then the next business day: made Friday at 6 PM, dated Monday. Change the hour beside it.</p>
<p>Made on the evening of 12/31/2026, an invoice is dated Monday 1/4/2027 and numbered 2027-0001.</p>
"""),
    # -------------------------------------------------------------------------------------------------- Rate sheets
    T("rates-sheets", RATES, "Rate sheets: your prices",
      "rate sheet prices price list rates csv excel city private template sample rates add new sheet folder edit "
      "what goes in",
      """
<p>Prices come from rate sheets: small CSV files you can edit in Excel. Open their folder with <b>File → Open rate
sheets folder</b> (it is <code>%APPDATA%\\YinItAgreementForm\\Rate Sheets</code>, or a folder you choose in
Settings → Defaults). Pick one from the <i>Rate sheet</i> dropdown under <i>Pages and dates</i>.</p>
<p>To add one, for example city rates:</p>
<ol>
<li>copy <i>Rate Sheet TEMPLATE.csv</i>;</li>
<li>rename it, e.g. <i>City Rates.csv</i>;</li>
<li>fill in the prices;</li>
<li>click ⟳ next to the <i>Rate sheet</i> dropdown.</li>
</ol>
<p>Files with "template" in the name are ignored. The bundled <i>Sample Rates</i> sheet is brought up to date when a
new version changes it (its prices, or a heading), unless you edited it.</p>
"""),
    T("rates-columns", RATES, "What a rate sheet holds", "rate sheet columns rows original copy email index days "
      "headings speed realtime other",
      """
<pre>Rate,Original,Copy,Email,Index,Days
Immediate,$7.60,$1.45,$1.45,$1.45,0
Daily,$6.50,$1.25,$1.25,$1.25,1
Expedite,$5.40,$1.10,$1.10,$1.10,5
Regular,$4.30,$1.00,$1.00,$1.00,15</pre>
<ul>
<li>Each row is a speed. List only the speeds you offer, and add a row for one the form has no box for (it is
marked under "Other").</li>
<li><b>Original</b> is the rate per page written on the form; the invoice uses it with <b>Copy</b>, <b>Email</b> (the
e-mailed copy) and <b>Index</b>.</li>
<li><b>Days</b> (optional) is the turnaround, in <a href="topic:dates-turnaround">business days</a>.</li>
<li>Headings don't have to be exact: <i>E-mail</i>, <i>Index Price</i> and a slip like <i>Idnex</i> are read too, as
long as only one heading could be it. The dropdown's tooltip says when a heading was read this way.</li>
</ul>
"""),
    T("rates-missing", RATES, "A price missing from a rate sheet", "missing price warning incomplete rate sheet use it "
      "anyway open the sheet to fill it in fix it lower cheaper faster speed costs less wrong prices order",
      """
<p>Every speed on a sheet needs all four prices ($0.00 counts). When one is missing, the app warns you and lists
what ("Regular: no Email or Index price"):</p>
<ul>
<li><i>Use it anyway</i> keeps the sheet and doesn't ask again until the file changes;</li>
<li><i>Go back to …</i> (when you had another sheet before) picks that one;</li>
<li><i>Open the sheet to fill it in</i> opens it; each time you save it, the app reads it again and says at the
bottom of the window what is still missing;</li>
<li><i>Not now</i> (shown instead of Go back, at start or after ⟳) keeps using it and asks again next time.</li>
</ul>
<p>It warns the same way when a price is lower at a faster speed, which can't be right ("Daily's Index, $1.00, is
less than Expedite's, $1.10"). Only Regular, Expedite, Daily and Immediate (also by their usual other names, such as
Rush or Next day) are compared, each with the next slower one on the sheet that charges it; a speed of another name,
such as Realtime, isn't, and neither is $0.00 (a charge not made at that speed). The prices are yours to get right: <i>Use it anyway</i> keeps the sheet as it is.</p>
"""),
    # --------------------------------------------------------------------------------------------------- Run sheet
    T("run-overview", RUNSHEET, "The run sheet of a shared trial",
      "run sheet takes shared trial reporters initials excel spreadsheet who wrote which pages by reporter witness "
      "folder saved case folder witnesses tab sheets who ordered paid trial runs",
      """
<p>When several reporters share a trial, each puts their initials at the foot of the pages they write. The run sheet
keeps track of who wrote what: an Excel sheet with a row per take, with the date, weekday, reporter, the day's and
running take, the pages written, the first and last page, and the headers printed at the top of its first and last
page (<i>Witness Start</i>, <i>Witness End</i>: the first and the last header printed in the take; Settings →
Run sheet can leave them blank).</p>
<ul>
<li>The <b>Run sheet</b> box in the Outputs box ticks itself when two or more reporters wrote a case's transcripts,
and unticks when one did. Once you click it, it stays as you set it until New job.</li>
<li>Title pages alone show as half a take (Note: <i>title page only</i>).</li>
<li>The weekday, take counts and page numbers are formulas, so rows you type in are counted too. Filter the Reporter
column for one reporter.</li>
</ul>
<p>Three more sheets help you look back at a trial:</p>
<ul>
<li><b>By Reporter</b>: each reporter's takes and pages, their share of the trial's pages, and the days they
worked.</li>
<li><b>Witnesses</b>: every running head the transcripts printed ("J. Doe - Plaintiff - Cross"), as printed, with
the days, the reporters and the pages it was on: also the heads inside a take, not only the first and last.</li>
<li><b>Who Ordered</b>: from your records, each invoice of the case (the firm, its side, the days, the speed, the
number, the amount, and whether it is paid), and each firm with a minute agreement but no invoice yet. It is
written again after Generate makes the invoices, so today's are on it too.</li>
</ul>
<p>Each case's run sheet is saved in the case's own folder, in its <b>Trial Runs</b> folder (a run sheet
saved in the case's folder itself, or started in <i>Documents\\YinIt Run Sheets</i>, by an earlier version is still
found and added to there). To keep every run
sheet in one folder instead, choose one in Settings → Options → Folders. <i>Open the run sheet's folder</i>, under
the Run sheet options, opens the folder of the case shown.</p>
"""),
    T("run-who-transcribed", RUNSHEET, "Who transcribed what",
      "who transcribed what wrote which pages reporter pages each day trial totals review save copy export headers "
      "correct wrong take misread initials undo only yours mine filter reporter highlight shade shading clear",
      """
<p>The <b>Who transcribed what</b> card, at the bottom of the form, lists every take of every day ticked in the job
list, read from the initials at the foot of the pages: the <i>Day</i>, the <i>Reporter</i>, the <i>Page numbers</i>, the <i>Pages in take</i> and the
<i>Headers</i> at the top of its pages as they are printed, each once (<i>PROCEEDINGS, DIRECT - PLAINTIFF - JANE
ROE</i>). Above it, what each reporter wrote in all (<i>These 3 days: Pat
Reporter 144 pages (you) · DS 76 pages</i>). It is there whenever a day ticked has a transcript, whatever outputs are
ticked. It starts folded, the totals on its line: click its heading to see every take.</p>
<p><b>Your takes</b> are shaded, your name in bold (Settings → Options → <i>Highlight your takes</i>, on at first).
Above the table, <b>Only yours</b> shows only your takes, and a box for each reporter hides that reporter's takes
when unticked, to see some reporters only. While anything is left out, <b>Clear filter</b> shows every take
again.</p>
<p><b>A take wrong?</b> When a page's initials were misread, or are missing, pages can land in the wrong take.
Double-click the take (or right-click it → <i>Correct where this take ends…</i>), type the page it really ends on,
and say yes in the <i>Are you sure?</i> box, which says how your pages change. The pages after it go to the next
take, and the takes, your pages (<i>Your pages</i> in the job list, the invoice) and the run sheet follow; the records of the files you
make from then on keep the correction. A corrected take shows ✎. Right-click → <i>Undo my corrections to this
transcript's takes</i> puts them back as the initials say. Files made already aren't changed: Generate the day again (a run sheet made already keeps its
rows, so correct it in Excel).</p>
<p><b>Save a copy…</b> saves the takes shown (as filtered) as an Excel workbook or a CSV file. For the full
record, kept and added to day
after day, tick <b>Run sheet</b> and Generate: the trial's <a href="topic:run-overview">run sheet</a>.</p>
"""),
    T("run-reporters", RUNSHEET, "Reporters' initials and names", "initials reporter names ds = dana run sheet reporters "
      "title page",
      """
<p>The initials on the pages become names in the Reporter column:</p>
<ul>
<li>your own initials: Settings → My info → <i>Initials</i>;</li>
<li>other reporters': Settings → Run sheet → <i>Reporters</i>, one per line ("ds = Dana");</li>
<li>without that, the reporters named on the title page ("DANA SMITH, Senior Court Reporter") are matched to the
initials; failing that, the initials are written.</li>
</ul>
"""),
    T("run-one-per-trial", RUNSHEET, "One run sheet per trial: adding to it",
      "add to existing run sheet new run sheet ask open in excel close duplicate takes",
      """
<p>Before adding, the app looks for the case's run sheet in the case's folder (and its Trial Runs folder), next
to the transcript and in
<i>Documents\\YinIt Run Sheets</i> (where earlier versions kept them): the same index number, or the same case
name. It then asks whether to add the takes to it or start a new one (the
<i>If one exists</i> choice in the Run sheet column, or Settings → Run sheet → <i>When the case has one</i>).</p>
<p>Takes already there are not added twice. New takes go in date and page order; rows already there keep their
place, and what you typed on them is kept.</p>
<p>If the run sheet is open in Excel, nothing is made until you close it, so trying again never makes a second
invoice.</p>
"""),
    T("run-elsewhere", RUNSHEET, "A run sheet made elsewhere", "google sheets downloaded xlsx existing run sheet other",
      """
<p>A run sheet made elsewhere, such as one downloaded from Google Sheets as .xlsx, can be added to as well. It needs
Date, Reporter and Pages columns. New rows go at its end with its own formulas copied down, and a copy of the file is
kept first ("… (before YinIt).xlsx").</p>
"""),
    # ----------------------------------------------------------------------------------------------------- Batches
    T("batch-folder", BATCH, "A folder or many documents at once",
      "batch folder whole folder many documents bulk several orders jobs sort group same case date",
      """
<p>Drop any number of documents at once, or a folder (<b>File → Open a folder of documents (batch)…</b>). The app
reads them all and sorts them into <b>jobs</b>, one per case and date:</p>
<ul>
<li>documents with the same index number and a shared date belong together: a transcript and the invoice for it make
one job;</li>
<li>a document without an index number is matched by its caption ("Smith v Jones" in an e-mail finds "John Smith v.
Jones Trucking Corp.");</li>
<li>two days of the same case make two jobs (Settings → Options → <i>Batches: put all days of the same case on one
form</i> reads them into one);</li>
<li>a document that names no date joins its case if there is only one job for it; one that names no case gets a job
of its own, left unticked.</li>
</ul>
<p>Batches are read with the built-in rules and Windows' text recognition only: the AI helper is not used.</p>
"""),
    T("batch-job-list", BATCH, "The job list", "job list jobs left table marks check tick ticked unticked greyed "
      "warning pages yours initials footer new job undo clear sort order oldest newest heading column day of the week "
      "weekday",
      """
<p>Each job has a row: its case, date, <i>Day</i> (the day of the week), <i>Total pages</i> (every reporter's pages of the
transcript, without the word index) and <i>Your pages</i> (the pages with your initials at the foot of the page; <b>?</b> until it can tell).
Hover over a job for its full name, index number and documents.</p>
<p><b>The ticks say which jobs count.</b> Every card on the right (Who ordered, Who pays what, Who transcribed
what; the Who ordered which pages window, the ticked days of the shown day's invoice) shows every ticked job, whichever one is
shown, and Generate all makes them (not those made already, but for the invoice of a made day still to bill).
Untick a job
to see what difference it makes: it is greyed and left out, but not removed, so ticking it brings it back. Everything
you add starts ticked, but a document that names no case.</p>
<p>The list is <b>by date, oldest first</b>, whatever order the documents were read in, and the job at the top of the
list is shown first. <b>Click a heading</b> to sort by it (a date as a date, pages as numbers); click it again for the other way.
Your choice is kept. A job's documents stay in the order they were read. Right-click the headings (or View →
<i>Show the day of the week in the job list</i>) to hide or show <i>Day</i>.</p>
<ul>
<li><b>✓</b> marks a job already made.</li>
<li><b>⚠</b> marks one that failed or needs a look: something required is missing, nobody is ticked, Whose pages… or
Who ordered which pages… to choose, Parties counting a party no firm named (on pages ordered at different speeds), index numbers
that don't match, more than two speeds on the same pages, or no pages to bill.
Hover over it to see what.</li>
</ul>
<p>Click a job to check it. A job of several documents lists them under it (<a href="topic:input-several">more</a>).
<b>New job</b> (Ctrl+N) clears the list without asking: <b>Undo</b> at the bottom of the window brings every job back
for 10 seconds, until you add something new (not when documents were still being read).</p>
"""),
    T("batch-generate-all", BATCH, "Generate all", "generate all every job batch make all ctrl+shift+enter",
      """
<p><b>Generate all</b> (Ctrl+Shift+Enter) makes the ticked outputs for every ticked job. Like Generate, it first shows
a preview of every file; nothing is saved until you click Save.</p>
<ul>
<li>The jobs it makes stay ticked, with a ✓, so the cards still show them. Pressed again, it makes only what is
left (<i>Generate the 1 day left</i>). To make one again, click it and use its own Generate button.</li>
<li>The days of one case get one invoice per attorney (<a href="topic:inv-several-days">more</a>).</li>
<li>A job without a transcript gets its forms but no run sheet, and no invoice unless you typed its pages.</li>
<li>The days of one trial go on one run sheet, and you're asked about it once.</li>
<li>A run sheet open in Excel is found before anything is made: close it and press Generate all again.</li>
<li>It lists first the jobs whose index numbers don't match, and asks once about case folders already there.</li>
</ul>
"""),
    T("batch-command-line", BATCH, "Batches from the command line", "command line --batch cmd powershell script "
      "automate batch.json outputs math",
      """
<p>The same can be done without the window:</p>
<pre>YinItAgreementForm.exe --batch &lt;output folder&gt; [--outputs agreement,mofr,invoice,runsheet] [--math] &lt;files or folders…&gt;</pre>
<ul>
<li>it makes the outputs saved as ticked in the window, unless <code>--outputs</code> says otherwise, into the output
folder, with no preview and no folder for each case (run sheets go to their own folder if Settings give them
one, and a case's run sheet found elsewhere is added to where it is);</li>
<li><code>--math</code> also saves the math of the invoices, as Settings → Invoice → <i>Save the math</i> says;</li>
<li>it writes a <code>batch.json</code> report: each job's <code>warnings</code> name a document without an index
number, index numbers that don't match, or a firm billed at the form's speed because its speed wasn't given.</li>
</ul>
<p>With nobody to ask, no invoice is made for a transcript several reporters wrote when whose pages to bill can't be
told; <code>batch.json</code> says why.</p>
"""),
    # ---------------------------------------------------------------------------------------------------- Settings
    T("set-my-info", SETTINGS, "Settings → My info", "my info personal details name title address telephone phone fax "
      "email website initials signature contact",
      """
<p>Your details, on every form and invoice: <b>Name</b>, <b>Title</b>, <b>Address</b>, <b>Telephone</b>,
<b>Fax</b>, <b>Email</b> and <b>Website</b>.</p>
<ul>
<li><b>Initials</b>: how your pages are found on a shared trial (<a href="topic:inv-reporters">more</a>), when they
aren't the first letters of your name.</li>
<li><b>Signature</b>: <i>Choose image...</i> and <i>Sign the court reporter line on every form</i>
(<a href="topic:set-signature">more</a>).</li>
</ul>
"""),
    T("set-signature", SETTINGS, "Your signature on the forms", "signature sign picture image scan photo court reporter "
      "line sign as court reporter",
      """
<p>Choose a photo or scan of your signature on white paper once: Settings → My info → <i>Choose image...</i>. The
paper is removed, so the form's line shows through. <i>Remove</i> takes it off; without one, your name is typed
instead.</p>
<p><i>Sign the court reporter line on every form</i> (Settings → My info), or <i>Sign as court reporter</i> in the
Outputs box's <i>Options ▾</i> (under Minute agreement), puts it on the court reporter line.</p>
"""),
    T("set-defaults", SETTINGS, "Settings → Defaults", "defaults court county copies rate sheet sheets folder turnaround "
      "days immediate daily expedited regular",
      """
<p>What new jobs start with: the <b>Court</b>, <b>County</b>, number of <b>Copies</b> and <b>Rate sheet</b>.</p>
<ul>
<li><b>Sheets folder</b>: where the <a href="topic:rates-sheets">rate sheets</a> are (<i>Open folder</i> opens
it).</li>
<li><b>Turnaround days</b> for <b>Immediate</b>, <b>Daily</b>, <b>Expedited</b> and <b>Regular</b>: used when a rate
sheet has no Days column (<a href="topic:dates-turnaround">more</a>).</li>
</ul>
"""),
    T("set-options", SETTINGS, "Settings → Options", "options preferences flatten open pdf preview title case yin yang "
      "form make by default mofr case instructions page batches folders save to file name theme zoom records search "
      "recaps invoice math new versions update index numbers patterns",
      """
<ul>
<li><i>Write "per email" in the attorney signature spot</i>, <i>Flatten the PDF (fields no longer editable)</i>,
<i>Open the PDF after saving</i>, <i>Show a preview before saving (Generate, Generate all)</i>.</li>
<li><i>Convert ALL-CAPS names to Title Case</i>: "DANA SMITH" becomes "Dana Smith".</li>
<li><i>Show the yin-yang (working / done / stumped pictures)</i>.</li>
<li><b>Form</b>: which <a href="topic:make-agreement">agreement form</a>. <b>Make by default</b>: what new jobs tick
in the Outputs box. <b>MOFR case</b>: Civil or Criminal. <i>Include the instructions page (UCS form page 2)</i>.</li>
<li><i>Batches: put all days of the same case on one form</i> and <i>Minute agreements and MOFRs: one for the whole
case (every day on its invoice)</i> (<a href="topic:inv-several-days">more</a>).</li>
<li><b>A firm you tick orders</b>: <i>The whole trial (days added later too)</i>, or <i>Only the day shown</i>
(<a href="topic:check-attorneys">more</a>).</li>
<li><b>Folders</b>: <i>Save to</i>, <i>A folder for each case, inside Save to</i>, <i>Case folder name</i>, <i>If
it's already there</i>, <i>Copy the documents read into an "Inputs" folder</i>, and a folder for each kind of file
(<a href="topic:make-folders">more</a>).</li>
<li><b>File name</b> and <b>MOFR file name</b> (<a href="topic:make-file-names">more</a>).</li>
<li><b>Theme</b> and <b>Zoom</b> (<a href="topic:start-room">more</a>).</li>
<li><b>Recent jobs</b>: <i>List them while nothing is open</i>, <i>up to</i> 3 (5 at most), <i>made in the last</i>
30 days (at first; 0 is <i>at any time</i>) (<a href="topic:rec-reopen">more</a>).</li>
<li><b>Who transcribed what</b>: <i>Highlight your takes</i> (on at first)
(<a href="topic:run-who-transcribed">more</a>).</li>
<li><b>Records search</b>: <i>Fuzzy search matches numbers loosely too</i> (<a href="topic:rec-search">more</a>).</li>
<li><b>Index numbers</b>: patterns of your own (<a href="topic:check-index">more</a>).</li>
<li><b>Recaps</b>: <i>Show a recap of last month (and last year) when Records is first opened</i>.</li>
<li><b>Invoice math</b>: <i>Show the math of each invoice</i> (<a href="topic:inv-math">more</a>).</li>
<li><b>New versions</b>: <i>Look for a newer version once a day</i>.</li>
</ul>
"""),
    T("set-dates", SETTINGS, "Settings → Dates", "dates tab date of agreement est delivery date business days evening "
      "court holidays settings",
      """
<ul>
<li><b>Date of agreement</b>: <i>Fill in the date of agreement (today, or the next business day as below)</i>.</li>
<li><b>Est. delivery date</b>: <i>Fill in the estimated delivery date from the turnaround days</i>.</li>
<li><b>Business days</b>: <i>Date forms and invoices on a business day</i>
(<a href="topic:dates-business-days">more</a>), <i>Count turnaround days as business days</i> and <i>Count the
turnaround from</i> (<a href="topic:dates-turnaround">more</a>).</li>
<li><b>Evening</b>: <i>Made after</i> 5:00 PM: dated the next day (<a href="topic:dates-evening">more</a>).</li>
<li><b>Court holidays</b>: the list, and <i>A holiday on a weekend is</i> moved or not
(<a href="topic:dates-holidays">more</a>).</li>
</ul>
"""),
    T("set-invoice", SETTINGS, "Settings → Invoice", "invoice settings speeds offered agreement form speed granular detail "
      "save the math emailed copy index split invoices rounding days of one case firms you "
      "answered turnaround invoice text numbers file name records folder",
      """
<ul>
<li><b>Speeds offered</b> and <b>Agreement form speed</b> (<a href="topic:inv-speeds">more</a>).</li>
<li><b>Firms ordering the same pages</b>: <i>Bill the speed each firm's row shows</i>, or <i>Ask me each firm's speed
at Generate</i> (<a href="topic:inv-who-ordered">more</a>).</li>
<li><b>Granular detail shows</b>: <i>Your page count</i>, <i>Your pages for each day</i>, <i>Price per page</i>, <i>The charges
in each amount</i>, <i>The split between parties</i>; and <i>Also save a detailed copy of each invoice</i>
(<a href="topic:inv-granular">more</a>).</li>
<li><b>Save the math</b> (<a href="topic:inv-math">more</a>).</li>
<li><i>Each party also gets an e-mailed copy (Email column of the rate sheet)</i>; <i>Add an index (and one for the
judge) from</i> 50 total pages; <b>Index on several days</b> and <b>Index on shared pages</b>
(<a href="topic:inv-index">more</a>).</li>
<li><b>Split invoices</b>: how firms that ordered the same pages at different speeds share the original
(<a href="topic:exc-speeds">more</a>).</li>
<li><b>Rounding</b> (<a href="topic:inv-rounding">more</a>) and <b>Days of one case</b>
(<a href="topic:inv-several-days">more</a>).</li>
<li><b>Firms you answered</b> (<a href="topic:check-same-firm">more</a>).</li>
<li><b>Regular turnaround</b>, <b>Expedited turnaround</b>, <b>Daily turnaround</b> and <b>Immediate
turnaround</b>: how the invoice words each speed's turnaround ("3 weeks").</li>
<li><b>Invoice text</b> (<a href="topic:inv-text">more</a>), <b>Invoice numbers</b>
(<a href="topic:inv-numbers">more</a>) and the invoices' <b>File name</b>.</li>
<li><b>Records folder</b>: where the CSV copies of your records are kept.</li>
</ul>
"""),
    T("set-records", SETTINGS, "Settings → Records", "records settings tick boxes add a box colour the rows add a colour "
      "count on the records button status words",
      """
<ul>
<li><b>The tick boxes</b>: Paid, and those you tick <i>Use</i>. <i>Add a box</i> for your own, <i>Up</i> and
<i>Down</i> to order them, <i>Restore defaults</i>. Each has a word for ticked and one for not ticked; <i>Whole
transcript</i> ticks it on the other firms' invoices of the same transcript, and on one made for it later.</li>
<li><i>Colour the rows</i>, and the colours: <i>Add a colour</i>, then click a box's cell for when it applies (✓
ticked, ✗ not ticked, – either way).</li>
<li><i>Count on the Records button</i>.</li>
</ul>
<p>What they do: <a href="topic:rec-boxes">Tick boxes, status and colours</a> and
<a href="topic:rec-button">the count on the Records button</a>.</p>
"""),
    T("set-run-sheet", SETTINGS, "Settings → Run sheet", "run sheet settings when the case has one reporters invoices "
      "for invoice details witness start end columns blank",
      """
<ul>
<li><b>When the case has one</b>: ask whether to add to it or start a new one, add without asking, or always start a
new run sheet (<a href="topic:run-one-per-trial">more</a>).</li>
<li><b>Witness Start / End</b>: what those two columns get: the first and the last header printed at the top of the
take's pages, as printed (<i>DIRECT - PLAINTIFF - JANE ROE</i>), or nothing, for you to type in.</li>
<li><b>File name</b>: <code>{month}</code> <code>{year}</code> <code>{case}</code> <code>{index}</code>
<code>{date}</code>.</li>
<li><b>Reporters</b>: initials = name, one per line (<a href="topic:run-reporters">more</a>).</li>
<li><b>Invoices for</b> and <i>Invoice details…</i>: the name, address and payment details of each other reporter
you make invoices for (<a href="topic:inv-reporters">more</a>).</li>
</ul>
<p>Run sheets are saved in each case's own folder (its Trial Runs folder), unless Options → Folders gives them
one.</p>
"""),
    T("set-ai", SETTINGS, "Settings → AI", "ai settings ollama model url timeout test connection use a local ai model",
      """
<ul>
<li><i>Use a local AI model (Ollama) to help read documents</i>.</li>
<li><i>Also ask the AI about e-mails and pasted text (slower, better for informal text)</i>.</li>
<li><b>The AI may tick who ordered</b>: from e-mails and pasted text only (the default), never, or from any input.</li>
<li><b>Model</b>, <b>Ollama URL</b> and <b>Timeout</b>; <b>Test connection</b>; <i>How to install Ollama +
gemma…</i>.</li>
</ul>
<p>See <a href="topic:ai-what">The AI helper</a>.</p>
"""),
    T("set-export", SETTINGS, "Moving to a new computer: Export and Import settings",
      "export import settings new computer colleague share copy backup settings transfer",
      """
<p><b>File → Export settings (for another computer)…</b> saves your details, options and rate sheets as one file. It
first asks whether to <b>include your personal details</b> (your name, contact details, payment text, other
reporters' names and your folders): include them for a computer of your own; leave them out for a colleague, who
keeps their own and gets your options, invoice wording and rate sheets.</p>
<p><b>File → Import settings…</b> reads it there. The settings you had are kept as <i>settings before import.json</i>
in the app's settings folder. Your signature picture and your records are not in the file.</p>
"""),
    # ------------------------------------------------------------------------------------------------- The AI helper
    T("ai-what", AI, "What the AI helper does (and doesn't)", "ai artificial intelligence ollama gemma local model llm "
      "purple badge informal email slow optional",
      """
<p>The app doesn't need AI: the built-in rules handle transcripts, invoices, photos and ordinary e-mails. The
optional AI helper, a model running on this computer through Ollama, helps most with very informal e-mails.</p>
<ul>
<li>Results appear as soon as the rules finish; the AI's suggestions (purple <b>AI</b> badge) are added when they
arrive. On a laptop without a graphics card that takes about 30–60 seconds a document.</li>
<li>Everything it says is checked against the original text, and invented values are dropped.</li>
<li>It may tick who ordered only from e-mails and pasted text: a transcript or a photo lists who appeared, not who
ordered (Settings → AI changes that).</li>
<li>Batches never use it.</li>
</ul>
<p>The line under the paste box says when Ollama is not running ("using rules only"), with a <i>How to set
up</i> link.</p>
"""),
    T("ai-setup", AI, "Setting up the AI helper (Ollama)", "install ollama setup download model gemma4 test connection",
      """
<ol>
<li>Install <b>Ollama for Windows</b> from ollama.com/download.</li>
<li>In the app: <b>Help → Set up the AI helper (Ollama)…</b> → <i>Download</i>. The download is 4.6 to 7.5 GB for
gemma4:e2b. Or run <code>ollama pull gemma4:e2b</code> in PowerShell.</li>
<li><b>Settings → AI → Test connection.</b></li>
</ol>
"""),
    T("ai-models", AI, "Which AI model", "model gemma4 e2b e4b smaller faster larger accurate graphics card gpu",
      """
<p>Settings → AI → <i>Model</i> offers two: <b>gemma4:e2b</b>, smaller and faster (the default), and
<b>gemma4:e4b</b>, larger and more accurate but much slower on a laptop without a graphics card. The box also lists
any other model Ollama has installed, and you can type a name.</p>
"""),
    # ----------------------------------------------------------------------------------------- If something goes wrong
    T("trouble-report", TROUBLE, "Reporting a problem", "problem bug error crash report log feedback support contact "
      "help diagnostics",
      """
<ul>
<li><b>Help → Copy details for a problem report</b> puts the versions, a few settings and the recent log on the
clipboard, ready to paste into an e-mail.</li>
<li><b>Help → Send feedback…</b> starts an e-mail with the version in the subject.</li>
<li><b>Help → Open the log folder</b> opens the folder, to attach the file.</li>
</ul>
<p>The log (<code>%APPDATA%\\YinItAgreementForm\\logs\\app.log</code>, about 3 MB at most) records the program and
Windows versions, which kind of file was read or failed, each form filled, and any crash. <b>It never records what
the documents say</b>: file names, e-mail addresses, index numbers, phone numbers and case names are left out, and
nothing is sent anywhere.</p>
"""),
    T("trouble-photos", TROUBLE, "Photos come out blank", "photo blank empty nothing read ocr language pack scan picture",
      """
<p>If photos and scans come out blank, Windows' text recognition language pack is missing. Install it from a
PowerShell window opened as administrator:</p>
<pre>Add-WindowsCapability -Online -Name "Language.OCR~~~en-US~0.0.1.0"</pre>
"""),
    T("trouble-open-file", TROUBLE, "A file is open in another program", "file open excel locked can't save in use close "
      "run sheet pdf viewer",
      """
<p>A file open in Excel or a PDF viewer can't be saved over. A run sheet open in Excel is found before anything is
made: close it and click Generate again. If a file of a case still can't be saved, nothing more is made for that
case, and the message says which file to close.</p>
"""),
    T("trouble-settings", TROUBLE, "The settings can't be read", "settings file broken corrupt defaults reset",
      """
<p>If the settings file can't be read when the app starts, it says so and runs on its defaults. Nothing is written
over the file until you press Save in Settings.</p>
"""),
    T("trouble-install", TROUBLE, "Installing and updating", "install installer windows protected your pc more info run "
      "anyway update new version download upgrade administrator",
      """
<p>The installer needs no administrator rights: at first it installs just for you (installing for all users needs
them). It isn't code-signed yet, so Windows may
show "Windows protected your PC": click <b>More info → Run anyway</b>. Installing a new version keeps your settings,
rate sheets, records and run sheets.</p>
<p>Once a day the app asks GitHub whether there is a newer version. When there is one, an <b>Update to …</b>
button shows at the top of the window, beside Records, each time you open the app until you've installed it; click
it to open the download page (nothing is installed by itself). <b>Help → Check for a newer version</b> asks now; the
<a href="{website}">website</a> has the latest installer.</p>
"""),
    # -------------------------------------------------------------------------------------------- Keyboard shortcuts
    T("keys", KEYS, "Keyboard shortcuts", "keyboard shortcuts keys hotkeys ctrl f1",
      """
<table cellpadding="3">
<tr><td><b>F1</b></td><td>Help for where you are</td></tr>
<tr><td><b>Ctrl+O</b></td><td>Open documents</td></tr>
<tr><td><b>Ctrl+V</b></td><td>Paste a screenshot or e-mail text</td></tr>
<tr><td><b>Ctrl+N</b></td><td>New job</td></tr>
<tr><td><b>Ctrl+Enter</b></td><td>Generate (this job)</td></tr>
<tr><td><b>Ctrl+Shift+Enter</b></td><td>Generate all</td></tr>
<tr><td><b>Ctrl+R</b></td><td>Records</td></tr>
<tr><td><b>Ctrl++</b> / <b>Ctrl+-</b> / <b>Ctrl+0</b></td><td>Zoom in, out, back to 100% (also Ctrl and the mouse
wheel)</td></tr>
<tr><td><b>Ctrl+Tab</b> / <b>Ctrl+Shift+Tab</b></td><td>In the preview: the next file, the one before (also
<b>Ctrl+PgDn</b> / <b>Ctrl+PgUp</b>)</td></tr>
<tr><td><b>Ctrl+Z</b></td><td>In Records: undo the last change</td></tr>
<tr><td><b>Delete</b></td><td>In Records: delete the records selected (to the trash); in Who ordered which pages…: remove the
run</td></tr>
<tr><td><b>F2</b></td><td>In Records: type a note</td></tr>
<tr><td><b>Ctrl+F</b></td><td>In this help: go to the search box</td></tr>
</table>
"""),
]

_BY_ID = {t.id: t for t in TOPICS}


def topic(topic_id: str) -> Topic | None:
    """The topic with this id, or None."""
    return _BY_ID.get(topic_id)


def links(t: Topic) -> list[str]:
    """The ids of the topics `t` links to, in order (<a href="topic:id">)."""
    return re.findall(r'href="topic:([\w-]+)"', t.html)
