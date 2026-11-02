"""Sanitized synthetic cards; requires lxml, never network or raw site forms."""
import sys
import unittest
from pathlib import Path
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from lxml import html
from audit_faculty_sources import OfficialRedirects, official
from verified_faculty_extract import extract_contacts, discover, identity


class VerifiedExtractTests(unittest.TestCase):
    def parse(self, markup, expected=None):
        return extract_contacts(html.fromstring(markup), expected)

    def test_webforms_body_is_not_discarded_with_hidden_tokens(self):
        rows = self.parse('<form><input type="hidden" value="synthetic-not-a-real-token"><article><h3>合成人 教授</h3><p>Email: synthetic@example.invalid</p></article></form>')
        self.assertEqual(rows[0]['teacher_name'], '合成人')

    def test_footer_cannot_supply_a_missing_teacher_address(self):
        self.assertEqual(self.parse('<main><h2>合成人 教授</h2></main><footer>office@example.invalid</footer>'), [])

    def test_two_cards_do_not_mix_identity_and_email(self):
        rows = self.parse('<main><article><h3>合成人 教授</h3><p>one@example.invalid</p></article><article><h3>測試人 副教授</h3><p>two@example.invalid</p></article></main>')
        self.assertEqual({r['teacher_name']:r['public_email'] for r in rows}, {'合成人':'one@example.invalid','測試人':'two@example.invalid'})

    def test_visible_and_mailto_disagreement_is_not_silently_chosen(self):
        self.assertEqual(self.parse('<article><h3>合成人 教授</h3><a href="mailto:wrong@example.invalid">right@example.invalid</a></article>'), [])

    def test_whitespace_email_repair_does_not_guess_an_address(self):
        row = self.parse('<article><h3>合成人 教授</h3><p>person@mail .nutn.edu.tw</p></article>')[0]
        self.assertEqual(row['public_email'], 'person@mail.nutn.edu.tw')
        self.assertTrue(row['email_whitespace_normalized'])

    def test_title_and_navigation_are_not_person_names(self):
        for value in ('副教授兼','系所介紹','行政助理','下一頁','助理'):
            self.assertIsNone(identity(value), value)

    def test_short_suffix_does_not_override_full_name(self):
        self.assertEqual(self.parse('<article><h3>劉仙湧 教授</h3><p>synthetic@example.invalid</p></article>', '仙湧'), [])

    def test_explicit_profile_and_pagination_discovered_but_login_external_ignored(self):
        doc = html.fromstring('<main><a href="teachers.asp?Page=2">下一頁</a><a href="/about/detail.php?apx=2">合成人 教授</a><a href="https://evil.example/detail.php">測試人 教授</a><a href="/login/detail.php">另一人 教授</a></main>')
        directories, profiles = discover(doc, 'https://drama.nutn.edu.tw/ch/teachers.asp')
        self.assertIn('https://drama.nutn.edu.tw/ch/teachers.asp?Page=2', directories)
        self.assertEqual(profiles, [('https://drama.nutn.edu.tw/about/detail.php?apx=2','合成人')])

    def test_official_domain_boundary(self):
        self.assertTrue(official('https://edu.nutn.edu.tw/'))
        for url in ('https://nutn.edu.tw.evil.example/','https://evilnutn.edu.tw/','https://user:secret@edu.nutn.edu.tw/','file:///tmp/a'):
            self.assertFalse(official(url))

    def test_redirect_is_blocked_before_a_nonofficial_request(self):
        with self.assertRaises(ValueError):
            OfficialRedirects().redirect_request(Request('https://edu.nutn.edu.tw/'), None,302,'Found',{},'https://evil.example/')


if __name__ == '__main__':
    unittest.main()
