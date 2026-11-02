"""The public UI grouping asset must match its source snapshots, not guess emails."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_email_directory import build_directory
from campus_service import CampusService
from gemini_email import GeminiEmailGenerator
from session_host import SessionHost


class EmailDirectoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = build_directory()

    def test_public_asset_is_reproducible_from_current_sources(self):
        checked_in = json.loads((ROOT / 'ui/email_directory.json').read_text(encoding='utf-8'))
        self.assertEqual(self.data, checked_in)

    def test_asset_never_exposes_emails_or_credentials(self):
        self.assertNotIn('@', json.dumps(self.data))
        self.assertEqual(set(self.data), {'schema_version', 'source_sha256', 'retrieved_at', 'units', 'recipients'})
        for row in self.data['recipients']:
            self.assertEqual(set(row), {'name', 'title', 'department', 'kind'})

    def test_categories_and_names_are_unique(self):
        self.assertEqual(len(self.data['units']), 73)
        self.assertEqual({row['category'] for row in self.data['units']}, {'academic', 'administrative'})
        names = [row['name'] for row in self.data['recipients']]
        self.assertEqual(len(names), len(set(names)))

    def test_faculty_are_grouped_under_real_academic_units(self):
        academic = {row['name'] for row in self.data['units'] if row['category'] == 'academic'}
        for row in self.data['recipients']:
            if row['kind'] == 'faculty':
                self.assertIn(row['department'], academic)

    def test_known_teachers_do_not_cross_departments(self):
        by_name = {row['name']: row for row in self.data['recipients']}
        self.assertEqual(by_name['林朝興']['department'], '資訊工程學系')
        self.assertEqual(by_name['盧陽明']['department'], '電機工程學系')
        self.assertEqual(by_name['資訊工程學系辦公室']['kind'], 'unit')

    def test_administrative_sections_have_valid_top_level_offices(self):
        admin = {row['name']: row for row in self.data['units'] if row['category'] == 'administrative'}
        for name, row in admin.items():
            parent = admin[row['parent_office']]
            self.assertEqual(parent['parent_office'], parent['name'])
            self.assertTrue(name.startswith(parent['name']))

    def test_sections_map_to_the_named_office(self):
        units = {row['name']: row for row in self.data['units']}
        self.assertEqual(units['教務處學籍成績組']['parent_office'], '教務處')
        self.assertEqual(units['圖資處讀者服務組']['parent_office'], '圖資處')
        self.assertEqual(units['主計室']['parent_office'], '主計室')

    def test_chinese_department_includes_all_ten_verified_profiles(self):
        rows = [row for row in self.data['recipients'] if row['department'] == '國語文學系' and row['kind'] == 'faculty']
        self.assertEqual({row['name'] for row in rows}, {'鄭憲仁','蔡玲婉','林登順','張惠貞','王建國','王琅','陳光明','楊素姿','莊千慧','陳昭吟'})

    def test_chinese_teacher_contact_keeps_its_individual_source(self):
        with tempfile.TemporaryDirectory() as directory:
            service = CampusService(campus_enabled=True, email_generator=GeminiEmailGenerator(api_key=''),
                                    outbox_path=Path(directory) / 'outbox.sqlite3')
            result = service.chat('鄭憲仁老師的 Email')
            self.assertEqual(result['status'], 'ok')
            self.assertIn('bronzeware@mail.nutn.edu.tw', result['answer'])
            self.assertNotIn('tigerjudy', result['answer'])
            self.assertIn('id=40&index=1', result['citations'][0]['url'])

    def test_chinese_teacher_draft_uses_profile_email_not_department_email(self):
        with tempfile.TemporaryDirectory() as directory:
            service = CampusService(campus_enabled=True, email_generator=GeminiEmailGenerator(api_key=''),
                                    outbox_path=Path(directory) / 'outbox.sqlite3')
            status, draft = service.create_email_draft({'teacher_name':'鄭憲仁','purpose':'course_question',
                'student_name':'合成學生','student_department':'資訊工程學系','student_grade':'大四',
                'request_details':'想詢問國語文教學相關課程資訊'})
            self.assertEqual(status, 200)
            self.assertEqual(draft['email_draft']['to'], 'bronzeware@mail.nutn.edu.tw')
            self.assertEqual(draft['send_status'], 'not_sent')

    def test_form_payload_works_for_teacher_and_office_without_auto_send(self):
        with tempfile.TemporaryDirectory() as directory:
            service = CampusService(campus_enabled=True, email_generator=GeminiEmailGenerator(api_key=''),
                                    outbox_path=Path(directory) / 'outbox.sqlite3')
            host = SessionHost(service_factory=lambda: service)
            self.assertEqual(service.config()['email_input_mode'], 'form')
            owner, session = host.bootstrap(None)
            for recipient in ('盧陽明', '圖資處'):
                status, result = host.handle(owner, session['csrf_token'], '/api/email-draft', {
                    'session_id': session['session_id'], 'generation': session['generation'],
                    'teacher_name': recipient, 'purpose': 'course_question', 'student_name': '合成學生',
                    'student_grade': '大四', 'student_department': '資訊工程學系',
                    'request_details': '想詢問課程相關資料是否可以提供', 'background': '', 'memory_selections': []})
                self.assertEqual(status, 200, result)
                self.assertEqual(result['teacher']['teacher_name'], recipient)
                self.assertEqual(result['send_status'], 'not_sent')
                self.assertIn('資訊工程學系', result['email_draft']['body'])


if __name__ == '__main__':
    unittest.main()
