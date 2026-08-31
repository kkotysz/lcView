# lcView — Light-Curve Analysis Workbench

[![CI](https://github.com/kkotysz/lcView/actions/workflows/ci.yml/badge.svg)](https://github.com/kkotysz/lcView/actions/workflows/ci.yml)

A desktop and command-line scientific application for **time-series analysis of astronomical light curves**, with interactive DFT inspection, iterative prewhitening, phase analysis, detrending, sigma clipping and model fitting.

The current application is built with `Python`, `PySide6`, `NumPy`, `SciPy`, `Pandas`, `Astropy` and `pyqtgraph`, while selected numerical routines are provided by bundled **C and Fortran legacy engines** that are compiled on demand.

## Engineering highlights

lcView is also a modernization project: it takes an older collection of research scripts and native numerical tools and turns them into a structured, testable Python application.

- **Scientific computing** — periodograms, frequency modelling, prewhitening, phase folding, detrending and time-dependent frequency analysis.
- **Legacy modernization** — older PyQt5 scripts are retained for reference while the maintained application lives in a modern `src/` package layout.
- **Python + native-code integration** — bundled C and Fortran routines are compiled automatically into a user cache and used as numerical backends.
- **GUI + CLI workflows** — interactive PySide6 workbench plus a batch `lcview-prewhiten` command.
- **Reproducible packaging** — `pyproject.toml`, console entry points and a documented Conda environment.
- **Automated tests** — unit tests cover core numerical logic, file loading, UI models and smoke-level GUI workflows.
- **Multiple input formats** — whitespace-separated, CSV, TSV and semicolon-separated light curves with automatic or interactive column selection.

## Architecture

The maintained implementation is split into several layers:

```text
src/lcview/core/      scientific and time-series algorithms
src/lcview/ui/        PySide6 interface
src/lcview/native/    C and Fortran numerical engines + build helper
src/lcview/legacy/    compatibility/parsing support
tests/                numerical, parsing and UI tests
scripts/              original/legacy research scripts
```

This separation makes it possible to test scientific logic independently of the GUI while still preserving and integrating trusted legacy routines.

## Installation

```bash
git clone https://github.com/kkotysz/lcView.git
cd lcView
conda env create -f lcView-env.yml
conda activate lcView
pip install -e .
```

If the environment already exists:

```bash
conda activate lcView
conda env update -f lcView-env.yml --prune
pip install -e .
```

## Running

Launch the GUI:

```bash
lcview
```

Open a light curve directly:

```bash
lcview path/to/lightcurve.dat
```

Batch prewhitening:

```bash
lcview-prewhiten path/to/lightcurve.dat \
  --start 0 --end 80 --precision 10 --export output/
```

The repository also includes a convenience launcher:

```bash
./lcView.sh
```

## Native numerical backends

The bundled native tools include:

- `fwpeaks`
- `hars-sin`
- `hars-ite`
- `smart-uf-fina-smars`
- `uf2`

They are compiled automatically into:

```text
~/.cache/lcview/native
```

A rebuild can be triggered manually with:

```bash
python -m lcview.native.build
```

DFT uses the native `fwpeaks` backend by default. A slower Python implementation can be selected explicitly:

```bash
lcview --dft-backend python path/to/lightcurve.dat
lcview-prewhiten --dft-backend python path/to/lightcurve.dat
```

## Main analysis workflow

The application supports an iterative workflow commonly used for variable-star and pulsation analysis:

1. load and inspect a light curve,
2. calculate the DFT/periodogram,
3. inspect candidate peaks and S/N,
4. accept or edit frequencies,
5. fit the multi-frequency model,
6. inspect residuals,
7. recalculate the residual DFT,
8. analyse phase curves and frequency combinations.

Additional tools include sigma clipping, detrending, harmonic terms, daily/yearly alias markers and time-dependent frequency analysis.

## Input handling

Supported input formats include:

- whitespace-separated text,
- CSV,
- TSV,
- semicolon-separated files.

Headered files are supported. When a file contains more than three candidate data columns, the GUI asks the user to select time, flux/magnitude and uncertainty columns.

## Tests

Run the test suite with:

```bash
python -m pip install -e '.[dev]'
pytest -q
```

A compile-only sanity check is also useful:

```bash
python -m compileall -q src
```

The test suite includes numerical tests for frequency models and prewhitening as well as parsing, UI-model and GUI smoke tests.

## Project status

lcView is an actively maintained scientific-software project focused on turning practical astronomical analysis workflows and established legacy numerical code into a cleaner, reusable and testable application.
