# lcView

lcView is now packaged as a PySide6 application with a Python prewhitening backend.
The legacy PyQt5 scripts are kept in `scripts/`, while the new application lives in
`src/lcview`.

## Setup

```bash
conda env create -f lcView-env.yml
conda activate lcView-env
./lcView.sh
```

The bundled native tools (`fwpeaks`, `hars-sin`, `hars-ite`, `smart-uf-fina-smars`,
`uf2`) are compiled automatically into `~/.cache/lcview/native` when first needed.
You can force a rebuild from the GUI menu or with:

```bash
python -m lcview.native.build
```

Batch mode:

```bash
lcview-prewhiten path/to/lightcurve.dat --start 0 --end 80 --precision 10 --export output/
```

To run lcView from any directory without activating the environment first, place a launcher somewhere in your `PATH`, for example:

```bash
printf '#!/usr/bin/env bash\nconda run --no-capture-output -n lcView-env /path/to/lcView/lcView.sh "$@"\n' > ~/bin/lcview
chmod +x ~/bin/lcview
```
