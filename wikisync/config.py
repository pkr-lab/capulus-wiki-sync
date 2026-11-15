import os
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_MIN_PAGES = 20
DEFAULT_RENDER_BATCH = 8
DEFAULT_EXCLUDE = ".github/**,scripts/**,CLAUDE.md,LICENSE,CHANGELOG.md,capulus-core/archiv/**"
REQUIRED = ("WIKIJS_API_URL", "WIKIJS_API_TOKEN")


class ConfigError(Exception):
    pass


def _split(value: str) -> tuple[str, ...]:
    return tuple(item.strip().strip("/") for item in value.split(",") if item.strip())


def _flag(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def _number(env: Mapping[str, str], name: str, default: int) -> int:
    try:
        return int(env.get(name, str(default)))
    except ValueError as error:
        raise ConfigError(f"{name} muss eine Zahl sein") from error


@dataclass(frozen=True)
class Config:
    owner: str
    repo: str
    branch: str
    github_token: str
    api_url: str
    api_token: str
    locale: str
    prefix: str
    exclude: tuple[str, ...]
    legacy_prefixes: tuple[str, ...]
    dry_run: bool
    min_pages: int
    site_id: str = ""
    render_batch: int = DEFAULT_RENDER_BATCH

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Config":
        env = os.environ if env is None else env
        missing = [name for name in REQUIRED if not env.get(name)]
        if missing:
            raise ConfigError("Pflichtvariablen fehlen: " + ", ".join(missing))
        prefix = env.get("WIKIJS_PATH_PREFIX", "docs").strip("/")
        if not prefix:
            raise ConfigError("WIKIJS_PATH_PREFIX darf nicht leer sein")
        min_pages = _number(env, "MIN_PAGES", DEFAULT_MIN_PAGES)
        render_batch = _number(env, "RENDER_BATCH", DEFAULT_RENDER_BATCH)
        if render_batch < 1:
            raise ConfigError("RENDER_BATCH muss mindestens 1 sein")
        return cls(
            owner=env.get("GITHUB_OWNER", "pkr-lab"),
            repo=env.get("GITHUB_REPO", "pkr-lab-docs"),
            branch=env.get("GITHUB_BRANCH", "main"),
            github_token=env.get("GITHUB_TOKEN", ""),
            api_url=env["WIKIJS_API_URL"].rstrip("/"),
            api_token=env["WIKIJS_API_TOKEN"],
            locale=env.get("WIKIJS_LOCALE", "en"),
            prefix=prefix,
            exclude=_split(env.get("EXCLUDE", DEFAULT_EXCLUDE)),
            legacy_prefixes=_split(env.get("WIKIJS_LEGACY_PREFIXES", "")),
            dry_run=_flag(env.get("DRY_RUN", "false")),
            min_pages=min_pages,
            site_id=env.get("WIKIJS_SITE_ID", "").strip(),
            render_batch=render_batch,
        )
