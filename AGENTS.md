# AGENTS.md

Instructions for coding agents working in this repository. Scope: the entire repository tree.

## Project Summary

lcView is a PySide6 desktop GUI for light-curve DFT, phase folding, and prewhitening.
The active application lives under `src/lcview`; `scripts/` contains legacy PyQt/tools and
should not be changed unless the task explicitly targets legacy behavior.

## Repository Layout

- `src/lcview/app.py` - CLI entry points for GUI and batch prewhitening.
- `src/lcview/core/` - light curves, DFT/periodogram, phase folding, frequency models, prewhitening.
- `src/lcview/ui/` - PySide6 windows, panels, widgets, table models, and pyqtgraph plot wrappers.
- `src/lcview/native/` - bundled C/Fortran native tools and build helper.
- `src/lcview/resources/` - QSS styles and packaged reference data.
- `tests/` - pytest tests, including offscreen Qt smoke tests.
- `scripts/` - legacy application/scripts kept for reference and compatibility.

## Environment

Prefer the conda environment named `lcView-env`.

```bash
conda run -n lcView-env pytest
conda run -n lcView-env python -m compileall -q src tests
```

Run the GUI from the repository root:

```bash
./lcView.sh
```

or inside the environment:

```bash
lcview
lcview path/to/lightcurve.dat
```

If host `python` lacks `PySide6`, do not treat that as a project failure; use `conda run -n lcView-env ...`.

## Validation

- Prefer focused tests for the code path first, then the full suite when feasible.
- Standard full check after Python changes:
  `conda run -n lcView-env pytest`
- Standard syntax check:
  `conda run -n lcView-env python -m compileall -q src tests`
- GUI tests use `QT_QPA_PLATFORM=offscreen` in test files. Keep that pattern for Qt tests.
- If a check cannot be run, report the exact command and reason.

## UI Synchronization Rules

lcView has coupled UI state. When changing tables, sorting, candidates, selection, phase controls,
or plots, verify the full chain:

`candidate/frequency table -> selected_frequency -> DFT selected marker -> phase controls -> status label`

Concrete expectations:

- Programmatic candidate updates must keep the visible selected row and `MainWindow.selected_frequency` aligned.
- If candidate sorting changes, the DFT marker must move to the same candidate selected in the table.
- If a click on the DFT plot inserts a candidate into the table, preserve that clicked candidate as selected even after sorting.
- If there are no candidates, only then fall back to `periodogram.best_frequency`.
- Plot refreshes must not leave stale selected markers from a previous frequency.
- DFT plot overlay toggles (`5 S/N`, accepted markers, peak markers, daily/yearly aliases) must update only plot layers, not restart DFT or fit workers.
- Editing an accepted base frequency must update derived harmonics/combinations, `selected_frequency`, DFT markers, phase controls, and then refresh fit + residual DFT.
- Changes to phase period/frequency controls must keep period and frequency synchronized.
- Phase-plot overlays (`Smooth`, errors, hide raw) should update both the Phase tab and frequency preview when their controls change.
- The `Frequency views` tab must expose its own phase controls synced with the main Phase controls.
- The `Sin/cos fit` overlays must render fitted Fourier/prewhitening parameters, not refit the currently plotted phase points.
- The phase sin/cos fit should include accepted harmonics that are integer multiples of the current phase frequency.
- Sigma clipping must preview proposed rejected points and let the user change the rejection mask before data is mutated; keep table checkboxes and plot box-selection synchronized.
- `Mag axis` is display-only Y inversion for brightness plots; do not negate or transform stored flux/magnitude values or model inputs.

## Prewhitening Performance Rules

- `Fit model` should stay fast: fit amplitudes/phases at accepted frequencies and do not recompute DFT implicitly.
- Adding an accepted frequency should run the full iteration: fit amplitudes/phases, refresh residual DFT, and refresh peak candidates.
- Manual full DFT refresh is explicit through `Calculate DFT`; after fit-only changes, stale peak candidates/DFT data should be cleared or clearly marked stale.
- DFT must use native `fwpeaks` by default. Do not silently fall back to Python DFT when `fwpeaks` fails.
- Python DFT is allowed only when the user explicitly selects the Python backend in the GUI or passes the explicit CLI option.
- Peak candidate classification must stay fast for many accepted frequencies; do not restore exhaustive 4-term combination scans as a default GUI path.
- Nonlinear frequency optimization belongs behind the explicit `Refine frequencies` action because native refinement can be slow or fragile for multi-frequency models.
- When changing fit/refine behavior, test both the numerical core and the GUI worker contract so slow DFT work does not return to the default fit path.

## Input File Rules

- Light-curve loading should support whitespace, CSV, TSV, and semicolon-separated tables.
- Preserve support for headerless three-column files.
- If a GUI-loaded table has more than three columns, show a column-selection dialog before creating the engine.
- Header names, including comment headers like `# time mag err`, should be used to suggest time/flux/error columns.

## Change Rules

- Keep changes focused and local; do not do unrelated cleanup.
- Preserve current PySide6 signal/slot patterns unless there is a concrete bug.
- Do not add new frameworks, formatters, linters, package managers, or heavy dependencies without explicit approval.
- Do not rewrite native or legacy `scripts/` code unless specifically asked.
- Treat native tool build behavior carefully; these tools may compile into `~/.cache/lcview/native`.
- Do not commit generated caches, compiled native binaries, temporary DFT output, or local environment files.

## Testing Expectations

- UI state, table sorting, selection, marker, or phase-control changes need tests that verify the dependent UI state, not only the changed widget.
- Table model changes belong in `tests/test_ui_models.py` unless they need a full `MainWindow`.
- End-to-end UI state changes belong in `tests/test_main_window_smoke.py`.
- Core numerical behavior belongs in the relevant `tests/test_*.py` file for `core/`.
- Prefer deterministic fixtures from `tests/fixtures/` over new large data files.
- Mock or isolate slow/native-heavy paths where the existing tests already do so.

## Git and Documentation

- The working tree may be dirty. Never revert unrelated user changes.
- Stage selectively if asked to commit.
- Do not use destructive git commands such as `git reset --hard`.
- Update `README.md` only when run/install/user-facing behavior changes.
