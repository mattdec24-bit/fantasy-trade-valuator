from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
import os
import unittest
from unittest.mock import patch

import trade_valuator
from evaluator.model import Engine
from evaluator.sources import demo


class CliTests(unittest.TestCase):
    def run_cli(self, flags):
        output = StringIO()
        with patch('sys.argv', ['trade_valuator.py'] + flags), redirect_stdout(output):
            trade_valuator.main()
        return json.loads(output.getvalue())

    def test_local_provider_opt_in_defaults_and_per_run_opt_out(self):
        trade = Engine(demo()).evaluate('harbor', 'orbit', ['harbor-2'], ['orbit-5'])
        shortlist = {'candidates':[trade], 'checked':1}
        manual = ['--other','orbit','--give','harbor-2','--get','orbit-5']
        configured = {'LLM_ENABLED':'true','LLM_PROVIDER':'openai','LLM_API_KEY':'synthetic'}
        for args, expected, method, annotated in [
                (manual, trade, 'summarize', trade | {'llm_summary':'Provider-written commentary.'}),
                ([], shortlist, 'rank', [trade | {'llm_summary':'Provider-written commentary.'}])]:
            for env, flag, requested in [({}, [], False), ({}, ['--no-llm'], False),
                                          (configured, [], True), (configured, ['--llm'], True),
                                          (configured, ['--no-llm'], False),
                                          ({'LLM_ENABLED':'true'}, [], False)]:
                with self.subTest(args=args, env=env, flag=flag), patch.dict(os.environ, env, clear=True), \
                        patch('trade_valuator.Engine.candidates', return_value=shortlist), \
                        patch('trade_valuator.llm.' + method, return_value=(annotated, 'mock summary')) as ai:
                    result = self.run_cli(args + flag)
                    self.assertEqual(ai.call_count, int(requested))
                    if requested:
                        self.assertEqual(result['llm_status'], 'mock summary')
                    else:
                        self.assertEqual(result, expected)

    def test_explicit_cli_request_cannot_bypass_operator_gate(self):
        for env, state in [({}, 'disabled'), ({'LLM_ENABLED':'false'}, 'disabled'),
                           ({'LLM_ENABLED':'true'}, 'unavailable: configure provider and key locally')]:
            with patch.dict(os.environ, env, clear=True), patch('evaluator.llm.urlopen') as network:
                result = self.run_cli(['--llm','--other','orbit','--give','harbor-2','--get','orbit-5'])
                self.assertEqual(result['llm_status'], state)
                self.assertNotIn('llm_summary', result)
                network.assert_not_called()
        with patch('sys.argv', ['trade_valuator.py','--llm','--no-llm']), redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as error:
                trade_valuator.main()
            self.assertEqual(error.exception.code, 2)
