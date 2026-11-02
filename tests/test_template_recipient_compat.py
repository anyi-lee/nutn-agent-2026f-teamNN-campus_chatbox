"""Old bare-name saved drafts, isolated accounts/SQLite, no model or real send."""
import secrets
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from campus_service import CampusService
from gemini_email import GeminiEmailGenerator
from session_host import SessionHost


class LegacyTemplateRecipientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.outbox = Path(self.temp.name)/'sandbox.sqlite3'
        self.service = CampusService(campus_enabled=True, email_generator=GeminiEmailGenerator(api_key=''), outbox_path=self.outbox)
        self.host = SessionHost(service_factory=lambda:self.service)
        self.owner, self.session = self.host.bootstrap(None)
        self.assertEqual(self.call('/api/auth/register', {'username':'synthetic_legacy','password':'synthetic-only-test-password'})[0],200)
        self.account = self.host._users[self.owner].account_id
        self.body = '許老師您好：\n這是合成的補交作業詢問，請保留完整原文。\n合成學生 敬上'
        # Fixture represents a row saved before qualified display names. This
        # writes only this test's temporary account store, never the user's DB.
        saved = self.host.accounts.mutate(self.account,'create',{'action':'create','confirmed':True,
            'operation_id':secrets.token_hex(16),'title':'合成舊草稿','kind':'draft_template',
            'content':self.body,'template_fields':{'teacher_name':'許世昌','subject':'合成作業補交詢問'}})
        self.ref = {'memory_id':saved['memory_id'],'version':saved['version']}

    def call(self,path,fields):
        status,result = self.host.handle(self.owner,self.session['csrf_token'],path,
            {'session_id':self.session['session_id'],'generation':self.session['generation'],**fields})
        self.owner = result.get('_set_cookie',self.owner)
        self.session = result.get('session',self.session)
        return status,result

    def apply(self, name='許世昌'):
        return self.call('/api/email-template-draft',{'teacher_name':name,'subject':'合成作業補交詢問',
            'body':self.body,'memory_selections':[self.ref],'confirmed':True})

    def count(self):
        with closing(sqlite3.connect(self.outbox)) as connection:
            return connection.execute('SELECT count(*) FROM sandbox_outbox').fetchone()[0]

    def test_legacy_name_resolves_same_official_email_preserving_saved_text(self):
        class MustNotCall:
            configured = True
            model = 'offline-must-not-call'
            def generate(self,*args,**kwargs):
                raise AssertionError('Saved approved text must not be rewritten')
        self.service.email_generator = MustNotCall()
        status,result = self.apply()
        self.assertEqual(status,200,result)
        self.assertEqual(result['teacher']['teacher_name'],'許世昌（電機工程學系）')
        self.assertEqual(result['email_draft']['to'],'scshei@mail.nutn.edu.tw')
        self.assertEqual(result['email_draft']['body'],self.body)
        self.assertEqual(result['generation']['provider'],'saved_draft')
        self.assertEqual(result['generation']['evidence_status'],'LIVE_NOT_RUN')
        self.assertTrue(result['requires_confirmation'])
        self.assertEqual(result['send_status'],'not_sent')
        self.assertEqual(self.count(),0)
        row = self.host.accounts.list_memories(self.account)[0]
        self.assertEqual(row['template_fields']['teacher_name'],'許世昌')
        self.assertEqual(row['content'],self.body)
        self.assertEqual(row['version'],1)

    def test_both_qualified_affiliations_remain_explicitly_selectable(self):
        for name in ('許世昌（電機工程學系）','許世昌（智慧製造在職學位學程）'):
            status,result = self.apply(name)
            self.assertEqual(status,200,result)
            self.assertEqual(result['teacher']['teacher_name'],name)
            self.assertEqual(result['email_draft']['to'],'scshei@mail.nutn.edu.tw')

    def test_different_email_stops_with_candidates_not_false_not_found(self):
        original = next(r for r in self.service.tool_server.teachers if r.get('person_name')=='許世昌')
        self.service.tool_server.teachers.append({**original,'chunk_id':'synthetic-other-person',
            'teacher_name':'許世昌（合成其他系）','department':'合成其他系','public_email':'different@example.invalid'})
        status,result = self.apply()
        self.assertEqual(status,409,result)
        self.assertEqual(result['error']['code'],'AMBIGUOUS_TEACHER')
        self.assertIn('許世昌（合成其他系）',result['error']['candidates'])
        self.assertEqual(self.count(),0)
        self.assertEqual(self.apply('許世昌（電機工程學系）')[0],200)

    def test_unknown_name_does_not_guess_a_recipient(self):
        status,result = self.apply('合成不存在的教師')
        self.assertEqual(status,404)
        self.assertEqual(result['error']['code'],'TEACHER_NOT_FOUND')
        self.assertEqual(self.count(),0)

    def test_send_requires_separate_confirmation_and_remains_idempotent(self):
        status,draft = self.apply()
        self.assertEqual(status,200,draft)
        self.assertEqual(self.call('/api/email-send',{'draft_id':draft['draft_id'],'confirmed':False})[0],409)
        self.assertEqual(self.count(),0)
        _,sent = self.call('/api/email-send',{'draft_id':draft['draft_id'],'confirmed':True})
        _,again = self.call('/api/email-send',{'draft_id':draft['draft_id'],'confirmed':True})
        self.assertEqual(sent['status'],'simulated_sent')
        self.assertEqual(again['status'],'already_processed')
        self.assertEqual(self.count(),1)

    def test_compatibility_does_not_bypass_account_ownership(self):
        other,session = self.host.bootstrap(None)
        status,result = self.host.handle(other,session['csrf_token'],'/api/email-template-draft',{
            'session_id':session['session_id'],'generation':session['generation'],'teacher_name':'許世昌',
            'subject':'合成主旨','body':self.body,'memory_selections':[self.ref],'confirmed':True})
        self.assertEqual(status,401)
        self.assertEqual(self.count(),0)


if __name__ == '__main__':
    unittest.main()
