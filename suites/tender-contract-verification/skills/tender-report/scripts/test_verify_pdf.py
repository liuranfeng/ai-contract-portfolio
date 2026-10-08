import tempfile
import unittest
from pathlib import Path
from pypdf import PdfWriter
from verify_pdf import inspect_pdf

class PdfChecks(unittest.TestCase):
    def test_blank_pages_are_reported_not_visual_pass(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'blank.pdf';w=PdfWriter();w.add_blank_page(width=842,height=595)
            with p.open('wb') as f:w.write(f)
            r=inspect_pdf(p)
            self.assertEqual(r['pageCount'],1)
            self.assertEqual(r['lowTextPages'],[1])
            self.assertEqual(r['visualReview'],'pending')

if __name__=='__main__':unittest.main()
