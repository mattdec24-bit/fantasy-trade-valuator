#!/usr/bin/env python3
"""Offline synthetic demo and read-only CLI using the same engine as the UI."""
import argparse
import json
from evaluator import llm
from evaluator.model import Engine
from evaluator.sources import demo, load_espn


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', action='store_true', help='Explicit synthetic offline mode (also the default)')
    parser.add_argument('--source', choices=['demo','espn'], default='demo')
    parser.add_argument('--team', default='harbor', help='Your team ID from /api/league')
    parser.add_argument('--other', help='Other team ID for manual evaluation')
    parser.add_argument('--give', help='Comma-separated outgoing player IDs')
    parser.add_argument('--get', dest='receive', help='Comma-separated incoming player IDs')
    ai = parser.add_mutually_exclusive_group()
    ai.add_argument('--llm', dest='use_llm', action='store_true',
                    help='Request anonymous AI summaries/ranking; requires local provider opt-in')
    ai.add_argument('--no-llm', dest='use_llm', action='store_false', help='Skip AI for this run')
    parser.set_defaults(use_llm=None)
    args = parser.parse_args()
    if args.demo and args.source != 'demo':
        parser.error('--demo cannot be combined with ESPN source')
    try:
        engine = Engine(demo() if args.source == 'demo' else load_espn())
        use_llm = llm.available() if args.use_llm is None else args.use_llm
        if args.other or args.give or args.receive:
            if not all([args.other,args.give,args.receive]):
                parser.error('Use --other, --give and --get together')
            result = engine.evaluate(args.team, args.other, args.give.split(','), args.receive.split(','))
            if use_llm:
                result, state = llm.summarize(result)
                result = result | {'llm_status': state}
        else:
            result = engine.candidates(args.team)
            if use_llm:
                ranked, state = llm.rank(result['candidates'])
                result = result | {'candidates': ranked, 'llm_status': state}
        print(json.dumps(result, indent=2, allow_nan=False))
    except ValueError as e:
        parser.exit(2, str(e) + '\n')


if __name__ == '__main__':
    main()
