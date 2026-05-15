"""Sliding-window time-dependent Fourier decomposition for lcView."""

from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np

from .frequency_model import FrequencyModel
from .lightcurve import LightCurve


@dataclass(frozen=True)
class TdfdOptions:
    source: str = "residual"
    auto_window: bool = True
    window_points: int | None = None
    step_points: int | None = None
    selected_base_index: int | None = None


@dataclass(frozen=True)
class TdfdTerm:
    term: tuple[int, ...]
    label: str
    frequency: float
    base_index: int | None = None
    family_base_index: int | None = None
    reported: bool = False


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
    start_index: int = 0
    end_index: int = 0
    offset: float = 0.0
    sin_coefficients: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    cos_coefficients: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    term_amplitudes: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    term_phases: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))


@dataclass(frozen=True)
class TdfdResult:
    bins: list[TdfdBin]
    residuals: LightCurve
    frequency_labels: tuple[str, ...] = ()
    source_light_curve: LightCurve | None = None
    bin_edges: np.ndarray | None = None
    bin_counts: np.ndarray | None = None
    min_points_per_bin: int = 0
    options: TdfdOptions = field(default_factory=TdfdOptions)
    fit_terms: tuple[TdfdTerm, ...] = ()
    report_terms: tuple[TdfdTerm, ...] = ()
    window_starts: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    window_ends: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    window_centers: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    window_counts: np.ndarray = field(default_factory=lambda: np.array([], dtype=int))
    window_points: int = 0
    step_points: int = 0
    fit_parameter_count: int = 0
    selected_base_index: int | None = None
    correction_term_indexes: tuple[int, ...] = ()
    interpolated_offset: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    interpolated_sin_coefficients: np.ndarray = field(default_factory=lambda: np.empty((0, 0), dtype=float))
    interpolated_cos_coefficients: np.ndarray = field(default_factory=lambda: np.empty((0, 0), dtype=float))
    full_model_flux: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    correction_flux: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    corrected_residuals: LightCurve | None = None
    message: str = ""


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


def independent_frequency_rows(model: FrequencyModel) -> list[dict]:
    rows = []
    for row in model.rows():
        coefficients = tuple(row["coefficients"])
        nonzero = [(index, value) for index, value in enumerate(coefficients) if value]
        if len(nonzero) == 1 and nonzero[0][1] == 1 and row["enabled"]:
            rows.append(row)
    return rows


def active_tdfd_terms(model: FrequencyModel) -> tuple[TdfdTerm, ...]:
    terms: list[TdfdTerm] = []
    for row in model.rows():
        if not row["enabled"]:
            continue
        coefficients = tuple(int(value) for value in row["coefficients"])
        frequency = float(row["frequency"])
        if not np.isfinite(frequency) or frequency <= 0:
            continue
        nonzero = [(index, value) for index, value in enumerate(coefficients) if value]
        base_index = nonzero[0][0] if len(nonzero) == 1 and nonzero[0][1] == 1 else None
        family_base_index = nonzero[0][0] if len(nonzero) == 1 and nonzero[0][1] > 0 else None
        terms.append(
            TdfdTerm(
                term=coefficients,
                label=str(row["label"]),
                frequency=frequency,
                base_index=base_index,
                family_base_index=family_base_index,
                reported=base_index is not None,
            )
        )
    return tuple(terms)


def _default_selected_base(report_terms: tuple[TdfdTerm, ...], selected_base_index: int | None) -> int | None:
    if selected_base_index is not None and any(term.base_index == selected_base_index for term in report_terms):
        return int(selected_base_index)
    if report_terms:
        return report_terms[0].base_index
    return None


def _window_parameters(point_count: int, fit_parameter_count: int, options: TdfdOptions) -> tuple[int, int]:
    if point_count <= 0:
        return 0, 0
    if options.auto_window or options.window_points is None:
        window_points = min(point_count, max(30, 4 * fit_parameter_count))
    else:
        window_points = min(point_count, max(1, int(options.window_points)))
    if options.step_points is None or int(options.step_points) <= 0:
        step_points = max(1, window_points // 4)
    else:
        step_points = max(1, int(options.step_points))
    return int(window_points), int(step_points)


def _window_slices(point_count: int, window_points: int, step_points: int) -> list[tuple[int, int]]:
    if window_points <= 0 or point_count < window_points:
        return []
    last_start = point_count - window_points
    starts = list(range(0, last_start + 1, max(1, step_points)))
    if starts[-1] != last_start:
        starts.append(last_start)
    return [(start, start + window_points) for start in starts]


def _fit_terms(light_curve: LightCurve, terms: tuple[TdfdTerm, ...]) -> tuple[float, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if not terms:
        offset = float(np.average(light_curve.flux, weights=1.0 / np.clip(light_curve.error, 1e-12, None)))
        model_flux = np.full_like(light_curve.flux, offset, dtype=float)
        residuals = light_curve.flux - model_flux
        return offset, np.array([]), np.array([]), model_flux, residuals
    columns = [np.ones_like(light_curve.time)]
    for term in terms:
        angle = 2.0 * np.pi * term.frequency * light_curve.time
        columns.append(np.sin(angle))
        columns.append(np.cos(angle))
    design = np.column_stack(columns)
    weights = 1.0 / np.clip(light_curve.error, 1e-12, None)
    coef, *_ = np.linalg.lstsq(design * weights[:, None], light_curve.flux * weights, rcond=None)
    model_flux = design @ coef
    residuals = light_curve.flux - model_flux
    sin_coefficients = np.asarray(coef[1::2], dtype=float)
    cos_coefficients = np.asarray(coef[2::2], dtype=float)
    return float(coef[0]), sin_coefficients, cos_coefficients, model_flux, residuals


def _term_model_flux(light_curve: LightCurve, terms: tuple[TdfdTerm, ...], sin_coefficients: np.ndarray, cos_coefficients: np.ndarray) -> np.ndarray:
    model = np.zeros_like(light_curve.flux, dtype=float)
    for index, term in enumerate(terms):
        angle = 2.0 * np.pi * term.frequency * light_curve.time
        model += sin_coefficients[index] * np.sin(angle) + cos_coefficients[index] * np.cos(angle)
    return model


def _interpolate_coefficients(
    light_curve: LightCurve,
    centers: np.ndarray,
    offsets: np.ndarray,
    sin_by_window: np.ndarray,
    cos_by_window: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if centers.size == 0:
        return (
            np.zeros_like(light_curve.flux, dtype=float),
            np.empty((sin_by_window.shape[1] if sin_by_window.ndim == 2 else 0, len(light_curve.time)), dtype=float),
            np.empty((cos_by_window.shape[1] if cos_by_window.ndim == 2 else 0, len(light_curve.time)), dtype=float),
        )
    time = np.asarray(light_curve.time, dtype=float)
    offset = np.interp(time, centers, offsets, left=float(offsets[0]), right=float(offsets[-1]))
    n_terms = sin_by_window.shape[1] if sin_by_window.ndim == 2 else 0
    sin_interp = np.empty((n_terms, len(time)), dtype=float)
    cos_interp = np.empty((n_terms, len(time)), dtype=float)
    for term_index in range(n_terms):
        sin_interp[term_index] = np.interp(
            time,
            centers,
            sin_by_window[:, term_index],
            left=float(sin_by_window[0, term_index]),
            right=float(sin_by_window[-1, term_index]),
        )
        cos_interp[term_index] = np.interp(
            time,
            centers,
            cos_by_window[:, term_index],
            left=float(cos_by_window[0, term_index]),
            right=float(cos_by_window[-1, term_index]),
        )
    return offset, sin_interp, cos_interp


def _model_from_interpolated_coefficients(
    light_curve: LightCurve,
    terms: tuple[TdfdTerm, ...],
    offset: np.ndarray,
    sin_coefficients: np.ndarray,
    cos_coefficients: np.ndarray,
    term_indexes: tuple[int, ...] | None = None,
    *,
    include_offset: bool = False,
) -> np.ndarray:
    model = np.zeros_like(light_curve.flux, dtype=float)
    if include_offset:
        model += offset
    indexes = term_indexes if term_indexes is not None else tuple(range(len(terms)))
    for term_index in indexes:
        term = terms[term_index]
        angle = 2.0 * np.pi * term.frequency * light_curve.time
        model += sin_coefficients[term_index] * np.sin(angle) + cos_coefficients[term_index] * np.cos(angle)
    return model


def run_tdfd(
    light_curve: LightCurve,
    model: FrequencyModel,
    bins: int | None = None,
    *,
    options: TdfdOptions | None = None,
) -> TdfdResult:
    options = options or TdfdOptions(window_points=bins, auto_window=bins is None)
    fit_terms = active_tdfd_terms(model)
    report_terms = tuple(term for term in fit_terms if term.reported)
    selected_base_index = _default_selected_base(report_terms, options.selected_base_index)
    correction_term_indexes = tuple(
        index for index, term in enumerate(fit_terms) if selected_base_index is not None and term.family_base_index == selected_base_index
    )
    frequencies = np.asarray([term.frequency for term in report_terms], dtype=float)
    labels = tuple(term.label for term in report_terms)
    fit_parameter_count = 1 + 2 * len(fit_terms)
    window_points, step_points = _window_parameters(len(light_curve.time), fit_parameter_count, options)
    min_points = fit_parameter_count
    slices = _window_slices(len(light_curve.time), window_points, step_points)
    bin_results: list[TdfdBin] = []
    offsets: list[float] = []
    sin_rows: list[np.ndarray] = []
    cos_rows: list[np.ndarray] = []
    window_starts: list[float] = []
    window_ends: list[float] = []
    window_centers: list[float] = []
    window_counts: list[int] = []

    report_indexes = [fit_terms.index(term) for term in report_terms]
    for start_index, end_index in slices:
        segment = LightCurve(
            light_curve.time[start_index:end_index],
            light_curve.flux[start_index:end_index],
            light_curve.error[start_index:end_index],
            light_curve.path,
        )
        point_count = len(segment.time)
        window_counts.append(point_count)
        if point_count < min_points:
            continue
        offset, sin_coefficients, cos_coefficients, _model_flux, residuals = _fit_terms(segment, fit_terms)
        offsets.append(offset)
        sin_rows.append(sin_coefficients)
        cos_rows.append(cos_coefficients)
        window_starts.append(float(segment.time[0]))
        window_ends.append(float(segment.time[-1]))
        window_centers.append(float(0.5 * (segment.time[0] + segment.time[-1])))
        term_amplitudes = np.hypot(sin_coefficients, cos_coefficients)
        term_phases = np.arctan2(cos_coefficients, sin_coefficients)
        report_amplitudes = term_amplitudes[report_indexes] if report_indexes else np.array([], dtype=float)
        report_phases = term_phases[report_indexes] if report_indexes else np.array([], dtype=float)
        bin_results.append(
            TdfdBin(
                start_time=float(segment.time[0]),
                end_time=float(segment.time[-1]),
                mid_time=float(0.5 * (segment.time[0] + segment.time[-1])),
                frequencies=frequencies.copy(),
                amplitudes=np.asarray(report_amplitudes, dtype=float),
                phases=np.asarray(report_phases, dtype=float),
                residual_std=float(np.std(residuals)),
                n_points=point_count,
                start_index=start_index,
                end_index=end_index,
                offset=offset,
                sin_coefficients=sin_coefficients,
                cos_coefficients=cos_coefficients,
                term_amplitudes=term_amplitudes,
                term_phases=term_phases,
            )
        )

    centers = np.asarray(window_centers, dtype=float)
    starts = np.asarray(window_starts, dtype=float)
    ends = np.asarray(window_ends, dtype=float)
    counts = np.asarray(window_counts, dtype=int)
    if bin_results:
        offset_series = np.asarray(offsets, dtype=float)
        sin_matrix = np.vstack(sin_rows) if sin_rows else np.empty((len(bin_results), 0), dtype=float)
        cos_matrix = np.vstack(cos_rows) if cos_rows else np.empty((len(bin_results), 0), dtype=float)
        interp_offset, interp_sin, interp_cos = _interpolate_coefficients(light_curve, centers, offset_series, sin_matrix, cos_matrix)
        full_model_flux = _model_from_interpolated_coefficients(
            light_curve,
            fit_terms,
            interp_offset,
            interp_sin,
            interp_cos,
            include_offset=True,
        )
        full_residual_flux = light_curve.flux - full_model_flux
        correction_flux = _model_from_interpolated_coefficients(
            light_curve,
            fit_terms,
            interp_offset,
            interp_sin,
            interp_cos,
            correction_term_indexes,
            include_offset=False,
        )
        corrected_flux = light_curve.flux - correction_flux
        message = "TDFD ready"
    else:
        interp_offset = np.zeros_like(light_curve.flux, dtype=float)
        interp_sin = np.zeros((len(fit_terms), len(light_curve.time)), dtype=float)
        interp_cos = np.zeros((len(fit_terms), len(light_curve.time)), dtype=float)
        full_model_flux = np.zeros_like(light_curve.flux, dtype=float)
        full_residual_flux = light_curve.flux - np.nanmean(light_curve.flux) if len(light_curve.flux) else light_curve.flux.copy()
        correction_flux = np.zeros_like(light_curve.flux, dtype=float)
        corrected_flux = light_curve.flux.copy()
        message = "No TDFD windows had enough points for a stable fit"

    residual_lc = light_curve.with_flux(full_residual_flux)
    corrected_lc = light_curve.with_flux(corrected_flux)
    return TdfdResult(
        bins=bin_results,
        residuals=residual_lc,
        frequency_labels=labels,
        source_light_curve=light_curve,
        bin_edges=None,
        bin_counts=counts,
        min_points_per_bin=min_points,
        options=options,
        fit_terms=fit_terms,
        report_terms=report_terms,
        window_starts=starts,
        window_ends=ends,
        window_centers=centers,
        window_counts=counts,
        window_points=window_points,
        step_points=step_points,
        fit_parameter_count=fit_parameter_count,
        selected_base_index=selected_base_index,
        correction_term_indexes=correction_term_indexes,
        interpolated_offset=interp_offset,
        interpolated_sin_coefficients=interp_sin,
        interpolated_cos_coefficients=interp_cos,
        full_model_flux=full_model_flux,
        correction_flux=correction_flux,
        corrected_residuals=corrected_lc,
        message=message,
    )
