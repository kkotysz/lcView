"""Detrending algorithms used by the GUI and batch prewhitening."""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from scipy.interpolate import Akima1DInterpolator

from .lightcurve import LightCurve


@dataclass(frozen=True)
class DetrendResult:
    corrected: LightCurve
    trend_x: np.ndarray
    trend_y: np.ndarray
    median_x: np.ndarray
    median_y: np.ndarray


def _bin_edges(x: np.ndarray, bin_value: float, by_points: bool) -> np.ndarray:
    if by_points:
        n = max(2, int(round(bin_value)))
        edges = np.arange(0, len(x), n, dtype=int)
        if edges[-1] != len(x) - 1:
            edges = np.append(edges, len(x) - 1)
        return edges
    if bin_value <= 0:
        raise ValueError("bin width must be positive")
    phase = (x - x[0]) % bin_value
    minima = np.r_[True, phase[1:] < phase[:-1]] & np.r_[phase[:-1] < phase[1:], True]
    edges = np.where(minima)[0]
    if len(edges) < 2:
        edges = np.array([0, len(x) - 1])
    elif edges[-1] != len(x) - 1:
        edges = np.append(edges, len(x) - 1)
    return edges


def akima_detrend(
    light_curve: LightCurve,
    bin_value: float,
    *,
    by_points: bool = False,
    period: float | None = None,
) -> DetrendResult:
    x = light_curve.time % period / period if period else light_curve.time
    order = np.argsort(x)
    x_sorted = np.asarray(x[order], dtype=float)
    flux_sorted = light_curve.flux[order]

    edges = _bin_edges(x_sorted, bin_value, by_points)
    med_x: list[float] = []
    med_y: list[float] = []
    for start, end in zip(edges[:-1], edges[1:]):
        if end <= start:
            continue
        med_x.append(float(np.median(x_sorted[start:end])))
        med_y.append(float(np.median(flux_sorted[start:end])))
    if len(med_x) < 2:
        raise ValueError("not enough bins for Akima detrending")
    median_x = np.asarray([x_sorted[0], *med_x, x_sorted[-1]], dtype=float)
    median_y = np.asarray([med_y[0], *med_y, med_y[-1]], dtype=float)
    interpolator = Akima1DInterpolator(median_x, median_y)

    trend = interpolator(x)
    corrected = light_curve.with_flux(light_curve.flux - trend)
    trend_x = np.linspace(float(np.min(x_sorted)), float(np.max(x_sorted)), 1000)
    trend_y = interpolator(trend_x)
    return DetrendResult(corrected=corrected, trend_x=trend_x, trend_y=trend_y, median_x=median_x, median_y=median_y)
