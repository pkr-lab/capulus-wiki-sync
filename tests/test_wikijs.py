import io
import json
import unittest
import urllib.error
from unittest import mock

from wikisync.wikijs import PAGE_SIZE, RenderLimitError, WikiClient, WikiError


class Response:
    def __init__(self, body):
        self.raw = b"" if body is None else json.dumps(body).encode()

    def read(self):
        return self.raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def http_error(code: int, detail: str = "nein") -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://wiki", code, "x", {}, io.BytesIO(detail.encode()))


class RequestTests(unittest.TestCase):
    def setUp(self):
        self.client = WikiClient("http://wiki", "geheim", "en", site_id="s1")
        sleep = mock.patch("wikisync.wikijs.time.sleep")
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)

    def urlopen(self, *effects):
        patcher = mock.patch("wikisync.wikijs.urllib.request.urlopen", side_effect=list(effects))
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_request_headers_and_body(self):
        opened = self.urlopen(Response({"ok": True}))
        self.assertEqual(self.client.request("POST", "/x", {"a": 1}), {"ok": True})
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, "http://wiki/_api/x")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer geheim")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(json.loads(request.data), {"a": 1})
        self.assertEqual(opened.call_args.kwargs["timeout"], 30)

    def test_empty_body_and_unauthorized(self):
        opened = self.urlopen(Response(None))
        self.assertEqual(self.client.request("GET", "/x", authorized=False), {})
        self.assertIsNone(opened.call_args.args[0].get_header("Authorization"))

    def test_client_error_is_not_retried(self):
        opened = self.urlopen(http_error(404))
        with self.assertRaisesRegex(WikiError, "^HTTP 404 von Wiki.js: nein$"):
            self.client.request("GET", "/x")
        self.assertEqual(opened.call_count, 1)

    def test_rate_limit_raises_render_limit(self):
        self.urlopen(http_error(429))
        with self.assertRaisesRegex(RenderLimitError, "^HTTP 429 von Wiki.js: nein$"):
            self.client.request("GET", "/x")

    def test_server_error_is_retried(self):
        opened = self.urlopen(http_error(502), urllib.error.URLError("weg"), Response({"ok": 1}))
        self.assertEqual(self.client.request("GET", "/x"), {"ok": 1})
        self.assertEqual(opened.call_count, 3)
        self.assertEqual([call.args[0] for call in self.sleep.call_args_list], [2, 4])

    def test_retries_exhausted(self):
        self.urlopen(http_error(500), http_error(503), http_error(500, "zuletzt"))
        with self.assertRaisesRegex(WikiError, "^HTTP 500 von Wiki.js: zuletzt$"):
            self.client.request("GET", "/x")
        self.assertEqual([call.args[0] for call in self.sleep.call_args_list], [2, 4, 6])

    def test_unreachable(self):
        self.urlopen(TimeoutError("t"), TimeoutError("t"), TimeoutError("t"))
        with self.assertRaisesRegex(WikiError, "^Wiki.js nicht erreichbar: t$"):
            self.client.request("GET", "/x")


class ClientTests(unittest.TestCase):
    def test_site_from_bootstrap(self):
        client = WikiClient("http://wiki", "t", "en")
        with mock.patch.object(client, "request", return_value={"site": {"id": "abc"}}) as request:
            self.assertEqual(client.site(), "abc")
            self.assertEqual(client.site(), "abc")
        request.assert_called_once_with("GET", "/bootstrap", authorized=False)

    def test_site_missing(self):
        client = WikiClient("http://wiki", "t", "en")
        with mock.patch.object(client, "request", return_value={}):
            with self.assertRaisesRegex(WikiError, "WIKIJS_SITE_ID"):
                client.site()

    def test_list_pages_pages_through_tree(self):
        client = WikiClient("http://wiki", "t", "de", site_id="s1")
        first = [{"type": "page", "id": str(index), "folderPath": "docs", "fileName": f"p{index}", "title": "T"} for index in range(PAGE_SIZE - 1)]
        first.append({"type": "folder", "id": "f", "folderPath": "", "fileName": "docs", "title": "docs"})
        second = [{"type": "page", "id": "root", "folderPath": "", "fileName": "home", "title": "Home"}]
        with mock.patch.object(client, "request", side_effect=[first, second]) as request:
            found = client.list_pages()
        self.assertEqual(len(found), PAGE_SIZE)
        self.assertEqual(found["home"].id, "root")
        self.assertEqual(found["docs/p0"].id, "0")
        paths = [call.args[1] for call in request.call_args_list]
        self.assertTrue(all(path.startswith("/sites/s1/tree?") for path in paths))
        self.assertIn("offset=0", paths[0])
        self.assertIn(f"offset={PAGE_SIZE}", paths[1])
        self.assertIn("locale=de", paths[0])

    def test_page_operations(self):
        client = WikiClient("http://wiki", "t", "en", site_id="s1")
        with mock.patch.object(client, "request", return_value={"page": {"id": "neu"}}) as request:
            self.assertEqual(client.create("docs/a", "A", "inhalt", "d"), "neu")
            client.update("p1", "A", "inhalt", "d")
            client.queue_render("p1")
            client.delete("p1")
            client.get_page("p1")
        calls = [(call.args[0], call.args[1]) for call in request.call_args_list]
        self.assertEqual(
            calls,
            [
                ("POST", "/sites/s1/pages"),
                ("PATCH", "/sites/s1/pages/p1"),
                ("POST", "/sites/s1/pages/p1/render"),
                ("DELETE", "/sites/s1/pages/p1"),
                ("GET", "/sites/s1/pages/p1?withContent=true"),
            ],
        )
        self.assertEqual(request.call_args_list[0].args[2]["publishState"], "published")
        self.assertEqual(request.call_args_list[1].args[2]["render"], "")


if __name__ == "__main__":
    unittest.main()
