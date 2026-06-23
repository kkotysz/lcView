"""Persistent lcView session state."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json

from .frequency_model import FrequencyModel


def _combination_base_indexes_from_value(value) -> list[int] | None:
    if value is None:
        return None
    try:
        iterator = iter(value)
    except TypeError:
        return None
    indexes: set[int] = set()
    for item in iterator:
        try:
            index = int(item)
        except (TypeError, ValueError):
            continue
        if index >= 0:
            indexes.add(index)
    return sorted(indexes)


@dataclass
class SessionSettings:
    start_frequency: float = 0.0
    end_frequency: float = 80.0
    precision: float = 10.0
    dft_backend: str = "fwpeaks"
    show_dft_log_amplitude: bool = False
    show_dft_nyquist: bool = True
    show_dft_snr_spectrum: bool = False
    show_dft_spectral_window: bool = False
    use_dft_adaptive_snr: bool = True
    show_dft_snr5: bool = True
    show_dft_accepted_markers: bool = True
    show_dft_peak_markers: bool = True
    show_dft_daily_aliases: bool = False
    show_dft_yearly_aliases: bool = False
    show_light_curve_errors: bool = False
    invert_y_axis: bool = False
    show_tdfd_legend: bool = True
    time_column: int | None = None
    flux_column: int | None = None
    error_column: int | None = None
    points_in_bin: float = 20.0
    sigma: float = 3.5
    tdfd_bins: int = 20
    tdfd_source: str = "residual"
    tdfd_auto_window: bool = True
    tdfd_window_points: int = 0
    tdfd_step_points: int = 0
    tdfd_selected_base_index: int | None = None
    combination_base_indexes: list[int] | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "SessionSettings":
        settings = cls()
        for key in settings.__dataclass_fields__:
            if key in data:
                if key == "combination_base_indexes":
                    settings.combination_base_indexes = _combination_base_indexes_from_value(data[key])
                else:
                    setattr(settings, key, data[key])
        return settings

    def to_dict(self) -> dict:
        return {
            "start_frequency": self.start_frequency,
            "end_frequency": self.end_frequency,
            "precision": self.precision,
            "dft_backend": self.dft_backend,
            "show_dft_log_amplitude": self.show_dft_log_amplitude,
            "show_dft_nyquist": self.show_dft_nyquist,
            "show_dft_snr_spectrum": self.show_dft_snr_spectrum,
            "show_dft_spectral_window": self.show_dft_spectral_window,
            "use_dft_adaptive_snr": self.use_dft_adaptive_snr,
            "show_dft_snr5": self.show_dft_snr5,
            "show_dft_accepted_markers": self.show_dft_accepted_markers,
            "show_dft_peak_markers": self.show_dft_peak_markers,
            "show_dft_daily_aliases": self.show_dft_daily_aliases,
            "show_dft_yearly_aliases": self.show_dft_yearly_aliases,
            "show_light_curve_errors": self.show_light_curve_errors,
            "invert_y_axis": self.invert_y_axis,
            "show_tdfd_legend": self.show_tdfd_legend,
            "time_column": self.time_column,
            "flux_column": self.flux_column,
            "error_column": self.error_column,
            "points_in_bin": self.points_in_bin,
            "sigma": self.sigma,
            "tdfd_bins": self.tdfd_bins,
            "tdfd_source": self.tdfd_source,
            "tdfd_auto_window": self.tdfd_auto_window,
            "tdfd_window_points": self.tdfd_window_points,
            "tdfd_step_points": self.tdfd_step_points,
            "tdfd_selected_base_index": self.tdfd_selected_base_index,
            "combination_base_indexes": _combination_base_indexes_from_value(self.combination_base_indexes),
        }


@dataclass
class SessionState:
    light_curve_path: Path
    session_dir: Path
    frequency_model: FrequencyModel = field(default_factory=FrequencyModel.empty)
    settings: SessionSettings = field(default_factory=SessionSettings)

    @property
    def json_path(self) -> Path:
        return self.session_dir / "session.json"

    @property
    def work_dir(self) -> Path:
        return self.session_dir / "work"

    @classmethod
    def for_light_curve(cls, light_curve_path: str | Path) -> "SessionState":
        light_curve_path = Path(light_curve_path).resolve()
        session_dir = light_curve_path.parent / ".lcview" / light_curve_path.name
        state = cls(light_curve_path=light_curve_path, session_dir=session_dir)
        state.session_dir.mkdir(parents=True, exist_ok=True)
        state.work_dir.mkdir(parents=True, exist_ok=True)
        freq_path = light_curve_path.parent / "freq"
        if freq_path.exists():
            state.frequency_model = FrequencyModel.from_freq_file(freq_path)
        if state.json_path.exists():
            state = cls.load(state.json_path)
        return state

    @classmethod
    def load(cls, path: str | Path) -> "SessionState":
        path = Path(path)
        data = json.loads(path.read_text())
        state = cls(
            light_curve_path=Path(data["light_curve_path"]),
            session_dir=path.parent,
            frequency_model=FrequencyModel.from_json_dict(data.get("frequency_model", {})),
            settings=SessionSettings.from_dict(data.get("settings", {})),
        )
        state.work_dir.mkdir(parents=True, exist_ok=True)
        return state

    def save(self) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.json_path.write_text(
            json.dumps(
                {
                    "light_curve_path": str(self.light_curve_path),
                    "frequency_model": self.frequency_model.to_json_dict(),
                    "settings": self.settings.to_dict(),
                },
                indent=2,
            )
        )

    def export_legacy(self, directory: str | Path | None = None) -> Path:
        directory = Path(directory) if directory else self.light_curve_path.parent
        directory.mkdir(parents=True, exist_ok=True)
        freq_path = directory / "freq"
        self.frequency_model.write_freq_file(freq_path)
        return freq_path
