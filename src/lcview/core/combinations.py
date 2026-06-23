"""Frequency combination and resolution helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations, product
import math
import numpy as np

from .frequency_model import FrequencyModel


@dataclass(frozen=True)
class FrequencyCandidate:
    frequency: float
    amplitude: float
    snr: float | None
    kind: str
    label: str
    coefficients: tuple[int, ...]
    delta: float
    score: float
    resolved: str
    rayleigh: float


@dataclass(frozen=True)
class CombinationIndex:
    coefficients: np.ndarray
    frequencies: np.ndarray
    complexities: np.ndarray
    order: np.ndarray


def rayleigh_resolution(baseline: float) -> float:
    if baseline <= 0:
        return math.inf
    return 0.5 / baseline


def resolution_status(frequency: float, model: FrequencyModel, baseline: float) -> tuple[str, float]:
    resolution = rayleigh_resolution(baseline)
    if model.is_empty or not model.terms:
        return "new", math.inf
    freqs = np.array([model.frequency_for_term(term) for term in model.terms], dtype=float)
    diff = float(np.min(np.abs(freqs - frequency)))
    if diff < resolution:
        return "not resolved", diff
    if diff < 2 * resolution:
        return "weakly resolved", diff
    return "resolved", diff


def _normalised_bounds(start_frequency: float | None, end_frequency: float | None) -> tuple[float | None, float | None]:
    start = None if start_frequency is None else float(start_frequency)
    end = None if end_frequency is None else float(end_frequency)
    if start is not None and not np.isfinite(start):
        start = None
    if end is not None and not np.isfinite(end):
        end = None
    if start is not None and end is not None and start > end:
        start, end = end, start
    return start, end


def _combination_bases(model: FrequencyModel, combination_base_indexes: Iterable[int] | None) -> tuple[float, ...]:
    bases = tuple(float(value) for value in model.bases)
    if combination_base_indexes is None:
        return bases

    selected: set[int] = set()
    for value in combination_base_indexes:
        try:
            index = int(value)
        except (TypeError, ValueError):
            continue
        if 0 <= index < len(bases):
            selected.add(index)
    if len(selected) == len(bases):
        return bases
    return tuple(frequency if index in selected else 0.0 for index, frequency in enumerate(bases))


def _in_frequency_range(frequency: float, start_frequency: float | None, end_frequency: float | None) -> bool:
    if not np.isfinite(frequency) or frequency <= 0:
        return False
    if start_frequency is not None and frequency < start_frequency:
        return False
    if end_frequency is not None and frequency > end_frequency:
        return False
    return True


def _fast_coefficient_space(
    bases: tuple[float, ...],
    start_frequency: float | None,
    end_frequency: float | None,
    max_harmonic: int,
    n_two: int,
    include_three: bool,
) -> tuple[np.ndarray, np.ndarray]:
    nbase = len(bases)
    coefficients: list[tuple[int, ...]] = []
    frequencies: list[float] = []
    seen: set[tuple[int, ...]] = set()
    positive_indexes = [index for index, frequency in enumerate(bases) if np.isfinite(frequency) and frequency > 0]

    def add(row: list[int], frequency: float) -> None:
        if not _in_frequency_range(frequency, start_frequency, end_frequency):
            return
        coeffs = tuple(row)
        if coeffs in seen:
            return
        seen.add(coeffs)
        coefficients.append(coeffs)
        frequencies.append(float(frequency))

    for index in positive_indexes:
        base_frequency = bases[index]
        harmonic_limit = max(1, int(max_harmonic))
        if end_frequency is not None:
            harmonic_limit = min(harmonic_limit, int(math.floor(end_frequency / base_frequency)))
        for harmonic in range(1, harmonic_limit + 1):
            row = [0] * nbase
            row[index] = harmonic
            add(row, harmonic * base_frequency)

    two_values = [value for value in range(-max(1, int(n_two)), max(1, int(n_two)) + 1) if value != 0]
    for first, second in combinations(positive_indexes, 2):
        first_frequency = bases[first]
        second_frequency = bases[second]
        for first_coeff in two_values:
            partial = first_coeff * first_frequency
            for second_coeff in two_values:
                row = [0] * nbase
                row[first] = first_coeff
                row[second] = second_coeff
                add(row, partial + second_coeff * second_frequency)

    if include_three:
        for indexes in combinations(positive_indexes, 3):
            base_values = [bases[index] for index in indexes]
            for multipliers in product((-1, 1), repeat=3):
                row = [0] * nbase
                frequency = 0.0
                for index, multiplier, base_frequency in zip(indexes, multipliers, base_values):
                    row[index] = multiplier
                    frequency += multiplier * base_frequency
                add(row, frequency)

    if not coefficients:
        return np.empty((0, nbase), dtype=np.int16), np.empty(0, dtype=float)
    return np.asarray(coefficients, dtype=np.int16), np.asarray(frequencies, dtype=float)


@lru_cache(maxsize=16)
def _combination_index(
    bases: tuple[float, ...],
    start_frequency: float | None,
    end_frequency: float | None,
    max_harmonic: int,
    n_two: int,
    include_three: bool,
) -> CombinationIndex:
    if not bases:
        empty_coefficients = np.empty((0, 0), dtype=np.int16)
        empty = np.empty(0, dtype=float)
        return CombinationIndex(empty_coefficients, empty, empty, np.empty(0, dtype=int))

    start_frequency, end_frequency = _normalised_bounds(start_frequency, end_frequency)
    coefficients, frequencies = _fast_coefficient_space(
        bases,
        start_frequency,
        end_frequency,
        max_harmonic,
        n_two,
        include_three,
    )
    if len(frequencies) == 0:
        empty = np.empty(0, dtype=float)
        return CombinationIndex(coefficients, empty, empty, np.empty(0, dtype=int))

    abs_coefficients = np.abs(coefficients.astype(float))
    base_weights = np.arange(1, len(bases) + 1, dtype=float) / 10.0
    complexities = np.sum(abs_coefficients, axis=1) + abs_coefficients @ base_weights
    return CombinationIndex(
        coefficients=coefficients,
        frequencies=frequencies,
        complexities=complexities,
        order=np.argsort(frequencies),
    )


def matching_combinations(
    frequency: float,
    model: FrequencyModel,
    baseline: float,
    *,
    start_frequency: float | None = None,
    end_frequency: float | None = None,
    combination_base_indexes: Iterable[int] | None = None,
    max_harmonic: int = 60,
    n_two: int = 15,
    n_three: int = 10,
    n_four: int = 8,
    limit: int = 15,
) -> list[tuple[tuple[int, ...], float, float]]:
    if model.is_empty:
        return []
    resolution = rayleigh_resolution(baseline)
    index = _combination_index(
        _combination_bases(model, combination_base_indexes),
        *_normalised_bounds(start_frequency, end_frequency),
        max_harmonic,
        n_two,
        n_three > 0,
    )
    return _matching_combinations_from_index(float(frequency), resolution, index, limit=limit)


def _matching_combinations_from_index(
    frequency: float,
    resolution: float,
    index: CombinationIndex,
    *,
    limit: int,
) -> list[tuple[tuple[int, ...], float, float]]:
    if len(index.frequencies) == 0:
        return []

    ordered_frequencies = index.frequencies[index.order]
    start = int(np.searchsorted(ordered_frequencies, frequency - resolution, side="left"))
    stop = int(np.searchsorted(ordered_frequencies, frequency + resolution, side="right"))
    if start >= stop:
        return []

    candidate_indexes = index.order[start:stop]
    deltas = index.frequencies[candidate_indexes] - frequency
    scores = index.complexities[candidate_indexes] * np.exp(np.minimum(100.0 * np.abs(deltas), 700.0))
    ranked = np.lexsort((np.abs(deltas), scores))[:limit]
    return [
        (
            tuple(int(value) for value in index.coefficients[candidate_indexes[row]]),
            float(deltas[row]),
            float(scores[row]),
        )
        for row in ranked
    ]


def clear_combination_cache() -> None:
    _combination_index.cache_clear()


def combination_cache_info():
    return _combination_index.cache_info()


def _model_term_frequencies(model: FrequencyModel) -> np.ndarray:
    if model.is_empty or not model.terms:
        return np.empty(0, dtype=float)
    frequencies = np.asarray([model.frequency_for_term(term) for term in model.terms], dtype=float)
    return frequencies[np.isfinite(frequencies)]


def _resolution_status_from_frequencies(frequency: float, frequencies: np.ndarray, resolution: float) -> tuple[str, float]:
    if len(frequencies) == 0:
        return "new", math.inf
    diff = float(np.min(np.abs(frequencies - frequency)))
    if diff < resolution:
        return "not resolved", diff
    if diff < 2 * resolution:
        return "weakly resolved", diff
    return "resolved", diff


def _kind_for_coefficients(coefficients: tuple[int, ...]) -> str:
    nonzero = [value for value in coefficients if value]
    if len(nonzero) == 1 and abs(nonzero[0]) > 1:
        return "harmonic"
    return "combination"


def _candidate_from_peak(
    frequency: float,
    amplitude: float,
    snr: float | None,
    model: FrequencyModel,
    resolution: float,
    model_frequencies: np.ndarray,
    combination_index: CombinationIndex,
) -> FrequencyCandidate:
    status, diff = _resolution_status_from_frequencies(frequency, model_frequencies, resolution)
    matches = _matching_combinations_from_index(frequency, resolution, combination_index, limit=1)
    if matches:
        coeffs, delta, score = matches[0]
        kind = _kind_for_coefficients(coeffs)
        label = model.label_for_term(coeffs)
    else:
        coeffs = tuple([0] * len(model.bases))
        delta = diff if math.isfinite(diff) else 0.0
        score = 0.0
        kind = "independent"
        label = "new"
    if frequency < 0.3:
        status = f"{status}; low frequency"
    return FrequencyCandidate(
        frequency=float(frequency),
        amplitude=float(amplitude),
        snr=snr,
        kind=kind,
        label=label,
        coefficients=coeffs,
        delta=float(delta),
        score=float(score),
        resolved=status,
        rayleigh=resolution,
    )


def classify_peak(
    frequency: float,
    amplitude: float,
    model: FrequencyModel,
    baseline: float,
    *,
    snr: float | None = None,
    start_frequency: float | None = None,
    end_frequency: float | None = None,
    combination_base_indexes: Iterable[int] | None = None,
) -> FrequencyCandidate:
    resolution = rayleigh_resolution(baseline)
    combination_index = _combination_index(
        _combination_bases(model, combination_base_indexes),
        *_normalised_bounds(start_frequency, end_frequency),
        60,
        15,
        True,
    )
    return _candidate_from_peak(
        frequency=float(frequency),
        amplitude=float(amplitude),
        snr=snr,
        model=model,
        resolution=resolution,
        model_frequencies=_model_term_frequencies(model),
        combination_index=combination_index,
    )


def candidates_from_peaks(
    peaks: list[dict],
    model: FrequencyModel,
    baseline: float,
    *,
    start_frequency: float | None = None,
    end_frequency: float | None = None,
    combination_base_indexes: Iterable[int] | None = None,
    snr_key: str = "snr",
) -> list[FrequencyCandidate]:
    resolution = rayleigh_resolution(baseline)
    model_frequencies = _model_term_frequencies(model)
    combination_index = _combination_index(
        _combination_bases(model, combination_base_indexes),
        *_normalised_bounds(start_frequency, end_frequency),
        60,
        15,
        True,
    )
    candidates: list[FrequencyCandidate] = []
    for peak in peaks:
        candidates.append(
            _candidate_from_peak(
                frequency=float(peak["frequency"]),
                amplitude=float(peak["amplitude"]),
                snr=peak.get(snr_key, peak.get("snr")),
                model=model,
                resolution=resolution,
                model_frequencies=model_frequencies,
                combination_index=combination_index,
            )
        )
    return candidates
