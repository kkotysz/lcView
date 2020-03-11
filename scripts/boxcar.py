# coding: utf-8

import numpy as np
from astropy.stats import sigma_clip
import matplotlib
import matplotlib.pyplot as plt
import sys

matplotlib.rcParams['mathtext.fontset'] = 'custom'
matplotlib.rcParams['axes.titleweight'] = 'bold'
matplotlib.rcParams['axes.titlesize'] = '18'
matplotlib.rcParams['axes.labelsize'] = '18'
matplotlib.rcParams['axes.labelweight'] = 'bold'
matplotlib.rcParams['mathtext.rm'] = 'Lato:bold'
matplotlib.rcParams['mathtext.it'] = 'Lato:bold'
matplotlib.rcParams['mathtext.bf'] = 'Lato:bold'
matplotlib.rcParams['font.family'] = 'Lato'
matplotlib.rcParams['font.weight'] = 'bold'
matplotlib.rcParams['xtick.labelsize'] = '15'
matplotlib.rcParams['ytick.labelsize'] = '15'


def smooth(x, window_len=11, window='flat'):
    """smooth the data using a window with requested size.

    This method is based on the convolution of a scaled window with the signal.
    The signal is prepared by introducing reflected copies of the signal
    (with the window size) in both ends so that transient parts are minimized
    in the begining and end part of the output signal.

    input:
        x: the input signal
        window_len: the dimension of the smoothing window; should be an odd integer
        window: the type of window from 'flat', 'hanning', 'hamming', 'bartlett', 'blackman'
            flat window will produce a moving average smoothing.

    output:
        the smoothed signal

    example:

    t=linspace(-2,2,0.1)
    x=sin(t)+randn(len(t))*0.1
    y=smooth(x)

    see also:

    np.hanning, np.hamming, np.bartlett, np.blackman, np.convolve
    scipy.signal.lfilter

    TODO: the window parameter could be the window itself if an array instead of a string
    NOTE: length(output) != length(input), to correct this: return y[(window_len/2-1):-(window_len/2)] instead of just y.
    """

    if x.ndim != 1:
        raise (ValueError, "smooth only accepts 1 dimension arrays.")

    if x.size < window_len:
        raise (ValueError, "Input vector needs to be bigger than window size.")

    if window_len < 3:
        return x

    if not window in ['flat', 'hanning', 'hamming', 'bartlett', 'blackman']:
        raise (ValueError, "Window is on of 'flat', 'hanning', 'hamming', 'bartlett', 'blackman'")

    s = np.r_[x[window_len - 1:0:-1], x, x[-2:-window_len - 1:-1]]
    # print(len(s))
    if window == 'flat':  # moving average
        w = np.ones(window_len, 'd')
    else:
        w = eval('np.' + window + '(window_len)')

    y = np.convolve(w / w.sum(), s, mode='valid')
    return y[(int(window_len / 2)):-(int(window_len / 2))]


if __name__ == "__main__":

    if len(sys.argv) < 4:
        print("\n 'boxcar.py' \n                                                     ")
        print(" Tool for boxcar smoothing of a lightcurve.  ")
        print(
            " Usage: boxcar.py <light_curve> <freq/period> <n_points/bin> [-n <n_of_phases_to_plot(==1, default)>] [-p]                 ")
        print(" Option '-p': period instead of frequency \n                              ")
        print(" Option '-n': set number of phases to plot \n                              ")
        print("                          K. Kotysz          \n ")
        exit()
    else:

        filename = sys.argv[1]
        if '-p' in sys.argv:
            freq = float(sys.argv[2])
        else:
            freq = 1. / float(sys.argv[2])
        nofpoints = int(sys.argv[3])
        if '-n' in sys.argv:
            nofphases = int(sys.argv[5])
        else:
            nofphases = 1
        print(freq)
        time, flux, err = np.loadtxt(filename, unpack=True)
        phase = (time) % (freq) / freq

        temp = zip(phase, flux)
        temp = sorted(temp)
        phase, flux = zip(*temp)

        phase = np.array(phase)
        flux = np.array(flux)

        filtered_flux = sigma_clip(flux, sigma=3.5, maxiters=6)

        smoothed_signal = smooth(filtered_flux, nofpoints)

        mask = np.ones_like(flux, dtype=bool)
        mask[np.where(flux == filtered_flux)] = 0

        new_phase = np.tile(phase, nofphases) + np.repeat(np.arange(0, nofphases), len(phase))
        new_flux = np.tile(flux, nofphases)
        new_filtered_flux = np.tile(filtered_flux, nofphases)
        new_smoothed_signal = np.tile(smoothed_signal, nofphases)
        new_mask = np.tile(mask, nofphases) + np.repeat(np.arange(0, nofphases), len(mask))

        fig = plt.figure(1)
        ax1 = fig.add_subplot(111)

        ax1.set_title(filename, pad=20)
        ax1.set_xlabel('PHASE')
        ax1.set_ylabel('FLUX [ppt]')

        ax1.plot(new_phase[new_mask], new_flux[new_mask], 'rx', ms=2.5, alpha=1.0, label="Noisy")
        ax1.plot(new_phase, new_filtered_flux, 'ko', ms=2.6, alpha=1.0, label="Filtered Noisy")
        ax1.plot(new_phase, new_smoothed_signal, 'go', ms=1.1, label="Filtered Smoothed")

        plt.show()
