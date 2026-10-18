import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


class WikiError(Exception):
    pass


@dataclass(frozen=True)
class Existing:
    id: int
    path: str
    title: str


class WikiClient:
    def __init__(self, api_url: str, token: str, locale: str, retries: int = 2):
        self.endpoint = f"{api_url}/graphql"
        self.token = token
        self.locale = locale
        self.retries = retries

    def graphql(self, query: str, variables: dict | None = None) -> dict:
        payload = json.dumps({"query": query, "variables": variables or {}}).encode()
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"},
            method="POST",
        )
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    body = json.loads(response.read())
                break
            except urllib.error.HTTPError as error:
                detail = error.read().decode(errors="replace")
                if error.code < 500:
                    raise WikiError(f"HTTP {error.code} von Wiki.js: {detail}") from error
                last = WikiError(f"HTTP {error.code} von Wiki.js: {detail}")
            except (urllib.error.URLError, TimeoutError) as error:
                last = WikiError(f"Wiki.js nicht erreichbar: {error}")
            time.sleep(2 * (attempt + 1))
        else:
            raise last or WikiError("Wiki.js nicht erreichbar")
        if body.get("errors"):
            raise WikiError(json.dumps(body["errors"]))
        return body["data"]

    @staticmethod
    def check(result: dict, action: str) -> None:
        response = result["responseResult"]
        if not response["succeeded"]:
            raise WikiError(f"{action} fehlgeschlagen: {response.get('errorCode')} {response.get('message')}")

    def list_pages(self) -> dict[str, Existing]:
        data = self.graphql("query { pages { list { id path locale title } } }")
        return {
            page["path"]: Existing(id=page["id"], path=page["path"], title=page["title"])
            for page in data["pages"]["list"]
            if page["locale"] == self.locale
        }

    def get_page(self, page_id: int) -> dict:
        data = self.graphql(
            "query ($id: Int!) { pages { single(id: $id) { content title description isPublished } } }",
            {"id": page_id},
        )
        return data["pages"]["single"]

    def create(self, path: str, title: str, content: str, description: str) -> None:
        data = self.graphql(
            """
            mutation ($path: String!, $title: String!, $content: String!, $description: String!, $locale: String!) {
              pages {
                create(path: $path, title: $title, content: $content, description: $description, locale: $locale,
                       editor: "markdown", isPublished: true, isPrivate: false, tags: []) {
                  responseResult { succeeded errorCode message }
                }
              }
            }
            """,
            {"path": path, "title": title, "content": content, "description": description, "locale": self.locale},
        )
        self.check(data["pages"]["create"], f"Anlegen von {path}")

    def update(self, page_id: int, path: str, title: str, content: str, description: str) -> None:
        data = self.graphql(
            """
            mutation ($id: Int!, $title: String!, $content: String!, $description: String!) {
              pages {
                update(id: $id, title: $title, content: $content, description: $description, isPublished: true) {
                  responseResult { succeeded errorCode message }
                }
              }
            }
            """,
            {"id": page_id, "title": title, "content": content, "description": description},
        )
        self.check(data["pages"]["update"], f"Aktualisieren von {path}")

    def delete(self, page_id: int, path: str) -> None:
        data = self.graphql(
            "mutation ($id: Int!) { pages { delete(id: $id) { responseResult { succeeded errorCode message } } } }",
            {"id": page_id},
        )
        self.check(data["pages"]["delete"], f"Löschen von {path}")
