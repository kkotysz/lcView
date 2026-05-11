"""Amplitude spectrum calculation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import math
import shutil
import subprocess
import tempfile
import time
import numpy as np

from lcview.native.build import NativeBuildError, ensure_native
from .lightcurve import LightCurve, from_array


@dataclass(frozen=True)
class PeriodogramResult:
    frequency: np.ndarray
    amplitude: np.ndarray
    peaks: list[dict]
    used_native: bool

    @property
    def best_frequency(self) -> float:
        valid = self.frequency > 0.3
        if np.any(valid):
            indexes = np.where(valid)[0]
            idx = indexes[np.argmax(self.amplitude[valid])]
        else:
            idx = int(np.argmax(self.amplitude))
        return float(self.frequency[idx])


def dft_step(precision: float, baseline: float) -> float:
    if precision <= 0:
        raise ValueError("precision must be positive")
    if baseline <= 0:
        raise ValueError("baseline must be positive")
    return 1.0 / precision / baseline


def _parse_trf(path: Path) -> tuple[np.ndarray, np.ndarray]:
    data = np.loadtxt(path, comments="%")
    if data.ndim == 1:
        data = data.reshape(1, -1)
    return data[:, 0], data[:, 1]


def _parse_max(path: Path, start: float | None = None, end: float | None = None) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open() as handle:
        for line in handle:
            if not line.strip() or line.lstrip().startswith("%"):
                continue
            values = np.fromstring(line, sep=" ")
            if values.size >= 5:
                frequency = float(values[1])
                amplitude = float(values[3])
                if not np.isfinite(frequency) or not np.isfinite(amplitude) or amplitude <= 0:
                    continue
                if start is not None and frequency < start:
                    continue
                if end is not None and frequency > end:
                    continue
                rows.append(
                    {
                        "index": int(values[0]),
                        "frequency": frequency,
                        "period": float(values[2]),
                        "amplitude": amplitude,
                        "snr": float(values[4]),
                    }
                )
    return rows


def _local_peaks(frequency: np.ndarray, amplitude: np.ndarray, limit: int = 50) -> list[dict]:
    if len(frequency) < 3:
        return []
    indexes = np.where((amplitude[1:-1] >= amplitude[:-2]) & (amplitude[1:-1] >= amplitude[2:]))[0] + 1
    if indexes.size == 0:
        indexes = np.array([int(np.argmax(amplitude))])
    ranked = indexes[np.argsort(amplitude[indexes])[::-1]][:limit]
    noise = float(np.median(amplitude)) or 1.0
    return [
        {
            "index": int(i),
            "frequency": float(frequency[i]),
            "period": float(1.0 / frequency[i]) if frequency[i] else math.inf,
            "amplitude": float(amplitude[i]),
            "snr": float(amplitude[i] / noise),
        }
        for i in ranked
    ]


ProgressCallback = Callable[[int, str], None]


def _report(progress_callback: ProgressCallback | None, percent: int, message: str) -> None:
    if progress_callback is not None:
        progress_callback(max(0, min(100, int(percent))), message)


def _python_periodogram(
    light_curve: LightCurve,
    start: float,
    end: float,
    step: float,
    progress_callback: ProgressCallback | None = None,
) -> PeriodogramResult:
    frequencies = np.arange(start, end + 0.5 * step, step, dtype=float)
    y = light_curve.flux - np.average(light_curve.flux)
    weights = 1.0 / np.clip(light_curve.error, 1e-12, None) ** 2
    amplitudes = np.empty_like(frequencies)
    _report(progress_callback, 0, "Calculating DFT")
    stride = max(1, len(frequencies) // 100)
    for idx, freq in enumerate(frequencies):
        angle = 2.0 * np.pi * freq * light_curve.time
        design = np.column_stack([np.sin(angle), np.cos(angle), np.ones_like(angle)])
        weighted = design * np.sqrt(weights[:, None])
        target = y * np.sqrt(weights)
        coef, *_ = np.linalg.lstsq(weighted, target, rcond=None)
        amplitudes[idx] = 2.0 * math.sqrt(coef[0] ** 2 + coef[1] ** 2)
        if idx % stride == 0 or idx == len(frequencies) - 1:
            _report(progress_callback, int((idx + 1) / len(frequencies) * 100), "Calculating DFT")
    _report(progress_callback, 100, "DFT ready")
    return PeriodogramResult(frequencies, amplitudes, _local_peaks(frequencies, amplitudes), used_native=False)


def compute_periodogram(
    light_curve: LightCurve,
    start: float,
    end: float,
    *,
    precision: float = 10.0,
    step: float | None = None,
    prefer_native: bool = True,
    work_dir: Path | None = None,
    progress_callback: ProgressCallback | None = None,
) -> PeriodogramResult:
    if start >= end:
        raise ValueError("start frequency must be lower than end frequency")
    centered = light_curve.centered_time()
    step = step or dft_step(precision, centered.baseline)
    if step <= 0:
        raise ValueError("frequency step must be positive")

    if prefer_native:
        try:
            tools = ensure_native()
            with tempfile.TemporaryDirectory(dir=work_dir) as tmp:
                tmp_path = Path(tmp)
                data_path = tmp_path / "lc.data"
                centered.save(data_path)
                expected_steps = max(1, int((end - start) / step) + 1)
                _report(progress_callback, 0, "Starting fwpeaks")
                process = subprocess.Popen(
                    [str(tools.fwpeaks), "-f", data_path.name, str(start), str(end), str(step)],
                    cwd=tmp_path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                trf = tmp_path / "lc.trf"
                while process.poll() is None:
                    if trf.exists():
                        try:
                            line_count = sum(1 for _ in trf.open())
                            percent = int(line_count / expected_steps * 95)
                            _report(progress_callback, percent, f"fwpeaks {line_count}/{expected_steps}")
                        except OSError:
                            pass
                    time.sleep(0.08)
                stdout, stderr = process.communicate()
                if process.returncode != 0:
                    raise subprocess.CalledProcessError(process.returncode, process.args, stdout, stderr)
                trf = tmp_path / "lc.trf"
                max_file = tmp_path / "lc.max"
                freq, amp = _parse_trf(trf)
                peaks = _parse_max(max_file, start, end) or _local_peaks(freq, amp)
                _report(progress_callback, 100, "DFT ready")
                return PeriodogramResult(freq, amp, peaks, used_native=True)
        except (NativeBuildError, subprocess.CalledProcessError, OSError, ValueError):
            pass

    return _python_periodogram(centered, start, end, step, progress_callback=progress_callback)


def periodogram_from_file(path: Path, start: float, end: float, precision: float = 10.0) -> PeriodogramResult:
    return compute_periodogram(from_array(np.loadtxt(path, usecols=(0, 1, 2))), start, end, precision=precision)
