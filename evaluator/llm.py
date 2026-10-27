"""Opt-in model-written commentary from anonymous deltas; computed results stay local."""
import json
import math
import os
import unicodedata
from urllib.request import Request
from .network import urlopen

REASONS = {
    'mutual_gain': 'Both teams improve their computed season lineup fit.',
    'your_gain': 'Prioritizes your computed season lineup gain.',
    'balanced_gain': 'Prioritizes the smaller of the two computed gains.',
    'weekly_gain': 'Prioritizes the computed current-week lineup changes.',
}
FALLBACK = 'unavailable: deterministic results retained'


def enabled():
    return os.getenv('LLM_ENABLED', 'false').lower() == 'true'


def available():
    return enabled() and os.getenv('LLM_PROVIDER') == 'openai' and bool(os.getenv('LLM_API_KEY', '').strip())


def _classification(yours, theirs):
    if yours == 0 and theirs == 0:
        return 'unchanged'
    if yours > 0 and theirs > 0:
        return 'both_gain'
    if yours > 0:
        return 'your_gain'
    if theirs > 0:
        return 'their_gain'
    return 'neither_gain'


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def _reject_constant(_):
    raise ValueError('nonfinite JSON number')


def _json(raw):
    return json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)


def _annotate(candidates, *, reorder):
    if not enabled():
        return candidates, 'disabled'
    if not candidates:
        return candidates, 'no candidates'
    if not available():
        return candidates, 'unavailable: configure provider and key locally'
    try:
        # Only four numeric deltas and request-local labels cross this boundary.
        # Never send the stable trade hash (derived from roster identities),
        # names/IDs, scores, warnings, raw rosters, OCR, images or user text.
        facts = []
        for i, candidate in enumerate(candidates):
            fact = {'id': f'c{i}'}
            for side, label in (('yours', 'your'), ('theirs', 'their')):
                for mode in ('season', 'week'):
                    value = candidate[side][mode]['delta']
                    if type(value) not in (int, float) or not math.isfinite(value):
                        raise ValueError('invalid delta')
                    fact[f'{label}_{mode}_delta'] = value
            facts.append(fact)
        payload = {'model': os.getenv('LLM_MODEL', 'gpt-4.1-mini'), 'temperature': 0,
                   'store': False, 'response_format': {'type': 'json_object'}, 'messages': [
            {'role': 'system', 'content': (
                'Use only the supplied computed deltas. Return JSON '
                '{"ranking":[{"id":"c0","reason":"reason code",'
                '"summary":{"season":"summary code","week":"summary code","text":"your concise summary"}}]}. '
                'Include every supplied id exactly once. '
                + ('Rank by lineup fit. ' if reorder else 'Preserve the supplied order. ')
                + 'Allowed reason codes: ' + ', '.join(REASONS) + '. '
                'mutual_gain and balanced_gain require both season deltas > 0; '
                'your_gain requires your season delta > 0; weekly_gain is always allowed. '
                'For each summary horizon use exactly the matching code: unchanged if both deltas are zero; '
                'both_gain if both > 0; your_gain if only yours > 0; their_gain if only theirs > 0; '
                'otherwise neither_gain. Write text as one or two concise plain-text English sentences, '
                'at most 280 characters, describing the season and current-week tradeoffs. '
                'Use only the supplied deltas; no identities, labels, digits, numerical metrics, '
                'external facts, predictions, advice, markup or URLs. Do not claim roster depth, '
                'availability, data completeness, trade acceptance, or a verdict. No extra fields.')},
            {'role': 'user', 'content': json.dumps(facts, allow_nan=False)}]}
        request = Request('https://api.openai.com/v1/chat/completions', data=json.dumps(payload, allow_nan=False).encode(),
                          headers={'Authorization': 'Bearer ' + os.environ['LLM_API_KEY'], 'Content-Type': 'application/json'}, method='POST')
        with urlopen(request, timeout=20) as response:
            body = response.read(100_001)
        if len(body) > 100_000:
            raise ValueError('oversized')
        envelope = _json(body)
        choices = envelope['choices']
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError('invalid choices')
        choice = choices[0]
        message = choice['message']
        if (choice.get('finish_reason') != 'stop' or message.get('role') != 'assistant'
                or message.get('refusal') or message.get('tool_calls') or message.get('function_call')
                or not isinstance(message.get('content'), str)):
            raise ValueError('incomplete or refused response')
        result = _json(message['content'])
        if not isinstance(result, dict) or set(result) != {'ranking'}:
            raise ValueError('invalid result')
        ranking = result['ranking']
        by_id = {f'c{i}': (c, facts[i]) for i, c in enumerate(candidates)}
        if not isinstance(ranking, list) or len(ranking) != len(candidates):
            raise ValueError('invalid candidate count')
        seen, output = set(), []
        for row in ranking:
            if not isinstance(row, dict) or set(row) != {'id', 'reason', 'summary'}:
                raise ValueError('invalid row')
            ref, reason, summary = row['id'], row['reason'], row['summary']
            if type(ref) is not str or ref not in by_id or ref in seen:
                raise ValueError('invalid candidate set')
            if type(reason) is not str or reason not in REASONS:
                raise ValueError('invalid reason')
            if not isinstance(summary, dict) or set(summary) != {'season', 'week', 'text'}:
                raise ValueError('invalid summary')
            candidate, fact = by_id[ref]
            ys, ts = fact['your_season_delta'], fact['their_season_delta']
            if ((reason in {'mutual_gain', 'balanced_gain'} and min(ys, ts) <= 0)
                    or (reason == 'your_gain' and ys <= 0)):
                raise ValueError('unsupported reason')
            for mode in ('season', 'week'):
                if summary[mode] != _classification(fact[f'your_{mode}_delta'], fact[f'their_{mode}_delta']):
                    raise ValueError('unsupported summary')
            prose = summary['text']
            if (type(prose) is not str or not 1 <= len(prose.strip()) <= 280
                    or any(unicodedata.category(ch).startswith('C') or ch.isdigit() for ch in prose)
                    or any(ch in prose for ch in '<>[]{}') or '://' in prose or 'www.' in prose.lower()):
                raise ValueError('invalid summary text')
            seen.add(ref)
            # Prose is returned verbatim as plain text; all computed fields are retained.
            output.append(candidate | {'llm_reason': REASONS[reason],
                                       'llm_summary': prose.strip()})
        if not reorder and [row['id'] for row in ranking] != list(by_id):
            raise ValueError('invalid order')
        return output, 'ranked and summarized' if reorder else 'summarized'
    except Exception:
        # Provider errors and untrusted output never replace deterministic data.
        return candidates, FALLBACK


def rank(candidates):
    return _annotate(candidates, reorder=True)


def summarize(trade):
    results, state = _annotate([trade], reorder=False)
    return results[0], state
