"""Build and locate the bundled C/Fortran numerical tools."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import subprocess


class NativeBuildError(RuntimeError):
    """Raised when a bundled native executable cannot be built."""


@dataclass(frozen=True)
class NativeTools:
    fwpeaks: Path
    hars_sin: Path
    hars_ite: Path
    smart_uf: Path
    uf2: Path

    def as_env_path(self) -> str:
        return str(self.fwpeaks.parent)


PACKAGE_NATIVE = Path(__file__).resolve().parent

SOURCES = {
    "fwpeaks": "fwpeaks.c",
    "hars-sin": "hars-sin.f",
    "hars-ite": "hars-ite.f",
    "smart-uf-fina-smars": "smart-uf-fina-smars.f",
    "uf2": "uf2.f",
}


def default_build_dir() -> Path:
    configured = os.environ.get("LCVIEW_NATIVE_BUILD")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.home() / ".cache" / "lcview" / "native"


def _needs_rebuild(source: Path, output: Path) -> bool:
    return not output.exists() or output.stat().st_mtime < source.stat().st_mtime


def _run(cmd: list[str]) -> None:
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError as exc:
        raise NativeBuildError(f"Compiler not found while running: {' '.join(cmd)}") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip()
        raise NativeBuildError(f"Native build failed for {' '.join(cmd)}\n{detail}") from exc


def build_native(build_dir: Path | None = None, force: bool = False) -> NativeTools:
    build_dir = (build_dir or default_build_dir()).resolve()
    build_dir.mkdir(parents=True, exist_ok=True)

    cc = os.environ.get("CC") or shutil.which("cc")
    fc = os.environ.get("FC") or shutil.which("gfortran")
    if not cc:
        raise NativeBuildError("No C compiler found. Install `cc` or set CC.")
    if not fc:
        raise NativeBuildError("No Fortran compiler found. Install `gfortran` or set FC.")

    for exe_name, source_name in SOURCES.items():
        source = PACKAGE_NATIVE / source_name
        output = build_dir / exe_name
        if not source.exists():
            raise NativeBuildError(f"Missing native source: {source}")
        if force or _needs_rebuild(source, output):
            if source.suffix == ".c":
                _run([cc, "-O3", "-w", "-o", str(output), str(source), "-lm", "-ffast-math"])
            else:
                _run([fc, "-std=legacy", "-O2", "-o", str(output), str(source)])
            output.chmod(0o755)

    return NativeTools(
        fwpeaks=build_dir / "fwpeaks",
        hars_sin=build_dir / "hars-sin",
        hars_ite=build_dir / "hars-ite",
        smart_uf=build_dir / "smart-uf-fina-smars",
        uf2=build_dir / "uf2",
    )


def ensure_native(build_dir: Path | None = None) -> NativeTools:
    return build_native(build_dir=build_dir, force=False)


def main() -> int:
    tools = build_native()
    print(f"Built lcView native tools in {tools.fwpeaks.parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
