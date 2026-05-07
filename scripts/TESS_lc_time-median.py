#!/usr/bin/env python3

import numpy as np
import pandas as pd
import sys
from os import system

#ODEJMUJE MEDIANE CZASU
if len(sys.argv) != 2:
    print('\nUSAGE: TESS_lc_time-median.py <filename>')
    exit()
df_lc = pd.read_csv(sys.argv[1], delimiter=r"\s+", header=None, comment="#", usecols=[0, 1, 2])
df_lc = df_lc.apply(pd.to_numeric, errors="coerce").dropna()
if df_lc.empty:
    raise ValueError(f"No numeric light-curve rows found in {sys.argv[1]}")
tbjd, mag_flux, err = df_lc[0].values, df_lc[1].values, df_lc[2].values
np.savetxt('median.dat', [np.median(tbjd)], fmt='%14.7f')
tbjd = tbjd - np.median(tbjd)
out = zip(tbjd, mag_flux, err)
out = sorted(out)
np.savetxt('lcf.temp', out, fmt='%14.7f %14.7f %14.7f')
