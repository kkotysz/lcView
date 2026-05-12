# lcView

lcView is now packaged as a PySide6 application with a Python prewhitening backend.
The legacy PyQt5 scripts are kept in `scripts/`, while the new application lives in
`src/lcview`.

## Installation

```bash
# from a fresh clone
git clone <repo-url> lcView
cd lcView

# create the conda environment and install lcView in editable mode
conda env create -f lcView-env.yml
conda activate lcView-env
```

If the environment already exists, update it instead:

```bash
conda activate lcView-env
conda env update -f lcView-env.yml --prune
pip install -e .
```

The environment installs `PySide6`, `pyqtgraph`, scientific Python dependencies,
`pytest`, and conda-forge C/Fortran compilers used to build the native legacy
engines.

## Running

Start the GUI from the repository root:

```bash
./lcView.sh
```

or, after activating the environment:

```bash
lcview
lcview path/to/lightcurve.dat
```

Input light curves may be whitespace-separated, CSV, TSV, or semicolon-separated.
Files with headers are supported, including comment headers like `# time mag err`.
When a GUI-loaded file has more than three columns, lcView asks which columns to
use for time, flux/magnitude, and error.

The bundled native tools (`fwpeaks`, `hars-sin`, `hars-ite`, `smart-uf-fina-smars`,
`uf2`) are compiled automatically into `~/.cache/lcview/native` when first needed.
You can force a rebuild from the GUI menu or with:

```bash
python -m lcview.native.build
```

Batch prewhitening mode:

```bash
lcview-prewhiten path/to/lightcurve.dat --start 0 --end 80 --precision 10 --export output/
```

DFT uses native `fwpeaks` by default. The slower Python DFT implementation is never
used as an implicit fallback; select it explicitly only when needed:

```bash
lcview --dft-backend python path/to/lightcurve.dat
lcview-prewhiten --dft-backend python path/to/lightcurve.dat
```

## GUI Workflow Notes

- `Fit model` updates residuals at the accepted frequencies without recomputing the DFT.
- Adding a frequency from `Current peak candidates` runs fit and then refreshes the residual DFT automatically.
- In `Accepted frequencies`, double-click an editable `Frequency` or `Period` cell to change a base frequency.
- Use `Calculate DFT` to refresh the residual periodogram and repopulate peak candidates.
- The DFT tab can show a dashed global `5 S/N` amplitude threshold, accepted/peak markers, and optional daily/yearly alias markers.
- Use `Mag axis` on the Light curve tab to invert brightness plots for magnitude data; calculations still use original values.
- Use `Refine frequencies` only when you explicitly want slower nonlinear frequency optimization.
- On the Phase tab, `Sin/cos fit` overlays the fitted Fourier model parameters and includes accepted harmonic terms automatically.
- In `Frequency views`, phase controls are available in the tab and `Sin/cos fit` overlays the same Fourier model on both the time plot and folded phase plot.
- `Sigma clip` opens a preview dialog; confirm or uncheck individual proposed rejected points before applying it.
- In the sigma-clipping preview, drag a rectangle on the plot to mass-mark points using `Box: reject` or `Box: keep`.

## Checking the Install

```bash
conda activate lcView-env
PYTHONPATH=src pytest -q
python -m compileall -q src
```

To run lcView from any directory without activating the environment first, place a launcher somewhere in your `PATH`, for example:

```bash
printf '#!/usr/bin/env bash\nconda run --no-capture-output -n lcView-env /path/to/lcView/lcView.sh "$@"\n' > ~/bin/lcview
chmod +x ~/bin/lcview
```

## Troubleshooting

- If the GUI opens without plots, make sure `pyqtgraph` is installed in the active environment.
- If prewhitening fails with a native build error, run `python -m lcview.native.build` and check that conda-forge `c-compiler` and `fortran-compiler` are installed.
- If command-line entry points are missing, rerun `pip install -e .` inside `lcView-env`.
