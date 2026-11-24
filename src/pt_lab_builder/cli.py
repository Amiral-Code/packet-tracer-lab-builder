"""The public `ptlab` command."""

from __future__ import annotations

import argparse
import os
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
    build.add_argument("--force", action="store_true", help="build even if the spec check or self-check fails")
    build.add_argument("--password", default=os.environ.get("PTLAB_PASSWORD"),
                       help="lock the Activity Wizard with this password (default: $PTLAB_PASSWORD); keep it out of "
                            "the spec, which is meant to be shared")
    lint = sub.add_parser("lint", help="check a spec and prove its answer network against its grade statements")
    lint.add_argument("spec", type=Path)
    check = sub.add_parser("check", help="grade a student's saved .pka")
    check.add_argument("spec", type=Path)
    check.add_argument("activity", type=Path)
    verify = sub.add_parser("verify", help="compare a lab with the same activity after Packet Tracer opened and saved it")
    verify.add_argument("spec", type=Path)
    verify.add_argument("saved", type=Path, help="the built .pka, opened in Packet Tracer and saved (Ctrl+S)")
    verify.add_argument("--values", type=Path, metavar="BARE_SAVED",
                        help="also compare every item's value with Packet Tracer's own: a `ptlab bare` copy of the "
                             "built .pka, opened and saved in Packet Tracer")
    bare = sub.add_parser("bare", help="copy a built .pka without its assessment items (for verify --values)")
    bare.add_argument("built", type=Path)
    bare.add_argument("output", type=Path)
    lp = sub.add_parser("live-prepare", help="copy a built .pka with a script that solves and grades it inside "
                                             "Packet Tracer (open it with a harness that accepts the prompt)")
    lp.add_argument("spec", type=Path)
    lp.add_argument("built", type=Path)
    lp.add_argument("output", type=Path)
    lp.add_argument("result", type=Path, help="where the script writes its JSON report (absolute path)")
    lp.add_argument("--save", type=Path, help="also save the solved network here (absolute path)")
    lr = sub.add_parser("live-report", help="verdict from a live-prepare script's JSON report")
    lr.add_argument("spec", type=Path)
    lr.add_argument("result", type=Path)
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
        labgen.build(str(args.spec), args.open_after, args.output_dir, force=args.force, password=args.password)
        return 0
    if args.command == "lint":
        return 0 if labgen.verify(labgen.load_spec(str(args.spec))) else 1
    if args.command == "check":
        return labgen.check(str(args.spec), str(args.activity))
    if args.command == "verify":
        from . import validate
        issues, n = validate.verify_saved(labgen.load_spec(str(args.spec)), str(args.saved))
        if n:
            issues.report(f"verify (items kept {n['kept']}/{n['expected']}, connectivity tests {n['saved_tests']}/"
                          f"{n['tests']}, local checks on Packet Tracer's answer {n['local']}/{n['local_total']})")
        else:
            issues.report("verify")
        failed = bool(issues.errors)
        if args.values:
            issues, n = validate.verify_values(labgen.load_spec(str(args.spec)), str(args.values))
            issues.report(f"values (same as Packet Tracer's own: {n['same']}/{n['items']})")
            failed = failed or bool(issues.errors)
        return 1 if failed else 0
    if args.command == "live-prepare":
        from . import live
        spec = labgen.load_spec(str(args.spec))
        live.instrument(spec, str(args.built), str(args.output), args.result.resolve(),
                        args.save.resolve() if args.save else None)
        print(f"wrote {args.output}")
        return 0
    if args.command == "live-report":
        from . import live
        ok, lines = live.report(labgen.load_spec(str(args.spec)), str(args.result))
        print(f"live check: {'ok' if ok else 'FAILED'}")
        print("\n".join(lines))
        return 0 if ok else 1
    if args.command == "bare":
        from . import validate
        validate.strip_assessment(str(args.built), str(args.output))
        print(f"wrote {args.output}: open it in Packet Tracer, save, then ptlab verify SPEC SAVED --values {args.output}")
        return 0
    if args.command == "models":
        return library.list_models()
    raise AssertionError(args.command)
