"""Light-curve loading and simple transformations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class LightCurve:
    time: np.ndarray
    flux: np.ndarray
    error: np.ndarray
    path: Path | None = None

    def __post_init__(self) -> None:
        lengths = {len(self.time), len(self.flux), len(self.error)}
        if len(lengths) != 1:
            raise ValueError("time, flux and error arrays must have the same length")

    @property
    def baseline(self) -> float:
        if len(self.time) == 0:
            raise ValueError("empty light curve has no baseline")
        return float(np.nanmax(self.time) - np.nanmin(self.time))

    @property
    def median_time(self) -> float:
        return float(np.nanmedian(self.time))

    def sorted(self) -> "LightCurve":
        order = np.argsort(self.time)
        return LightCurve(self.time[order], self.flux[order], self.error[order], self.path)

    def centered_time(self) -> "LightCurve":
        return LightCurve(self.time - self.median_time, self.flux.copy(), self.error.copy(), self.path).sorted()

    def with_flux(self, flux: Iterable[float]) -> "LightCurve":
        return LightCurve(self.time.copy(), np.asarray(list(flux), dtype=float), self.error.copy(), self.path).sorted()

    def masked(self, mask: np.ndarray) -> "LightCurve":
        return LightCurve(self.time[mask], self.flux[mask], self.error[mask], self.path).sorted()

    def to_array(self) -> np.ndarray:
        return np.column_stack([self.time, self.flux, self.error])

    def save(self, path: Path) -> None:
        np.savetxt(path, self.to_array(), fmt="%16.8f %16.8f %12.6f")


def read_light_curve(path: str | Path) -> LightCurve:
    path = Path(path)
    df = pd.read_csv(path, delimiter=r"\s+", header=None, comment="#", usecols=[0, 1, 2])
    df = df.apply(pd.to_numeric, errors="coerce").dropna()
    if df.empty:
        raise ValueError(f"No numeric light-curve rows found in {path}")
    return LightCurve(
        time=df[0].to_numpy(dtype=float),
        flux=df[1].to_numpy(dtype=float),
        error=df[2].to_numpy(dtype=float),
        path=path,
    ).sorted()


def from_array(data: np.ndarray, path: Path | None = None) -> LightCurve:
    data = np.asarray(data, dtype=float)
    if data.ndim != 2 or data.shape[1] < 3:
        raise ValueError("expected a two-dimensional array with at least three columns")
    return LightCurve(data[:, 0], data[:, 1], data[:, 2], path).sorted()
