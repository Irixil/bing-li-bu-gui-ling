import json
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import ThreadingHTTPServer


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: object
    body: object


class HttpClient:
    def __init__(self, base_url, default_headers=None):
        self.base_url = base_url
        self.default_headers = default_headers or {}
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(
        self,
        method,
        path,
        body=None,
        *,
        headers=None,
        raw_body=None,
        timeout=5,
    ):
        request_headers = {**self.default_headers, **(headers or {})}
        request = urllib.request.Request(
            self.base_url + path,
            method=method,
            headers=request_headers,
            data=(
                raw_body
                if raw_body is not None
                else None
                if body is None
                else json.dumps(body).encode("utf-8")
            ),
        )
        try:
            response = self.opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw_response = response.read()
            payload = json.loads(raw_response) if raw_response else None
            return HttpResponse(response.status, response.headers, payload)


@contextmanager
def running_http_server(handler):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=2)
