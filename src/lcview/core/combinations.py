"""Frequency combination and resolution helpers."""

from __future__ import annotations

from dataclasses import dataclass
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


def _coefficient_space(nbase: int, max_harmonic: int, n_two: int, n_three: int, n_four: int) -> list[tuple[int, ...]]:
    coeffs: list[tuple[int, ...]] = []
    for idx in range(nbase):
        for harmonic in range(2, max_harmonic + 1):
            row = [0] * nbase
            row[idx] = harmonic
            coeffs.append(tuple(row))
        row = [0] * nbase
        row[idx] = 1
        coeffs.append(tuple(row))

    limits = {2: n_two, 3: n_three, 4: n_four}
    for order in range(2, min(4, nbase) + 1):
        limit = max(1, limits[order])
        values = [value for value in range(-limit, limit + 1) if value != 0]
        for indexes in combinations(range(nbase), order):
            for multipliers in product(values, repeat=order):
                row = [0] * nbase
                for index, multiplier in zip(indexes, multipliers):
                    row[index] = multiplier
                if sum(abs(v) for v in row) <= 1:
                    continue
                coeffs.append(tuple(row))
    return coeffs


def matching_combinations(
    frequency: float,
    model: FrequencyModel,
    baseline: float,
    *,
    max_harmonic: int = 60,
    n_two: int = 15,
    n_three: int = 10,
    n_four: int = 8,
    limit: int = 15,
) -> list[tuple[tuple[int, ...], float, float]]:
    if model.is_empty:
        return []
    resolution = rayleigh_resolution(baseline)
    matches: list[tuple[tuple[int, ...], float, float]] = []
    seen: set[tuple[int, ...]] = set()
    for coeffs in _coefficient_space(len(model.bases), max_harmonic, n_two, n_three, n_four):
        if coeffs in seen:
            continue
        seen.add(coeffs)
        combo_freq = model.frequency_for_term(coeffs)
        if combo_freq <= 0:
            continue
        delta = combo_freq - frequency
        if abs(delta) <= resolution:
            complexity = sum(abs(v) for v in coeffs) + sum(i * abs(v) for i, v in enumerate(coeffs, start=1)) / 10
            score = complexity * math.exp(100 * abs(delta))
            matches.append((coeffs, delta, score))
    matches.sort(key=lambda item: (item[2], abs(item[1])))
    return matches[:limit]


def classify_peak(
    frequency: float,
    amplitude: float,
    model: FrequencyModel,
    baseline: float,
    *,
    snr: float | None = None,
) -> FrequencyCandidate:
    resolution = rayleigh_resolution(baseline)
    status, diff = resolution_status(frequency, model, baseline)
    matches = matching_combinations(frequency, model, baseline, limit=1)
    if matches:
        coeffs, delta, score = matches[0]
        nonzero = sum(1 for value in coeffs if value)
        kind = "harmonic" if nonzero == 1 and max(abs(v) for v in coeffs) > 1 else "combination"
        label = model.label_for_term(coeffs)
    else:
        coeffs = tuple([0] * len(model.bases))
        delta = diff if math.isfinite(diff) else 0.0
        score = 0.0
        kind = "independent"
        label = "new independent"
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


def candidates_from_peaks(peaks: list[dict], model: FrequencyModel, baseline: float) -> list[FrequencyCandidate]:
    candidates: list[FrequencyCandidate] = []
    for peak in peaks:
        candidates.append(
            classify_peak(
                frequency=float(peak["frequency"]),
                amplitude=float(peak["amplitude"]),
                snr=peak.get("snr"),
                model=model,
                baseline=baseline,
            )
        )
    return candidates
