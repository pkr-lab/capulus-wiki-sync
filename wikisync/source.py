import fnmatch
import io
import posixpath
import tarfile
import urllib.request
from dataclasses import dataclass, field

MAX_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class Tree:
    markdown: dict[str, str] = field(default_factory=dict)
    others: frozenset[str] = frozenset()
    directories: frozenset[str] = frozenset()

    @classmethod
    def of(cls, markdown: dict[str, str], others: frozenset[str] | set[str] = frozenset()) -> "Tree":
        found: set[str] = set()
        for relative in markdown:
            directory = relative.rpartition("/")[0]
            while True:
                found.add(directory)
                if not directory:
                    break
                directory = directory.rpartition("/")[0]
        return cls(markdown=markdown, others=frozenset(others), directories=frozenset(found))


def tarball_url(owner: str, repo: str, branch: str) -> str:
    return f"https://api.github.com/repos/{owner}/{repo}/tarball/{branch}"


def fetch_tarball(owner: str, repo: str, branch: str, token: str) -> bytes:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(tarball_url(owner, repo, branch), headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Tarball ist größer als erlaubt")
    return data


def excluded(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def read_tree(data: bytes, exclude: tuple[str, ...]) -> Tree:
    markdown: dict[str, str] = {}
    others: set[str] = set()
    total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
        for member in archive:
            if not member.isfile():
                continue
            _, _, relative = member.name.partition("/")
            relative = posixpath.normpath(relative)
            if not relative or relative.startswith(("/", "..")) or relative.startswith(".git/"):
                continue
            total += member.size
            if total > MAX_BYTES:
                raise ValueError("Archiv ist größer als erlaubt")
            if excluded(relative, exclude):
                continue
            if relative.endswith(".md"):
                extracted = archive.extractfile(member)
                if extracted is not None:
                    markdown[relative] = extracted.read().decode("utf-8")
            else:
                others.add(relative)
    return Tree.of(markdown, others)
