import sys
from dataclasses import dataclass, field

from .config import Config
from .render import CollisionError, Page, build_pages
from .source import fetch_tarball, read_tree
from .wikijs import WikiClient, WikiError


@dataclass
class Report:
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: int = 0
    deleted: list[str] = field(default_factory=list)
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
        or not current.get("isPublished", True)
    )


def reconcile(config: Config, client, pages: dict[str, Page]) -> Report:
    report = Report()
    existing = client.list_pages()
    for path, page in sorted(pages.items()):
        known = existing.get(path)
        try:
            if known is None:
                if not config.dry_run:
                    client.create(path, page.title, page.content, page.description)
                report.created.append(path)
                print(f"[CREATE] /{config.locale}/{path}")
            elif differs(client.get_page(known.id), page):
                if not config.dry_run:
                    client.update(known.id, path, page.title, page.content, page.description)
                report.updated.append(path)
                print(f"[UPDATE] /{config.locale}/{path}")
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
    client = client or WikiClient(config.api_url, config.api_token, config.locale)
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
        f"unverändert={report.unchanged} gelöscht={len(report.deleted)} Fehler={len(report.errors)}"
    )
    return 1 if report.errors else 0
