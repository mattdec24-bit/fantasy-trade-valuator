"""Compatibility entry point for the shared read-only engine.

No credential discovery, Keychain access, persistence, or ESPN writes.
Use environment configuration and explicit evaluator.sources.load_espn().
"""
from evaluator.model import Engine, League, Player, Team
from evaluator.sources import demo, load_espn

__all__ = ['Engine', 'League', 'Player', 'Team', 'demo', 'load_espn']
