import sys
from dataclasses import dataclass, field

from .config import Config
from .render import CollisionError, Page, build_pages
from .source import fetch_tarball, read_tree
from .wikijs import RenderLimitError, WikiClient, WikiError


@dataclass
class Report:
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: int = 0
    deleted: list[str] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)
    rendered: int = 0
    errors: list[str] = field(default_factory=list)


def normalized(text: str) -> str:
    return text.replace("\r\n", "\n").rstrip("\n")


def under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def differs(current: dict, page: Page) -> bool:
    return (
        normalized(current["content"]) != normalized(page.content)
        or current["title"] != page.title
        or (current.get("description") or "") != page.description
        or current.get("publishState", "published") != "published"
    )


class RenderBudget:
    def __init__(self, size: int):
        self.left = size

    def take(self) -> bool:
        if self.left < 1:
            return False
        self.left -= 1
        return True

    def exhaust(self) -> None:
        self.left = 0


def queue_render(config: Config, client, budget: RenderBudget, report: Report, page_id: str, path: str) -> None:
    if config.dry_run:
        return
    try:
        client.queue_render(page_id)
        report.rendered += 1
    except RenderLimitError:
        budget.exhaust()
        print(f"[WARN] Render-Limit erreicht, {path} wird im nächsten Lauf gerendert", file=sys.stderr)
    except WikiError as error:
        print(f"[WARN] Render für {path} nicht eingereiht: {error}", file=sys.stderr)


def reconcile(config: Config, client, pages: dict[str, Page]) -> Report:
    report = Report()
    budget = RenderBudget(10**9 if config.dry_run else config.render_batch)
    existing = client.list_pages()
    for path, page in sorted(pages.items()):
        known = existing.get(path)
        try:
            if known is None:
                if not budget.take():
                    report.deferred.append(path)
                    continue
                page_id = None if config.dry_run else client.create(path, page.title, page.content, page.description)
                report.created.append(path)
                print(f"[CREATE] /{config.locale}/{path}")
                if page_id:
                    queue_render(config, client, budget, report, page_id, path)
                continue
            current = client.get_page(known.id)
            if differs(current, page):
                if not budget.take():
                    report.deferred.append(path)
                    continue
                if not config.dry_run:
                    client.update(known.id, path, page.title, page.content, page.description)
                report.updated.append(path)
                print(f"[UPDATE] /{config.locale}/{path}")
                queue_render(config, client, budget, report, known.id, path)
            elif not current.get("render") and budget.take():
                print(f"[RENDER] /{config.locale}/{path}")
                queue_render(config, client, budget, report, known.id, path)
            else:
                report.unchanged += 1
        except WikiError as error:
            report.errors.append(f"{path}: {error}")
            print(f"[ERR] {path}: {error}", file=sys.stderr)
    stale = [
        (path, known.id)
        for path, known in existing.items()
        if (under(path, config.prefix) and path not in pages)
        or any(under(path, legacy) for legacy in config.legacy_prefixes)
    ]
    for path, page_id in sorted(stale):
        try:
            if not config.dry_run:
                client.delete(page_id, path)
            report.deleted.append(path)
            print(f"[DELETE] /{config.locale}/{path}")
        except WikiError as error:
            report.errors.append(f"{path}: {error}")
            print(f"[ERR] {path}: {error}", file=sys.stderr)
    return report


def run(config: Config, fetch=fetch_tarball, client=None) -> int:
    client = client or WikiClient(config.api_url, config.api_token, config.locale, config.site_id)
    try:
        data = fetch(config.owner, config.repo, config.branch, config.github_token)
        tree = read_tree(data, config.exclude)
        pages = build_pages(config, tree)
    except (OSError, ValueError, CollisionError) as error:
        print(f"[FATAL] Quelle nicht verwendbar: {error}", file=sys.stderr)
        return 1
    print(f"[INFO] {len(tree.markdown)} Markdown-Dateien aus {config.owner}/{config.repo}@{config.branch}, {len(pages)} Wiki-Seiten")
    if len(pages) < config.min_pages:
        print(f"[FATAL] Nur {len(pages)} Seiten, mindestens {config.min_pages} erwartet; nichts wird geändert", file=sys.stderr)
        return 1
    try:
        report = reconcile(config, client, pages)
    except WikiError as error:
        print(f"[FATAL] {error}", file=sys.stderr)
        return 1
    suffix = " (DryRun)" if config.dry_run else ""
    print(
        f"[DONE]{suffix} neu={len(report.created)} geändert={len(report.updated)} "
        f"unverändert={report.unchanged} gelöscht={len(report.deleted)} zurückgestellt={len(report.deferred)} "
        f"gerendert={report.rendered} Fehler={len(report.errors)}"
    )
    return 1 if report.errors else 0
