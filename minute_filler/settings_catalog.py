"""Where every setting lives and the one decision it makes: the Settings window's pages (PAGES) and an entry for
each field of Settings and of its Profile (ENTRIES). SETTINGS.md, at the top of the project, says how a setting
is placed and what to check before one is added; tests/test_settings_catalog.py holds the code to it (every field
has an entry, every entry shown in the window has a control there, a setting and those it needs share a page, the
window writes no setting it doesn't declare, every "Settings → …" path written anywhere is a page of today's).

An entry's home is one of:
- "settings": shown in the Settings window, on `page` under the heading `section`, named `label` (the text of its
  row or its tick box). The window may show it too (`also_in`: a shortcut that writes the same value), and a job
  may set its own instead (`job_field`, a Job attribute: the setting is then the default a new job starts from).
- "window": set where it acts, in the main window or another window (`where`), never in Settings: a way of looking
  at a view, or a choice remembered there.
- "internal": the app's own memory (`where` says what), never shown.

No Qt here: the Settings window (gui/settings_dialog.py) and the help read it, and so do the tests.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, fields

SETTINGS, WINDOW, INTERNAL = "settings", "window", "internal"


@dataclass(frozen=True)
class Page:
    """A page of the Settings window, listed on its left with its summary under its title."""
    key: str
    title: str
    summary: str        # the grey line under the title in the page list: what is on it
    belongs: str        # "a setting belongs here if it ...": the rule SETTINGS.md gives for it
    sections: tuple     # its headings, in order
    group: int          # pages of one group are listed together, a line between groups
    help: str           # its help topic (help_topics), opened by Help and F1


@dataclass(frozen=True)
class Entry:
    """One field of Settings (or "profile.<field>" of its Profile): where it lives and what it decides."""
    key: str
    home: str                   # SETTINGS, WINDOW or INTERNAL
    page: str = ""              # a Page.key (home SETTINGS)
    section: str = ""           # one of that page's sections
    label: str = ""             # its row's label or its tick box's text; "" when it shares the row of `row_of`
    decides: str = ""           # the one decision it makes, in a sentence
    needs: tuple = ()           # the keys it depends on: greyed out while one of them is off (same page)
    job_field: str = ""         # a Job attribute a job sets for itself, this setting its default
    also_in: tuple = ()         # other places that set the same value (the main window's shortcuts...)
    row_of: str = ""            # the entry whose row it is shown in (an unlabelled part of that row)
    keywords: str = ""          # more words to find it by (Find a setting)
    rows: tuple = ()            # the labels of its other rows, for a setting shown in several ("Invoices for")
    where: str = ""             # home WINDOW or INTERNAL: where it is set, or what it remembers


PAGES = (
    Page("my_info", "My info", "Name, address, initials, signature",
         "is about you, as forms and invoices give your details", ("Contact", "Initials", "Signature"), 0,
         "set-my-info"),
    Page("reporters", "Other reporters", "Their names; invoices in their name",
         "is about another reporter: their name on run sheets, the invoices for their pages",
         ("Reporters",), 0, "set-other-reporters"),
    Page("reading", "Reading documents", "When a document doesn't say",
         "changes how documents are read, or what fills in when they don't say",
         ("When a document doesn't say", "Names", "Index numbers", "Firms you answered"), 1, "set-reading"),
    Page("ai", "AI helper", "The local AI model (Ollama)",
         "is about the local AI model (Ollama) that helps read documents", ("AI helper", "The model"), 1, "set-ai"),
    Page("trials", "Trials", "A case of several days",
         "decides how the days of one case are ticked, billed or made together",
         ("Who ordered", "Invoices and forms", "Batches"), 1, "set-trials"),
    Page("dates", "Dates", "Turnaround, court holidays",
         "decides a date on a form or an invoice, or how turnaround days are counted",
         ("Filling in", "Turnaround", "Business days", "Court holidays"), 1, "set-dates"),
    Page("rates", "Rates and speeds", "Rate sheet, speeds offered",
         "decides a price, a rate sheet or a speed",
         ("Rate sheets", "Speeds", "Same pages, different speeds"), 1, "set-rates"),
    Page("outputs", "Outputs", "What Generate makes; the forms",
         "decides which outputs are made, or how a minute agreement or a MOFR is filled in",
         ("Make by default", "Minute agreement", "MOFR"), 2, "set-outputs"),
    Page("invoices", "Invoices", "Charges, index, text, the math",
         "decides what an invoice charges or shows, its number, or its math",
         ("Charges", "Index", "What the invoice shows", "Invoice text", "Numbers", "The math"), 2, "set-invoice"),
    Page("runsheets", "Run sheets", "Adding to a case's run sheet",
         "decides how a run sheet is filled in", ("Run sheets",), 2, "set-run-sheet"),
    Page("records", "Records", "Tick boxes, colours, recaps",
         "decides how the Records window tracks, finds or sums up your invoices",
         ("Tick boxes and colours", "Search", "Recaps", "CSV copies"), 2, "set-records"),
    Page("files", "Files and folders", "Where files go; their names",
         "decides where a file is saved, what it is called, or what happens as it is saved",
         ("Folders", "File names", "Saving"), 3, "set-files"),
    Page("program", "Program", "Theme, zoom, new versions",
         "is about the program itself: how it looks, how it starts, its updates",
         ("Look", "Start card", "New versions"), 3, "set-program"),
)
PAGE = {p.key: p for p in PAGES}

_WELCOME = "the Welcome questions, at the first start"
_OPTIONS = "the main window's Outputs box → Options ▾"


def _s(key, page, section, label, decides, **kw) -> Entry:
    """An entry shown in the Settings window."""
    return Entry(key, SETTINGS, page, section, label, decides, **kw)


def _w(key, where, decides) -> Entry:
    """An entry set where it acts, outside Settings."""
    return Entry(key, WINDOW, decides=decides, where=where)


def _i(key, where) -> Entry:
    """The app's own memory, never shown."""
    return Entry(key, INTERNAL, decides=where, where=where)


ENTRIES = (
    # --- My info
    _s("profile.name", "my_info", "Contact", "Name", "Your name, on every form and invoice.", also_in=(_WELCOME,)),
    _s("profile.title", "my_info", "Contact", "Title", "Your title, under your name."),
    _s("profile.address1", "my_info", "Contact", "Address", "Your address, on forms and invoices.",
       also_in=(_WELCOME,)),
    _s("profile.address2", "my_info", "Contact", "", "The second line of your address.", row_of="profile.address1",
       also_in=(_WELCOME,)),
    _s("profile.phone", "my_info", "Contact", "Telephone", "Your telephone number.", also_in=(_WELCOME,),
       keywords="phone"),
    _s("profile.fax", "my_info", "Contact", "Fax", "Your fax number."),
    _s("profile.email", "my_info", "Contact", "Email", "Your e-mail address.", also_in=(_WELCOME,),
       keywords="e-mail"),
    _s("profile.website", "my_info", "Contact", "Website", "Your website, on invoices."),
    _s("profile.initials", "my_info", "Initials", "Initials",
       "Which pages of a transcript are yours: those with these initials at their foot.", also_in=(_WELCOME,),
       keywords="your pages whose pages"),
    _s("signature_image", "my_info", "Signature", "Picture", "The picture of your signature on the forms.",
       keywords="signature sign image scan"),
    _s("sign_reporter", "my_info", "Signature", "Sign the court reporter line on every form",
       "Whether the court reporter line of the forms is signed.", also_in=(_OPTIONS,)),

    # --- Other reporters
    _s("reporters", "reporters", "Reporters", "Names",
       "Each other reporter's name on run sheets, and the details of the invoices made for their pages.",
       also_in=("Whose pages… → Details…",), rows=("Invoices for",), keywords="reporters initials colleague invoice "
       "details"),

    # --- Reading documents
    _s("default_court", "reading", "When a document doesn't say", "Court",
       "The court a new job gets when no document names one."),
    _s("default_county", "reading", "When a document doesn't say", "County",
       "The county a new job gets when no document names one."),
    _s("default_copies", "reading", "When a document doesn't say", "Copies",
       "The No. of copies when nobody is ticked and no document says.", keywords="number of copies"),
    _s("title_case_names", "reading", "Names", "Convert ALL-CAPS names to Title Case",
       "Whether names read in capitals are written in Title Case."),
    _s("index_patterns", "reading", "Index numbers", "Index numbers",
       "Your own patterns for index numbers, tried as well as the app's.", keywords="pattern regex"),
    _s("firm_answers", "reading", "Firms you answered", "Firms you answered",
       "Your answers on whether two rows are one firm.", also_in=("the question whether two rows are one firm "
                                                                  "(Remember)",), keywords="same firm forget"),

    # --- AI helper
    _s("use_ai", "ai", "AI helper", "Use a local AI model (Ollama) to help read documents",
       "Whether a local AI model helps read documents.", keywords="ollama gemma"),
    _s("ai_for_text", "ai", "AI helper",
       "Also ask the AI about e-mails and pasted text (slower, better for informal text)",
       "Whether the AI also reads e-mails and pasted text.", needs=("use_ai",)),
    _s("ai_ticks", "ai", "AI helper", "The AI may tick who ordered",
       "From which documents the AI may tick who ordered.", needs=("use_ai",)),
    _s("ollama_model", "ai", "The model", "Model", "Which AI model is asked.", keywords="gemma ollama"),
    _s("ollama_host", "ai", "The model", "Ollama URL", "Where Ollama is reached."),
    _s("ai_timeout", "ai", "The model", "Timeout", "How long an answer is waited for."),

    # --- Trials
    _s("trial_orders", "trials", "Who ordered", "A firm you tick orders",
       "Whether a tick in Who ordered orders the whole trial or only the day shown.", keywords="several days"),
    _s("invoice_joint", "trials", "Invoices and forms", "Days of one case",
       "Whether Generate all bills the days of a case on one invoice or one invoice a day.",
       keywords="joint invoice several days each day"),
    _s("forms_per_case", "trials", "Invoices and forms",
       "Minute agreements and MOFRs: one for the whole case (every day on its invoice)",
       "Whether the days on one invoice get one minute agreement per firm and one MOFR.", needs=("invoice_joint",)),
    _s("batch_combine_dates", "trials", "Batches", "Put all days of the same case on one form",
       "Whether documents of one case on different days make one job.", keywords="batch combine dates"),

    # --- Dates
    _s("agreement_today", "dates", "Filling in",
       "Fill in the date of agreement (today, or the next business day as below)",
       "Whether the date of agreement is filled in."),
    _s("fill_delivery_date", "dates", "Filling in", "Fill in the estimated delivery date from the turnaround days",
       "Whether the estimated delivery date is filled in."),
    _s("invoice_turnaround", "dates", "Turnaround", "On the invoice",
       "How the invoice words each speed's turnaround.", keywords="turnaround wording words"),
    _s("days_immediate", "dates", "Turnaround", "Immediate", "Immediate's turnaround days when the rate sheet has "
       "none.", keywords="turnaround days"),
    _s("days_daily", "dates", "Turnaround", "Daily", "Daily's turnaround days when the rate sheet has none.",
       keywords="turnaround days"),
    _s("days_expedited", "dates", "Turnaround", "Expedited", "Expedited's turnaround days when the rate sheet has "
       "none.", keywords="turnaround days"),
    _s("days_regular", "dates", "Turnaround", "Regular", "Regular's turnaround days when the rate sheet has none.",
       keywords="turnaround days"),
    _s("turnaround_business_days", "dates", "Turnaround", "Count turnaround days as business days",
       "Whether turnaround days are business days or calendar days.", keywords="calendar days"),
    _s("turnaround_from", "dates", "Turnaround", "Count the turnaround from",
       "From which day turnaround days are counted."),
    _s("business_day_dating", "dates", "Business days", "Date forms and invoices on a business day",
       "Whether a form or invoice made on a weekend or holiday is dated the next business day.",
       keywords="weekend"),
    _s("after_hours", "dates", "Business days", "Evening",
       "Whether a form or invoice made in the evening is dated the next day.", keywords="made after late"),
    _s("after_hours_from", "dates", "Business days", "", "The hour from which the evening counts.",
       row_of="after_hours", needs=("after_hours",)),
    _s("holidays", "dates", "Court holidays", "Court holidays", "The days the court is closed."),
    _s("holiday_weekend", "dates", "Court holidays", "A holiday on a weekend is",
       "Whether a holiday on a weekend moves to a weekday."),

    # --- Rates and speeds
    _s("rate_sheet", "rates", "Rate sheets", "Rate sheet", "Which rate sheet prices the forms and invoices.",
       also_in=("the main window's Pages and dates card", _WELCOME), keywords="prices csv"),
    _s("rate_sheets_dir", "rates", "Rate sheets", "Sheets folder", "Where the rate sheets are kept."),
    _s("invoice_speeds", "rates", "Speeds", "Speeds offered", "Which speeds the invoice offers.",
       also_in=("the main window's Who ordered card",),
       keywords="regular expedited daily immediate"),
    _s("agreement_speed_first", "rates", "Speeds", "Agreement form speed",
       "Which offered speed the minute agreement form names."),
    _s("agreement_speed_fallback", "rates", "Speeds", "If it isn't offered",
       "The form's speed when the one above isn't offered."),
    _s("split_speeds", "rates", "Same pages, different speeds", "Firms ordering the same pages",
       "Whether each firm's speed is billed as Who ordered shows it, or asked at Generate."),
    _s("invoice_split_rule", "rates", "Same pages, different speeds", "Split invoices",
       "How firms that ordered the same pages at different speeds share the one original."),

    # --- Outputs
    _s("outputs", "outputs", "Make by default", "Make by default", "Which outputs a new job makes.",
       also_in=("the main window's Outputs box",)),
    _s("form_choice", "outputs", "Minute agreement", "Form", "Which minute agreement form is filled in.",
       also_in=(_OPTIONS,), keywords="ucs original scan"),
    _s("include_instructions", "outputs", "Minute agreement", "Include the instructions page (UCS form page 2)",
       "Whether the form's instructions page is kept."),
    _s("per_email", "outputs", "Minute agreement", "Write \"per email\" in the attorney signature spot",
       "Whether \"per email\" is written where the attorney signs.", also_in=(_OPTIONS,)),
    _s("mofr_division", "outputs", "MOFR", "MOFR case", "Whether the MOFR is ticked Civil or Criminal.",
       also_in=(_OPTIONS,)),

    # --- Invoices
    _s("invoice_include_email", "invoices", "Charges",
       "Each party also gets an e-mailed copy (Email column of the rate sheet)",
       "Whether each party is billed an e-mailed copy.", job_field="invoice_email"),
    _s("invoice_rounding", "invoices", "Charges", "Rounding", "How a price a page with part of a cent is rounded.",
       keywords="cents"),
    _s("invoice_include_index", "invoices", "Index", "Bill an index from",
       "Whether a new job bills an index (each firm's own, and the judge's as Judge's index says); a job's "
       "Peripherals… can say otherwise.", job_field="invoice_index"),
    _s("invoice_index_threshold", "invoices", "Index", "", "From how many total pages an index is billed.",
       row_of="invoice_include_index"),
    _s("invoice_index_rule", "invoices", "Index", "Index on several days",
       "Which days of a several-day invoice get an index."),
    _s("invoice_index_shared", "invoices", "Index", "Index on shared pages",
       "Whether firms that ordered the same pages each pay their own index of them or split one."),
    _s("invoice_judge_index", "invoices", "Index", "Judge's index",
       "Whether the judge's index is billed to the firms (split page by page) or not billed.",
       keywords="judge index judges"),
    _s("invoice_detail_items", "invoices", "What the invoice shows", "Granular detail shows",
       "What granular detail adds to an invoice.", job_field="invoice_show"),
    _s("invoice_detailed_copy", "invoices", "What the invoice shows", "Also save a detailed copy of each invoice",
       "Whether a copy with granular detail is saved beside each invoice."),
    _s("invoice_texts", "invoices", "Invoice text", "Invoice text",
       "The invoice's own text: payment details, notes, the footer.", keywords="payment footer note wording"),
    _s("invoice_number_format", "invoices", "Numbers", "Invoice numbers", "How invoice numbers are written."),
    _s("show_math", "invoices", "The math", "Show the math of each invoice",
       "Whether Generate shows how each amount was reached.",
       also_in=("the math window's Don't show this anymore",)),
    _s("save_math", "invoices", "The math", "Save the math", "Which PDFs of the math Generate saves.",
       also_in=("under the math (preview, math window): Generate saves the math",)),

    # --- Run sheets
    _s("runsheet_existing", "runsheets", "Run sheets", "When the case has one",
       "Whether a case's run sheet is added to, a new one started, or you are asked.", also_in=(_OPTIONS,)),
    _s("runsheet_witness", "runsheets", "Run sheets", "Witness Start / End",
       "What the run sheet's witness columns get."),

    # --- Records
    _s("tracking_boxes", "records", "Tick boxes and colours", "Tick boxes and colours",
       "The tick boxes of the Records window.",
       keywords="tick boxes paid status"),
    _s("tracking_rules", "records", "Tick boxes and colours", "", "The colours of the Records rows.",
       row_of="tracking_boxes", keywords="colours colors"),
    _s("records_colours", "records", "Tick boxes and colours", "Colour the rows",
       "Whether the Records rows are coloured.", keywords="colors"),
    _s("records_count", "records", "Tick boxes and colours", "Count on the Records button",
       "Which invoices the Records button counts."),
    _s("fuzzy_numbers", "records", "Search", "Fuzzy search matches numbers loosely too",
       "Whether Records' fuzzy search matches numbers loosely."),
    _s("recaps", "records", "Recaps", "Show a recap of last month (and last year) when Records is first opened",
       "Whether Records sums up last month and last year.",
       also_in=("the recap's Don't show me monthly or annual recaps anymore",)),
    _s("records_dir", "records", "CSV copies", "Records folder", "Where the CSV copies of the records are kept."),

    # --- Files and folders
    _s("output_dir", "files", "Folders", "Save to", "The folder every file is saved in.", also_in=(_WELCOME,),
       keywords="output folder"),
    _s("case_folders", "files", "Folders", "A folder for each case, inside Save to",
       "Whether each case's files go in a folder of its own."),
    _s("case_folder_pattern", "files", "Folders", "Case folder name", "What a case's folder is called.",
       needs=("case_folders",)),
    _s("case_folder_existing", "files", "Folders", "If it's already there",
       "What happens when the case's folder is already there.", needs=("case_folders",),
       also_in=("the question when a case's folder is already there (Don't ask again)",)),
    _s("save_inputs", "files", "Folders", "Copy the documents read into an \"Inputs\" folder beside the files",
       "Whether the documents read are copied beside the files made."),
    _s("output_dirs", "files", "Folders", "A folder of its own for each output",
       "A folder of its own for one kind of output."),
    _s("filename_pattern", "files", "File names", "Minute agreements", "What a minute agreement's file is called.",
       keywords="file name filename pattern"),
    _s("mofr_filename_pattern", "files", "File names", "MOFRs", "What a MOFR's file is called.",
       keywords="file name filename pattern"),
    _s("invoice_filename_pattern", "files", "File names", "Invoices", "What an invoice's file is called.",
       keywords="file name filename pattern"),
    _s("runsheet_filename_pattern", "files", "File names", "Run sheets", "What a run sheet's file is called.",
       keywords="file name filename pattern"),
    _s("preview_before_saving", "files", "Saving", "Show a preview before saving (Generate, Generate all)",
       "Whether Generate shows the files before saving them.",
       also_in=("the preview's Don't show previews anymore",)),
    _s("open_after", "files", "Saving", "Open the PDF after saving", "Whether a file made is opened."),
    _s("flatten", "files", "Saving", "Flatten the PDF (fields no longer editable)",
       "Whether the PDFs made are locked.", keywords="lock"),

    # --- Program
    _s("theme", "program", "Look", "Theme", "Light, dark, or as Windows is.", also_in=("View → Theme",),
       keywords="dark mode light colours"),
    _s("zoom", "program", "Look", "Zoom", "How big everything is drawn.",
       also_in=("View → Zoom in / Zoom out, Ctrl + and Ctrl −",), keywords="size bigger smaller"),
    _s("show_yin", "program", "Look", "Show the yin-yang (working / done / stumped pictures)",
       "Whether the yin-yang pictures are shown.", also_in=("View → Show the yin-yang",), keywords="picture"),
    _s("recent_jobs_show", "program", "Start card", "Recent jobs",
       "Whether the start card lists the jobs made lately."),
    _s("recent_jobs_count", "program", "Start card", "", "How many recent jobs it lists.",
       row_of="recent_jobs_show", needs=("recent_jobs_show",)),
    _s("recent_jobs_days", "program", "Start card", "", "How lately a job listed was made.",
       row_of="recent_jobs_show", needs=("recent_jobs_show",)),
    _s("check_updates", "program", "New versions", "Look for a newer version once a day",
       "Whether the app looks for a newer version.", keywords="update"),

    # --- set where they act
    _w("excerpt_hidden_speeds", "the Who ordered which pages window: Show prices for", "Its speeds hidden."),
    _w("excerpt_show_place", "the Who ordered which pages window: Show each run's place in the day",
       "Whether it shows each run's place in the day."),
    _w("excerpt_hidden_cols", "the Who ordered which pages window: Columns ▾", "Its count columns hidden."),
    _w("excerpt_only_mine", "the Who ordered which pages window: Only your pages", "Whether it shows yours alone."),
    _w("takes_only_mine", "the Who transcribed what card: Only yours", "Whether the card shows your takes alone."),
    _w("takes_highlight_mine", "the Who transcribed what card: Highlight yours",
       "Whether the card shades your takes (highlight)."),
    _w("records_columns", "the Records window: Columns…", "Its columns shown."),
    _w("math_layout", "the math: By invoice / Firms side by side", "How the math's tables are laid out."),
    _w("folded_cards", "the main window's cards (View → Fold all cards)", "Which cards are folded."),
    _w("job_sort", "the job list's headings", "How the job list is sorted."),
    _w("job_weekday", "View → Show the day of the week in the job list", "Whether the job list shows the day."),
    _w("recent_files", "File → Open recent", "The documents opened lately."),

    # --- the app's own memory
    _i("settings_version", "which version of the settings file this is"),
    _i("settings_page", "the Settings page shown last"),
    _i("rate_sheets_ok", "the incomplete rate sheets used anyway (Use it anyway)"),
    _i("sheet_days_kept", "the rate sheets whose old turnaround days were kept when asked"),
    _i("window_geometry", "the main window's size and place"),
    _i("window_splits", "where the main window's dividers are"),
    _i("welcomed", "whether the Welcome questions were shown"),
    _i("opened_year", "the year the app was last opened in"),
    _i("new_year_day", "the day the New Year picture shows"),
    _i("update_checked", "the day a newer version was last looked for"),
    _i("update_version", "the newer version found"),
    _i("update_page", "that version's download page"),
    _i("recap_month", "the month a recap was last shown in"),
    _i("recap_year", "the year a yearly recap was last shown in"),
)
ENTRY = {e.key: e for e in ENTRIES}


def entry(key: str) -> Entry:
    """The entry of a setting ("invoice_rounding", "profile.name")."""
    return ENTRY[key]


def page_of(key: str) -> Page:
    """The page a setting shown in Settings is on."""
    return PAGE[ENTRY[key].page]


def shown_label(key: str) -> str:
    """What a setting is called where it is shown: its own label, or that of the row it is part of."""
    e = ENTRY[key]
    return e.label or (ENTRY[e.row_of].label if e.row_of else "")


def path(key: str = "", page: str = "", row: str = "") -> str:
    """How a message names where a setting is: "Settings → Invoices → Rounding" (a page alone with `page`:
    "Settings → Invoices"; one of the setting's other rows with `row`: "Settings → Other reporters → Invoices for").
    Messages use it rather than writing the path, so a setting moved is named where it is now."""
    if key:
        assert not row or row in ENTRY[key].rows, (key, row)
        return f"Settings → {page_of(key).title} → {row or shown_label(key)}"
    return f"Settings → {PAGE[page].title}"


def setting_keys() -> list[str]:
    """Every key an entry is needed for: the Settings fields (Profile's as "profile.<field>")."""
    from .settings import Profile, Settings
    keys = [f.name for f in fields(Settings) if f.name != "profile"]
    return keys + [f"profile.{f.name}" for f in fields(Profile)]


def _words(text: str) -> list[str]:
    """Lower-case words, straight quotes and accents aside ("Judge's" -> "judge's", "e-mail" -> "e", "mail")."""
    return re.findall(r"[a-z0-9']+", text.lower().replace("’", "'"))


def search(text: str, windows: bool = False) -> list[Entry]:
    """The settings shown in Settings that `text` finds (Find a setting): every word of it begins a word of the
    entry's label, page, heading, decision or keywords (or of the label of the row it is part of). Best first:
    those whose own label it finds, then in page order. windows: also those set where they act (home WINDOW, by
    their `where` and decision), after the others: "highlight" finds the Who transcribed what card's box."""
    wanted = _words(text)
    if not wanted:
        return []
    def stem(w: str) -> str:
        """A word without its apostrophe and a last s: "judges", "judge's" and "judge" are alike."""
        w = w.replace("'", "")
        return w[:-1] if len(w) > 3 and w.endswith("s") else w

    wanted = [stem(w) for w in wanted]
    order = {p.key: i for i, p in enumerate(PAGES)}
    found, shown = [], set()
    for n, e in enumerate(ENTRIES):
        if e.home == WINDOW and windows:
            label = [stem(w) for w in _words(e.where)]
            hay = label + [stem(w) for w in _words(f"{e.decides} {e.keywords}")]
            if all(any(h.startswith(w) for h in hay) for w in wanted):
                found.append((True, len(PAGES), n, e))
            continue
        if e.home != SETTINGS:
            continue
        if (e.page, e.section, shown_label(e.key)) in shown:
            continue  # (a part of a row already listed: "Tick boxes and colours" once)
        # (its heading counts as its name too: "signature" finds My info's Signature first)
        label = [stem(w) for w in _words(" ".join((shown_label(e.key), e.section) + e.rows))]
        hay = label + [stem(w) for w in _words(f"{PAGE[e.page].title} {e.decides} {e.keywords}")]
        if all(any(h.startswith(w) for h in hay) for w in wanted):
            in_label = all(any(h.startswith(w) for h in label) for w in wanted)
            found.append((not in_label, order[e.page], n, e))
            shown.add((e.page, e.section, shown_label(e.key)))
    return [e for *_, e in sorted(found, key=lambda t: t[:3])]
