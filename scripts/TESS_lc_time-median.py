#!/usr/bin/env python3

import numpy as np
import sys
from os import system

#ODEJMUJE MEDIANE CZASU
if len(sys.argv) != 2:
    print('\nUSAGE: TESS_lc_time-median.py <filename>')
    exit()
tbjd, mag_flux, err = np.loadtxt(sys.argv[1], unpack=True)
np.savetxt('median.dat', [np.median(tbjd)], fmt='%14.7f')
tbjd = tbjd - np.median(tbjd)
out = zip(tbjd, mag_flux, err)
out = sorted(out)
np.savetxt('lcf.temp', out, fmt='%14.7f %14.7f %14.7f')
