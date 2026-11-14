import io
import tarfile

from wikisync.config import Config


def make_config(**overrides) -> Config:
    values = dict(
        owner="pkr-lab",
        repo="pkr-lab-docs",
        branch="main",
        github_token="",
        api_url="http://wiki",
        api_token="t",
        locale="en",
        prefix="docs",
        exclude=(),
        legacy_prefixes=(),
        dry_run=False,
        min_pages=1,
        site_id="",
        render_batch=8,
    )
    values.update(overrides)
    return Config(**values)


def make_tarball(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in files.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(f"pkr-lab-pkr-lab-docs-abc123/{name}")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


class FakeClient:
    def __init__(self, pages=None, render_limit=None):
        self.pages = {
            path: dict(page, id=f"id-{index}", render=page.get("render", "<p>x</p>"))
            for index, (path, page) in enumerate((pages or {}).items(), start=1)
        }
        self.calls: list[tuple] = []
        self.next_id = 1000
        self.render_limit = render_limit

    def list_pages(self):
        from wikisync.wikijs import Existing

        return {path: Existing(id=page["id"], path=path, title=page["title"]) for path, page in self.pages.items()}

    def get_page(self, page_id):
        for page in self.pages.values():
            if page["id"] == page_id:
                return {
                    "content": page["content"],
                    "title": page["title"],
                    "description": page["description"],
                    "publishState": page.get("publishState", "published"),
                    "render": page["render"],
                }
        raise AssertionError("unbekannte Seite")

    def create(self, path, title, content, description):
        self.calls.append(("create", path))
        self.next_id += 1
        self.pages[path] = {"id": f"id-{self.next_id}", "title": title, "content": content, "description": description, "render": ""}
        return self.pages[path]["id"]

    def update(self, page_id, path, title, content, description):
        self.calls.append(("update", path))
        self.pages[path].update(title=title, content=content, description=description, render="")

    def queue_render(self, page_id):
        from wikisync.wikijs import RenderLimitError

        renders = len([call for call in self.calls if call[0] == "render"])
        if self.render_limit is not None and renders >= self.render_limit:
            raise RenderLimitError("zu viele")
        for path, page in self.pages.items():
            if page["id"] == page_id:
                self.calls.append(("render", path))
                page["render"] = "<p>gerendert</p>"
                return
        raise AssertionError("unbekannte Seite")

    def delete(self, page_id, path):
        self.calls.append(("delete", path))
        del self.pages[path]
