"""Offline local HTTP and real Tesseract smoke, using only synthetic inputs."""
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app import create_server
from scripts.offline_tests import deny_external_network


def main():
    sys.addaudithook(deny_external_network)
    os.environ['LLM_ENABLED'] = 'false'
    from PIL import Image, ImageDraw, ImageFont
    server=create_server(port=0,source='demo',token='')
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    base=f'http://127.0.0.1:{server.server_port}'
    def request(path,data=None,mime='application/json'):
        raw=json.dumps(data).encode() if data is not None and mime=='application/json' else data
        with urlopen(Request(base+path,data=raw,headers={'Content-Type':mime}),timeout=30) as response:
            assert response.status==200
            return response.read()
    try:
        health=json.loads(request('/health'));assert health['status']=='ok' and health['read_only'] and not health['llm_enabled']
        page = request('/')
        assert b'TRADE ROOM' in page and b'id="llm-summary"' in page and b'id="llm-rank"' in page
        league=json.loads(request('/api/league'));assert len(league['teams'])==6
        result=json.loads(request('/api/candidates',{'team_id':'harbor'}));assert result['checked']==2205 and len(result['candidates'])==12
        c=result['candidates'][0]
        evaluated=json.loads(request('/api/evaluate',{k:c[k] for k in ['team_id','other_id','give','receive']}));assert c==evaluated
        assert all('filled' in c[side][mode][phase] and 'benched_slots' in c[side][mode][phase]
                   for side in ('yours','theirs') for mode in ('week','season') for phase in ('before','after'))
        assert c['season_model'] == result['season_model']
        assert c['season_model']['ros']['available'] is False and c['season_model']['ros']['value'] is None
        assert c['sensitivity']['affects_ranking'] is False
        assert c['sensitivity']['policy'] == 'exclude_doubtful_out_ir_free_agents'
        assert all(c['sensitivity'][side]['before'] == c[side]['season']['before']
                   and c['sensitivity'][side]['after'] == c[side]['season']['after'] for side in ('yours','theirs'))
        assert all(len(c['season_model']['replacement'][policy]) == 6 for policy in ('primary','doubtful_out_ir_filtered'))
        proposal = {k:c[k] for k in ('team_id','other_id','give','receive')}
        disabled = json.loads(request('/api/evaluate', proposal | {'use_llm':True}))
        assert disabled.pop('llm_status') == 'disabled' and disabled == c
        def provider(req, timeout):
            facts = json.loads(json.loads(req.data)['messages'][1]['content'])
            rows = []
            for fact in facts:
                assert set(fact) == {'id','your_season_delta','their_season_delta','your_week_delta','their_week_delta'}
                summary = {'text': 'These computed deltas describe the season and current-week tradeoffs.'}
                for mode in ('season','week'):
                    a,b = fact[f'your_{mode}_delta'],fact[f'their_{mode}_delta']
                    summary[mode] = ('unchanged' if a == b == 0 else 'both_gain' if min(a,b)>0
                                     else 'your_gain' if a>0 else 'their_gain' if b>0 else 'neither_gain')
                rows.append({'id':fact['id'],'reason':'weekly_gain','summary':summary})
            return BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{
                'role':'assistant','content':json.dumps({'ranking':rows})}}]}).encode())
        def computed(trade):
            return {k:v for k,v in trade.items() if k not in {'llm_summary','llm_reason','llm_status'}}
        with patch.dict(os.environ, {'LLM_ENABLED':'true','LLM_PROVIDER':'openai','LLM_API_KEY':'synthetic-key'}):
            with patch('evaluator.llm.urlopen', side_effect=provider) as mocked:
                summary = json.loads(request('/api/evaluate', proposal | {'use_llm':True}))
                assert summary['llm_status'] == 'summarized' and summary['llm_summary'] and computed(summary) == c
                ranked = json.loads(request('/api/candidates', {'team_id':'harbor','use_llm':True}))
                assert ranked['llm_status'] == 'ranked and summarized'
                assert all(t['llm_summary'] for t in ranked['candidates'])
                assert [computed(t) for t in ranked['candidates']] == result['candidates'] and mocked.call_count == 2
            with patch('evaluator.llm.urlopen', side_effect=TimeoutError):
                fallback = json.loads(request('/api/evaluate', proposal | {'use_llm':True}))
                assert fallback.pop('llm_status') == 'unavailable: deterministic results retained' and fallback == c
                fallback = json.loads(request('/api/candidates', {'team_id':'harbor','use_llm':True}))
                assert fallback.pop('llm_status') == 'unavailable: deterministic results retained'
                assert fallback == {k:v for k,v in result.items() if k != 'llm_status'}
        assert json.loads(request('/api/candidates', {'team_id':'harbor'})) == result
        image=Image.new('RGB',(900,220),'white');draw=ImageDraw.Draw(image);font=ImageFont.load_default(size=42)
        own_name = league['teams'][0]['players'][2]['name']
        draw.text((30,25),'Bennett Vale',fill='black',font=font);draw.text((30,110),own_name,fill='black',font=font)
        buf=BytesIO();image.save(buf,format='PNG')
        ocr=json.loads(request('/api/ocr',buf.getvalue(),'image/png'))
        assert ocr['requires_confirmation'] and not ocr['retained']
        ids={m['player_id'] for row in ocr['suggestions'] for m in row['matches']}
        assert {'harbor-2','harbor-3'} <= ids,ocr['text']
        proposal={'team_id':'harbor','roster_ids':[p['id'] for p in league['teams'][0]['players']],'source':'ocr','use_llm':False}
        try:
            request('/api/candidates',proposal)
            raise AssertionError('Unconfirmed OCR should be rejected')
        except HTTPError as error:
            with error:assert error.code==400
        confirmed=json.loads(request('/api/candidates',proposal|{'confirmed':True}))
        assert confirmed == result and confirmed['opponents'] == 5 and len(confirmed['candidates']) == 12
        print('PASS OCR own-roster confirmation: unconfirmed HTTP 400; confirmed scan HTTP 200, all 5 opponents, 12 cards')
        print('PASS health: HTTP 200, synthetic source, read_only=true, llm_enabled=false')
        print('PASS UI and league: HTTP 200, 6 synthetic teams')
        print(f"PASS candidate generation: {result['checked']} checked, {result['qualified']} qualified, {len(result['candidates'])} returned")
        print('PASS manual evaluation: identical computed candidate')
        print('PASS coverage: filled and intentionally benched slots disclosed separately')
        print('PASS season model: positional baseline provenance, separate Doubtful/Out/IR-filtered sensitivity, ROS unavailable/null; demo primary unchanged')
        print('PASS opt-in AI: disabled by default; mocked model-written manual/card summaries; deltas-only payload; timeout retains exact deterministic results')
        print(f'PASS real local OCR: synthetic own-team PNG → Bennett Vale / {own_name}; confirmation required; retained=false')
        print('PASS smoke: local server closed cleanly; no private ESPN data or LLM used')
    finally:server.shutdown();server.server_close();worker.join()


if __name__=='__main__':main()
