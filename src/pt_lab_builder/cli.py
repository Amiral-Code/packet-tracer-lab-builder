"""The public `ptlab` command."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from . import __version__, labgen, library
from .native import build_codec
from .paths import activity_base_path, codec_path, find_packet_tracer, library_dir, user_data_dir


def doctor() -> int:
    checks = [
        ("Python", f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}", sys.version_info >= (3, 11)),
        ("data directory", str(user_data_dir()), True),
        ("codec", str(codec_path(required=False) or "missing"), codec_path(required=False) is not None),
        ("device index", str(library_dir() / "devices" / "index.json"), (library_dir() / "devices" / "index.json").is_file()),
        ("topology base", str(library_dir() / "base.xml"), (library_dir() / "base.xml").is_file()),
        ("activity base", str(activity_base_path()), activity_base_path().is_file()),
        ("Packet Tracer", str(find_packet_tracer() or "not auto-detected"), find_packet_tracer() is not None),
    ]
    for label, value, ok in checks:
        print(f"{'ok' if ok else 'MISSING':7} {label:16} {value}")
    required = checks[0][2] and all(item[2] for item in checks[2:6])
    if not required:
        print("\nRun `ptlab init --build-codec --source PATH` with a folder containing your own .pkt/.pka files.")
    return 0 if required else 1


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ptlab", description="Build native Packet Tracer activities from TOML specs")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="build the local codec and device/activity template library")
    init.add_argument("--source", action="append", default=[], metavar="PATH",
                      help="folder containing legally obtained .pkt/.pka files; repeatable")
    init.add_argument("--build-codec", action="store_true", help="compile ptcrypt for this computer")
    build = sub.add_parser("build", help="build a .pka and answer guide")
    build.add_argument("spec", type=Path)
    build.add_argument("--output-dir", type=Path)
    build.add_argument("--open", action="store_true", dest="open_after")
    check = sub.add_parser("check", help="grade a student's saved .pka")
    check.add_argument("spec", type=Path)
    check.add_argument("activity", type=Path)
    sub.add_parser("doctor", help="show whether the local installation is ready")
    sub.add_parser("models", help="list locally available Packet Tracer device model keys")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "doctor":
        return doctor()
    if args.command == "init":
        if args.build_codec:
            print(f"built codec: {build_codec()}")
        if args.source:
            library.build([Path(source).expanduser().resolve() for source in args.source])
        if not args.build_codec and not args.source:
            raise SystemExit("ptlab init: pass --build-codec and/or at least one --source PATH")
        return doctor()
    if args.command == "build":
        labgen.build(str(args.spec), args.open_after, args.output_dir)
        return 0
    if args.command == "check":
        return labgen.check(str(args.spec), str(args.activity))
    if args.command == "models":
        return library.list_models()
    raise AssertionError(args.command)
