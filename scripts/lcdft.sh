#!/bin/bash
set -euo pipefail

#rm lcf.data lcf.trf
echo "===================START===================="
echo "===============create lc.data==============="
dir_path=$5
cd "$dir_path.temp_lcView/"
python "$dir_path"'TESS_lc_time-median.py' "$1"
mv lcf.temp lcf.data

#baza czasowa
head -n 1 lcf.data | awk '{print $1}' > .t0
tail -n 1 lcf.data | awk '{print $1}' > .tn
paste .t0 .tn > .ttt
deltaT=$(awk '{print $2-$1}' .ttt)
deltaf=$(echo 1/$4/$deltaT | bc -l)

echo
echo
echo "===================fwpeaks=================="
fwpeaks_bin="${dir_path}fwpeaks"
fwpeaks_src="${dir_path}fwpeaks.c"
if [[ ! -x "$fwpeaks_bin" ]]; then
    compiler="${CC:-cc}"
    "$compiler" -O3 -w -o "$fwpeaks_bin" "$fwpeaks_src" -lm -ffast-math
fi
"$fwpeaks_bin" -f lcf.data "$2" "$3" "$deltaf" | head -n 10
sed '1d;$d' lcf.trf > res; mv res lcf.trf

# mv lcf.data lcf.trf "$dir_path/.temp_lcView"

rm .t0 .tn .ttt median.dat lcf.max
