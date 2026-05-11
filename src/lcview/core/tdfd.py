"""Native time-dependent Fourier decomposition for lcView."""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from .frequency_model import FrequencyModel
from .lightcurve import LightCurve


@dataclass(frozen=True)
class TdfdBin:
    start_time: float
    end_time: float
    mid_time: float
    frequencies: np.ndarray
    amplitudes: np.ndarray
    phases: np.ndarray
    residual_std: float
    n_points: int


@dataclass(frozen=True)
class TdfdResult:
    bins: list[TdfdBin]
    residuals: LightCurve


def fit_fixed_frequencies(light_curve: LightCurve, frequencies: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if frequencies.size == 0:
        return np.array([]), np.array([]), light_curve.flux - np.mean(light_curve.flux)
    columns = [np.ones_like(light_curve.time)]
    for freq in frequencies:
        angle = 2.0 * np.pi * freq * light_curve.time
        columns.append(np.sin(angle))
        columns.append(np.cos(angle))
    design = np.column_stack(columns)
    weights = 1.0 / np.clip(light_curve.error, 1e-12, None)
    coef, *_ = np.linalg.lstsq(design * weights[:, None], light_curve.flux * weights, rcond=None)
    model_flux = design @ coef
    amplitudes = []
    phases = []
    for idx in range(len(frequencies)):
        sin_coef = coef[1 + 2 * idx]
        cos_coef = coef[2 + 2 * idx]
        amplitudes.append(float(np.hypot(sin_coef, cos_coef)))
        phases.append(float(np.arctan2(cos_coef, sin_coef)))
    return np.asarray(amplitudes), np.asarray(phases), light_curve.flux - model_flux


def run_tdfd(light_curve: LightCurve, model: FrequencyModel, bins: int = 20) -> TdfdResult:
    if bins < 2:
        raise ValueError("TDFD requires at least two bins")
    frequencies = np.array([row["frequency"] for row in model.rows() if row["enabled"]], dtype=float)
    edges = np.linspace(float(np.min(light_curve.time)), float(np.max(light_curve.time)), bins + 1)
    bin_results: list[TdfdBin] = []
    residual_time = []
    residual_flux = []
    residual_error = []

    for start, end in zip(edges[:-1], edges[1:]):
        mask = (light_curve.time >= start) & (light_curve.time <= end if end == edges[-1] else light_curve.time < end)
        if np.count_nonzero(mask) < max(3, 2 * len(frequencies) + 1):
            continue
        segment = light_curve.masked(mask)
        amplitudes, phases, residuals = fit_fixed_frequencies(segment, frequencies)
        residual_time.append(segment.time)
        residual_flux.append(residuals)
        residual_error.append(segment.error)
        bin_results.append(
            TdfdBin(
                start_time=float(start),
                end_time=float(end),
                mid_time=float((start + end) / 2.0),
                frequencies=frequencies.copy(),
                amplitudes=amplitudes,
                phases=phases,
                residual_std=float(np.std(residuals)),
                n_points=len(segment.time),
            )
        )

    if residual_time:
        residual_lc = LightCurve(
            np.concatenate(residual_time),
            np.concatenate(residual_flux),
            np.concatenate(residual_error),
            light_curve.path,
        ).sorted()
    else:
        residual_lc = light_curve.with_flux(light_curve.flux - np.mean(light_curve.flux))
    return TdfdResult(bins=bin_results, residuals=residual_lc)
