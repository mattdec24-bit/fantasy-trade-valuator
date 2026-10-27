"""Do not forward credentials through redirects."""
from urllib.request import HTTPRedirectHandler, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def urlopen(request, timeout=15):
    return build_opener(NoRedirect).open(request, timeout=timeout)
