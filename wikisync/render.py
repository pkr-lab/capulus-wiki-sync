import posixpath
import re
from dataclasses import dataclass

from .config import Config
from .source import Tree

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")
FENCE = re.compile(r"^\s{0,3}(```|~~~)")
CODE_SPAN = re.compile(r"(`+[^`]*`+)")
MD_LINK = re.compile(r"(!?\[[^\]]*\]\()([^)\s]+)((?:\s+\"[^\"]*\")?\))")
HTML_ATTR = re.compile(r"(\b(?:src|href)=\")([^\"]+)(\")")
NUMBERED = re.compile(r"^([0-9a-f]{5})[-_.]")
SEGMENT = re.compile(r"[^\w-]+")


class CollisionError(Exception):
    pass


@dataclass(frozen=True)
class Page:
    title: str
    content: str
    description: str


def segment(name: str) -> str:
    return SEGMENT.sub("-", name).strip("-") or "seite"


def directory_path(config: Config, directory: str) -> str:
    parts = [segment(part) for part in directory.split("/") if part]
    return "/".join([config.prefix, *parts])


def wiki_path(config: Config, relative: str) -> str:
    directory, _, filename = relative.rpartition("/")
    stem = filename[:-3]
    if stem.lower() == "index" or (not directory and stem == "README"):
        return directory_path(config, directory)
    return directory_path(config, directory) + "/" + segment(stem)


def wiki_url(config: Config, path: str) -> str:
    return f"/{config.locale}/{path}"


def first_heading(text: str) -> str | None:
    fenced = False
    for line in text.splitlines():
        if FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced and line.startswith("# "):
            return line[2:].strip()
    return None


def page_title(relative: str, text: str) -> str:
    filename = relative.rpartition("/")[2]
    stem = filename[:-3]
    heading = first_heading(text)
    if heading is None:
        directory = relative.rpartition("/")[0].rpartition("/")[2]
        heading = directory if stem.lower() == "index" and directory else stem
    match = NUMBERED.match(filename)
    if match and not heading.startswith(match.group(1)):
        return f"{match.group(1)} - {heading}"
    return heading


def raw_url(config: Config, path: str) -> str:
    return f"https://raw.githubusercontent.com/{config.owner}/{config.repo}/{config.branch}/{path}"


def blob_url(config: Config, path: str, mode: str = "blob") -> str:
    return f"https://github.com/{config.owner}/{config.repo}/{mode}/{config.branch}/{path}"


def has_directory_page(tree: Tree, directory: str) -> bool:
    if directory == "":
        return "README.md" in tree.markdown or "index.md" in tree.markdown
    return f"{directory}/index.md" in tree.markdown


def resolve_target(config: Config, tree: Tree, source: str, target: str, image: bool) -> str | None:
    if not target or target.startswith(("#", "/", "//")) or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
        return None
    path, _, anchor = target.partition("#")
    suffix = f"#{anchor}" if anchor else ""
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source), path))
    if resolved.startswith(".."):
        return None
    if resolved in tree.markdown:
        return wiki_url(config, wiki_path(config, resolved)) + suffix
    if resolved in tree.others:
        if image or resolved.lower().endswith(IMAGE_SUFFIXES):
            return raw_url(config, resolved)
        return blob_url(config, resolved) + suffix
    directory = "" if resolved == "." else resolved.rstrip("/")
    if directory in tree.directories:
        return wiki_url(config, directory_path(config, directory)) + suffix
    return None


def rewrite_line(config: Config, tree: Tree, source: str, line: str) -> str:
    spans = [(match.start(), match.end()) for match in CODE_SPAN.finditer(line)]

    def in_code(position: int) -> bool:
        return any(start <= position < end for start, end in spans)

    def replace_link(match: re.Match[str]) -> str:
        if in_code(match.start()):
            return match.group(0)
        image = match.group(1).startswith("!")
        new = resolve_target(config, tree, source, match.group(2), image)
        return match.group(0) if new is None else match.group(1) + new + match.group(3)

    def replace_attr(match: re.Match[str]) -> str:
        if in_code(match.start()):
            return match.group(0)
        new = resolve_target(config, tree, source, match.group(2), match.group(1).startswith("src"))
        return match.group(0) if new is None else match.group(1) + new + match.group(3)

    return HTML_ATTR.sub(replace_attr, MD_LINK.sub(replace_link, line))


def rewrite_links(config: Config, tree: Tree, source: str, text: str) -> str:
    fenced = False
    lines = []
    for line in text.split("\n"):
        if FENCE.match(line):
            fenced = not fenced
            lines.append(line)
        elif fenced:
            lines.append(line)
        else:
            lines.append(rewrite_line(config, tree, source, line))
    return "\n".join(lines)


def children(tree: Tree, directory: str) -> tuple[list[str], list[str]]:
    prefix = f"{directory}/" if directory else ""
    pages = sorted(
        relative
        for relative in tree.markdown
        if relative.startswith(prefix)
        and "/" not in relative[len(prefix):]
        and relative[len(prefix):].lower() not in {"index.md"}
        and not (directory == "" and relative == "README.md")
    )
    directories = sorted(
        {
            prefix + relative[len(prefix):].partition("/")[0]
            for relative in tree.markdown
            if relative.startswith(prefix) and "/" in relative[len(prefix):]
        }
    )
    return pages, directories


def index_content(config: Config, tree: Tree, directory: str, titles: dict[str, str]) -> str:
    name = directory.rpartition("/")[2] or config.repo
    lines = [f"# {name}", "", "Diese Übersicht wird automatisch aus der Ordnerstruktur erzeugt.", ""]
    pages, directories = children(tree, directory)
    if directories:
        lines += ["## Bereiche", ""]
        for child in directories:
            lines.append(f"- [{child.rpartition('/')[2]}]({wiki_url(config, directory_path(config, child))})")
        lines.append("")
    if pages:
        lines += ["## Seiten", ""]
        for relative in pages:
            lines.append(f"- [{titles[relative]}]({wiki_url(config, wiki_path(config, relative))})")
        lines.append("")
    return "\n".join(lines)


def build_pages(config: Config, tree: Tree) -> dict[str, Page]:
    pages: dict[str, Page] = {}
    owners: dict[str, str] = {}
    titles = {relative: page_title(relative, text) for relative, text in tree.markdown.items()}

    def add(path: str, page: Page, origin: str) -> None:
        if path in owners:
            raise CollisionError(f"Wiki-Pfad {path} doppelt vergeben: {owners[path]} und {origin}")
        owners[path] = origin
        pages[path] = page

    for relative, text in sorted(tree.markdown.items()):
        add(
            wiki_path(config, relative),
            Page(
                title=titles[relative],
                content=rewrite_links(config, tree, relative, text),
                description=f"Quelle: {config.owner}/{config.repo}/{relative}",
            ),
            relative,
        )
    for directory in sorted(tree.directories):
        if has_directory_page(tree, directory):
            continue
        add(
            directory_path(config, directory),
            Page(
                title=directory.rpartition("/")[2] or config.repo,
                content=index_content(config, tree, directory, titles),
                description="Automatisch erzeugte Übersicht",
            ),
            f"Übersicht {directory or '/'}",
        )
    return pages
