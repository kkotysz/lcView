#!/bin/bash

echo "===================START===================="
echo "===============create lc.data==============="
dir_path=$4
python3 $dir_path'TESS_lc_time-median.py' $1
mv lcf.temp lcf.data

#baza czasowa
head -n 1 lcf.data | awk '{print $1}' > .t0
tail -n 1 lcf.data | awk '{print $1}' > .tn
paste .t0 .tn > .ttt
deltaT=`awk '{print $2-$1}' .ttt`

echo
echo
echo "===================fwpeaks=================="
deltaf=0.1/$deltaT
fwpeaks -f lcf.data $2 $3 $deltaf | head -n 10
sed '1d;$d' lcf.trf > res; mv res lcf.trf

rm .t0 .tn .ttt median.dat lcf.max