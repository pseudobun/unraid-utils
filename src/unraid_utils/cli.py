"""Command-line entry point.

Note the asymmetry: `--execute` is a global flag and dry-run is the default, so
the only way to change the filesystem is to say so explicitly. Read-only
commands ignore it entirely.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import logging_setup
from .context import DEFAULT_ALLOWED_ROOTS, OutsideAllowedRoot, RunContext
from .manifest import DEFAULT_STATE_DIR
from .prompt import Aborted

DEFAULT_SHOWS = Path("/mnt/user/plex/shows")
DEFAULT_DOWNLOADS = Path("/mnt/user/plex/downloads")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="unraid-utils",
        description="Media tools for Unraid, with dry-run by default.")
    parser.add_argument("--execute", action="store_true",
                        help="actually make changes (default: dry run)")
    parser.add_argument("--yes", action="store_true",
                        help="assume yes for confirmations (non-interactive)")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR,
                        help=f"logs and manifest (default: {DEFAULT_STATE_DIR})")
    parser.add_argument("--log-file", type=Path, default=None)

    sub = parser.add_subparsers(dest="command", required=True)

    p_audit = sub.add_parser("audit", help="read-only inspection; changes nothing")
    audit_sub = p_audit.add_subparsers(dest="audit_command", required=True)
    p_links = audit_sub.add_parser(
        "links", help="hardlink census — how much of the library is a sole copy")
    p_links.add_argument("roots", nargs="*", type=Path,
                         default=[DEFAULT_SHOWS, DEFAULT_DOWNLOADS])
    p_parse = audit_sub.add_parser("parse", help="what the parser cannot place")
    p_parse.add_argument("roots", nargs="*", type=Path, default=[DEFAULT_SHOWS])
    audit_sub.add_parser("topology", help="storage branches behind /mnt/user")

    p_link = sub.add_parser(
        "hardlink", help="link a downloaded release into the show library")
    p_link.add_argument("source", type=Path, help="downloaded release directory")
    p_link.add_argument("dest", type=Path, help="show directory in the library")
    p_link.add_argument("--no-subtitles", action="store_true",
                        help="link video only")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    log = logging_setup.setup(args.verbose, args.quiet, args.state_dir,
                              args.log_file)

    # Refuse to run at all if the dead parser is shadowing the maintained one.
    from .media import assert_correct_parser
    try:
        assert_correct_parser()
    except RuntimeError as exc:
        log.error("%s", exc)
        return 2

    ctx = RunContext(dry_run=not args.execute, assume_yes=args.yes,
                     state_dir=args.state_dir, allowed_roots=DEFAULT_ALLOWED_ROOTS,
                     log=log)

    try:
        if args.command == "audit":
            from .commands import audit
            if args.audit_command == "links":
                return audit.links(ctx, args.roots)
            if args.audit_command == "parse":
                return audit.parse(ctx, args.roots)
            return audit.topology(ctx)

        if args.command == "hardlink":
            from .commands import hardlink
            return hardlink.run(ctx, args.source, args.dest,
                                include_subtitles=not args.no_subtitles)
    except Aborted as exc:
        log.warning("aborted: %s", exc)
        return 130
    except OutsideAllowedRoot as exc:
        log.error("%s", exc)
        return 2
    except KeyboardInterrupt:
        log.warning("interrupted")
        return 130

    return 2


if __name__ == "__main__":
    sys.exit(main())
