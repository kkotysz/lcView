"""Python orchestration for the legacy prewhitening numerical tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shutil
import subprocess
import numpy as np

from lcview.native.build import NativeBuildError, NativeTools, ensure_native
from .combinations import FrequencyCandidate, candidates_from_peaks
from .frequency_model import FrequencyHistory, FrequencyModel
from .lightcurve import LightCurve, read_light_curve, from_array
from .periodogram import PeriodogramResult, compute_periodogram
from .results import FrequencyReport, build_frequency_report
from .session import SessionState
from .tdfd import TdfdResult


@dataclass
class FourierTerm:
    term: tuple[int, ...]
    frequency: float
    sin_coefficient: float
    cos_coefficient: float
    amplitude: float
    phase: float


@dataclass
class FitResult:
    residuals: LightCurve
    model: FrequencyModel
    converged: bool
    ampl_text: str = ""
    stderr: str = ""
    used_native: bool = False
    offset: float = 0.0
    fourier_terms: tuple[FourierTerm, ...] = ()
    report: FrequencyReport | None = None


@dataclass
class PrewhiteningEngine:
    state: SessionState
    light_curve: LightCurve = field(init=False)
    history: FrequencyHistory = field(init=False)
    tools: NativeTools | None = field(default=None, init=False)
    last_periodogram: PeriodogramResult | None = None
    last_candidates: list[FrequencyCandidate] = field(default_factory=list)
    residuals: LightCurve | None = None
    last_report: FrequencyReport | None = None
    tdfd_result: TdfdResult | None = None
    tdfd_correction_active: bool = False
    tdfd_correction_label: str = ""
    tdfd_correction_stale_reason: str = ""
    _pre_tdfd_residuals: LightCurve | None = None

    def __post_init__(self) -> None:
        settings = self.state.settings
        columns = None
        if settings.time_column is not None and settings.flux_column is not None and settings.error_column is not None:
            columns = (settings.time_column, settings.flux_column, settings.error_column)
        self.light_curve = read_light_curve(self.state.light_curve_path, columns=columns).centered_time()
        self.history = FrequencyHistory(current=self.state.frequency_model.clone())
        self.state.work_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_file(cls, path: str | Path, columns: tuple[int, int, int] | None = None) -> "PrewhiteningEngine":
        state = SessionState.for_light_curve(path)
        if columns is not None:
            state.settings.time_column, state.settings.flux_column, state.settings.error_column = [int(column) for column in columns]
            state.save()
        return cls(state)

    @property
    def model(self) -> FrequencyModel:
        return self.history.current

    def save_state(self) -> None:
        self.state.frequency_model = self.model.clone()
        self.state.save()

    def _ensure_tools(self) -> NativeTools:
        if self.tools is None:
            self.tools = ensure_native()
        return self.tools

    def _reset_work_dir(self) -> None:
        self.state.work_dir.mkdir(parents=True, exist_ok=True)
        for path in self.state.work_dir.iterdir():
            if path.is_file() or path.is_symlink():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)

    def _invalidate_periodogram(self) -> None:
        self.last_periodogram = None
        self.last_candidates = []

    def _classify_periodogram_candidates(self, result: PeriodogramResult) -> list[FrequencyCandidate]:
        settings = self.state.settings
        return candidates_from_peaks(
            result.peaks,
            self.model,
            self.light_curve.baseline,
            start_frequency=settings.start_frequency,
            end_frequency=settings.end_frequency,
            combination_base_indexes=settings.combination_base_indexes,
            snr_key="local_snr" if settings.use_dft_adaptive_snr else "global_snr",
        )

    def refresh_candidates(self) -> list[FrequencyCandidate]:
        if self.last_periodogram is None:
            self.last_candidates = []
            return self.last_candidates
        self.last_candidates = self._classify_periodogram_candidates(self.last_periodogram)
        return self.last_candidates

    def _mark_report_stale(self, reason: str = "stale until next fit") -> None:
        if self.last_report is not None:
            self.last_report.mark_stale(reason)

    def _remove_combination_base_index(self, removed_index: int) -> None:
        indexes = self.state.settings.combination_base_indexes
        if indexes is None:
            return
        adjusted: list[int] = []
        for value in indexes:
            index = int(value)
            if index == removed_index:
                continue
            adjusted.append(index - 1 if index > removed_index else index)
        remaining = sorted({index for index in adjusted if 0 <= index < len(self.model.bases)})
        self.state.settings.combination_base_indexes = None if len(remaining) == len(self.model.bases) else remaining

    def _invalidate_tdfd_correction(self, reason: str) -> None:
        if self.tdfd_correction_active:
            self.residuals = self._pre_tdfd_residuals
        self.tdfd_result = None
        self.tdfd_correction_active = False
        self.tdfd_correction_label = ""
        self.tdfd_correction_stale_reason = reason
        self._pre_tdfd_residuals = None

    def apply_tdfd_correction(self, result: TdfdResult) -> LightCurve:
        if result.corrected_residuals is None:
            raise ValueError("TDFD result does not contain corrected residuals")
        if not self.tdfd_correction_active:
            self._pre_tdfd_residuals = self.residuals
        self.tdfd_result = result
        self.residuals = result.corrected_residuals
        self.tdfd_correction_active = True
        self.tdfd_correction_stale_reason = ""
        label = "TDFD"
        base_index = result.selected_base_index
        if base_index is not None:
            label = f"TDFD f{base_index + 1}"
        self.tdfd_correction_label = label
        self._invalidate_periodogram()
        return self.residuals

    def clear_tdfd_correction(self) -> bool:
        if not self.tdfd_correction_active:
            self.tdfd_result = None
            self.tdfd_correction_label = ""
            self.tdfd_correction_stale_reason = ""
            self._pre_tdfd_residuals = None
            return False
        self.residuals = self._pre_tdfd_residuals
        self.tdfd_result = None
        self.tdfd_correction_active = False
        self.tdfd_correction_label = ""
        self.tdfd_correction_stale_reason = ""
        self._pre_tdfd_residuals = None
        self._invalidate_periodogram()
        return True

    def _write_work_inputs(self, model: FrequencyModel | None = None) -> None:
        model = model or self.model
        self.light_curve.save(self.state.work_dir / "lc.data")
        self.light_curve.save(self.state.work_dir / "resid.dat")
        np.savetxt(self.state.work_dir / "ttt", [[self.light_curve.time[0], self.light_curve.time[-1]]], fmt="%16.8f")
        model.write_freq_file(self.state.work_dir / "freq")

    def compute_periodogram(
        self,
        residuals: LightCurve | None = None,
        progress_callback=None,
        backend: str | None = None,
    ) -> PeriodogramResult:
        settings = self.state.settings
        result = compute_periodogram(
            residuals or self.residuals or self.light_curve,
            settings.start_frequency,
            settings.end_frequency,
            precision=settings.precision,
            backend=backend or settings.dft_backend,
            work_dir=self.state.work_dir,
            progress_callback=progress_callback,
        )
        self.last_periodogram = result
        if progress_callback is not None:
            progress_callback(99, "Classifying peak candidates")
        self.last_candidates = self._classify_periodogram_candidates(result)
        if progress_callback is not None:
            progress_callback(99, "Peak candidates ready")
        return result

    def component_path(self, base_index: int) -> Path:
        if base_index < 0:
            raise IndexError(base_index)
        return self.state.work_dir / f"resid{base_index + 1:02d}.dat"

    def component_light_curve(self, base_index: int) -> LightCurve | None:
        path = self.component_path(base_index)
        if not path.exists():
            return None
        data = np.loadtxt(path, usecols=(0, 1, 2))
        if data.ndim == 1:
            data = data.reshape(1, -1)
        return from_array(data, self.state.light_curve_path)

    def initial_candidates(self) -> list[FrequencyCandidate]:
        if self.last_periodogram is None:
            self.compute_periodogram()
        return self.last_candidates

    def add_independent(self, frequency: float) -> int:
        self._invalidate_tdfd_correction("Accepted frequencies changed")
        self.history.snapshot()
        index = self.model.add_independent(frequency)
        self._mark_report_stale()
        self._invalidate_periodogram()
        self.save_state()
        return index

    def add_combination(self, coefficients: tuple[int, ...]) -> int:
        self._invalidate_tdfd_correction("Accepted frequencies changed")
        self.history.snapshot()
        index = self.model.add_combination(coefficients)
        self._mark_report_stale()
        self._invalidate_periodogram()
        self.save_state()
        return index

    def set_base_frequency(self, index: int, frequency: float) -> None:
        self._invalidate_tdfd_correction("Accepted frequencies changed")
        self.history.snapshot()
        self.model.set_base_frequency(index, frequency)
        self._mark_report_stale()
        self._invalidate_periodogram()
        self.save_state()

    def remove_term(self, index: int) -> None:
        self._invalidate_tdfd_correction("Accepted frequencies changed")
        self.history.snapshot()
        self.model.remove_term(index)
        self._mark_report_stale()
        self._invalidate_periodogram()
        self.save_state()

    def remove_term_or_base(self, index: int) -> None:
        self._invalidate_tdfd_correction("Accepted frequencies changed")
        self.history.snapshot()
        base_index = self._identity_base_index_for_term(index)
        if base_index is None:
            self.model.remove_term(index)
        else:
            self.model.remove_base(base_index)
            self._remove_combination_base_index(base_index)
        self._mark_report_stale()
        self._invalidate_periodogram()
        self.save_state()

    def _identity_base_index_for_term(self, index: int) -> int | None:
        if index < 0 or index >= len(self.model.terms):
            raise IndexError(index)
        term = self.model.terms[index]
        nonzero = [(base_index, value) for base_index, value in enumerate(term) if value]
        if len(nonzero) == 1 and nonzero[0][1] == 1:
            return nonzero[0][0]
        return None

    def clear_frequencies(self) -> None:
        self._invalidate_tdfd_correction("Accepted frequencies changed")
        self.history.snapshot()
        self.model.clear()
        self.state.settings.combination_base_indexes = None
        self.residuals = self.light_curve
        self._mark_report_stale()
        self._invalidate_periodogram()
        self.save_state()

    def apply_observation_mask(self, keep_mask: np.ndarray) -> None:
        keep_mask = np.asarray(keep_mask, dtype=bool)
        if keep_mask.shape != (len(self.light_curve.time),):
            raise ValueError("observation mask must match the original light curve length")
        if not np.any(keep_mask):
            raise ValueError("observation mask would remove all points")
        self.light_curve = self.light_curve.masked(keep_mask)
        self.residuals = None
        self.tdfd_result = None
        self.tdfd_correction_active = False
        self.tdfd_correction_label = ""
        self.tdfd_correction_stale_reason = "Light curve mask changed"
        self._pre_tdfd_residuals = None
        self._mark_report_stale()
        self._invalidate_periodogram()
        self._reset_work_dir()
        self._write_work_inputs()
        self.save_state()

    def set_term_enabled(self, index: int, enabled: bool) -> None:
        self._invalidate_tdfd_correction("Accepted frequencies changed")
        self.history.snapshot()
        self.model.set_term_enabled(index, enabled)
        self._mark_report_stale()
        self._invalidate_periodogram()
        self.save_state()

    def undo(self) -> bool:
        changed = self.history.undo()
        if changed:
            self._invalidate_tdfd_correction("Accepted frequencies changed")
            self._mark_report_stale()
            self._invalidate_periodogram()
            self.save_state()
        return changed

    def redo(self) -> bool:
        changed = self.history.redo()
        if changed:
            self._invalidate_tdfd_correction("Accepted frequencies changed")
            self._mark_report_stale()
            self._invalidate_periodogram()
            self.save_state()
        return changed

    def fit_model(self, *, cstop: float = 0.005, refine_frequencies: bool = False) -> FitResult:
        self.clear_tdfd_correction()
        if self.model.is_empty or not self.model.active_terms():
            self.residuals = self.light_curve
            self._invalidate_periodogram()
            self.last_report = build_frequency_report(self.light_curve, self.model, fit_source="fixed")
            return FitResult(self.residuals, self.model.clone(), True, report=self.last_report)
        if not refine_frequencies:
            return self._fit_fixed_frequency_model()
        return self._fit_native_model(cstop=cstop)

    def _fit_fixed_frequency_model(self) -> FitResult:
        terms = self.model.active_terms()
        frequencies = np.asarray([self.model.frequency_for_term(term) for term in terms], dtype=float)
        if not np.all(np.isfinite(frequencies)):
            raise ValueError("model contains non-finite frequencies")

        columns = [np.ones_like(self.light_curve.time)]
        term_columns: list[tuple[np.ndarray, np.ndarray]] = []
        for frequency in frequencies:
            angle = 2.0 * np.pi * frequency * self.light_curve.time
            sin_col = np.sin(angle)
            cos_col = np.cos(angle)
            columns.extend([sin_col, cos_col])
            term_columns.append((sin_col, cos_col))

        design = np.column_stack(columns)
        weights = 1.0 / np.clip(self.light_curve.error, 1e-12, None)
        coef, *_ = np.linalg.lstsq(design * weights[:, None], self.light_curve.flux * weights, rcond=None)
        model_flux = design @ coef
        residuals = self.light_curve.with_flux(self.light_curve.flux - model_flux)

        self._reset_work_dir()
        self._write_work_inputs()
        residuals.save(self.state.work_dir / "resid.dat")
        self._write_component_residuals(terms, coef, term_columns)
        ampl_text = self._ampl_text(terms, frequencies, coef, residuals)
        (self.state.work_dir / "ampl").write_text(ampl_text)

        self.residuals = residuals
        self._invalidate_periodogram()
        self.save_state()
        self.last_report = build_frequency_report(self.light_curve, self.model, fit_source="fixed")
        return FitResult(
            residuals=residuals,
            model=self.model.clone(),
            converged=True,
            ampl_text=ampl_text,
            used_native=False,
            offset=float(coef[0]),
            fourier_terms=self._fourier_terms_from_coefficients(terms, frequencies, coef),
            report=self.last_report,
        )

    @staticmethod
    def _fourier_terms_from_coefficients(
        terms: list[tuple[int, ...]],
        frequencies: np.ndarray,
        coef: np.ndarray,
    ) -> tuple[FourierTerm, ...]:
        result: list[FourierTerm] = []
        for index, term in enumerate(terms):
            sin_coef = float(coef[1 + 2 * index])
            cos_coef = float(coef[2 + 2 * index])
            amplitude = float(np.hypot(sin_coef, cos_coef))
            phase = float(np.arctan2(cos_coef, sin_coef))
            result.append(
                FourierTerm(
                    term=tuple(term),
                    frequency=float(frequencies[index]),
                    sin_coefficient=sin_coef,
                    cos_coefficient=cos_coef,
                    amplitude=amplitude,
                    phase=phase,
                )
            )
        return tuple(result)

    def _write_component_residuals(
        self,
        terms: list[tuple[int, ...]],
        coef: np.ndarray,
        term_columns: list[tuple[np.ndarray, np.ndarray]],
    ) -> None:
        for base_index in range(len(self.model.bases)):
            model_flux = np.full_like(self.light_curve.flux, coef[0], dtype=float)
            for term_index, term in enumerate(terms):
                total_order = sum(abs(value) for value in term)
                only_this_base = term[base_index] != 0 and total_order == abs(term[base_index])
                if only_this_base:
                    continue
                sin_col, cos_col = term_columns[term_index]
                model_flux += coef[1 + 2 * term_index] * sin_col + coef[2 + 2 * term_index] * cos_col
            component = self.light_curve.with_flux(self.light_curve.flux - model_flux)
            component.save(self.component_path(base_index))

    def _ampl_text(
        self,
        terms: list[tuple[int, ...]],
        frequencies: np.ndarray,
        coef: np.ndarray,
        residuals: LightCurve,
    ) -> str:
        lines = [
            "Data file : lc.data",
            f"           a0: {coef[0]:12.6f}",
            f"Nobs:  {len(self.light_curve.time):8d}",
            f"SDEV:  {float(np.std(residuals.flux)):12.6f}",
        ]
        for index, frequency in enumerate(self.model.bases, start=1):
            lines.append(f"Basic fr. #{index:3d}: {frequency:12.7f}")
        for index, frequency in enumerate(frequencies, start=1):
            lines.append(f"Frequency #{index:3d}: {frequency:13.7f}")
        for index, term in enumerate(terms, start=1):
            sin_coef = coef[1 + 2 * (index - 1)]
            cos_coef = coef[2 + 2 * (index - 1)]
            amplitude = float(np.hypot(sin_coef, cos_coef))
            phase = float(np.arctan2(cos_coef, sin_coef))
            lines.append(f"Ampl. #{index:3d}: {amplitude:11.6f}")
            lines.append(f"Phase #{index:3d}: {phase:11.6f}")
            lines.append(f"Term #{index:3d}: {' '.join(str(value) for value in term)}")
        return "\n".join(lines) + "\n"

    def _fit_native_model(self, *, cstop: float = 0.005) -> FitResult:
        try:
            tools = self._ensure_tools()
        except NativeBuildError as exc:
            raise RuntimeError(str(exc)) from exc

        self._reset_work_dir()
        self._write_work_inputs()
        env = {"PATH": f"{tools.as_env_path()}:{Path.cwd()}", **dict()}
        stderr_parts: list[str] = []
        for command in ([tools.hars_sin], [tools.hars_ite, str(cstop)], [tools.uf2]):
            completed = subprocess.run(
                [str(item) for item in command],
                cwd=self.state.work_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=None,
            )
            stderr_parts.append(completed.stderr)
            if completed.returncode != 0:
                raise RuntimeError(f"{Path(str(command[0])).name} failed:\n{completed.stderr or completed.stdout}")

        resid_path = self.state.work_dir / "resid.dat"
        residuals = from_array(np.loadtxt(resid_path, usecols=(0, 1, 2)), self.state.light_curve_path)
        self.residuals = residuals
        if (self.state.work_dir / "freq").exists():
            self.history.current = FrequencyModel.from_freq_file(self.state.work_dir / "freq")
        self._invalidate_periodogram()
        self.save_state()
        err_path = self.state.work_dir / "hars-ite.err"
        converged = not err_path.exists() or err_path.read_text().strip() == "0"
        ampl_text = (self.state.work_dir / "ampl").read_text() if (self.state.work_dir / "ampl").exists() else ""
        offset, fourier_terms = self._fourier_terms_from_ampl_text(ampl_text)
        self.last_report = build_frequency_report(self.light_curve, self.model, fit_source="native-refine")
        return FitResult(
            residuals=residuals,
            model=self.model.clone(),
            converged=converged,
            ampl_text=ampl_text,
            stderr="\n".join(stderr_parts),
            used_native=True,
            offset=offset,
            fourier_terms=fourier_terms,
            report=self.last_report,
        )

    @staticmethod
    def _fourier_terms_from_ampl_text(ampl_text: str) -> tuple[float, tuple[FourierTerm, ...]]:
        offset = 0.0
        frequencies: dict[int, float] = {}
        amplitudes: dict[int, float] = {}
        phases: dict[int, float] = {}
        terms: dict[int, tuple[int, ...]] = {}
        for raw_line in ampl_text.splitlines():
            line = raw_line.strip()
            if line.startswith("a0:"):
                try:
                    offset = float(line.split(":", 1)[1].split()[0])
                except (IndexError, ValueError):
                    offset = 0.0
            elif line.startswith("Frequency #"):
                try:
                    left, right = line.split(":", 1)
                    index = int(left.split("#", 1)[1])
                    frequencies[index] = float(right.split()[0])
                except (IndexError, ValueError):
                    continue
            elif line.startswith("Ampl. #"):
                try:
                    left, right = line.split(":", 1)
                    index = int(left.split("#", 1)[1])
                    amplitudes[index] = float(right.split()[0])
                except (IndexError, ValueError):
                    continue
            elif line.startswith("Phase #"):
                try:
                    left, right = line.split(":", 1)
                    index = int(left.split("#", 1)[1])
                    phases[index] = float(right.split()[0])
                except (IndexError, ValueError):
                    continue
            elif line.startswith("Term #"):
                try:
                    left, right = line.split(":", 1)
                    index = int(left.split("#", 1)[1])
                    terms[index] = tuple(int(value) for value in right.split())
                except (IndexError, ValueError):
                    continue

        parsed: list[FourierTerm] = []
        for index, term in sorted(terms.items()):
            amplitude = amplitudes.get(index)
            phase = phases.get(index)
            frequency = frequencies.get(index)
            if amplitude is None or phase is None or frequency is None:
                continue
            sin_coef = float(amplitude * np.cos(phase))
            cos_coef = float(amplitude * np.sin(phase))
            parsed.append(
                FourierTerm(
                    term=term,
                    frequency=float(frequency),
                    sin_coefficient=sin_coef,
                    cos_coefficient=cos_coef,
                    amplitude=float(amplitude),
                    phase=float(phase),
                )
            )
        return offset, tuple(parsed)

    def iterate_after_model_change(self, progress_callback=None) -> tuple[FitResult, PeriodogramResult, list[FrequencyCandidate]]:
        fit = self.fit_model()
        periodogram = self.compute_periodogram(fit.residuals, progress_callback=progress_callback)
        return fit, periodogram, self.last_candidates

    def export_legacy(self, directory: str | Path | None = None) -> Path:
        target = self.state.export_legacy(directory)
        if self.residuals is not None:
            self.residuals.save(target.parent / "resid.dat")
        if self.last_periodogram is not None:
            np.savetxt(
                target.parent / "periodogram.dat",
                np.column_stack([self.last_periodogram.frequency, self.last_periodogram.amplitude]),
                fmt="%12.6f %12.6f",
            )
        ampl = self.state.work_dir / "ampl"
        if ampl.exists():
            shutil.copy2(ampl, target.parent / "ampl")
        return target
