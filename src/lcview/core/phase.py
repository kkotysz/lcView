"""Phase folding and smoothing helpers."""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from .lightcurve import LightCurve


@dataclass(frozen=True)
class FoldedLightCurve:
    phase: np.ndarray
    flux: np.ndarray
    error: np.ndarray


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
