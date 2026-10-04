"""Quotes, VAT, sequences, and mixed Hebrew-English PDF text order."""

import re
import subprocess
import unittest
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from amud import create_app
from amud.money import document_totals, format_nis

BIDI = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
DESCRIPTION = "התקנת WordPress אתר"


def pdf_text(pdf: bytes) -> str:
    proc = subprocess.run(
        ["pdftotext", "-layout", "-", "-"],
        input=pdf,
        capture_output=True,
        check=True,
    )
    return BIDI.sub("", proc.stdout.decode("utf-8"))


def pdf_words(pdf: bytes):
    proc = subprocess.run(
        ["pdftotext", "-bbox-layout", "-", "-"],
        input=pdf,
        capture_output=True,
        check=True,
    )
    raw = proc.stdout.decode("utf-8")
    start = raw.find("<html")
    root = ET.fromstring(raw[start:])
    words = []
    for el in root.iter():
        if not el.tag.endswith("word"):
            continue
        words.append(
            {
                "x": float(el.get("xMin")),
                "y": float(el.get("yMin")),
                "text": el.text or "",
            }
        )
    return words


class MoneyTests(unittest.TestCase):
    def test_vat_rounds_half_up_to_agorot(self):
        totals = document_totals(
            [{"quantity": "1", "unit_price": "10.05"}],
            vat_percent="18",
        )
        self.assertEqual(totals["subtotal"], Decimal("10.05"))
        self.assertEqual(totals["vat"], Decimal("1.81"))
        self.assertEqual(totals["total"], Decimal("11.86"))

    def test_shekel_format(self):
        self.assertEqual(format_nis("1250.5"), "₪1,250.50")
        self.assertEqual(format_nis("236"), "₪236.00")


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.app = create_app(db_path=Path(self.tmp.name) / "amud.sqlite")
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_fresh_database_has_no_customers_or_documents(self):
        page = self.client.get("/documents")
        body = page.data.decode("utf-8")
        self.assertEqual(page.status_code, 200)
        self.assertIn('dir="rtl"', body)
        self.assertIn('lang="he"', body)
        self.assertIn("עדיין אין מסמכים", body)
        customers = self.client.get("/customers")
        self.assertIn("עדיין אין לקוחות", customers.data.decode("utf-8"))

    def _business_and_customer(self):
        settings = self.client.post(
            "/settings",
            data={
                "business_name": "סטודיו עמוד",
                "address": "הרצל 10, תל אביב",
                "company_number": "515555555",
                "company_number_label": "ח.פ.",
                "phone": "03-5551234",
            },
            follow_redirects=True,
        )
        self.assertIn("פרטי העסק נשמרו", settings.data.decode("utf-8"))
        created = self.client.post(
            "/customers",
            data={
                "name": "לקוח ABC Ltd",
                "address": "אלנבי 1, תל אביב",
                "id_number": "123456789",
            },
            follow_redirects=True,
        )
        body = created.data.decode("utf-8")
        self.assertIn("לקוח", body)
        self.assertIn("ABC Ltd", body)

    def _new_doc(self, doc_type, description=DESCRIPTION, allocation="", price="100", qty="2"):
        return self.client.post(
            "/documents/new",
            data={
                "doc_type": doc_type,
                "customer_id": "1",
                "issue_date": "2026-10-04",
                "allocation_number": allocation,
                "notes": "",
                "description": description,
                "quantity": qty,
                "unit_price": price,
            },
            follow_redirects=False,
        )

    def test_sequences_vat_and_mixed_pdf(self):
        blocked = self.client.post(
            "/documents/new",
            data={"doc_type": "quote"},
            follow_redirects=False,
        )
        self.assertEqual(blocked.status_code, 302)
        self.assertIn("/settings", blocked.headers["Location"])

        self._business_and_customer()
        first = self._new_doc("quote")
        self.assertEqual(first.status_code, 302)
        self.assertTrue(first.headers["Location"].endswith("/documents/1"))

        second = self._new_doc("quote", description="ייעוץ", price="50", qty="1")
        self.assertTrue(second.headers["Location"].endswith("/documents/2"))

        invoice = self._new_doc("tax_invoice", allocation="99887766")
        self.assertTrue(invoice.headers["Location"].endswith("/documents/3"))

        detail = self.client.get("/documents/3")
        detail_body = detail.data.decode("utf-8")
        self.assertIn("חשבונית מס", detail_body)
        self.assertIn("0001", detail_body)
        self.assertIn("99887766", detail_body)
        self.assertIn("₪236.00", detail_body)
        self.assertIn("₪36.00", detail_body)
        self.assertIn("התקנת", detail_body)
        self.assertIn("WordPress", detail_body)
        self.assertIn("אתר", detail_body)

        quote = self.client.get("/documents/2")
        self.assertIn("0002", quote.data.decode("utf-8"))
        self.assertIn("הצעת מחיר", quote.data.decode("utf-8"))

        listing = self.client.get("/documents").data.decode("utf-8")
        self.assertIn("ABC Ltd", listing)
        self.assertEqual(listing.count("/pdf"), 3)

        pdf_response = self.client.get("/documents/3/pdf")
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response.mimetype, "application/pdf")
        pdf = pdf_response.data
        self.assertGreater(len(pdf), 1000)
        self.assertTrue(pdf.startswith(b"%PDF"))

        text = pdf_text(pdf)
        self.assertIn("התקנת", text)
        self.assertNotIn("תנקתה", text)
        self.assertIn("WordPress", text)
        self.assertIn("אתר", text)
        install = text.find("התקנת")
        english = text.find("WordPress")
        site = text.find("אתר", install)
        self.assertGreaterEqual(install, 0)
        self.assertLess(install, english)
        self.assertLess(english, site)
        self.assertIn("₪", text)
        self.assertIn("236.00", text)
        self.assertIn("36.00", text)
        self.assertIn("18", text)
        self.assertIn("99887766", text)
        self.assertIn("סטודיו עמוד", text)
        self.assertIn("515555555", text)
        self.assertIn("03-5551234", text)
        self.assertNotIn("4321", text)

        again = self.client.get("/documents/3/pdf").data
        self.assertTrue(again.startswith(b"%PDF"))
        again_text = pdf_text(again)
        self.assertLess(again_text.find("התקנת"), again_text.find("WordPress"))
        self.assertLess(again_text.find("WordPress"), again_text.find("אתר", again_text.find("התקנת")))

        words = pdf_words(pdf)
        wordpress = [w for w in words if w["text"] == "WordPress"]
        self.assertTrue(wordpress, words)
        line_y = wordpress[0]["y"]
        on_line = [w for w in words if abs(w["y"] - line_y) < 2]
        amounts = [w for w in on_line if "200.00" in w["text"]]
        qty = [w for w in on_line if w["text"] == "2"]
        self.assertTrue(amounts, on_line)
        self.assertTrue(qty, on_line)
        # Description is the right-hand column; the line total is the left-hand one.
        self.assertGreater(wordpress[0]["x"], qty[0]["x"])
        self.assertGreater(qty[0]["x"], amounts[0]["x"])
        abc = next(w for w in words if w["text"] == "ABC")
        ltd = next(w for w in words if w["text"] == "Ltd")
        self.assertLess(abc["x"], ltd["x"])
        self.assertLess(text.find("ABC"), text.find("Ltd"))

    def test_rejects_empty_line(self):
        self._business_and_customer()
        response = self.client.post(
            "/documents/new",
            data={
                "doc_type": "quote",
                "customer_id": "1",
                "issue_date": "2026-10-04",
                "description": "",
                "quantity": "1",
                "unit_price": "10",
            },
            follow_redirects=True,
        )
        self.assertIn("חסר תיאור", response.data.decode("utf-8"))
        self.assertIn("עדיין אין מסמכים", self.client.get("/documents").data.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
