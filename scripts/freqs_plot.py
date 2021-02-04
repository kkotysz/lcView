#!/usr/bin/env python3

import numpy as np
import sys
from os import system

def create_freqs(*args):
    try:
        temp_path=str(args[0])
        full_path=str(args[1])
        with open(str(full_path)+'freq') as f:
            freqs_plot=open(str(temp_path)+'freqs_plot', 'w')
            harms_plot=open(str(temp_path)+'harms_plot', 'w')
            harms2_plot=open(str(temp_path)+'harms2_plot', 'w')
            combs_plot=open(str(temp_path)+'combs_plot', 'w')
        
            lines = f.readlines()
            norig, nall = np.fromstring(lines[0], dtype=int, sep=' ')
            freqs_array = np.array(lines[1:norig+1], dtype=float)
        
            # only basic freqs
            for i in range(1, norig+1):
                myarray = np.fromstring(lines[i], dtype=float, sep=' ')
                print("{0:12.6f}{1:>8s}".format(myarray[0], 'f_{'+str(i)+'}'), file=freqs_plot)
        
            #only harmonics
            for i in range(norig+1, nall+norig+1):
                myarray = np.fromstring(lines[i], dtype=float, sep=' ')
                if myarray[0] > 0.:
                    print("{0:12.6f}".format(myarray[0]*float(lines[1])), file=harms_plot)
        
            #only harmonics for 2nd basic freq
            for i in range(norig+1, nall+norig+1):
                myarray = np.fromstring(lines[i], dtype=float, sep=' ')
                try:
                    if myarray[1] > 0.:
                        print("{0:12.6f}".format(myarray[1]*float(lines[2])), file=harms2_plot)
                except IndexError:
                    pass
        
            #combination freqs
            for i in range(norig+1, nall+norig+1):
                myarray = np.fromstring(lines[i], dtype=float, sep=' ')
        
                if int(np.min(myarray)) == 0 and int(np.sum(myarray)) == 1:
                    continue
        
                # LABELS for gnuplot
        
                fno, fmult = list(np.where(myarray!=0.)[0]+1), list(myarray[np.where(myarray!=0.)[0]])
                fno = ["f" + str(fn) for fn in fno]                     # list w/ freq. no ([f1], [f1,f3], [f2,f4,f7], etc.)
                fall = []
                for fm,fn, i in zip(fmult,fno,range(len(fmult))):       #fm - multiplier of freq, fn - freq number
                    if fm != 1:                         # part of freq is multiplied by smth. > 1
                        if fm == -1 and i != 0:             # part of freq is not first and mult is -1
                            fall.append(' - '+str(fn))
                        elif fm == -1 and i == 0:           # part of freq is first and mult is not -1
                            fall.append('-'+str(fn))
                        elif fm < 0 and i != 0:             # part of freq is not first and mult is less than 0
                            fall.append(' - '+str(np.abs(int(fm)))+str(fn))
                        elif fm < 0 and i == 0:             # part of freq is first and mult is less than 0
                            fall.append('-'+str(np.abs(int(fm)))+str(fn))
                        else:                               # all remaining cases
                            fall.append(str(int(fm))+str(fn))
                    else:                               # part of freq is multiplied by 1
                        fall.append(str(fn))
        
                fall = [' + '+fa if ('-' not in fa and i != 0) else fa for i,fa in zip(range(len(fall)),fall)]     # add plus signs when '-' is not present and part of freq is not first
        
                print("{0:12.6f} \"{1:s}\"".format(np.sum(np.multiply(myarray,freqs_array)), ' '.join(fall)), file=combs_plot)
        return True
    except (FileNotFoundError, IndexError) as e:
        # raise e
        print("[freqs_plot.py WARNING]: There is no freq file!")
        return False
        


if __name__ == "__main__":
    create_freqs()
    
