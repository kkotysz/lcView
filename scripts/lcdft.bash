#!/bin/bash
#rm lcf.data lcf.trf
echo "===================START===================="
echo "===============create lc.data==============="
dir_path=$5
python3 $dir_path'TESS_lc_time-median.py' $1
mv lcf.temp lcf.data

#baza czasowa
head -n 1 lcf.data | awk '{print $1}' > .t0
tail -n 1 lcf.data | awk '{print $1}' > .tn
paste .t0 .tn > .ttt
deltaT=`awk '{print $2-$1}' .ttt`
deltaf=$(echo 1/$4/$deltaT | bc -l)

echo
echo
echo "===================fwpeaks=================="
fwpeaks -f lcf.data $2 $3 $deltaf | head -n 10
sed '1d;$d' lcf.trf > res; mv res lcf.trf

mv lcf.data lcf.trf "$dir_path/.temp_lcView"

rm .t0 .tn .ttt median.dat lcf.max