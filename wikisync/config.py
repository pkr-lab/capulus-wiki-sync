import os
from collections.abc import Mapping
from dataclasses import dataclass


class ConfigError(Exception):
    pass


def _split(value: str) -> tuple[str, ...]:
    return tuple(item.strip().strip("/") for item in value.split(",") if item.strip())


def _flag(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


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

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Config":
        env = os.environ if env is None else env
        missing = [name for name in ("WIKIJS_API_URL", "WIKIJS_API_TOKEN") if not env.get(name)]
        if missing:
            raise ConfigError("Pflichtvariablen fehlen: " + ", ".join(missing))
        prefix = env.get("WIKIJS_PATH_PREFIX", "docs").strip("/")
        if not prefix:
            raise ConfigError("WIKIJS_PATH_PREFIX darf nicht leer sein")
        try:
            min_pages = int(env.get("MIN_PAGES", "20"))
        except ValueError as error:
            raise ConfigError("MIN_PAGES muss eine Zahl sein") from error
        return cls(
            owner=env.get("GITHUB_OWNER", "pkr-lab"),
            repo=env.get("GITHUB_REPO", "pkr-lab-docs"),
            branch=env.get("GITHUB_BRANCH", "main"),
            github_token=env.get("GITHUB_TOKEN", ""),
            api_url=env["WIKIJS_API_URL"].rstrip("/"),
            api_token=env["WIKIJS_API_TOKEN"],
            locale=env.get("WIKIJS_LOCALE", "en"),
            prefix=prefix,
            exclude=_split(env.get("EXCLUDE", ".github/**,scripts/**,CLAUDE.md,LICENSE,CHANGELOG.md,capulus-core/archiv/**")),
            legacy_prefixes=_split(env.get("WIKIJS_LEGACY_PREFIXES", "")),
            dry_run=_flag(env.get("DRY_RUN", "false")),
            min_pages=min_pages,
        )
