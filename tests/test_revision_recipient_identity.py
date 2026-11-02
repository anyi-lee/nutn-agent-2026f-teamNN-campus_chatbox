"""Offline model doubles exercise the real function-call adapter and host.

Omitting a display affiliation must not change the selected record, and another
teacher/affiliation must still fail before model-proposed tool dispatch.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from campus_service import CampusService
from gemini_email import GeminiEmailGenerator, GeminiEmailError, confirmed_contact_query
from session_host import SessionHost
import test_langchain_email as lc_fixture
from langchain_email import LangChainEmailGenerator

SELECTED = '許世昌（智慧製造在職學位學程）'
FACTS = {'teacher_name':SELECTED,'teacher_person_name':'許世昌','recipient_kind':'faculty',
         'student_name':'合成學生','request_details':'改作業三'}
EDITED = {'subject':'作業三補交詢問','body':'許老師您好：\n想詢問作業三的補交方式。\n學生 合成學生 敬上'}
TOOL = {'name':'get_teacher_contact','description':'官方公開收件資料',
        'inputSchema':{'type':'object','properties':{'teacher_query':{'type':'string'}},'required':['teacher_query']}}


def proposal(query):
    return {'candidates':[{'content':{'role':'model','parts':[{'functionCall':{
        'id':'offline-call','name':'get_teacher_contact','args':{'teacher_query':query}}}]}}]}


class RevisionRecipientIdentityTests(unittest.TestCase):
    def test_canonical_and_attested_bare_name_always_dispatch_canonical(self):
        for query in (SELECTED,'許世昌',' 許世昌 '):
            self.assertEqual(confirmed_contact_query(FACTS,query),SELECTED)

    def test_other_people_partial_names_and_other_affiliations_are_rejected(self):
        for query in ('許','許老師','許世昌教授','李健興','許世昌（電機工程學系）','許世昌 (智慧製造在職學位學程)'):
            with self.subTest(query=query),self.assertRaises(GeminiEmailError):
                confirmed_contact_query(FACTS,query)

    def test_person_name_must_be_host_attested_and_not_an_office(self):
        for facts in ({k:v for k,v in FACTS.items() if k!='teacher_person_name'},
                      {**FACTS,'teacher_person_name':'其他人'}, {**FACTS,'recipient_kind':'unit'}):
            with self.assertRaises(GeminiEmailError):
                confirmed_contact_query(facts,'許世昌')

    def test_manual_roundtrip_retains_raw_trace_but_uses_only_selected_record(self):
        generator = GeminiEmailGenerator(api_key='offline-test-key')
        calls = []
        def contact(name,args):
            calls.append((name,dict(args)))
            return {'status':'found','teacher':{'teacher_id':'selected-program-record','name':SELECTED,'public_email':'synthetic@example.invalid'}}
        with patch.object(generator,'_post',side_effect=[proposal('許世昌'),
            {'candidates':[{'content':{'parts':[{'text':json.dumps(EDITED,ensure_ascii=False)}]}}]}]) as post:
            draft,trace = generator.generate_with_contact_tool(FACTS,tool_definition=TOOL,call_tool=contact)
        self.assertEqual(draft,EDITED)
        self.assertEqual(calls,[('get_teacher_contact',{'teacher_query':SELECTED})])
        self.assertEqual(trace[0]['model_arguments'],{'teacher_query':'許世昌'})
        self.assertEqual(trace[0]['arguments'],{'teacher_query':SELECTED})
        self.assertTrue(trace[0]['query_normalized'])
        declaration = post.call_args_list[0].args[0]['tools'][0]['functionDeclarations'][0]
        self.assertEqual(declaration['parameters']['properties']['teacher_query']['enum'],[SELECTED])
        self.assertEqual(post.call_args_list[1].args[0]['contents'][2]['parts'][0]['functionResponse']['id'],'offline-call')

    def test_changed_teacher_never_reaches_model_proposed_tool_dispatch(self):
        generator = GeminiEmailGenerator(api_key='offline-test-key')
        for query in ('李健興','許世昌（電機工程學系）'):
            with patch.object(generator,'_post',return_value=proposal(query)),self.assertRaises(GeminiEmailError):
                generator.generate_with_contact_tool(FACTS,tool_definition=TOOL,
                    call_tool=lambda *args:self.fail('changed recipient must not be dispatched'))

    def test_real_host_revision_keeps_program_affiliation_and_source_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = CampusService(campus_enabled=True,email_generator=GeminiEmailGenerator(api_key=''),outbox_path=Path(tmp)/'outbox.sqlite3')
            host = SessionHost(service_factory=lambda:service)
            owner,session = host.bootstrap(None)
            def call(path,fields):
                return host.handle(owner,session['csrf_token'],path,{'session_id':session['session_id'],'generation':session['generation'],**fields})
            status,source = call('/api/email-draft',{'teacher_name':SELECTED,'purpose':'late_submission_request',
                'student_name':'合成學生','request_details':'想詢問作業二的補交方式'})
            self.assertEqual(status,200,source)
            generator = GeminiEmailGenerator(api_key='offline-test-key')
            service.email_generator = generator
            with patch.object(generator,'_post',side_effect=[proposal('許世昌'),
                {'candidates':[{'content':{'parts':[{'text':json.dumps(EDITED,ensure_ascii=False)}]}}]}]),patch.object(
                    service.tool_server,'call_tool',wraps=service.tool_server.call_tool) as read:
                status,revised = call('/api/email-draft-revise',{'source_draft_id':source['draft_id'],'instructions':'改作業三'})
            self.assertEqual(status,200,revised)
            self.assertEqual(revised['teacher']['chunk_id'],source['teacher']['chunk_id'])
            self.assertEqual(revised['teacher']['teacher_name'],SELECTED)
            self.assertEqual(revised['email_draft']['to'],source['email_draft']['to'])
            self.assertEqual(revised['email_draft']['body'],EDITED['body'])
            self.assertNotIn('作業二',revised['email_draft']['body'])
            self.assertEqual(revised['send_status'],'not_sent')
            self.assertTrue(revised['requires_confirmation'])
            self.assertTrue(all(c.args[1]=={'teacher_query':SELECTED} for c in read.call_args_list))
            # These success statuses come from an explicit _post double, not a
            # real provider call; the evidence log labels this OFFLINE_MODEL_DOUBLE.

    @unittest.skipUnless(lc_fixture.LANGCHAIN_AVAILABLE,'Week 5 LangChain dependencies are not installed')
    def test_langchain_uses_the_same_bound_canonical_query(self):
        calls = []
        generator = LangChainEmailGenerator(api_key='offline-test-key',model_factory=lc_fixture.fake_model_factory,
            agent_factory=lambda **kw:lc_fixture.FakeAgent(kw['tools'][0],query='許世昌',draft=EDITED))
        def contact(name,args):
            calls.append((name,dict(args)))
            return {'status':'found','teacher':{'teacher_id':'selected-program-record','name':SELECTED,'public_email':'synthetic@example.invalid'}}
        draft,trace = generator.generate_with_contact_tool(FACTS,tool_definition=TOOL,call_tool=contact)
        self.assertEqual(draft,EDITED)
        self.assertEqual(calls,[('get_teacher_contact',{'teacher_query':SELECTED})])
        self.assertTrue(trace[1]['query_normalized'])
        self.assertEqual(trace[1]['model_arguments'],{'teacher_query':'許世昌'})


if __name__ == '__main__':
    unittest.main()
