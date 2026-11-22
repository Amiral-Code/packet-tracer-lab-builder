"""Build the small Packet Tracer XML codec on the current platform."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

from .paths import PACKAGE_DIR, user_data_dir


def build_codec(output: Path | None = None) -> Path:
    output = output or user_data_dir() / "bin" / ("ptcrypt.exe" if os.name == "nt" else "ptcrypt")
    output.parent.mkdir(parents=True, exist_ok=True)
    source = PACKAGE_DIR / "ptcrypt.cpp"
    cxx = os.environ.get("CXX") or next((x for x in ("g++", "clang++", "c++") if shutil.which(x)), None)
    if not cxx:
        raise RuntimeError("no C++ compiler found; install g++/clang++ or set CXX")
    command = [cxx, "-std=c++17", "-O2", str(source), "-o", str(output)]
    include_flags: list[str] = []
    library_flags: list[str] = []
    for variable in ("CRYPTOPP_ROOT", "ZLIB_ROOT"):
        if root := os.environ.get(variable):
            include_flags += ["-I", str(Path(root) / "include")]
            library_flags += ["-L", str(Path(root) / "lib")]
    if sys.platform == "darwin":
        for root in (Path("/opt/homebrew/opt/cryptopp"), Path("/usr/local/opt/cryptopp")):
            if root.exists():
                include_flags += ["-I", str(root / "include")]
                library_flags += ["-L", str(root / "lib")]
                break
    command[1:1] = include_flags
    command += library_flags + ["-lcryptopp", "-lz"]
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(
            "codec build failed; install Crypto++ and zlib development files\n"
            f"command: {' '.join(command)}\n{result.stderr.strip()}"
        )
    if os.name != "nt":
        output.chmod(0o755)
    return output
