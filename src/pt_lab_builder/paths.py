"""Cross-platform paths and Packet Tracer launching."""

from __future__ import annotations

import glob
import os
from pathlib import Path
import shutil
import subprocess
import sys

APP_DIRNAME = "pt-lab-builder"
PACKAGE_DIR = Path(__file__).resolve().parent


def user_data_dir() -> Path:
    override = os.environ.get("PTLAB_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / APP_DIRNAME


def library_dir() -> Path:
    override = os.environ.get("PTLAB_LIBRARY_DIR")
    return Path(override).expanduser().resolve() if override else user_data_dir() / "library"


def work_dir() -> Path:
    override = os.environ.get("PTLAB_WORK_DIR")
    return Path(override).expanduser().resolve() if override else user_data_dir() / "work"


def activity_base_path() -> Path:
    override = os.environ.get("PTLAB_PKA_BASE")
    return Path(override).expanduser().resolve() if override else library_dir() / "pka-base.xml"


def codec_path(required: bool = True) -> Path | None:
    names = ["ptcrypt.exe"] if os.name == "nt" else ["ptcrypt"]
    candidates: list[Path] = []
    if os.environ.get("PTLAB_PTCRYPT"):
        candidates.append(Path(os.environ["PTLAB_PTCRYPT"]).expanduser())
    candidates.extend(user_data_dir() / "bin" / name for name in names)
    candidates.extend(PACKAGE_DIR / name for name in names)
    for name in names:
        if found := shutil.which(name):
            candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    if required:
        raise FileNotFoundError("ptcrypt is not installed; run `ptlab init --build-codec --source PATH`")
    return None


def find_packet_tracer() -> Path | None:
    override = os.environ.get("PTLAB_PACKET_TRACER")
    if override and Path(override).expanduser().exists():
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        roots = [os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.environ.get("LOCALAPPDATA")]
        patterns = ["Cisco Packet Tracer*\\bin\\PacketTracer.exe", "Cisco Packet Tracer*\\PacketTracer.exe"]
        for root in filter(None, roots):
            for pattern in patterns:
                hits = sorted(glob.glob(str(Path(root) / pattern)), reverse=True)
                if hits:
                    return Path(hits[0])
    elif sys.platform == "darwin":
        for candidate in (Path("/Applications/Cisco Packet Tracer.app"), Path.home() / "Applications/Cisco Packet Tracer.app"):
            if candidate.exists():
                return candidate
    else:
        for name in ("packettracer", "PacketTracer"):
            if found := shutil.which(name):
                return Path(found)
        for candidate in (
            Path("/usr/lib/packettracer/packettracer.AppImage"),
            Path("/opt/pt/packettracer"),
            Path("/opt/packettracer/packettracer"),
        ):
            if candidate.exists():
                return candidate
    return None


def open_packet_tracer(activity: str | os.PathLike[str]) -> None:
    activity = str(Path(activity).resolve())
    app = find_packet_tracer()
    if os.name == "nt":
        if app:
            subprocess.Popen([str(app), activity], close_fds=True)
        else:
            os.startfile(activity)  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        command = ["open", "-a", str(app or "Cisco Packet Tracer"), activity]
    elif app:
        command = [str(app), activity]
    elif shutil.which("xdg-open"):
        command = ["xdg-open", activity]
    else:
        raise FileNotFoundError("Packet Tracer was not found; set PTLAB_PACKET_TRACER to its executable")
    env = dict(os.environ, APPIMAGELAUNCHER_DISABLE="1")
    subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     stdin=subprocess.DEVNULL, start_new_session=True)
