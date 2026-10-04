# Amud (עמוד)

Amud is a small local web app for Israeli businesses whose quote and invoice PDFs break when Hebrew and English share a line. Foreign no-code tools often reverse Hebrew, or reverse the English words and numbers inside a Hebrew sentence. Amud's product is the PDF: a right-to-left document in which Hebrew stays Hebrew, an English word such as WordPress stays in Latin order, and amounts stay in shekels.

It is not a translation service.

## Run

From this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

WeasyPrint needs the usual Cairo/Pango libraries (on Debian/Ubuntu: `libcairo2`, `libpango-1.0-0`, `libpangocairo-1.0-0`, `libgdk-pixbuf-2.0-0`, `shared-mime-info`). The app ships IBM Plex Sans Hebrew (SIL Open Font License, see `amud/static/fonts/OFL.txt`) and uses it for both the screen and the PDF, so glyph coverage does not depend on fonts installed on the machine.

The database is a SQLite file at `data/amud.sqlite`, created on first run. Override it with `AMUD_DATABASE=/path/to/file.sqlite`. Nothing is seeded.

## What you can do

- Save business details once: name, address, company number (ח.פ. or ע.מ.), phone.
- Save customers: name, address, id number.
- Issue a quote (הצעת מחיר) or a tax invoice (חשבונית מס) with line items. A description may mix Hebrew and English. Quantity and unit price are in NIS.
- VAT is 18%, shown separately from the total. Each document type has its own running number.
- An optional allocation number (מספר הקצאה) can be typed in. If it is present, it is printed. Amud does not obtain one.
- Download a PDF, see the saved documents, and download the same document again.

## Tests

`pdftotext` from Poppler is required (`poppler-utils`).

```bash
source .venv/bin/activate
python -m unittest discover -s tests -v
```

The PDF test builds a tax invoice whose line is `התקנת WordPress אתר`, checks the file is a non-empty PDF, and checks Poppler extracts those words in logical order (the Hebrew is not character-reversed, and WordPress sits between the two Hebrew words). Tests use a temporary database and do not touch `data/amud.sqlite`.

## What this does not do

- It does not talk to the Israel Tax Authority, and it does not issue allocation numbers, digital signatures, or approved electronic invoices.
- It does not collect payment, send email, or connect to an accounting system (Priority, Hashavshevet, Morning, Rivhit, or anything else).
- It does not translate text.
- It is not a substitute for an accountant or for invoicing software your accountant has told you to use. Treat the footer on each PDF as part of the product: the file is produced locally, on your machine, and stays there.

Numbers are calculated with decimal agorot (half-up), not binary floats.

Hebrew in the PDF is not pre-reversed. WeasyPrint and Pango apply the Unicode bidi algorithm, and each run of Latin letters or digits is kept left-to-right so a phrase such as `ABC Ltd` inside a Hebrew sentence is not swapped. A known extractor quirk remains: `pdftotext` sometimes drops the space between an English word and the Hebrew word that follows it (`WordPressאתר`) even though that space is visible on the page.
