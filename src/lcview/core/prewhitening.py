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
from .session import SessionState


@dataclass
class FitResult:
    residuals: LightCurve
    model: FrequencyModel
    converged: bool
    ampl_text: str = ""
    stderr: str = ""


@dataclass
class PrewhiteningEngine:
    state: SessionState
    light_curve: LightCurve = field(init=False)
    history: FrequencyHistory = field(init=False)
    tools: NativeTools | None = field(default=None, init=False)
    last_periodogram: PeriodogramResult | None = None
    last_candidates: list[FrequencyCandidate] = field(default_factory=list)
    residuals: LightCurve | None = None

    def __post_init__(self) -> None:
        self.light_curve = read_light_curve(self.state.light_curve_path).centered_time()
        self.history = FrequencyHistory(current=self.state.frequency_model.clone())
        self.state.work_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_file(cls, path: str | Path) -> "PrewhiteningEngine":
        return cls(SessionState.for_light_curve(path))

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

    def _write_work_inputs(self, model: FrequencyModel | None = None) -> None:
        model = model or self.model
        self.light_curve.save(self.state.work_dir / "lc.data")
        self.light_curve.save(self.state.work_dir / "resid.dat")
        np.savetxt(self.state.work_dir / "ttt", [[self.light_curve.time[0], self.light_curve.time[-1]]], fmt="%16.8f")
        model.write_freq_file(self.state.work_dir / "freq")

    def compute_periodogram(self, residuals: LightCurve | None = None, progress_callback=None) -> PeriodogramResult:
        settings = self.state.settings
        result = compute_periodogram(
            residuals or self.residuals or self.light_curve,
            settings.start_frequency,
            settings.end_frequency,
            precision=settings.precision,
            work_dir=self.state.work_dir,
            progress_callback=progress_callback,
        )
        self.last_periodogram = result
        self.last_candidates = candidates_from_peaks(result.peaks, self.model, self.light_curve.baseline)
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

    def add_independent(self, frequency: float) -> None:
        self.history.snapshot()
        self.model.add_independent(frequency)
        self.save_state()

    def add_combination(self, coefficients: tuple[int, ...]) -> None:
        self.history.snapshot()
        self.model.add_combination(coefficients)
        self.save_state()

    def remove_term(self, index: int) -> None:
        self.history.snapshot()
        self.model.remove_term(index)
        self.save_state()

    def clear_frequencies(self) -> None:
        self.history.snapshot()
        self.model.clear()
        self.residuals = self.light_curve
        self.save_state()

    def set_term_enabled(self, index: int, enabled: bool) -> None:
        self.history.snapshot()
        self.model.set_term_enabled(index, enabled)
        self.save_state()

    def undo(self) -> bool:
        changed = self.history.undo()
        if changed:
            self.save_state()
        return changed

    def redo(self) -> bool:
        changed = self.history.redo()
        if changed:
            self.save_state()
        return changed

    def fit_model(self, *, cstop: float = 0.005) -> FitResult:
        if self.model.is_empty or not self.model.active_terms():
            self.residuals = self.light_curve
            return FitResult(self.residuals, self.model.clone(), True)
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
        self.save_state()
        err_path = self.state.work_dir / "hars-ite.err"
        converged = not err_path.exists() or err_path.read_text().strip() == "0"
        ampl_text = (self.state.work_dir / "ampl").read_text() if (self.state.work_dir / "ampl").exists() else ""
        return FitResult(residuals=residuals, model=self.model.clone(), converged=converged, ampl_text=ampl_text, stderr="\n".join(stderr_parts))

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
