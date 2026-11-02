"""School-wide sources and conversation-to-draft acceptance (offline)."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import http.cookiejar
from http.server import ThreadingHTTPServer
from urllib import request, error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from campus_catalog import CATALOG_PATH, CampusCatalog, resolve_recipient
from campus_service import CampusService, FACULTY_DATA_PATH, OFFICE_DATA_PATH
from email_conversation import FIELDS, EmailConversationPlanner, validate_fields
from gemini_email import GeminiEmailError, GeminiEmailGenerator
from session_host import SessionHost


class NoModel:
    configured = False


class FailingPlanner:
    configured = True
    evidence_mode = 'offline'
    def extract(self, history, current):
        raise GeminiEmailError('Injected provider failure')


class CampusConversationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = CampusService(campus_enabled=True,
            email_generator=GeminiEmailGenerator(api_key=''),
            outbox_path=Path(self.temp.name) / 'outbox.sqlite3')
        self.host = SessionHost(service_factory=lambda: self.service,
            source_paths=(FACULTY_DATA_PATH, OFFICE_DATA_PATH, CATALOG_PATH), email_planner=NoModel())
        self.owner, self.session = self.host.bootstrap(None)
        self.counter = 0

    def send(self, message, *, turn_id=None, owner=None, session=None):
        self.counter += 1
        return self.host.handle(owner or self.owner, (session or self.session)['csrf_token'],
            '/api/email-conversation', {'session_id': (session or self.session)['session_id'],
                'generation': (session or self.session)['generation'],
                'message': message, 'turn_id': turn_id or f'turn-{self.counter:08}'})

    def complete(self):
        self.send('幫我寫信給林朝興老師')
        self.send('想詢問多媒體系統課程能否加簽')
        return self.send('我叫合成學生')

    def test_school_directory_includes_cross_department_sources(self):
        result = self.service.chat('國文系電話')
        self.assertEqual(result['status'], 'ok')
        self.assertIn('620', result['answer'])
        self.assertNotIn('林朝興', result['answer'])
        self.assertEqual(result['retrieval']['model'], 'campus_directory')
        self.assertTrue(any('personnel.nutn.edu.tw' in c['url'] for c in result['citations']))

    def test_school_office_and_unknown_hours_stop_with_source(self):
        answer = self.service.chat('圖書館幾點開放？')
        self.assertEqual(answer['status'], 'insufficient_evidence')
        self.assertEqual(answer['error']['code'], 'DETAIL_NOT_IN_SOURCE')
        self.assertIn('未收錄', answer['answer'])
        self.assertFalse(answer['retrieval']['evidence_gate']['passed'])

    def test_office_directory_is_not_evidence_for_appointment_or_policy(self):
        for query in ('國文系主任是誰', '想聯絡校長', '教務處學生證補發流程'):
            answer = self.service.chat(query)
            self.assertEqual(answer['status'], 'insufficient_evidence', query)
            self.assertIsNone(answer['detected_teacher'])

    def test_cross_department_teacher_contact_and_citation(self):
        response = self.service.chat('盧陽明老師的 Email')
        self.assertEqual(response['status'], 'ok')
        self.assertIn('ymlu@mail.nutn.edu.tw', response['answer'])
        self.assertIn('ee.nutn.edu.tw', response['citations'][0]['url'])
        self.assertNotEqual(response['citations'][0]['label'], '南大資工系－師資陣容')

    def test_directory_coverage_is_partial_not_all_faculty_claim(self):
        coverage = self.service.config()['campus_coverage']
        self.assertGreaterEqual(coverage['units'], 30)
        self.assertEqual(coverage['faculty_coverage'], 'partial')

    def test_school_teacher_does_not_use_csie_only_dense_aliases(self):
        response = self.service.chat('盧陽明老師的 Email', retriever='dense_stub')
        self.assertEqual(response['status'], 'ok')
        self.assertEqual(response['retrieval']['model'], 'bm25')
        self.assertNotIn('來自資工系', response['answer'])

    def test_explicit_person_wins_over_department_but_unknown_person_does_not(self):
        matches = resolve_recipient(self.service, '幫我寫信給電機系盧陽明老師')
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['teacher_name'], '盧陽明')
        self.assertEqual(resolve_recipient(self.service, '國文系未知姓名老師'), [])
        self.assertEqual(resolve_recipient(self.service, '英語系林老師'), [])
        result = self.service.chat('國文系未知姓名老師的 Email')
        self.assertEqual(result['status'], 'insufficient_evidence')
        self.assertIsNone(result['detected_teacher'])

    def test_duplicate_bare_names_require_department(self):
        original = self.service.teacher_by_name['林朝興']
        self.service.teacher_by_name['林朝興（合成系）'] = {
            **original, 'teacher_name': '林朝興（合成系）', 'person_name': '林朝興', 'department': '合成系',
            'public_email': 'synthetic@example.invalid'}
        self.assertEqual(len(resolve_recipient(self.service, '林朝興')), 2)

    def test_same_person_same_email_in_two_affiliations_is_not_ambiguous(self):
        original = self.service.teacher_by_name['林朝興']
        self.service.teacher_by_name['林朝興（合成系）'] = {
            **original, 'teacher_name': '林朝興（合成系）', 'person_name': '林朝興', 'department': '合成系'}
        self.assertEqual(len(resolve_recipient(self.service, '林朝興')), 1)
        self.assertEqual(resolve_recipient(self.service, '林朝興（合成系）')[0]['department'], '合成系')

    def test_recipient_department_never_becomes_student_identity(self):
        self.send('我想寫信')
        self.send('國文系')
        self.send('詢問國文系下學期轉系申請需要準備哪些文件')
        _, result = self.send('我叫合成學生')
        self.assertNotIn('我是國文系', result['email_draft']['body'])
        self.assertEqual(self.host._users[self.owner].email_fields['student_department'], '')

    def test_explicit_student_department_is_preserved(self):
        self.send('寫信給國文系，詢問轉系需要哪些文件')
        _, result = self.send('我是資訊工程學系大四學生，我叫合成學生')
        self.assertIn('資訊工程學系', result['email_draft']['body'])
        self.assertEqual(self.host._users[self.owner].email_fields['student_department'], '資訊工程學系')

    def test_model_cannot_relabel_recipient_department_as_sender(self):
        fields = {key: '' for key in FIELDS}
        fields.update(recipient_query='國文系', student_department='國文系')
        with self.assertRaises(GeminiEmailError):
            validate_fields(fields, ['幫我寫信給國文系'])

    def test_collects_missing_fields_in_order_without_creating_or_sending(self):
        _, first = self.send('幫我寫一封信')
        self.assertEqual(first['conversation']['awaiting'], 'recipient_query')
        _, second = self.send('林朝興老師')
        self.assertEqual(second['conversation']['awaiting'], 'request_details')
        _, third = self.send('想詢問多媒體系統課程能否加簽')
        self.assertEqual(third['conversation']['awaiting'], 'student_name')
        self.assertEqual(self.service.pending_drafts, {})
        status, fourth = self.send('合成學生')
        self.assertEqual(status, 200)
        self.assertEqual(fourth['status'], 'draft_created')
        self.assertEqual(fourth['email_draft']['to'], 'mikelin@mail.nutn.edu.tw')
        self.assertIn('合成學生', fourth['email_draft']['body'])
        self.assertNotIn('資訊工程學系', fourth['email_draft']['body'])
        self.assertEqual(fourth['send_status'], 'not_sent')
        self.assertEqual(fourth['analysis']['live_status'], 'LIVE_NOT_RUN')

    def test_unit_recipient_is_verified_and_not_called_teacher(self):
        self.send('幫我寫信給國文系')
        self.send('想詢問國語文相關課程資訊')
        status, result = self.send('我叫合成學生')
        self.assertEqual(status, 200)
        self.assertEqual(result['email_draft']['to'], 'tigerjudy@mail.nutn.edu.tw')
        self.assertIn('國語文學系承辦人您好', result['email_draft']['body'])
        self.assertNotIn('老師您好', result['email_draft']['body'])
        self.assertIn('chinese.nutn.edu.tw', result['citations'][0]['url'])

    def test_partial_surname_is_not_auto_selected(self):
        _, response = self.send('幫我寫信給林老師')
        self.assertEqual(response['conversation']['awaiting'], 'recipient_query')
        self.assertIn('多個', response['answer'])
        self.assertFalse(self.service.pending_drafts)

    def test_unknown_address_does_not_become_recipient(self):
        self.send('幫我寄到 fake@example.com')
        _, response = self.send('fake@example.com')
        self.assertEqual(response['conversation']['awaiting'], 'recipient_query')
        self.assertFalse(self.service.pending_drafts)

    def test_turn_replay_returns_same_draft_and_conflict_is_rejected(self):
        self.send('幫我寫信給林朝興老師')
        self.send('想詢問多媒體系統課程能否加簽')
        _, first = self.send('我叫合成學生', turn_id='stable-turn-0001')
        _, repeat = self.send('我叫合成學生', turn_id='stable-turn-0001')
        self.assertEqual(first['draft_id'], repeat['draft_id'])
        self.assertEqual(len(self.service.pending_drafts), 1)
        status, conflict = self.send('換個名字', turn_id='stable-turn-0001')
        self.assertEqual(status, 409)
        self.assertEqual(conflict['error']['code'], 'EMAIL_TURN_CONFLICT')

    def test_draft_owner_confirmation_and_send_replay(self):
        _, draft = self.complete()
        other, session = self.host.bootstrap(None)
        payload = {'session_id': session['session_id'], 'generation': session['generation'],
                   'draft_id': draft['draft_id'], 'confirmed': True}
        self.assertEqual(self.host.handle(other, session['csrf_token'], '/api/email-send', payload)[0], 404)
        payload.update(session_id=self.session['session_id'], generation=self.session['generation'], confirmed=False)
        self.assertEqual(self.host.handle(self.owner, self.session['csrf_token'], '/api/email-send', payload)[0], 409)
        payload['confirmed'] = True
        _, sent = self.host.handle(self.owner, self.session['csrf_token'], '/api/email-send', payload)
        _, replay = self.host.handle(self.owner, self.session['csrf_token'], '/api/email-send', payload)
        self.assertEqual(sent['status'], 'simulated_sent')
        self.assertEqual(replay['status'], 'already_processed')
        self.assertEqual(sent['receipt']['message_id'], replay['receipt']['message_id'])

    def test_cancel_invalidates_old_draft_and_clears_private_history(self):
        _, draft = self.complete()
        self.send('重新開始')
        self.assertEqual(self.host._users[self.owner].email_history, [])
        self.assertNotIn(draft['draft_id'], self.service.pending_drafts)

    def test_second_browser_and_reset_cannot_read_previous_collection(self):
        self.send('幫我寫信給林朝興老師')
        other, session = self.host.bootstrap(None)
        _, response = self.send('我叫合成學生', owner=other, session=session)
        self.assertEqual(response['conversation']['awaiting'], 'recipient_query')
        _, result = self.host.handle(self.owner, self.session['csrf_token'], '/api/session/reset',
            {'session_id': self.session['session_id'], 'generation': self.session['generation']})
        self.session = result['session']
        _, response = self.send('我叫另一學生')
        self.assertEqual(response['conversation']['awaiting'], 'recipient_query')

    def test_provider_failure_is_explicit_and_fallback_collects_only_user_facts(self):
        self.host.email_planner = FailingPlanner()
        _, response = self.send('幫我寫信給林朝興老師')
        self.assertEqual(response['analysis']['status'], 'model_failed_fallback')
        self.assertEqual(response['analysis']['live_status'], 'LIVE_NOT_RUN')
        self.assertEqual(response['conversation']['awaiting'], 'request_details')

    def test_reset_during_model_work_discards_reply_and_draft(self):
        host, owner, session = self.host, self.owner, self.session
        class ResetPlanner:
            configured = True
            evidence_mode = 'offline'
            def extract(self, history, current):
                host.handle(owner, session['csrf_token'], '/api/session/reset',
                    {'session_id': session['session_id'], 'generation': session['generation']})
                return {key: '' for key in FIELDS}
        self.host.email_planner = ResetPlanner()
        status, response = self.send('幫我寫一封信')
        self.assertEqual(status, 409)
        self.assertEqual(response['error']['code'], 'STALE_SESSION')
        self.assertFalse(self.service.pending_drafts)

    def test_email_turn_cannot_inject_fields_or_send_authorization(self):
        payload = {'session_id': self.session['session_id'], 'generation': 0, 'message': '幫我寫信',
                   'turn_id': 'inject-turn-001', 'to': 'fake@example.com', 'confirmed': True}
        status, _ = self.host.handle(self.owner, self.session['csrf_token'], '/api/email-conversation', payload)
        self.assertEqual(status, 422)

    def test_model_cannot_fabricate_identity_or_fields(self):
        fields = {key: '' for key in FIELDS}
        fields['student_name'] = '未提供的姓名'
        with self.assertRaises(GeminiEmailError):
            validate_fields(fields, ['幫我寫信'])
        with self.assertRaises(GeminiEmailError):
            validate_fields({**fields, 'confirmed': True}, ['幫我寫信'])

    def test_model_transport_omits_credentials_and_uses_bounded_fields(self):
        class Client:
            configured = True
            def _post(self, payload):
                self.payload = payload
                fields = {key: '' for key in FIELDS}
                fields.update(recipient_query='林朝興', request_details='詢問多媒體課程', student_name='合成學生')
                return {'candidates': [{'content': {'parts': [{'text': json.dumps(fields)}]}}]}
        client = Client()
        fields = EmailConversationPlanner(client).extract(['我是合成學生，想找林朝興詢問多媒體課程'], {'owner':'private-owner'})
        self.assertEqual(fields['student_name'], '合成學生')
        self.assertNotIn('private-owner', json.dumps(client.payload))

    def test_http_conversation_draft_confirm_and_browser_isolation(self):
        from app import CampusRequestHandler
        host = self.host
        class Handler(CampusRequestHandler):
            session_host = host
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(lambda: thread.join(3))
        self.addCleanup(server.shutdown)
        url = f'http://127.0.0.1:{server.server_address[1]}'
        browser = request.build_opener(request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        other = request.build_opener(request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        with browser.open(url + '/api/session') as response:
            session = json.load(response)['session']
        with other.open(url + '/api/session') as response:
            other_session = json.load(response)['session']
        def post(client, state, endpoint, fields):
            payload = {'session_id': state['session_id'], 'generation': state['generation'], **fields}
            req = request.Request(url + endpoint, data=json.dumps(payload).encode(),
                headers={'Content-Type': 'application/json', 'X-CSRF-Token': state['csrf_token']})
            with client.open(req) as response:
                return json.load(response)
        for i, (message, awaiting) in enumerate((('我想寫信', 'recipient_query'), ('國文系', 'request_details'),
                ('詢問轉系申請需要準備哪些文件', 'student_name'), ('我叫合成學生', None))):
            result = post(browser, session, '/api/email-conversation',
                          {'message': message, 'turn_id': f'http-turn-{i:08}'})
            self.assertEqual(result['conversation']['awaiting'], awaiting)
        self.assertEqual(result['send_status'], 'not_sent')
        send = {'draft_id': result['draft_id'], 'confirmed': True}
        for client, state, fields, expected in ((other, other_session, send, 404),
                (browser, session, {**send, 'confirmed': False}, 409)):
            with self.assertRaises(error.HTTPError) as failed:
                post(client, state, '/api/email-send', fields)
            self.assertEqual(failed.exception.code, expected)
            failed.exception.close()
        sent = post(browser, session, '/api/email-send', send)
        replay = post(browser, session, '/api/email-send', send)
        self.assertEqual(sent['status'], 'simulated_sent')
        self.assertEqual(replay['status'], 'already_processed')
        self.assertEqual(sent['receipt']['message_id'], replay['receipt']['message_id'])


if __name__ == '__main__':
    unittest.main()
