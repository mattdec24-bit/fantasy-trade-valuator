from io import BytesIO
import json
import os
import unittest
from unittest.mock import patch
from evaluator import llm, ocr
from evaluator.sources import demo, normalize_espn, espn_get
from evaluator.model import Engine
from evaluator.network import NoRedirect


class Response(BytesIO):
    def geturl(self):return 'https://api.openai.com/v1/chat/completions'


class PrivacyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidate = Engine(demo()).evaluate('harbor','orbit',['harbor-2'],['orbit-5'])
        cls.env = {'LLM_ENABLED':'true','LLM_PROVIDER':'openai','LLM_API_KEY':'llm-secret',
                   'ESPN_S2':'espn-secret','ESPN_SWID':'swid-secret','APP_ACCESS_TOKEN':'app-secret'}

    def row(self, candidate=None, ref='c0'):
        candidate = candidate or self.candidate
        summary = {'text': 'These computed deltas describe the season and current-week tradeoffs.'}
        for mode in ('season', 'week'):
            yours, theirs = candidate['yours'][mode]['delta'], candidate['theirs'][mode]['delta']
            summary[mode] = ('unchanged' if yours == theirs == 0 else 'both_gain' if min(yours, theirs) > 0
                             else 'your_gain' if yours > 0 else 'their_gain' if theirs > 0 else 'neither_gain')
        return {'id': ref, 'reason': 'weekly_gain', 'summary': summary}

    def response(self, ranking, **choice_fields):
        choice = {'finish_reason': 'stop', 'message': {'role':'assistant', 'content':json.dumps({'ranking':ranking})}}
        choice.update(choice_fields)
        return Response(json.dumps({'choices':[choice]}).encode())

    def test_llm_disabled_never_calls_network(self):
        for env in ({}, {'LLM_ENABLED':'false'}):
            with patch.dict(os.environ, env, clear=True), patch('evaluator.llm.urlopen',side_effect=AssertionError('network')) as call:
                self.assertEqual(llm.rank([{'id':'x'}])[1],'disabled')
                self.assertEqual(llm.summarize({'id':'x'}), ({'id':'x'}, 'disabled'))
                call.assert_not_called()

    def test_llm_unconfigured_and_empty_never_call_network(self):
        for config in ({}, {'LLM_PROVIDER':'other','LLM_API_KEY':'key'}, {'LLM_PROVIDER':'openai'}):
            with patch.dict(os.environ, {'LLM_ENABLED':'true'} | config, clear=True), patch('evaluator.llm.urlopen') as call:
                self.assertEqual(llm.rank([]), ([], 'no candidates'))
                self.assertTrue(llm.summarize(self.candidate)[1].startswith('unavailable:'))
                call.assert_not_called()

    def test_llm_payload_whitelist_for_ranking_and_manual_summary(self):
        # Poison every non-delta field; the adapter must build its own payload.
        candidate = self.candidate | {'name':'PRIVATE-NAME', 'league_id':'PRIVATE-LEAGUE',
                     'ocr':'PRIVATE-OCR', 'screenshot':'PRIVATE-IMAGE', 'roster':['PRIVATE-ROSTER'],
                     'warnings':['PRIVATE-WARNING'], 'explanation':'PRIVATE-PROMPT'}
        pristine = json.loads(json.dumps(candidate))
        for manual in (False, True):
            with patch.dict(os.environ,self.env, clear=True), patch('evaluator.llm.urlopen',return_value=self.response([self.row()])) as call:
                if manual:
                    out, state = llm.summarize(candidate)
                    self.assertEqual(state, 'summarized')
                else:
                    out, state = llm.rank([candidate]); out = out[0]
                    self.assertEqual(state, 'ranked and summarized')
                self.assertEqual({k:v for k,v in out.items() if k not in {'llm_summary','llm_reason'}}, candidate)
                self.assertEqual(out['llm_summary'], self.row()['summary']['text'])
                request = call.call_args.args[0]
                self.assertEqual(request.full_url, 'https://api.openai.com/v1/chat/completions')
                self.assertEqual(request.get_method(), 'POST')
                self.assertEqual(request.get_header('Authorization'), 'Bearer llm-secret')
                payload = json.loads(request.data)
                self.assertFalse(payload['store'])
                facts = json.loads(payload['messages'][1]['content'])
                self.assertEqual(facts, [{'id':'c0', 'your_season_delta':0, 'their_season_delta':0,
                                         'your_week_delta':0, 'their_week_delta':0}])
                serialized = json.dumps(payload)
                for forbidden in ['PRIVATE-', 'espn-secret','llm-secret','swid-secret','app-secret',
                                  'Harbor','Avery','harbor-2', candidate['id'], 'computed_score']:
                    self.assertNotIn(forbidden, serialized)
        self.assertEqual(candidate, pristine)

    def test_llm_valid_permutation_preserves_computed_fields_and_inputs(self):
        engine = Engine(demo())
        first = self.candidate
        second = engine.evaluate('harbor','orbit',['harbor-3'],['orbit-6'])
        candidates = [first, second]
        pristine = json.loads(json.dumps(candidates))
        with patch.dict(os.environ,self.env, clear=True), patch('evaluator.llm.urlopen',return_value=self.response([
                self.row(second, 'c1'), self.row(first, 'c0')])):
            out, state = llm.rank(candidates)
        self.assertEqual(state, 'ranked and summarized')
        self.assertEqual([{k:v for k,v in c.items() if k not in {'llm_reason','llm_summary'}} for c in out], [second, first])
        self.assertEqual(candidates, pristine)

    def test_llm_summaries_handle_negative_positive_zero_and_mixed_deltas(self):
        for ys, ts, yw, tw in [(2,3,-1,4),(2,-3,0,0),(-2,3,-1,-3),(-1,0,3,4),(0,0,1,-2)]:
            candidate = json.loads(json.dumps(self.candidate))
            for side, season, week in [('yours',ys,yw),('theirs',ts,tw)]:
                candidate[side]['season']['delta'], candidate[side]['week']['delta'] = season, week
            with patch.dict(os.environ,self.env, clear=True), patch('evaluator.llm.urlopen',return_value=self.response([self.row(candidate)])):
                out, state = llm.summarize(candidate)
            self.assertEqual(state, 'summarized')
            self.assertEqual(out['warnings'], candidate['warnings'])
            self.assertEqual(out['verdict'], candidate['verdict'])
            self.assertTrue(out['llm_summary'])

    def test_llm_invalid_output_and_failures_retain_deterministic_results(self):
        good = self.row()
        invalid_rankings = [
            [], [good, good], [None], [True], ['text'], {}, None,
            [good | {'id':'invented'}], [good | {'id':self.candidate['id']}], [good | {'id':0}],
            [good | {'reason':'invented metrics'}], [good | {'reason':[]}],
            [good | {'players':['Fake']}], [good | {'summary':'Unverified prose'}],
            [good | {'summary':good['summary'] | {'season':'both_gain'}}],
            [good | {'summary':good['summary'] | {'metrics':42}}],
            [good | {'reason':'mutual_gain'}], [good | {'reason':'your_gain'}],
        ]
        invalid_rankings.extend([[good | {'summary': good['summary'] | {'text': text}}]
                                 for text in (None, True, {}, '', '  ', 'x' * 281, 'Gain 99 points.',
                                              '<script>bad</script>', '[click](https://invalid.test)',
                                              'line\nbreak', 'hidden\u202etext')])
        responses = [self.response(rows).getvalue() for rows in invalid_rankings]
        for content in ('[]','null','{"ranking":[],"prose":"extra"}',
                        '{"ranking":[],"ranking":[]}', '{"ranking":NaN}',
                        json.dumps({'ranking':[good]}).replace('"season": "unchanged"', '"season":"both_gain","season":"unchanged"')):
            responses.append(json.dumps({'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':content}}]}).encode())
        responses.extend([
            self.response([good], finish_reason='length').getvalue(),
            self.response([good], finish_reason='content_filter').getvalue(),
            self.response([good], message={'role':'assistant','refusal':'No','content':json.dumps({'ranking':[good]})}).getvalue(),
            self.response([good], message={'role':'assistant','tool_calls':[{}],'content':json.dumps({'ranking':[good]})}).getvalue(),
            b'{"choices":[]}', b'not json', b'x'*100001,
        ])
        for raw in responses:
            with self.subTest(raw=raw[:150]), patch.dict(os.environ,self.env, clear=True), patch('evaluator.llm.urlopen',return_value=Response(raw)):
                self.assertEqual(llm.rank([self.candidate]), ([self.candidate], llm.FALLBACK))
            with patch.dict(os.environ,self.env, clear=True), patch('evaluator.llm.urlopen',return_value=Response(raw)):
                self.assertEqual(llm.summarize(self.candidate), (self.candidate, llm.FALLBACK))
        # Exact set checks must reject duplicates even when the total count matches.
        with patch.dict(os.environ,self.env, clear=True), patch('evaluator.llm.urlopen',return_value=self.response([good,good])):
            self.assertEqual(llm.rank([self.candidate,self.candidate])[1], llm.FALLBACK)
        for error in (TimeoutError, OSError, ValueError):
            with patch.dict(os.environ,self.env, clear=True), patch('evaluator.llm.urlopen',side_effect=error):
                self.assertEqual(llm.rank([self.candidate]), ([self.candidate], llm.FALLBACK))
                self.assertEqual(llm.summarize(self.candidate), (self.candidate, llm.FALLBACK))

    def test_llm_nonfinite_or_untyped_deltas_fail_before_network(self):
        for invalid in (float('nan'), float('inf'), True, 'PRIVATE-TEXT', None):
            candidate = json.loads(json.dumps(self.candidate))
            candidate['yours']['week']['delta'] = invalid
            with patch.dict(os.environ,self.env, clear=True), patch('evaluator.llm.urlopen') as call:
                out, state = llm.summarize(candidate)
                self.assertIs(out, candidate)
                self.assertEqual(state, llm.FALLBACK)
                call.assert_not_called()

    def test_local_ocr_suggests_only_rostered_players_and_needs_confirmation(self):
        result=ocr.suggestions('Bennett Vale\nEllis Ridge\nDefinitely Invented Player',demo())
        self.assertEqual(result[0]['matches'][0]['player_id'],'harbor-2')
        valid={p.id for t in demo().teams for p in t.players}
        self.assertTrue(all(m['player_id'] in valid for row in result for m in row['matches']))
        with self.assertRaises(ValueError):ocr.extract(b'not an image')
        with self.assertRaises(ValueError):ocr.extract(b'x'*(ocr.MAX_UPLOAD+1))

    def test_ocr_process_stdin_stdout_no_file_or_network(self):
        from PIL import Image
        buf=BytesIO();Image.new('RGB',(100,40),'white').save(buf,format='PNG')
        with patch('evaluator.ocr.shutil.which',return_value='/local/tesseract'),patch('evaluator.ocr.subprocess.run') as run:
            run.return_value.stdout=b'Bennett Vale'
            self.assertEqual(ocr.extract(buf.getvalue()),'Bennett Vale')
            self.assertEqual(run.call_args.args[0],['/local/tesseract','stdin','stdout','-l','eng','--psm','6'])
            self.assertTrue(run.call_args.kwargs['input'].startswith(b'\x89PNG'))
            self.assertEqual(run.call_args.kwargs['timeout'],15)

    def test_ocr_reencoding_strips_all_png_and_jpeg_metadata(self):
        from PIL import Image, PngImagePlugin
        for image_format in ('PNG', 'JPEG'):
            with self.subTest(image_format=image_format):
                image = Image.new('RGB', (100, 40), (240, 230, 220))
                exif = Image.Exif();exif[0x010E] = 'private EXIF description'
                metadata = {'icc_profile':b'private ICC profile', 'exif':exif, 'dpi':(300, 300)}
                if image_format == 'PNG':
                    pnginfo = PngImagePlugin.PngInfo()
                    pnginfo.add_text('Comment', 'private PNG text')
                    pnginfo.add_itxt('Description', 'private PNG international text')
                    pnginfo.add_text('Compressed', 'private compressed PNG text', zip=True)
                    metadata['pnginfo'] = pnginfo
                else:
                    metadata['comment'] = b'private JPEG comment'
                buf = BytesIO();image.save(buf, format=image_format, **metadata)
                with Image.open(BytesIO(buf.getvalue())) as source:
                    source.load()
                    self.assertIn('icc_profile', source.info)
                    self.assertTrue(source.getexif())
                    expected_pixels = source.convert('RGB').tobytes()
                with patch('evaluator.ocr.shutil.which', return_value='/local/tesseract'), patch('evaluator.ocr.subprocess.run') as run:
                    run.return_value.stdout = b'Synthetic OCR'
                    self.assertEqual(ocr.extract(buf.getvalue()), 'Synthetic OCR')
                sanitized = run.call_args.kwargs['input']
                with Image.open(BytesIO(sanitized)) as clean:
                    clean.load()
                    self.assertEqual(clean.format, 'PNG')
                    self.assertEqual(clean.mode, 'RGB')
                    self.assertEqual(clean.size, (100, 40))
                    self.assertEqual(clean.tobytes(), expected_pixels)
                    self.assertEqual(clean.info, {})
                    self.assertFalse(clean.getexif())
                # Inspect the actual subprocess input, including ancillary PNG chunks.
                chunks, offset = [], 8
                while offset < len(sanitized):
                    size = int.from_bytes(sanitized[offset:offset + 4], 'big')
                    chunks.append(sanitized[offset + 4:offset + 8])
                    offset += size + 12
                self.assertEqual(offset, len(sanitized))
                self.assertEqual(chunks[0], b'IHDR');self.assertEqual(chunks[-1], b'IEND')
                self.assertEqual(set(chunks), {b'IHDR', b'IDAT', b'IEND'})

    def test_espn_get_only_fixed_host_and_get(self):
        with patch('evaluator.sources.urlopen',return_value=Response(b'{}')) as call:
            # geturl mismatch is rejected rather than following arbitrary destinations.
            with self.assertRaises(ValueError):espn_get('2026','123',['mRoster'],'secret')
            req=call.call_args.args[0]
            self.assertEqual(req.get_method(),'GET')
            self.assertTrue(req.full_url.startswith('https://lm-api-reads.fantasy.espn.com/'))
            self.assertEqual(req.data,None)
        self.assertIsNone(NoRedirect().redirect_request(None,None,302,'',{},'https://other.invalid'))

    def test_espn_synthetic_response_normalization_missing_stays_null(self):
        def player(pid):return {'playerPoolEntry':{'player':{'id':pid,'fullName':f'Synthetic {pid}','defaultPositionId':2,'eligibleSlots':[2,23],
                  'stats':[{'seasonId':2026,'statSourceId':1,'statSplitTypeId':0,'appliedTotal':170},
                           {'seasonId':2026,'statSourceId':0,'statSplitTypeId':1,'scoringPeriodId':7,'appliedTotal':99}]}}}
        data={'settings':{'name':'Synthetic adapter test','rosterSettings':{'lineupSlotCounts':{'2':1,'20':2}}},'scoringPeriodId':7,
              'teams':[{'id':1,'name':'First','roster':{'entries':[player(1)]}},{'id':2,'name':'Second','roster':{'entries':[player(2)]}}]}
        league=normalize_espn(data,{},2026)
        self.assertEqual(league.teams[0].players[0].season,170)
        self.assertIsNone(league.teams[0].players[0].weekly)
        self.assertEqual(league.roster_limit,3)
        self.assertNotIn('owners',league.public())

    def test_espn_duplicate_projection_records_fail_closed_on_conflict(self):
        def record(split, value, **extra):
            return {'seasonId':2026, 'statSourceId':1, 'statSplitTypeId':split,
                    'scoringPeriodId':7 if split == 1 else 0, 'appliedTotal':value} | extra
        def normalize(stats, free=False):
            def player(pid, values):
                return {'player':{'id':pid, 'fullName':'Synthetic player', 'defaultPositionId':2, 'stats':values}}
            data = {'settings':{'name':'Synthetic duplicates', 'rosterSettings':{'lineupSlotCounts':{'2':1}}},
                    'scoringPeriodId':7, 'teams':[
                        {'id':1, 'name':'A', 'roster':{'entries':[player(1, [] if free else stats)]}},
                        {'id':2, 'name':'B', 'roster':{'entries':[player(2, [])]}}]}
            return normalize_espn(data, {'players':[player(3, stats) | {'status':'FREEAGENT'}]} if free else {}, 2026)
        for split in (0, 1):
            for free in (False, True):
                for values in ((170, 171), (None, 0), (170, 170.004)):
                    stats = [record(split, v) for v in values]
                    for order in (stats, list(reversed(stats))):
                        with self.subTest(split=split, free=free, values=values), self.assertRaisesRegex(
                                ValueError, 'Conflicting ESPN .*projection records'):
                            normalize(order, free)
                for value in (None, 0, -1, 170):
                    league = normalize([record(split, value), record(split, value)], free)
                    p = league.free_agents[0] if free else league.teams[0].players[0]
                    self.assertEqual(p.season if split == 0 else p.weekly, value)
        # Different horizons, actuals, other years/weeks, and unverified splits do not collide.
        league = normalize([record(0, 170), record(0, '170.0'), record(1, 0),
                            record(0, 999, statSourceId=0), record(0, 999, seasonId=2025),
                            record(1, 999, scoringPeriodId=6), record(99, 999)])
        self.assertEqual((league.teams[0].players[0].season, league.teams[0].players[0].weekly), (170, 0))
        self.assertIn('no verified ROS field', league.source)
        for value in ('bad', float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize([record(0, value), record(0, 170)])
