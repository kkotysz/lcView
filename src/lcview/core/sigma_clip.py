"""Sigma-clipping helpers."""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from .lightcurve import LightCurve


@dataclass(frozen=True)
class SigmaClipResult:
    cleaned: LightCurve
    rejected: LightCurve
    keep_mask: np.ndarray
    sigma: float


def sigma_clip_light_curve(light_curve: LightCurve, sigma: float = 3.5, maxiters: int = 6) -> SigmaClipResult:
    try:
        from astropy.stats import sigma_clip as astropy_sigma_clip

        clipped = astropy_sigma_clip(light_curve.flux, sigma=sigma, maxiters=maxiters)
        keep = ~np.ma.getmaskarray(clipped)
    except Exception:
        median = np.median(light_curve.flux)
        mad = np.median(np.abs(light_curve.flux - median)) or np.std(light_curve.flux) or 1.0
        keep = np.abs(light_curve.flux - median) <= sigma * 1.4826 * mad
    return SigmaClipResult(
        cleaned=light_curve.masked(keep),
        rejected=light_curve.masked(~keep) if np.any(~keep) else LightCurve(light_curve.time[:0], light_curve.flux[:0], light_curve.error[:0], light_curve.path),
        keep_mask=keep,
        sigma=float(sigma),
    )
