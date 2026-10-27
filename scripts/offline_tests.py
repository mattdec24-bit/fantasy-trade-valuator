"""Run the test suite with an audit hook rejecting non-loopback networking."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def deny_external_network(event, args):
    if event == 'socket.getaddrinfo':
        host = args[0]
    elif event == 'socket.connect':
        address = args[1]
        if not isinstance(address, tuple):
            return  # Local Unix sockets are not internet connections.
        host = address[0]
    else:
        return
    if host not in {'localhost', '127.0.0.1', '::1'}:
        raise RuntimeError('Offline test blocked non-loopback network access')


if __name__ == '__main__':
    sys.addaudithook(deny_external_network)
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
