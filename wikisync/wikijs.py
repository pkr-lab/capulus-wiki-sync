import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

PAGE_SIZE = 1000


class WikiError(Exception):
    pass


class RenderLimitError(WikiError):
    pass


@dataclass(frozen=True)
class Existing:
    id: str
    path: str
    title: str


class WikiClient:
    def __init__(self, api_url: str, token: str, locale: str, site_id: str = "", retries: int = 2):
        self.base = f"{api_url}/_api"
        self.token = token
        self.locale = locale
        self.site_id = site_id
        self.retries = retries

    def request(self, method: str, path: str, body: dict | None = None, authorized: bool = True):
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if authorized:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(f"{self.base}{path}", data=data, headers=headers, method=method)
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    raw = response.read()
                return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as error:
                detail = error.read().decode(errors="replace")
                if error.code == 429:
                    raise RenderLimitError(f"HTTP 429 von Wiki.js: {detail}") from error
                if error.code < 500:
                    raise WikiError(f"HTTP {error.code} von Wiki.js: {detail}") from error
                last = WikiError(f"HTTP {error.code} von Wiki.js: {detail}")
            except (urllib.error.URLError, TimeoutError) as error:
                last = WikiError(f"Wiki.js nicht erreichbar: {error}")
            time.sleep(2 * (attempt + 1))
        raise last or WikiError("Wiki.js nicht erreichbar")

    def site(self) -> str:
        if not self.site_id:
            site = self.request("GET", "/bootstrap", authorized=False).get("site") or {}
            if not site.get("id"):
                raise WikiError("Site-ID nicht ermittelbar, WIKIJS_SITE_ID setzen")
            self.site_id = site["id"]
        return self.site_id

    def pages_path(self, suffix: str = "") -> str:
        return f"/sites/{self.site()}/pages{suffix}"

    def list_pages(self) -> dict[str, Existing]:
        found: dict[str, Existing] = {}
        offset = 0
        while True:
            query = urllib.parse.urlencode(
                {
                    "types": "page",
                    "depth": 10,
                    "locale": self.locale,
                    "limit": PAGE_SIZE,
                    "offset": offset,
                    "orderBy": "createdAt",
                }
            )
            entries = self.request("GET", f"/sites/{self.site()}/tree?{query}")
            for entry in entries:
                if entry.get("type") != "page":
                    continue
                folder = entry.get("folderPath") or ""
                path = f"{folder}/{entry['fileName']}" if folder else entry["fileName"]
                found[path] = Existing(id=entry["id"], path=path, title=entry["title"])
            if len(entries) < PAGE_SIZE:
                return found
            offset += PAGE_SIZE

    def get_page(self, page_id: str) -> dict:
        return self.request("GET", self.pages_path(f"/{page_id}?withContent=true"))

    def create(self, path: str, title: str, content: str, description: str) -> str:
        data = self.request(
            "POST",
            self.pages_path(),
            {
                "path": path,
                "title": title,
                "description": description,
                "editor": "markdown",
                "content": content,
                "locale": self.locale,
                "publishState": "published",
            },
        )
        return data["page"]["id"]

    def update(self, page_id: str, path: str, title: str, content: str, description: str) -> None:
        self.request(
            "PATCH",
            self.pages_path(f"/{page_id}"),
            {
                "title": title,
                "description": description,
                "content": content,
                "publishState": "published",
                "render": "",
            },
        )

    def queue_render(self, page_id: str) -> None:
        self.request("POST", self.pages_path(f"/{page_id}/render"))

    def delete(self, page_id: str, path: str) -> None:
        self.request("DELETE", self.pages_path(f"/{page_id}"))
