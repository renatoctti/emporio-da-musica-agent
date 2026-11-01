"""Console entry point: `emporio` and `python -m emporio`."""

import sys

from emporio import cli


def main() -> None:
    # Windows consoles default to a legacy code page; the agent talks in Portuguese.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(cli.main())


if __name__ == "__main__":
    main()
