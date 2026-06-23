"""Frequency model reporting utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import math
import numpy as np

from .frequency_model import FrequencyModel
from .lightcurve import LightCurve


@dataclass(frozen=True)
class FrequencyReportRow:
    index: int
    enabled: bool
    kind: str
    label: str
    coefficients: tuple[int, ...]
    frequency: float
    frequency_error: float | None
    period: float | None
    period_error: float | None
    amplitude: float | None
    amplitude_error: float | None
    phase_cycles: float | None
    phase_error_cycles: float | None
    status: str


@dataclass
class FrequencyReport:
    rows: tuple[FrequencyReportRow, ...]
    nobs: int
    n_terms: int
    n_active_terms: int
    sdev: float | None
    fit_source: str
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    stale: bool = False
    message: str = "ready"

    def mark_stale(self, message: str = "stale until next fit") -> None:
        self.stale = True
        self.message = message


def kind_for_coefficients(coefficients: tuple[int, ...]) -> str:
    nonzero = [value for value in coefficients if value]
    if len(nonzero) == 1 and nonzero[0] == 1:
        return "independent"
    if len(nonzero) == 1 and abs(nonzero[0]) > 1:
        return "harmonic"
    return "combination"


def _period(frequency: float) -> float | None:
    if not math.isfinite(float(frequency)) or frequency <= 0:
        return None
    return 1.0 / float(frequency)


def _frequency_error(coefficients: tuple[int, ...], baseline: float) -> float | None:
    if baseline <= 0 or not math.isfinite(baseline):
        return None
    coeff_norm = math.sqrt(sum(int(value) ** 2 for value in coefficients))
    if coeff_norm <= 0:
        return None
    return coeff_norm / baseline


def _montgomery_frequency_error(
    *,
    amplitude: float | None,
    residual_std: float | None,
    baseline: float,
    nobs: int,
) -> float | None:
    if amplitude is None or residual_std is None:
        return None
    if baseline <= 0 or nobs <= 0:
        return None
    amplitude_value = float(amplitude)
    residual_value = float(residual_std)
    if not math.isfinite(amplitude_value) or amplitude_value <= 0:
        return None
    if not math.isfinite(residual_value) or residual_value < 0:
        return None
    return float(math.sqrt(6.0) / (math.pi * baseline) * residual_value / (amplitude_value * math.sqrt(nobs)))


def _propagated_frequency_error(
    coefficients: tuple[int, ...],
    *,
    base_errors: dict[int, float],
    fallback: float | None,
) -> float | None:
    nonzero = [(index, int(value)) for index, value in enumerate(coefficients) if int(value) != 0]
    if not nonzero:
        return None
    terms: list[float] = []
    for index, coefficient in nonzero:
        sigma = base_errors.get(index, fallback)
        if sigma is None or not math.isfinite(float(sigma)) or float(sigma) <= 0:
            return fallback
        terms.append((abs(coefficient) * float(sigma)) ** 2)
    if not terms:
        return fallback
    return float(math.sqrt(sum(terms)))


def _period_error(frequency: float, frequency_error: float | None) -> float | None:
    if frequency_error is None or frequency <= 0 or not math.isfinite(float(frequency)):
        return None
    return float(frequency_error) / (float(frequency) ** 2)


def _fit_active_terms(light_curve: LightCurve, terms: list[tuple[int, ...]], frequencies: np.ndarray):
    columns = [np.ones_like(light_curve.time, dtype=float)]
    for frequency in frequencies:
        angle = 2.0 * np.pi * frequency * light_curve.time
        columns.append(np.sin(angle))
        columns.append(np.cos(angle))
    design = np.column_stack(columns)
    weights = 1.0 / np.clip(light_curve.error, 1e-12, None)
    weighted_design = design * weights[:, None]
    weighted_flux = light_curve.flux * weights
    coef, *_ = np.linalg.lstsq(weighted_design, weighted_flux, rcond=None)
    model_flux = design @ coef
    residual_flux = light_curve.flux - model_flux
    weighted_residuals = residual_flux * weights
    dof = max(1, len(light_curve.time) - design.shape[1])
    reduced_chi2 = float(np.sum(weighted_residuals**2) / dof)
    normal = weighted_design.T @ weighted_design
    covariance = np.linalg.pinv(normal) * reduced_chi2
    return coef, covariance, residual_flux


def _term_values(coef: np.ndarray, covariance: np.ndarray, active_index: int):
    sin_index = 1 + 2 * active_index
    cos_index = sin_index + 1
    sin_coef = float(coef[sin_index])
    cos_coef = float(coef[cos_index])
    amplitude = float(np.hypot(sin_coef, cos_coef))
    subcov = covariance[np.ix_([sin_index, cos_index], [sin_index, cos_index])]
    if amplitude <= 1e-12 or not np.all(np.isfinite(subcov)):
        return amplitude, None, None, None
    amp_gradient = np.array([sin_coef / amplitude, cos_coef / amplitude], dtype=float)
    amp_var = float(amp_gradient @ subcov @ amp_gradient)
    amp_error = math.sqrt(max(0.0, amp_var)) if math.isfinite(amp_var) else None
    denom = amplitude**2
    phase_gradient = np.array([-cos_coef / denom, sin_coef / denom], dtype=float) / (2.0 * np.pi)
    phase_var = float(phase_gradient @ subcov @ phase_gradient)
    phase_error = math.sqrt(max(0.0, phase_var)) if math.isfinite(phase_var) else None
    phase_cycles = float((math.atan2(cos_coef, sin_coef) / (2.0 * np.pi)) % 1.0)
    return amplitude, amp_error, phase_cycles, phase_error


def build_frequency_report(light_curve: LightCurve, model: FrequencyModel, *, fit_source: str = "fixed") -> FrequencyReport:
    rows = model.rows()
    active_terms = model.active_terms()
    active_frequencies = np.asarray([model.frequency_for_term(term) for term in active_terms], dtype=float)
    active_index_by_term = {tuple(term): index for index, term in enumerate(active_terms)}
    coef = np.array([float(np.nanmean(light_curve.flux)) if len(light_curve.flux) else 0.0])
    covariance = np.zeros((1, 1), dtype=float)
    residual_flux = light_curve.flux - coef[0] if len(light_curve.flux) else light_curve.flux.copy()
    if active_terms:
        coef, covariance, residual_flux = _fit_active_terms(light_curve, active_terms, active_frequencies)
    baseline = light_curve.baseline if len(light_curve.time) else math.nan
    residual_std = float(np.std(residual_flux)) if len(residual_flux) else None
    fallback_frequency_error = _frequency_error((1,), baseline)
    base_frequency_errors: dict[int, float] = {}
    for row in rows:
        coefficients = tuple(int(value) for value in row["coefficients"])
        nonzero = [(index, value) for index, value in enumerate(coefficients) if value]
        if len(nonzero) != 1 or nonzero[0][1] != 1:
            continue
        active_index = active_index_by_term.get(coefficients)
        amplitude = None
        if row["enabled"] and active_index is not None:
            amplitude, _, _, _ = _term_values(coef, covariance, active_index)
        sigma = _montgomery_frequency_error(
            amplitude=amplitude,
            residual_std=residual_std,
            baseline=baseline,
            nobs=len(light_curve.time),
        )
        if sigma is None:
            sigma = fallback_frequency_error
        if sigma is not None:
            base_frequency_errors[nonzero[0][0]] = float(sigma)
    report_rows: list[FrequencyReportRow] = []
    for row in rows:
        coefficients = tuple(int(value) for value in row["coefficients"])
        frequency = float(row["frequency"])
        freq_error = _propagated_frequency_error(
            coefficients,
            base_errors=base_frequency_errors,
            fallback=fallback_frequency_error,
        )
        period = _period(frequency)
        amplitude = None
        amplitude_error = None
        phase_cycles = None
        phase_error_cycles = None
        status = "disabled"
        active_index = active_index_by_term.get(coefficients)
        if row["enabled"] and active_index is not None:
            amplitude, amplitude_error, phase_cycles, phase_error_cycles = _term_values(coef, covariance, active_index)
            status = "fit"
        report_rows.append(
            FrequencyReportRow(
                index=int(row["index"]),
                enabled=bool(row["enabled"]),
                kind=kind_for_coefficients(coefficients),
                label=str(row["label"]),
                coefficients=coefficients,
                frequency=frequency,
                frequency_error=freq_error,
                period=period,
                period_error=_period_error(frequency, freq_error),
                amplitude=amplitude,
                amplitude_error=amplitude_error,
                phase_cycles=phase_cycles,
                phase_error_cycles=phase_error_cycles,
                status=status,
            )
        )
    return FrequencyReport(
        rows=tuple(report_rows),
        nobs=len(light_curve.time),
        n_terms=len(rows),
        n_active_terms=len(active_terms),
        sdev=residual_std,
        fit_source=fit_source,
    )
