"""Phase folding and smoothing helpers."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable
import numpy as np

from .lightcurve import LightCurve


@dataclass(frozen=True)
class FoldedLightCurve:
    phase: np.ndarray
    flux: np.ndarray
    error: np.ndarray


@dataclass(frozen=True)
class PhaseSeriesFit:
    phase: np.ndarray
    flux: np.ndarray
    harmonics: tuple[int, ...]
    coefficients: np.ndarray


def fold_light_curve(
    light_curve: LightCurve,
    period: float,
    *,
    repeats: int = 1,
    shift_fraction: float = 0.0,
) -> FoldedLightCurve:
    if period <= 0:
        raise ValueError("period must be positive")
    repeats = max(1, int(repeats))
    base_phase = np.mod(light_curve.time / period + float(shift_fraction), 1.0)
    phase = np.tile(base_phase, repeats) + np.repeat(np.arange(repeats), len(base_phase))
    flux = np.tile(light_curve.flux, repeats)
    error = np.tile(light_curve.error, repeats)
    order = np.argsort(phase)
    return FoldedLightCurve(phase[order], flux[order], error[order])


def boxcar_smooth(flux: np.ndarray, window_len: int, window: str = "flat") -> np.ndarray:
    values = np.asarray(flux, dtype=float)
    if values.ndim != 1:
        raise ValueError("smooth only accepts 1 dimension arrays")
    if values.size == 0:
        return values.copy()
    window_len = min(max(1, int(round(window_len))), values.size)
    if window_len < 3:
        return values.copy()
    if window not in ["flat", "hanning", "hamming", "bartlett", "blackman"]:
        raise ValueError("Window is one of 'flat', 'hanning', 'hamming', 'bartlett', 'blackman'")

    reflected = np.r_[values[window_len - 1 : 0 : -1], values, values[-2 : -window_len - 1 : -1]]
    weights = np.ones(window_len, dtype=float) if window == "flat" else getattr(np, window)(window_len)
    smoothed = np.convolve(weights / weights.sum(), reflected, mode="valid")
    half = int(window_len / 2)
    if window_len % 2:
        return smoothed[half:-half]
    return smoothed[half : -half + 1]


def _series_design(phase: np.ndarray, harmonics: tuple[int, ...]) -> np.ndarray:
    columns = [np.ones_like(phase, dtype=float)]
    for harmonic in harmonics:
        angle = 2.0 * np.pi * harmonic * phase
        columns.extend([np.sin(angle), np.cos(angle)])
    return np.column_stack(columns)


def evaluate_sincos_series(phase: np.ndarray, harmonics: Iterable[int], coefficients: np.ndarray) -> np.ndarray:
    unique_harmonics = tuple(sorted({int(value) for value in harmonics if int(value) > 0}))
    return _series_design(np.asarray(phase, dtype=float), unique_harmonics) @ np.asarray(coefficients, dtype=float)


def fit_sincos_series(
    folded: FoldedLightCurve,
    harmonics: Iterable[int],
    *,
    samples_per_cycle: int = 400,
) -> PhaseSeriesFit | None:
    unique_harmonics = tuple(sorted({int(value) for value in harmonics if int(value) > 0}))
    if not unique_harmonics or folded.phase.size == 0:
        return None

    phase = np.asarray(folded.phase, dtype=float)
    flux = np.asarray(folded.flux, dtype=float)
    error = np.asarray(folded.error, dtype=float)
    valid = np.isfinite(phase) & np.isfinite(flux) & np.isfinite(error)
    if np.count_nonzero(valid) < 1 + 2 * len(unique_harmonics):
        return None

    phase = phase[valid]
    flux = flux[valid]
    error = error[valid]
    design = _series_design(phase, unique_harmonics)
    weights = 1.0 / np.clip(error, 1e-12, None)
    coefficients, *_ = np.linalg.lstsq(design * weights[:, None], flux * weights, rcond=None)

    max_phase = float(np.max(phase)) if phase.size else 1.0
    repeats = max(1, int(np.floor(max_phase)) + 1)
    samples = max(120, repeats * int(samples_per_cycle))
    grid = np.linspace(0.0, float(repeats), samples, endpoint=True)
    fitted_flux = _series_design(grid, unique_harmonics) @ coefficients
    return PhaseSeriesFit(grid, fitted_flux, unique_harmonics, coefficients)
