import unittest
from document_display import render_document, document_diff

class DisplayTests(unittest.TestCase):
    def test_markdown_table_and_emphasis(self):
        s=render_document('| 项目 | 承诺 |\n| --- | --- |\n| 质保 | **5年** |')
        self.assertIn('<table>',s);self.assertIn('<strong>5年</strong>',s)
        self.assertNotIn('| ---',s)
    def test_html_table_keeps_spans_but_no_active_content(self):
        s=render_document('<table onclick="bad()"><tr><td rowspan="2">服务</td><td>5年</td></tr></table><script>evil()</script><img src="https://example.test/a?token=secret" onerror="bad()">')
        self.assertIn('rowspan="2"',s);self.assertNotIn('onclick',s);self.assertNotIn('evil()',s)
        self.assertNotIn('https://',s);self.assertNotIn('onerror',s);self.assertIn('原文图像',s)
    def test_escaped_markup_simple_formula_and_literal_comparison(self):
        s=render_document('&lt;p&gt;质保 $\\underline{5}$ 年&lt;/p&gt;\n响应 <= 2小时')
        self.assertIn('<u>5</u>',s);self.assertIn('&lt;=',s);self.assertNotIn('&lt;p&gt;',s)
    def test_diff_marks_text_without_breaking_tables(self):
        a,b=document_diff('|项目|承诺|\n|---|---|\n|质保|5年|','<table><tr><th>项目</th><th>承诺</th></tr><tr><td>质保</td><td>3年</td></tr></table>')
        self.assertIn('<table>',a);self.assertIn('<mark>5</mark>',a);self.assertIn('<mark>3</mark>',b)
        self.assertNotIn('&lt;table',b)
    def test_literal_newline_inside_cell_is_not_an_extra_row(self):
        s=render_document('| 区域 | 人数 |\n|---|---|\n| T1\\n出发层 | 14人 |')
        self.assertEqual(s.count('<tr>'),2)
        self.assertIn('<td>T1<br>出发层</td>',s)

if __name__=='__main__':unittest.main()
