"""Analyze a finished run folder without the GUI: the same computations as the
Detailed Analysis tab (averaged transients -> multi-window DLTS spectra ->
Arrhenius fit -> Et, capture cross-section, Nt), plus a summary figure.

    python examples/analyze_run.py "C:\\Users\\spencer\\Desktop\\DATA\\DLTS\\092826\\114655"
    python examples/analyze_run.py RUN_FOLDER --t1-min 0.5 --t1-max 5 --tp 300 400 --png summary.png

The reverse-bias duration comes from the folder's runParams.txt (State Enable
Time); pass --rb-ms to override. No instruments are used.
"""
import argparse
import os
import sys

os.environ.setdefault('LOKY_MAX_CPU_COUNT', str(os.cpu_count()))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import matplotlib
import numpy as np


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('folder', help='run folder with p25p0.h5 / .txt step files')
    parser.add_argument('--rb-ms', type=float, help='reverse-bias duration (ms); default from runParams.txt')
    parser.add_argument('--t1-min', type=float, default=5.0, help='shortest rate window t1 (ms)')
    parser.add_argument('--t1-max', type=float, default=90.0, help='longest rate window t1 (ms)')
    parser.add_argument('--ratio', type=float, default=5.0, help='t2/t1')
    parser.add_argument('--n-windows', type=int, default=16)
    parser.add_argument('--tp', type=float, nargs=2, default=(250.0, 400.0), metavar=('LO_K', 'HI_K'),
                        help='peak search range (K)')
    parser.add_argument('--gamma', type=float, default=1.66e21, help='cm^-2 s^-1 K^-2 (4H-SiC 1.66e21, Si 3.256e21)')
    parser.add_argument('--nd', type=float, default=3.2e14, help='background doping (cm^-3)')
    parser.add_argument('--png', help='save the summary figure here (default: show it)')
    args = parser.parse_args(argv)
    if args.png:
        matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import liveDataTab as ldT
    import detailedAnalysisTab as deT

    rbMs = args.rb_ms or (ldT._legacy_run_timing(args.folder) or (1.0, 500.0))[1]
    data, temps, errors = deT._load_detailed_data(args.folder, None, None, None, rbMs, 0.4, 0.9)
    for e in errors:
        print('warning:', e)
    if not temps:
        sys.exit('No temperatures could be loaded from ' + args.folder)
    print(f'{len(temps)} temperatures, {temps[0]:g} to {temps[-1]:g} C, reverse bias {rbMs:g} ms')

    t1 = np.logspace(np.log10(args.t1_min), np.log10(args.t1_max), 5)
    params = dict(nWin=args.n_windows, t1Min=args.t1_min, t1Max=args.t1_max, ratio=args.ratio,
                  stdWins=[(float(a), float(args.ratio * a)) for a in t1], gamma=args.gamma, nd=args.nd,
                  tpLo=args.tp[0], tpHi=args.tp[1], peakMethod=deT.PEAK_METHOD_SPLINE,
                  signalMethod=deT.SIGNAL_METHOD_MEASURED, denoise=deT.DENOISE_NONE, rbMs=rbMs,
                  showStd=True, showSpectra=False, nSpectra=5, showTmap=False, showTau=False, showRwm=False)
    out = deT._compute_detailed_analysis(data, temps, params)
    r = out['resMw']
    print(f"Et = {r['Et']:.3f} +/- {r['Et_se']:.3f} eV   sigma = {r['sigma']:.2e} cm^2   "
          f"Nt = {out['Nt']:.2e} cm^-3   ({r['N']} windows used, R2 = {r['R2']:.3f})")

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(15, 4.4))
    cmap, norm = matplotlib.colormaps['plasma'], matplotlib.colors.Normalize(min(temps), max(temps))
    for tc in temps:
        t_ms, cap, cinf = data[tc]
        keep = t_ms >= 0.02 * rbMs
        ax1.plot(t_ms[keep], cap[keep], color=cmap(norm(tc)), lw=1)
    ax1.set(xlabel='time from reverse-bias start (ms)', ylabel='averaged capacitance (pF)',
            title='Averaged transients')
    ax1.ticklabel_format(axis='y', useOffset=False)
    fig.colorbar(matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap), ax=ax1, label='T (°C)')

    T_K = np.array(temps) + 273.15
    for (a, b), color in zip(out['mw'][::max(1, len(out['mw']) // 5)], matplotlib.colormaps['viridis'](np.linspace(0, 0.9, 5))):
        S = []
        for tc in temps:
            t_ms, cap, cinf = data[tc]
            S.append((cap[np.argmin(abs(t_ms - a))] - cap[np.argmin(abs(t_ms - b))]) / cinf)
        ax2.plot(T_K, S, '-', color=color, lw=1.5, label=f't1/t2 = {a:.2g}/{b:.2g} ms')
    ax2.axvspan(*args.tp, color='0.9', zorder=0, label='peak search range')
    ax2.set(xlabel='temperature (K)', ylabel='DLTS signal  (C(t1) - C(t2)) / C∞', title='DLTS spectra')
    ax2.legend(fontsize=8)

    ok = r['fit_mask']
    x, y = 1000 / r['Tp_arr'], np.log(r['en_arr'] / r['Tp_arr'] ** 2)
    ax3.errorbar(x[ok], y[ok], xerr=1000 * r['Tp_err_arr'][ok] / r['Tp_arr'][ok] ** 2, fmt='o', label='peaks used')
    if (~ok).any():
        ax3.plot(x[~ok], y[~ok], 'x', color='0.5', label='excluded')
    xs = np.linspace(x.min(), x.max(), 50)
    ax3.plot(xs, np.polyval(np.polyfit(x[ok], y[ok], 1), xs), '-', color='C3',
             label=f"Et = {r['Et']:.3f} ± {r['Et_se']:.3f} eV")
    ax3.set(xlabel='1000 / T  (1/K)', ylabel='ln(e_n / T²)', title='Arrhenius')
    ax3.legend(fontsize=8)
    fig.tight_layout()
    if args.png:
        fig.savefig(args.png, dpi=130)
        print('saved', args.png)
    else:
        plt.show()
    return out


if __name__ == '__main__':
    main()
