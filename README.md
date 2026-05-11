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
