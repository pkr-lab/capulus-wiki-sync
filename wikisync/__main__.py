import sys

from .config import Config, ConfigError
from .sync import run


def main() -> int:
    try:
        config = Config.from_env()
    except ConfigError as error:
        print(f"[FATAL] {error}", file=sys.stderr)
        return 2
    return run(config)


if __name__ == "__main__":
    sys.exit(main())
