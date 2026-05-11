"""Command-line entry points for lcView."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .core.prewhitening import PrewhiteningEngine
from .display import frequency_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Interactive lcView GUI")
    parser.add_argument("file", nargs="?", help="optional light-curve file to open")
    args = parser.parse_args(argv)

    from PySide6 import QtWidgets
    from .ui.main_window import MainWindow

    app = QtWidgets.QApplication(sys.argv[:1])
    window = MainWindow(args.file)
    window.show()
    return app.exec()


def prewhiten_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Batch lcView prewhitening")
    parser.add_argument("file", help="light-curve file")
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--end", type=float, default=80.0)
    parser.add_argument("--precision", type=float, default=10.0)
    parser.add_argument("--add", type=float, action="append", default=[], help="add independent frequency before fitting")
    parser.add_argument("--export", type=Path, default=None, help="directory for legacy freq/resid/ampl/periodogram output")
    args = parser.parse_args(argv)

    engine = PrewhiteningEngine.from_file(args.file)
    engine.state.settings.start_frequency = args.start
    engine.state.settings.end_frequency = args.end
    engine.state.settings.precision = args.precision
    for frequency in args.add:
        engine.add_independent(frequency)
    if args.add:
        engine.iterate_after_model_change()
    periodogram = engine.compute_periodogram()
    if args.export is not None:
        engine.export_legacy(args.export)
    print(f"best_frequency {frequency_text(periodogram.best_frequency)}")
    for idx, candidate in enumerate(engine.last_candidates[:10], start=1):
        print(
            f"{idx:2d} {frequency_text(candidate.frequency):>8s} {candidate.amplitude:12.6f} "
            f"{candidate.kind:12s} {candidate.label:20s} {candidate.resolved}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
