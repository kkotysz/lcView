"""In-memory model for the legacy `freq` file."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
import copy
import json
import numpy as np


def _pad_coefficients(coefficients: Iterable[int], size: int) -> tuple[int, ...]:
    values = [int(v) for v in coefficients]
    if len(values) > size:
        raise ValueError("too many coefficients for the current number of base frequencies")
    values.extend([0] * (size - len(values)))
    return tuple(values)


@dataclass
class FrequencyModel:
    bases: list[float] = field(default_factory=list)
    terms: list[tuple[int, ...]] = field(default_factory=list)
    disabled_terms: set[int] = field(default_factory=set)

    @classmethod
    def empty(cls) -> "FrequencyModel":
        return cls()

    @classmethod
    def from_freq_text(cls, text: str) -> "FrequencyModel":
        lines = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        if not lines:
            return cls.empty()
        header = np.fromstring(lines[0], dtype=int, sep=" ")
        if header.size < 2:
            raise ValueError("freq header must contain `<norig> <nall>`")
        norig, nall = int(header[0]), int(header[1])
        if len(lines) < 1 + norig:
            raise ValueError("freq file ended before all base frequencies were read")
        bases = [float(np.fromstring(lines[i], dtype=float, sep=" ")[0]) for i in range(1, 1 + norig)]
        terms: list[tuple[int, ...]] = []
        for line in lines[1 + norig : 1 + norig + nall]:
            coeffs = np.fromstring(line, dtype=int, sep=" ")
            terms.append(_pad_coefficients(coeffs.tolist(), norig))
        model = cls(bases=bases, terms=terms)
        model.ensure_identity_terms()
        return model

    @classmethod
    def from_freq_file(cls, path: str | Path) -> "FrequencyModel":
        return cls.from_freq_text(Path(path).read_text())

    @classmethod
    def from_json_dict(cls, data: dict) -> "FrequencyModel":
        return cls(
            bases=[float(v) for v in data.get("bases", [])],
            terms=[tuple(int(x) for x in row) for row in data.get("terms", [])],
            disabled_terms={int(i) for i in data.get("disabled_terms", [])},
        )

    def to_json_dict(self) -> dict:
        return {
            "bases": self.bases,
            "terms": [list(row) for row in self.terms],
            "disabled_terms": sorted(self.disabled_terms),
        }

    def clone(self) -> "FrequencyModel":
        return copy.deepcopy(self)

    @property
    def is_empty(self) -> bool:
        return not self.bases

    def identity_term(self, index: int) -> tuple[int, ...]:
        values = [0] * len(self.bases)
        values[index] = 1
        return tuple(values)

    def ensure_identity_terms(self) -> None:
        for idx in range(len(self.bases)):
            identity = self.identity_term(idx)
            if identity not in self.terms:
                self.terms.insert(idx, identity)

    def add_independent(self, frequency: float) -> int:
        self.bases.append(float(frequency))
        self.terms = [tuple(list(term) + [0]) for term in self.terms]
        self.terms.append(self.identity_term(len(self.bases) - 1))
        return len(self.bases) - 1

    def add_combination(self, coefficients: Iterable[int]) -> int:
        if not self.bases:
            raise ValueError("cannot add a combination without base frequencies")
        term = _pad_coefficients(coefficients, len(self.bases))
        if not any(term):
            raise ValueError("combination coefficients cannot all be zero")
        if term not in self.terms:
            self.terms.append(term)
        return self.terms.index(term)

    def clear(self) -> None:
        self.bases.clear()
        self.terms.clear()
        self.disabled_terms.clear()

    def remove_term(self, index: int) -> None:
        if index < 0 or index >= len(self.terms):
            raise IndexError(index)
        del self.terms[index]
        self.disabled_terms = {i - 1 if i > index else i for i in self.disabled_terms if i != index}
        self.ensure_identity_terms()

    def remove_base(self, index: int) -> None:
        if index < 0 or index >= len(self.bases):
            raise IndexError(index)
        del self.bases[index]
        new_terms: list[tuple[int, ...]] = []
        for term in self.terms:
            if term[index] != 0:
                continue
            new_terms.append(tuple(v for i, v in enumerate(term) if i != index))
        self.terms = []
        self.disabled_terms = set()
        for term in new_terms:
            if any(term) and term not in self.terms:
                self.terms.append(term)
        self.ensure_identity_terms()

    def set_term_enabled(self, index: int, enabled: bool) -> None:
        if enabled:
            self.disabled_terms.discard(index)
        else:
            self.disabled_terms.add(index)

    def active_terms(self) -> list[tuple[int, ...]]:
        return [term for idx, term in enumerate(self.terms) if idx not in self.disabled_terms]

    def frequency_for_term(self, term: Iterable[int]) -> float:
        coeffs = _pad_coefficients(term, len(self.bases))
        return float(np.dot(np.asarray(coeffs, dtype=float), np.asarray(self.bases, dtype=float)))

    def label_for_term(self, term: Iterable[int]) -> str:
        coeffs = _pad_coefficients(term, len(self.bases))
        parts: list[str] = []
        for idx, coeff in enumerate(coeffs, start=1):
            if coeff == 0:
                continue
            sign = "-" if coeff < 0 else "+"
            magnitude = abs(coeff)
            body = f"f{idx}" if magnitude == 1 else f"{magnitude}f{idx}"
            if not parts:
                parts.append(body if sign == "+" else f"-{body}")
            else:
                parts.append(f" {sign} {body}")
        return "".join(parts) if parts else "0"

    def rows(self) -> list[dict]:
        rows: list[dict] = []
        for idx, term in enumerate(self.terms):
            rows.append(
                {
                    "index": idx,
                    "frequency": self.frequency_for_term(term),
                    "label": self.label_for_term(term),
                    "coefficients": term,
                    "enabled": idx not in self.disabled_terms,
                    "kind": "independent" if sum(abs(x) for x in term) == 1 and max(term) == 1 else "combination",
                }
            )
        return rows

    def to_freq_text(self, active_only: bool = True) -> str:
        terms = self.active_terms() if active_only else list(self.terms)
        lines = [f"{len(self.bases):5d} {len(terms):4d}"]
        lines.extend(f"{freq:12.6f}" for freq in self.bases)
        width = max(1, len(self.bases))
        for term in terms:
            padded = _pad_coefficients(term, width)
            lines.append("".join(f"{value:4d}" for value in padded))
        return "\n".join(lines) + "\n"

    def write_freq_file(self, path: str | Path, active_only: bool = True) -> None:
        Path(path).write_text(self.to_freq_text(active_only=active_only))


@dataclass
class FrequencyHistory:
    current: FrequencyModel = field(default_factory=FrequencyModel.empty)
    undo_stack: list[FrequencyModel] = field(default_factory=list)
    redo_stack: list[FrequencyModel] = field(default_factory=list)

    def snapshot(self) -> None:
        self.undo_stack.append(self.current.clone())
        self.redo_stack.clear()

    def set(self, model: FrequencyModel) -> None:
        self.snapshot()
        self.current = model.clone()

    def undo(self) -> bool:
        if not self.undo_stack:
            return False
        self.redo_stack.append(self.current.clone())
        self.current = self.undo_stack.pop()
        return True

    def redo(self) -> bool:
        if not self.redo_stack:
            return False
        self.undo_stack.append(self.current.clone())
        self.current = self.redo_stack.pop()
        return True

    def to_json(self) -> str:
        return json.dumps(self.current.to_json_dict(), indent=2)
