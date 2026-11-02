"""Published faculty data, provenance and cross-affiliation acceptance checks."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
from campus_catalog import CampusCatalog, resolve_recipient
from campus_service import CampusService
from gemini_email import GeminiEmailGenerator
from build_email_directory import build_directory
from publish_faculty_audit import merge, retain_reviewed_faculty

COUNTS = {'教育學系':20, '特殊教育學系':8, '幼兒教育學系':8, '體育學系':9,
    '諮商與輔導學系':9, '文化與自然資源學系':7, '英語學系':6, '應用數學系':8,
    '數位學習科技學系':11, '智慧製造在職學位學程':11, '綠色能源科技學系':8,
    '音樂學系':9, '視覺藝術與設計學系':10, '戲劇創作與應用學系':7,
    '經營與管理學系':9, '行政管理學系':7}


class FacultyExpansionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = CampusCatalog()
        cls.directory = build_directory()

    def test_all_sixteen_departments_have_reviewed_counts(self):
        for department, count in COUNTS.items():
            with self.subTest(department=department):
                records = [r for r in self.catalog.contacts if r['department'] == department]
                options = [r for r in self.directory['recipients'] if r['department'] == department and r['kind'] == 'faculty']
                self.assertEqual(len(records), count)
                self.assertEqual(len(options), count)
        self.assertEqual(sum(COUNTS.values()), 147)

    def test_every_new_contact_has_both_membership_and_contact_source(self):
        docs = {r['url']: r for r in self.catalog.document['sources']}
        for row in self.catalog.contacts:
            if row['department'] not in COUNTS:
                continue
            for url in (row['source_url'], row['membership_source_url']):
                self.assertIn(url, docs)
                self.assertRegex(docs[url]['sha256'], r'^[0-9a-f]{64}$')
            self.assertNotIn(row['teacher_name'], {'副教授兼','助理','系所介紹','仙湧'})
            self.assertFalse(row['public_email'].endswith('twTel'))

    def test_pagination_and_individual_profiles_are_not_lost(self):
        by_name = {r['teacher_name']: r for r in self.catalog.contacts}
        self.assertIn('Page=2', by_name['張麗玉']['source_url'])
        self.assertIn('facultyview_', by_name['林美吟']['source_url'])
        self.assertIn('faculty=', by_name['嚴子陵']['source_url'])
        self.assertEqual(by_name['龔憶琳']['public_email'], 'kil5@mail.nutn.edu.tw')
        self.assertTrue(by_name['龔憶琳']['email_whitespace_normalized'])

    def test_conflicting_education_links_use_corroborated_sources(self):
        by_name = {r['teacher_name']: r for r in self.catalog.contacts}
        for name in ('呂明蓁','蘇建元','張主揚'):
            self.assertNotIn('mode02.asp', by_name[name]['source_url'])
        self.assertEqual(by_name['蘇建元']['public_email'], 'cysu@mail.nutn.edu.tw')
        self.assertEqual(by_name['張主揚']['public_email'], 'cychang@mail.nutn.edu.tw')

    def test_support_faculty_remain_available_in_both_departments(self):
        rows = self.directory['recipients']
        self.assertTrue(any(r['name'] == '孫光天（數位學習科技學系）' for r in rows))
        self.assertTrue(any(r['name'] == '孫光天（智慧製造在職學位學程）' for r in rows))
        self.assertEqual(len({r['name'] for r in rows}), len(rows))

    def test_program_unresolved_contacts_are_not_guessed(self):
        program = [r['teacher_name'] for r in self.catalog.contacts if r['department'] == '智慧製造在職學位學程']
        for name in ('李建樹','許正良','蕭鳳翔'):
            self.assertNotIn(name, program)

    def test_form_draft_and_citation_for_new_department(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = CampusService(campus_enabled=True, email_generator=GeminiEmailGenerator(api_key=''),
                                    outbox_path=Path(tmp)/'outbox.sqlite3')
            for department in COUNTS:
                expected = next(r for r in self.catalog.contacts if r['department'] == department)
                option = next(r for r in service.teacher_by_name.values()
                              if r.get('department') == department and (r.get('person_name') or r['teacher_name']) == expected['teacher_name'])
                with self.subTest(department=department):
                    status, result = service.create_email_draft({'teacher_name':option['teacher_name'],
                        'purpose':'course_question', 'student_name':'合成學生', 'student_department':'測試系所',
                        'student_grade':'大四', 'request_details':'想詢問課程相關資料是否可以提供'})
                    self.assertEqual(status, 200, result)
                    self.assertEqual(result['email_draft']['to'], expected['public_email'])
                    self.assertEqual(result['send_status'], 'not_sent')
                    self.assertEqual(result['citations'][0]['url'], expected['source_url'])
            self.assertEqual(len(resolve_recipient(service, '孫光天')), 1)
            self.assertEqual(resolve_recipient(service, '數位學習科技學系孫光天')[0]['department'], '數位學習科技學系')
            self.assertEqual(resolve_recipient(service, '智慧製造在職學位學程孫光天')[0]['department'], '智慧製造在職學位學程')

    def test_publication_rejects_untrusted_or_conflicting_data_without_mutation(self):
        row = next(r for r in self.catalog.contacts if r['department'] == '教育學系')
        source = next(d for d in self.catalog.document['sources'] if d['url'] == row['source_url'])
        report = {'schema_version':'faculty-audit-v1', 'departments':[{
            'department':row['department'], 'url':row['membership_source_url'], 'contacts':[copy.deepcopy(row)],
            'documents':[source], 'conflicts':[], 'limit_reached':False}]}
        before = copy.deepcopy(self.catalog.document)
        self.assertEqual(len(merge(before, report)['contacts']), len(before['contacts']))
        report['departments'][0]['contacts'][0]['source_url'] = 'https://example.invalid/faculty'
        with self.assertRaises(ValueError):
            merge(before, report)
        self.assertEqual(before, self.catalog.document)

    def test_shallow_refresh_preserves_deep_profiles_with_original_provenance(self):
        original = self.catalog.document
        shallow = {**original, 'contacts':[], 'sources':[]}
        kept = retain_reviewed_faculty(original, shallow)
        self.assertEqual(len(kept['contacts']), 147)
        row = kept['contacts'][0]
        previous = next(r for r in original['contacts'] if r['chunk_id'] == row['chunk_id'])
        self.assertEqual(row, previous)
        self.assertIn(row['source_url'], {s['url'] for s in kept['sources']})
        shallow['contacts'] = [{**row, 'public_email':'conflict@example.invalid'}]
        with self.assertRaises(ValueError):
            retain_reviewed_faculty(original, shallow)


if __name__ == '__main__':
    unittest.main()
