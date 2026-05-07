# lcView

## Setup

```bash
conda env create -f lcView-env.yml
conda activate lcView-env
./lcView.sh
```

`scripts/fwpeaks.c` is compiled automatically to `scripts/fwpeaks` on the first DFT run when the binary is missing.

To run lcView from any directory without activating the environment first, place a launcher somewhere in your `PATH`, for example:

```bash
printf '#!/usr/bin/env bash\nconda run --no-capture-output -n lcView-env /path/to/lcView/lcView.sh "$@"\n' > ~/bin/lcview
chmod +x ~/bin/lcview
```
