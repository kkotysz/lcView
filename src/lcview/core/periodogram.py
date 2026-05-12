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
    noise_level: float | None = None

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
                snr = float(values[4])
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
                        "snr": snr if np.isfinite(snr) and snr > 0 else None,
                    }
                )
    return rows


def _median_positive(values: np.ndarray) -> float | None:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite) & (finite > 0)]
    if finite.size == 0:
        return None
    return float(np.median(finite))


def _mean_positive(values: np.ndarray) -> float | None:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite) & (finite > 0)]
    if finite.size == 0:
        return None
    return float(np.mean(finite))


def _noise_from_peaks(peaks: list[dict]) -> float | None:
    ratios = []
    for peak in peaks:
        amplitude = peak.get("amplitude")
        snr = peak.get("snr")
        try:
            amplitude_value = float(amplitude)
            snr_value = float(snr)
        except (TypeError, ValueError):
            continue
        if np.isfinite(amplitude_value) and np.isfinite(snr_value) and amplitude_value > 0 and snr_value > 0:
            ratios.append(amplitude_value / snr_value)
    return _median_positive(np.asarray(ratios, dtype=float))


def _local_peaks(frequency: np.ndarray, amplitude: np.ndarray, limit: int = 50) -> list[dict]:
    if len(frequency) < 3:
        return []
    indexes = np.where((amplitude[1:-1] >= amplitude[:-2]) & (amplitude[1:-1] >= amplitude[2:]))[0] + 1
    if indexes.size == 0:
        indexes = np.array([int(np.argmax(amplitude))])
    ranked = indexes[np.argsort(amplitude[indexes])[::-1]][:limit]
    noise = _median_positive(amplitude) or 1.0
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
DFT_BACKEND_FWPEAKS = "fwpeaks"
DFT_BACKEND_PYTHON = "python"
DFT_BACKENDS = {DFT_BACKEND_FWPEAKS, DFT_BACKEND_PYTHON}
MAX_PYTHON_DFT_CHUNK_ELEMENTS = 5_000_000


def _report(progress_callback: ProgressCallback | None, percent: int, message: str) -> None:
    if progress_callback is not None:
        progress_callback(max(0, min(100, int(percent))), message)


def _python_chunk_size(point_count: int) -> int:
    if point_count <= 0:
        return 1
    return max(8, min(256, MAX_PYTHON_DFT_CHUNK_ELEMENTS // point_count))


def _single_frequency_amplitude(
    time_values: np.ndarray,
    target: np.ndarray,
    sqrt_weights: np.ndarray,
    frequency: float,
) -> float:
    angle = 2.0 * np.pi * frequency * time_values
    design = np.column_stack([np.sin(angle), np.cos(angle), np.ones_like(angle)])
    coef, *_ = np.linalg.lstsq(design * sqrt_weights[:, None], target * sqrt_weights, rcond=None)
    return 2.0 * math.sqrt(coef[0] ** 2 + coef[1] ** 2)


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
    sqrt_weights = np.sqrt(weights)
    weighted_y = weights * y
    weight_sum = float(np.sum(weights))
    weighted_y_sum = float(np.sum(weighted_y))
    amplitudes = np.empty_like(frequencies)
    _report(progress_callback, 0, "Calculating DFT")
    chunk_size = _python_chunk_size(len(light_curve.time))
    last_percent = 0
    for chunk_start in range(0, len(frequencies), chunk_size):
        chunk_end = min(len(frequencies), chunk_start + chunk_size)
        chunk = frequencies[chunk_start:chunk_end]
        zero_mask = np.isclose(chunk, 0.0, atol=1e-15)
        if np.any(~zero_mask):
            local_indexes = np.flatnonzero(~zero_mask)
            active_frequencies = chunk[local_indexes]
            angle = 2.0 * np.pi * active_frequencies[:, None] * light_curve.time[None, :]
            sin_values = np.sin(angle)
            cos_values = np.cos(angle)

            sin_sin = np.einsum("ij,j->i", sin_values * sin_values, weights, optimize=True)
            cos_cos = np.einsum("ij,j->i", cos_values * cos_values, weights, optimize=True)
            sin_cos = np.einsum("ij,j->i", sin_values * cos_values, weights, optimize=True)
            sin_sum = sin_values @ weights
            cos_sum = cos_values @ weights
            sin_y = sin_values @ weighted_y
            cos_y = cos_values @ weighted_y

            normal = np.empty((len(active_frequencies), 3, 3), dtype=float)
            normal[:, 0, 0] = sin_sin
            normal[:, 0, 1] = sin_cos
            normal[:, 0, 2] = sin_sum
            normal[:, 1, 0] = sin_cos
            normal[:, 1, 1] = cos_cos
            normal[:, 1, 2] = cos_sum
            normal[:, 2, 0] = sin_sum
            normal[:, 2, 1] = cos_sum
            normal[:, 2, 2] = weight_sum
            rhs = np.column_stack(
                [
                    sin_y,
                    cos_y,
                    np.full(len(active_frequencies), weighted_y_sum, dtype=float),
                ]
            )
            try:
                coef = np.linalg.solve(normal, rhs[..., None])[..., 0]
                amplitudes[chunk_start + local_indexes] = 2.0 * np.hypot(coef[:, 0], coef[:, 1])
            except np.linalg.LinAlgError:
                for local_index, frequency in zip(local_indexes, active_frequencies):
                    amplitudes[chunk_start + local_index] = _single_frequency_amplitude(
                        light_curve.time,
                        y,
                        sqrt_weights,
                        float(frequency),
                    )
        for local_index in np.flatnonzero(zero_mask):
            amplitudes[chunk_start + local_index] = _single_frequency_amplitude(
                light_curve.time,
                y,
                sqrt_weights,
                float(chunk[local_index]),
            )
        percent = min(99, int(chunk_end / len(frequencies) * 99))
        if percent > last_percent or chunk_end == len(frequencies):
            last_percent = percent
            _report(progress_callback, percent, "Calculating DFT")
    _report(progress_callback, 99, "DFT output ready")
    noise = _median_positive(amplitudes)
    return PeriodogramResult(
        frequencies,
        amplitudes,
        _local_peaks(frequencies, amplitudes),
        used_native=False,
        noise_level=noise,
    )


def compute_periodogram(
    light_curve: LightCurve,
    start: float,
    end: float,
    *,
    precision: float = 10.0,
    step: float | None = None,
    prefer_native: bool | None = None,
    backend: str = DFT_BACKEND_FWPEAKS,
    work_dir: Path | None = None,
    progress_callback: ProgressCallback | None = None,
) -> PeriodogramResult:
    if start >= end:
        raise ValueError("start frequency must be lower than end frequency")
    centered = light_curve.centered_time()
    step = step or dft_step(precision, centered.baseline)
    if step <= 0:
        raise ValueError("frequency step must be positive")

    if prefer_native is not None:
        backend = DFT_BACKEND_FWPEAKS if prefer_native else DFT_BACKEND_PYTHON
    if backend not in DFT_BACKENDS:
        raise ValueError(f"unsupported DFT backend: {backend}")
    if backend == DFT_BACKEND_PYTHON:
        return _python_periodogram(centered, start, end, step, progress_callback=progress_callback)

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
                        percent = min(95, int(line_count / expected_steps * 95))
                        _report(progress_callback, percent, f"fwpeaks {line_count}/{expected_steps}")
                    except OSError:
                        pass
                time.sleep(0.08)
            stdout, stderr = process.communicate()
            if process.returncode != 0:
                detail = stderr.strip() or stdout.strip() or f"exit code {process.returncode}"
                raise RuntimeError(f"fwpeaks failed: {detail}")
            trf = tmp_path / "lc.trf"
            max_file = tmp_path / "lc.max"
            _report(progress_callback, 98, "Reading fwpeaks output")
            freq, amp = _parse_trf(trf)
            peaks = _parse_max(max_file, start, end) or _local_peaks(freq, amp)
            noise = _noise_from_peaks(peaks) or _mean_positive(amp)
            _report(progress_callback, 99, "DFT output ready")
            return PeriodogramResult(freq, amp, peaks, used_native=True, noise_level=noise)
    except (NativeBuildError, subprocess.CalledProcessError, OSError, ValueError, RuntimeError) as exc:
        try:
            message = str(exc)
        except Exception:
            message = repr(exc)
        raise RuntimeError(f"fwpeaks DFT failed: {message}. Select the Python DFT backend explicitly to use the slower fallback.") from exc


def periodogram_from_file(path: Path, start: float, end: float, precision: float = 10.0) -> PeriodogramResult:
    return compute_periodogram(from_array(np.loadtxt(path, usecols=(0, 1, 2))), start, end, precision=precision)
