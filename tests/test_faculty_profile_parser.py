"""Offline parser checks: labelled faculty rows must not borrow a footer email."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from faculty_profile_parser import parse_profile_tables, profile_links

URL = 'https://chinese.nutn.edu.tw/index.php?option=module&lang=cht&task=showlist&id=16&index=1'


class FacultyProfileParserTests(unittest.TestCase):
    def setUp(self):
        self.markup = (ROOT / 'tests/fixtures/chinese_faculty_profile.html').read_text(encoding='utf-8')

    def test_name_title_and_email_are_read_from_labelled_rows(self):
        rows = parse_profile_tables(self.markup, '鄭憲仁')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['teacher_name'], '鄭憲仁')
        self.assertEqual(rows[0]['title'], '副教授')
        self.assertEqual(rows[0]['public_email'], 'bronzeware@mail.nutn.edu.tw')

    def test_footer_email_does_not_replace_person_email(self):
        self.assertNotIn('tigerjudy', str(parse_profile_tables(self.markup)))

    def test_professional_fields_are_not_inferred_from_cv(self):
        row = parse_profile_tables(self.markup)[0]
        self.assertEqual(row['research_areas'], ['文字學', '禮學', '古器物學', '先秦史', '國語文教學'])
        self.assertNotIn('系主任', row['title'])

    def test_long_cv_does_not_discard_contact_fields(self):
        markup = self.markup.replace('履歷可以很長', '合成經歷' * 4000)
        self.assertEqual(len(parse_profile_tables(markup)), 1)

    def test_wrong_profile_identity_is_rejected(self):
        self.assertEqual(parse_profile_tables(self.markup, '別位老師'), [])

    def test_multiple_email_addresses_in_one_contact_row_are_rejected(self):
        markup = self.markup.replace('bronzeware@mail.nutn.edu.tw</a>', 'bronzeware@mail.nutn.edu.tw second@example.invalid</a>')
        self.assertEqual(parse_profile_tables(markup), [])

    def test_duplicate_name_labels_are_ambiguous(self):
        markup = self.markup.replace('</table>', '<tr><th>姓名</th><td>合成人</td></tr></table>')
        self.assertEqual(parse_profile_tables(markup), [])

    def test_unlabelled_email_or_missing_email_never_uses_footer(self):
        markup = self.markup.replace('<th>電子信箱</th>', '<th>其他</th>')
        self.assertEqual(parse_profile_tables(markup), [])

    def test_directory_links_are_same_host_named_profile_pages_only(self):
        markup = '''<a href="index.php?task=pageinfo&amp;id=40"><img alt="鄭憲仁"></a>
        <a href="https://example.invalid/index.php?task=pageinfo&id=2"><img alt="合成人"></a>
        <a href="http://chinese.nutn.edu.tw/index.php?task=pageinfo&id=3"><img alt="合成人"></a>
        <a href="index.php?task=news&id=4"><img alt="合成人"></a>'''
        self.assertEqual(profile_links(markup, URL), [('https://chinese.nutn.edu.tw/index.php?task=pageinfo&id=40', '鄭憲仁')])


if __name__ == '__main__':
    unittest.main()
