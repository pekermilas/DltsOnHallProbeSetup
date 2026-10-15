"""DLTS device physics shared by Detailed Analysis, Quick Analysis and Trap
Concentration: the rate-window emission rate and boxcar factor measured from
the end of the fill pulse, fill-pulse information read from the AuxInput1
bias monitor, and the trap concentration Nt with the N_D(T), fill-geometry and
large-signal corrections, plus the fill-pulse scan analysis.

Ported from Dr. Kayi's standalone "DLTS Multiwindow Analysis" v3.1
(DrKayisCorrectionsScript.txt; DLTS_APP.py is its v1.3, which Detailed
Analysis was first ported from). Differences from v3.1, all deliberate:
  - temperatures are Kelvin throughout (the analysis tabs show K only);
  - the geometry settings are passed in as a dict instead of read from a
    module-level GEOM, so these stay pure functions a worker process can run;
  - the combined Nt is the error-weighted mean of the windows (median and
    window scatter are still reported, as v3.1 does), and every window's Nt
    carries the error propagated from its peak-height error;
  - fill_record_info() finds the first fill pulse wherever it sits in the
    record (v3.1 assumes the first 30 ms), so continuous multi-cycle records
    work too; for v3.1's records the result is the same.
Pure numpy/pandas, no Tk.
"""
import glob
import json
import os
import re

import numpy as np
import pandas as pd

Q_E = 1.602176634e-19          # C
KB_EV = 8.617333262145e-5      # eV/K (CODATA 2018), as detailedAnalysisTab.KB_EV
EPS0_F_CM = 8.8541878e-14      # vacuum permittivity, F/cm (v3.1's value)

# Fill-end time (ms) of ZI MFIA exports: their time axis starts 1 ms before the
# trigger (grid offset -1 ms), so the emission starts ~1.307 ms into the record
# (v3.1's estimate). The JSON / h5 step files of this app are cut at the
# falling edge of the fill pulse (liveDataTab._find_reverse_bias_starts), so
# their transients already start at the fill end: t_FE = 0.
T_FE_ZI_MS = 1.307
T_FE_STEP_FILES_MS = 0.0

DEFAULT_F_OSC_HZ = 100e3       # v3.1's fallback when runParams.txt has no oscillation frequency

# Fill-pulse geometry defaults (v3.1, 4H-SiC PiN diode)
DEFAULT_V_FILL = 0.0
DEFAULT_V_REV = -5.0
DEFAULT_VBI = 2.9
DEFAULT_DIAM_MM = 6.5
DEFAULT_EPS_R = 9.7
DEFAULT_WF_RATIO = 0.762       # W_F/W_R from C-V, 0 V fill at 25 °C (4.86 / 6.38 µm)
DEFAULT_T_REF_K = 298.15       # temperature of the C-V measurement N_D comes from
G_MIN = 0.05                   # lower limit of the geometry factor g

WF_MODE_CFILL, WF_MODE_RATIO, WF_MODE_VBI = 'cfill', 'ratio', 'vbi'
WF_MODES = {'Measured C_fill': WF_MODE_CFILL, 'C-V ratio': WF_MODE_RATIO, 'V_bi model': WF_MODE_VBI}


#---------------------RATE WINDOWS-------------------------#
def emission_rate(t1, t2, t_fe=0.0):
    """Rate-window emission rate e_n (s^-1) for t1, t2 in ms, with the times
    measured from the fill end: e_n = ln(tau2/tau1) / (tau2 - tau1), tau = t - t_fe.
    None when the window starts inside / before the fill pulse (tau1 <= 0) or
    tau2 <= tau1."""
    tau1, tau2 = t1 - t_fe, t2 - t_fe
    if tau1 <= 0 or tau2 <= tau1:
        return None
    return float(np.log(tau2 / tau1) / ((tau2 - tau1) * 1e-3))

def boxcar_factor(t1, t2, t_fe=0.0):
    """S_peak / (ΔC/C0) of an ideal exponential transient for the double boxcar
    (t1, t2): f(r) = r^(-1/(r-1)) * (1 - 1/r), r = (t2 - t_fe) / (t1 - t_fe)
    (f = 0.947 for 5/490 ms)."""
    r = (t2 - t_fe) / (t1 - t_fe)
    return float(r ** (-1.0 / (r - 1.0)) * (1.0 - 1.0 / r))

def weighted_mean(values, errs):
    """Error-weighted mean of values when every one has an error (its error the
    weighted-mean error, scaled up by sqrt(reduced chi-square) when the values
    scatter more than their errors), else the plain mean and its standard
    error. Returns (mean, err); err is None for a single value without one."""
    values = np.asarray(values, dtype=float)
    errs = np.array([np.nan if e is None else e for e in errs], dtype=float)
    if values.size and np.all(np.isfinite(errs)) and np.all(errs > 0):
        w = 1.0 / errs ** 2
        mean = float(np.sum(w * values) / np.sum(w))
        err = float(np.sqrt(1.0 / np.sum(w)))
        if values.size > 1:
            redchi = float(np.sum(w * (values - mean) ** 2) / (values.size - 1))
            err *= np.sqrt(max(redchi, 1.0))
        return mean, err
    mean = float(np.mean(values))
    return mean, (float(np.std(values, ddof=1) / np.sqrt(values.size)) if values.size > 1 else None)


#---------------------RECORD INFORMATION (LOADER)-------------------------#
def read_osc_frequency(folder):
    """Oscillation frequency (Hz) from a run folder's runParams.txt, or None."""
    try:
        with open(os.path.join(folder, 'runParams.txt'), encoding='utf-8') as fh:
            return float(json.load(fh)['Oscillation Frequency'])
    except Exception:
        return None

def capacitance_mode(raw_values, f_osc):
    """'direct' when ImpedanceIm holds the capacitance in farads, else
    'susceptance' (the parallel-model B in siemens, C = B / (2π f_osc)), decided
    from the values' magnitude as v3.1 does: B/ω below 1 pF while the raw
    value read as farads is 5 pF - 100 nF means direct capacitance."""
    med = float(np.nanmedian(np.abs(np.asarray(raw_values, dtype=float))))
    c_susc, c_dir = med / (2.0 * np.pi * f_osc) * 1e12, med * 1e12
    return 'direct' if (c_susc < 1.0 and 5.0 <= c_dir <= 1e5) else 'susceptance'

def fill_record_info(t_ms, cap_pF, aux_V, tail=(50.0, 450.0), t_first_max=30.0, relaxed=False):
    """Fill-pulse information from ONE raw temperature record (v3.0).

    Needs the fill-bias monitor channel (AuxInput1) recorded next to the
    capacitance. Returns a dict:
      v_rev, v_fill     bias before / during the first pulse (V)
      t_end, width_ms   end of the plateau and pulse width (width NaN when the
                        record already starts inside the pulse)
      c_fill            capacitance at the END of the pulse (pF): median of the
                        last ~0.1 ms of the plateau (the lock-in has settled, the
                        edge samples are excluded)
      ok                True when c_fill is usable (pulse >= 0.3 ms)
      c_pre, pre_ok     mean C of the two samples before the pulse, and whether
                        the bias there is the reverse bias (pre-pulse equilibrium)
      next_pulse_ms     time from t_end to the start of the next pulse (NaN if
                        none in the record)
      in_record, note
    C_fill gives the depletion width during the fill pulse, W_F = εA/C_fill,
    measured at the DLTS temperature itself.
    """
    out = dict(ok=False, v_rev=np.nan, v_fill=np.nan, c_fill=np.nan, width_ms=np.nan, t_end=np.nan,
               in_record=False, c_pre=np.nan, pre_ok=False, next_pulse_ms=np.nan, note='')
    try:
        t = np.asarray(t_ms, float); c = np.asarray(cap_pF, float); v = np.asarray(aux_V, float)
    except Exception:
        return out
    n = min(len(t), len(c), len(v))
    if n < 50:
        return out
    t, c, v = t[:n], c[:n], v[:n]
    m_tail = (t >= tail[0]) & (t <= min(tail[1], 0.8 * t[-1]))
    if m_tail.sum() < 10:
        return out
    v_rev = float(np.median(v[m_tail])); out['v_rev'] = v_rev
    dev = np.abs(v - v_rev)
    pulse = np.where(dev > 0.5)[0]
    # The first pulse: v3.1's records hold it within the first 30 ms; a
    # continuous record can start anywhere in the cycle.
    t0 = float(t[pulse[0]]) if len(pulse) and t[pulse[0]] > t_first_max else 0.0
    early = pulse[t[pulse] < t0 + t_first_max] if len(pulse) else pulse
    if len(early) < (1 if relaxed else 3):
        out['note'] = 'no fill pulse found in the bias monitor'
        return out
    v_fill = float(np.median(v[early])); out['v_fill'] = v_fill
    plat = early[np.abs(v[early] - v_fill) < 0.1]
    if len(plat) < (1 if relaxed else 2):
        out['note'] = 'fill plateau not resolved'
        return out
    dt = float(np.median(np.diff(t[:200])))
    t_end = float(t[plat[-1]] + 0.5 * dt); out['t_end'] = t_end
    i0 = int(early[0])
    started = i0 > 0 and dev[i0 - 1] < 0.9 * abs(v_fill - v_rev)    # pulse starts inside the record
    out['in_record'] = bool(started)
    if started:
        out['width_ms'] = float(t_end - t[i0])
    # Pre-pulse equilibrium: v3.1 takes the record's first two samples; for a
    # record whose first pulse is later, the two samples just before it.
    ip = 0 if t0 == 0.0 else max(i0 - 2, 0)
    if ip + 2 <= i0:
        out['c_pre'] = float(np.mean(c[ip:ip + 2]))
        out['pre_ok'] = bool(abs(float(np.mean(v[ip:ip + 2])) - v_rev) < 0.5)
    after = np.where((t > t_end + 5.0) & (dev > 0.5))[0]
    if len(after):
        out['next_pulse_ms'] = float(t[after[0]] - t_end)
    win = (t >= t_end - 0.15) & (t <= t_end - 0.04)
    if win.sum() >= 2:
        cf = float(np.median(c[win]))
        w = out['width_ms']
        if np.isfinite(cf) and cf > 0 and (not np.isfinite(w) or w >= 0.3):
            out['c_fill'] = cf; out['ok'] = True
        elif np.isfinite(w) and w < 0.3:
            out['note'] = f'pulse {w:.2f} ms: lock-in not settled, C_fill not used'
    return out

def c0_estimate(t_ms, cap, rb_ms, cinf_lo, cinf_hi, info=None):
    """Baseline capacitance C0 of one averaged transient (time from the fill
    end). Tail mean over [cinf_lo, cinf_hi] x rb_ms, cut 5 ms before a second
    fill pulse inside the transient; with fill information (info, from
    fill_record_info) the lower of that and the pre-pulse equilibrium C, as
    v3.1 does: at low T the tail may not have fully decayed, so the pre-pulse
    points give the better C0. Returns (c0, source text)."""
    t_ms, cap = np.asarray(t_ms, dtype=np.float64), np.asarray(cap, dtype=np.float64)
    lo_t, hi_t = cinf_lo * rb_ms, cinf_hi * rb_ms
    nxt = np.nan if info is None else info.get('next_pulse_ms', np.nan)
    if np.isfinite(nxt) and hi_t > nxt - 5.0:
        hi_t = nxt - 5.0
        lo_t = min(lo_t, 0.8 * hi_t)
    mi = (t_ms >= lo_t) & (t_ms <= hi_t)
    tail = float(np.nanmean(cap[mi])) if mi.any() else float(np.nanmean(cap[-100:]))
    if info is None or not info.get('pre_ok') or not np.isfinite(info.get('c_pre', np.nan)):
        return tail, 'tail'
    pre = float(info['c_pre'])
    c0 = min(pre, tail)
    if c0 <= 0:
        c0 = max(pre, tail)
    return c0, ('pre-pulse' if c0 == pre else 'tail')

def detect_second_pulse(data, temps, lo_frac=0.5, hi_frac=0.97):
    """Time (ms) of a second fill pulse inside the transients, or None (v3.1).
    data[tc] = (t_ms, cap, ...). Rate windows must end before it."""
    if not temps:
        return None
    hits = []
    for k in np.linspace(0, len(temps) - 1, 5).astype(int):
        t, c = np.asarray(data[temps[k]][0], float), np.asarray(data[temps[k]][1], float)
        rb = t[-1]
        m = (t >= lo_frac * rb) & (t <= hi_frac * rb)
        if m.sum() < 20:
            continue
        g = np.abs(np.gradient(c[m], t[m]))
        i = int(np.argmax(g))
        if g[i] > 20.0 * (np.median(g) + 1e-12):
            hits.append(float(t[m][i]))
    return float(np.median(hits)) if len(hits) >= 3 else None

def fill_summary(fill_by_T):
    """Median fill bias / reverse bias / width over the loaded records (or None)."""
    ok = [d for d in fill_by_T.values() if d and np.isfinite(d.get('v_fill', np.nan))]
    if not ok:
        return None
    ws = [d['width_ms'] for d in ok if np.isfinite(d.get('width_ms', np.nan))]
    return dict(v_fill=float(np.median([d['v_fill'] for d in ok])),
                v_rev=float(np.median([d['v_rev'] for d in ok])),
                v_fill_sd=float(np.std([d['v_fill'] for d in ok])),
                width_ms=float(np.median(ws)) if ws else None,
                n=len(ok), n_cfill=sum(1 for d in ok if d.get('ok')))


#---------------------TRAP CONCENTRATION-------------------------#
def default_geometry():
    """Geometry settings with v3.1's defaults: correction on, measured C_fill,
    N_D(T) scaling on, large-signal term off. T (K), C0, CF (pF) arrays are
    filled by geometry_arrays()."""
    return dict(on=True, v_fill=DEFAULT_V_FILL, v_rev=DEFAULT_V_REV, vbi=DEFAULT_VBI, diam_mm=DEFAULT_DIAM_MM,
                eps_r=DEFAULT_EPS_R, wf_mode=WF_MODE_CFILL, wf_ratio=DEFAULT_WF_RATIO, ls=False, nd_scale=True,
                t_ref=DEFAULT_T_REF_K, T=None, C0=None, CF=None)

def geometry_arrays(c0_by_T, fill_by_T=None):
    """T (K, sorted), baseline capacitance C0(T) and fill-pulse capacitance
    C_fill(T) in pF (NaN where the record has no usable fill information).
    With the fill bias applied the capacitance must exceed C0 (W_F < W_R) and
    stay within a physical factor; under forward bias the parallel-model C is
    dominated by conductance at high T (C_fill collapses), so records with
    C0/C_fill outside 0.2-0.9 are rejected."""
    fill_by_T = fill_by_T or {}
    T = np.array(sorted(c0_by_T), float)
    C0 = np.array([float(c0_by_T[t]) for t in sorted(c0_by_T)])
    CF = np.array([float(fill_by_T[t]['c_fill']) if (t in fill_by_T and fill_by_T[t].get('ok')) else np.nan
                   for t in sorted(c0_by_T)])
    with np.errstate(invalid='ignore', divide='ignore'):
        ratio = C0 / CF
        CF = np.where((ratio >= 0.20) & (ratio <= 0.90), CF, np.nan)
    return T, C0, CF

def nd_at(T_K, nd, geom):
    """Net doping seen at the DLTS temperature: N_D(T) = N_D (C0(T)/C0(T_ref))².

    N_D from C-V is a room-temperature value. In the depletion approximation
    C0 = εA/W_R with W_R² ∝ 1/N_eff, so scaling with C0² is the same as
    repeating the C-V at the DLTS temperature (V_bi and ε change by < 3 %).
    Off (or no C0(T)) -> N_D constant."""
    if not geom.get('nd_scale') or geom.get('T') is None or len(geom['T']) < 2:
        return float(nd)
    c_t = float(np.interp(T_K, geom['T'], geom['C0']))
    c_r = float(np.interp(geom.get('t_ref', DEFAULT_T_REF_K), geom['T'], geom['C0']))
    return float(nd) * (c_t / c_r) ** 2

def debye_lambda_cm(T_K, Et, nd, eps_r):
    """λ = sqrt(2ε(E_F - Et)/(q N_D)) in cm, with E_C - E_F = kT ln(N_c/N_D),
    N_c = 1.7e19 (T/300)^1.5 (4H-SiC)."""
    eps = eps_r * EPS0_F_CM
    Nc = 1.7e19 * (T_K / 300.0) ** 1.5
    dEc = KB_EV * T_K * np.log(max(Nc / nd, 1.0))
    return float(np.sqrt(2.0 * eps * max(float(Et) - dEc, 0.0) / (Q_E * nd)))

def fill_geometry_factor(T_K, Et, nd, geom):
    """Fraction g of the depletion region that is filled and then emits:

        g = [(W_R - λ)² - (W_F - λ)²] / W_R²           (uniform Nt and N_D)

      W_R = εA / C0(T)            baseline (reverse-bias) capacitance at T
      W_F = εA / C_fill(T)        measured at the end of the fill pulse at T
            ('C-V ratio' / 'V_bi model' are the fall-backs when no record
            within 25 K has usable fill information)
      λ   = see debye_lambda_cm

    Returns (g, info); g = 1 and info = None when the correction is off or
    there is no C0(T)."""
    G = geom
    if not G.get('on') or G.get('T') is None or len(G['T']) < 2:
        return 1.0, None
    eps = G['eps_r'] * EPS0_F_CM
    area = np.pi * (G['diam_mm'] / 20.0) ** 2                 # cm²
    c0 = float(np.interp(T_K, G['T'], G['C0'])) * 1e-12
    W_R = eps * area / c0
    mode = G.get('wf_mode', WF_MODE_CFILL); src = None; cf = np.nan; W_F = None
    if mode == WF_MODE_CFILL:
        CF = G.get('CF')
        if CF is not None:
            ok = np.isfinite(CF)
            if ok.any() and np.min(np.abs(np.asarray(G['T'])[ok] - T_K)) <= 25.0:
                cf = float(np.interp(T_K, np.asarray(G['T'])[ok], np.asarray(CF)[ok]))
                if np.isfinite(cf) and cf > 0:
                    W_F = eps * area / (cf * 1e-12)
                    src = 'measured C_fill'
                    if W_F > W_R:                              # no wider than W_R
                        W_F = W_R; src = 'measured C_fill (W_F capped at W_R)'
        if W_F is None:
            mode = WF_MODE_RATIO; src = 'C-V ratio (no usable C_fill at this T)'
            cf = np.nan
    if mode == WF_MODE_RATIO:
        W_F = W_R * G['wf_ratio']; src = src or 'C-V ratio'
    elif mode == WF_MODE_VBI:
        vf, vr = -G['v_fill'], -G['v_rev']
        W_F = W_R * np.sqrt(max(G['vbi'] + vf, 1e-6) / (G['vbi'] + vr)); src = 'V_bi model'
    lam = debye_lambda_cm(T_K, Et, nd, G['eps_r'])
    wr = W_R - lam
    wf = max(W_F - lam, 0.0)
    g_raw = (wr ** 2 - wf ** 2) / W_R ** 2 if wr > 0 else 0.0
    g = max(g_raw, G_MIN)
    return float(g), dict(W_R=W_R * 1e4, W_F=W_F * 1e4, lam=lam * 1e4, g=g, C0=c0 * 1e12, C_fill=cf,
                          src=src, clipped=bool(g_raw < G_MIN))

def nt_core(a, nd, g, large_signal=False):
    """Nt from the amplitude a = S_pk / f(r) = ΔC∞/C0, and dNt/da.

    small signal : Nt = 2 N_D a / g
    large signal : Nt = N_D a (2 - a) / g     (exact for a uniform profile, from
                   C ∝ sqrt(N_eff); lowers Nt by a/2, e.g. 5 % at a = 0.1)"""
    if large_signal and a < 1.0:
        return nd * a * (2.0 - a) / g, nd * (2.0 - 2.0 * a) / g
    return 2.0 * nd * a / g, 2.0 * nd / g

def trap_concentration(peaks, nd, Et, geom, t_fe=0.0):
    """Trap concentration of one trap from its rate-window peaks.

        Nt = 2 N_D(T) (S_pk / f(r)) / g,   f(r) = r^(-1/(r-1)) (1 - 1/r)

    peaks: dicts with t1, t2 (ms), T_peak (K), S_peak, S_peak_err (or None).
    Each window uses its own r (from the fill end when t_fe > 0), N_D at its
    peak temperature (nd_at) and the geometry factor there (fill_geometry_factor,
    with the trap's Et for λ). Returns None without peaks, else a dict:
    rows (one dict per window: t1, t2, T_peak, S_peak, f, a, nd_T, g, nt,
    nt_err, nt_raw, info), Nt / Nt_err (error-weighted mean of the windows,
    see weighted_mean), Nt_median / Nt_sd (v3.1's median and window scatter),
    Nt_raw / Nt_raw_err (the same without the geometry factor and large-signal
    term), frac (Nt / median N_D(T)), nd, nd_med, a_med, g_med, geom (info of
    the median-g window), clipped (any window's g at its lower limit)."""
    if not peaks:
        return None
    ls = bool(geom.get('ls'))
    rows = []
    for p in peaks:
        f = boxcar_factor(p['t1'], p['t2'], t_fe)
        S = abs(float(p['S_peak']))
        Serr = p.get('S_peak_err')
        a = S / f
        a_err = None if Serr is None or not np.isfinite(Serr) else float(Serr) / f
        nd_T = nd_at(p['T_peak'], nd, geom)
        g, info = fill_geometry_factor(p['T_peak'], Et, nd_T, geom)
        nt, dnt_da = nt_core(a, nd_T, g, ls)
        rows.append(dict(t1=p['t1'], t2=p['t2'], T_peak=p['T_peak'], S_peak=S, f=f, a=a, nd_T=nd_T, g=g,
                         nt=nt, nt_err=None if a_err is None else abs(dnt_da) * a_err,
                         nt_raw=2.0 * nd_T * a, nt_raw_err=None if a_err is None else 2.0 * nd_T * a_err,
                         info=info))
    nts = np.array([r['nt'] for r in rows])
    gs = np.array([r['g'] for r in rows])
    nds = np.array([r['nd_T'] for r in rows])
    Nt, Nt_err = weighted_mean(nts, [r['nt_err'] for r in rows])
    Nt_raw, Nt_raw_err = weighted_mean([r['nt_raw'] for r in rows], [r['nt_raw_err'] for r in rows])
    mid = int(np.argsort(gs)[len(gs) // 2])
    return dict(rows=rows, Nt=Nt, Nt_err=Nt_err, Nt_median=float(np.median(nts)),
                Nt_sd=float(np.std(nts, ddof=1)) if len(nts) > 1 else 0.0,
                Nt_raw=Nt_raw, Nt_raw_err=Nt_raw_err, frac=Nt / float(np.median(nds)), nd=float(nd),
                nd_med=float(np.median(nds)), a_med=float(np.median([r['a'] for r in rows])),
                g_med=float(np.median(gs)), geom=rows[mid]['info'],
                clipped=any(r['info'] is not None and r['info']['clipped'] for r in rows), t_fe=t_fe, Et=Et)

def nt_checks(tc, geom, fill, nd_source=None):
    """Plain-language checks on one trap's Nt (v3.1's quality notes on Nt).
    tc: trap_concentration() result; fill: fill_summary() or None; nd_source:
    the N_D the source analysis used, if known."""
    notes = []
    if tc is None:
        return notes
    if tc['frac'] > 0.10:
        notes.append(f'Nₜ/N_D = {tc["frac"] * 100:.0f} % (> 10 %): the small-signal formula '
                     f'Nₜ = 2·N_D·ΔC/C₀/f(r) is no longer accurate.')
    gi = tc.get('geom')
    if geom.get('on') and gi:
        cf_txt = f', C_fill = {gi["C_fill"]:.0f} pF' if np.isfinite(gi.get('C_fill', np.nan)) else ''
        notes.append(f'Nₜ includes the fill-pulse geometry correction (fill {geom["v_fill"]:g} V, reverse '
                     f'{geom["v_rev"]:g} V): W_R ≈ {gi["W_R"]:.2f} µm (C₀ = {gi["C0"]:.0f} pF), W_F ≈ {gi["W_F"]:.2f} µm '
                     f'[{gi["src"]}{cf_txt}], λ ≈ {gi["lam"]:.2f} µm, g = {gi["g"]:.2f}. It assumes uniform Nₜ and '
                     f'N_D; without it Nₜ would be {tc["Nt_raw"]:.2e} cm⁻³.')
        if tc.get('clipped'):
            notes.append(f'g hit its lower limit ({G_MIN:g}) in at least one window: W_R-λ is very small, '
                         f'Nₜ is not reliable there.')
        if gi['C0'] < 1.0 or gi['C0'] > 1e5:
            notes.append(f'C₀ = {gi["C0"]:.3g} pF is not a plausible capacitance: the source transients are not '
                         f'in pF (e.g. an unconverted susceptance), so W_R, W_F and g are meaningless. Load the '
                         f'data in Detailed Analysis, or turn the geometry correction off.')
        notes.append('Model uncertainty of the corrected Nₜ is about ±30 %: in the 25 °C fill-bias scan the '
                     'apparent Nₜ changed by ±25 % between -2 V and +2 V fill bias (Nₜ not uniform in depth '
                     'and/or λ underestimated). Quote Nₜ with the fill bias and width used.')
    elif not geom.get('on') and geom.get('v_fill') != geom.get('v_rev'):
        notes.append('Fill-pulse geometry correction is OFF: if the fill bias does not reach the neutral region '
                     '(e.g. 0 V on a PiN diode) Nₜ is underestimated by about 1/g ≈ 2-4.')
    if geom.get('nd_scale') and tc.get('nd_med'):
        ratio = tc['nd_med'] / tc['nd']
        if abs(ratio - 1.0) > 0.05:
            notes.append(f'N_D scaled with C₀(T)² to the peak temperature: N_D(T) = {tc["nd_med"]:.2e} cm⁻³ '
                         f'(×{ratio:.2f} of the C-V value at {geom.get("t_ref", DEFAULT_T_REF_K):g} K). '
                         f'Nₜ is proportional to it; untick "N_D(T)" to use the constant C-V value.')
    if fill:
        if fill.get('width_ms') is not None and fill['width_ms'] < 3.0:
            notes.append(f'Fill pulse is {fill["width_ms"]:.2g} ms: the slow-capture part of the transient is not '
                         f'saturated (1 ms gives ~97.6 % and 3 ms ~99 % of the 10 ms amplitude at 25 °C). '
                         f'Use >= 3 ms for the Nₜ measurement.')
        if fill['v_fill'] >= 2.4:
            notes.append(f'Fill bias +{fill["v_fill"]:.1f} V: in the 25 °C scan the amplitude fell above +2 V '
                         f'(hole injection / series resistance). Use <= +1.5 V and check at the EH₆/₇ temperature.')
    if geom.get('on') and tc.get('a_med', 0) > 0.05:
        notes.append(f'Large-signal check: amplitude a = ΔC/C₀ = {tc["a_med"]:.2f}; the exact uniform-profile '
                     f'relation Nₜ = N_D·a·(2-a)/g is {tc["a_med"] / 2 * 100:.0f} % lower than the small-signal '
                     f'2·N_D·a/g ' + ('(applied).' if geom.get('ls') else '(not applied; tick "Large-signal term").'))
    if nd_source is not None and abs(nd_source / tc['nd'] - 1.0) > 1e-6:
        notes.append(f'N_D here ({tc["nd"]:.2e} cm⁻³) differs from the one the source analysis used '
                     f'({nd_source:.2e} cm⁻³), so its uncorrected Nₜ differs from this one.')
    notes.append('N_D should be the average of the C-V profile between W_F and W_R at the DLTS biases for each '
                 'sample. When Nₜ/N_D is not small, or the layer is nearly fully depleted, Nₜ from ΔC/C₀ is '
                 'order-of-magnitude only.')
    return notes


#---------------------FILL-PULSE SCAN ANALYSIS-------------------------#
# Bias and width scans at one temperature (v3.0): ZI csv exports with one chunk
# per setting, the setting coded in the history name (FP1ms1p5V = 1 ms at +1.5 V).
_FS_NAME = re.compile(r'^FP([0-9p.]+)ms(-?[0-9p.]+)V', re.I)

def _fs_num(s):
    return float(s.replace('p', '.'))

def scan_temperature_K(folder):
    """Scan temperature (K) coded in a folder name as _<T>C (e.g. ..._25C_...), or None."""
    m = re.search(r'_(-?\d+)C(?:_|$)', os.path.basename(os.path.normpath(folder)))
    return float(m.group(1)) + 273.15 if m else None

def load_fill_scan(folder):
    """Load a ZI-MFIA csv fill-pulse scan folder. Returns a list of
    dict(name, width_set, v_set, t_ms, C_pF, V, reps)."""
    base = lambda f: os.path.basename(f).lower()
    cap_f = [f for f in glob.glob(os.path.join(folder, '*param1_avg*.csv')) if 'header' not in base(f)]
    hdr_f = glob.glob(os.path.join(folder, '*param1_avg_header*.csv'))
    aux_f = [f for f in glob.glob(os.path.join(folder, '*auxin0_avg*.csv')) if 'header' not in base(f)]
    if not cap_f or not hdr_f or not aux_f:
        raise ValueError('Folder needs the *param1_avg*, *param1_avg_header* and *auxin0_avg* csv files of '
                         'the MFIA export.')
    hdr = pd.read_csv(hdr_f[0], sep=';')
    cap = pd.read_csv(cap_f[0], sep=';'); aux = pd.read_csv(aux_f[0], sep=';')
    out = []
    for _, row in hdr.iterrows():
        nm = str(row.get('history_name', ''))
        m = _FS_NAME.match(nm)
        if not m:
            continue
        ch = int(row['chunk_number'])
        c = cap[cap['chunk'] == ch]; a = aux[aux['chunk'] == ch]
        n = min(len(c), len(a))
        if n < 100:
            continue
        ts = c['timestamp'].values[:n].astype(float)
        dt = float(row.get('grid_col_delta', 0) or 0) * 1e3
        t_ms = np.arange(n) * dt if dt > 0 else (ts - ts[0]) / 60e6 * 1e3
        out.append(dict(name=nm.split('_')[0], width_set=_fs_num(m.group(1)), v_set=_fs_num(m.group(2)),
                        t_ms=t_ms, C_pF=c['value'].values[:n].astype(float) * 1e12,
                        V=a['value'].values[:n].astype(float), reps=int(row.get('grid_repetitions', 0) or 0)))
    if not out:
        raise ValueError('No FP{width}ms{bias}V history names found in the header file.')
    return out

def analyze_fill_scan(rows, nd, diam_mm=DEFAULT_DIAM_MM, eps_r=DEFAULT_EPS_R, Et=0.63, T_K=298.15,
                      t1=5.0, t2=490.0, t_fe_off=0.307, large_signal=False):
    """ΔC = C(t2) - C(t1) (times AFTER the fill pulse) for every setting, then
    the geometry factor from the measured C_fill, the apparent Nt, and the
    recommended fill bias / width.

    Recommendation rules (from the 25 °C Run2 scans):
      bias : lowest bias whose ΔC is >= 97 % of the maximum and at least 0.5 V
             below the first bias where ΔC drops below 97 % of the maximum
             again (hole injection / series-resistance cliff)
      width: shortest pulse whose ΔC is >= 99 % of the longest pulse."""
    eps = eps_r * EPS0_F_CM; area = np.pi * (diam_mm / 20.0) ** 2
    lam = debye_lambda_cm(T_K, Et, nd, eps_r)
    r = (t2 - t_fe_off) / (t1 - t_fe_off)
    f = r ** (-1.0 / (r - 1.0)) * (1.0 - 1.0 / r)
    recs = []
    for d in rows:
        ri = fill_record_info(d['t_ms'], d['C_pF'], d['V'])
        if not np.isfinite(ri['t_end']):               # very short pulses (< 3 samples)
            ri = fill_record_info(d['t_ms'], d['C_pF'], d['V'], relaxed=True)
        if not np.isfinite(ri['t_end']):
            continue
        t, C, V = d['t_ms'], d['C_pF'], d['V']
        dev = np.abs(V - ri['v_rev'])
        late = np.where((dev > 0.5) & (t > 100.0))[0]
        t_sec = float(t[late[0]]) if len(late) else float(t[-1])
        te = ri['t_end']

        def seg(a, b):
            b = min(b, t_sec - 3.0)
            m = (t >= a) & (t <= b)
            return ((float(C[m].mean()), float(C[m].std(ddof=1) / np.sqrt(m.sum()))) if m.sum() >= 3
                    else (np.nan, np.nan))
        c1, e1 = seg(te + t1 - 0.5, te + t1 + 0.5)
        c2, e2 = seg(te + t2 - 6.0, te + t2 + 2.0)
        mr = (t >= te + 300.0) & (t <= t_sec - 5.0)
        Cr = float(np.median(C[mr])) if mr.sum() > 10 else np.nan
        dC = c2 - c1
        S = dC / Cr
        WR = eps * area / (Cr * 1e-12) * 1e4
        WF = eps * area / (ri['c_fill'] * 1e-12) * 1e4 if ri['ok'] else np.nan
        recs.append(dict(name=d['name'], width=d['width_set'], bias=d['v_set'], dC=dC,
                         err=float(np.hypot(e1, e2)), S=S, Cr=Cr, WR=WR, WF=WF,
                         C_fill=ri['c_fill'], v_meas=ri['v_fill'], flag=''))
    if not recs:
        raise ValueError('No usable records.')
    df = pd.DataFrame(recs)
    nb, nw = df.bias.nunique(), df.width.nunique()
    out = dict(lam=lam * 1e4, f=f, r=r, T_K=T_K, t1=t1, t2=t2, Et=Et, nd=nd, bias=None, width=None,
               rec_bias=None, rec_width=None, v_cliff=np.nan, notes=[])
    if nb > 1:
        w0 = df.width.mode().iloc[0]
        b = df[df.width == w0].sort_values('bias').reset_index(drop=True)
        ref = b[np.isclose(b.bias, 0.0)]
        b['rel0'] = b.dC / ref.dC.iloc[0] if len(ref) else np.nan
        ipk = int(b.dC.idxmax()); dpk = float(b.dC.max())
        cliff = b[(b.index > ipk) & (b.dC < 0.97 * dpk)]
        v_cliff = float(cliff.bias.iloc[0]) if len(cliff) else np.nan
        if len(cliff):
            b.loc[b.index >= cliff.index[0], 'flag'] = 'past cliff'
        g = []
        for _, x in b.iterrows():
            if x.flag or not np.isfinite(x.WF):
                g.append(np.nan); continue
            wr = x.WR - lam * 1e4; wf = max(x.WF - lam * 1e4, 0.0)
            g.append(max((wr ** 2 - wf ** 2) / x.WR ** 2, G_MIN))
        b['g'] = g
        a = b.S / f
        b['Nt'] = (nd * a * (2 - a) if large_signal else 2 * nd * a) / b.g
        good = b[b.dC >= 0.97 * dpk]
        if np.isfinite(v_cliff):
            good = good[good.bias <= v_cliff - 0.5]
        out['rec_bias'] = float(good.bias.min()) if len(good) else float(b.bias.iloc[ipk])
        out['bias'] = b; out['width_scan_w'] = float(w0); out['v_cliff'] = v_cliff
    if nw > 1:
        v0 = df.bias.mode().iloc[0]
        w = df[np.isclose(df.bias, v0)].sort_values('width').reset_index(drop=True)
        w['frac'] = w.dC / w.dC.iloc[-1]
        ok = w[w.frac >= 0.99]
        out['rec_width'] = float(ok.width.iloc[0]) if len(ok) else float(w.width.iloc[-1])
        out['width'] = w; out['bias_of_width_scan'] = float(v0)
    b = out['bias']
    if b is not None and b.Nt.notna().sum() >= 3:
        nt = b.Nt.dropna()
        out['notes'].append(
            f'Apparent Nₜ varies from {nt.min():.2e} to {nt.max():.2e} cm⁻³ across the fill biases '
            f'({100 * (nt.max() - nt.min()) / nt.mean():.0f} % of the mean): for a uniform Nₜ and a correct g it '
            f'would be flat.  Quote Nₜ with about ±30 % model uncertainty and use the same fill bias when '
            f'comparing samples.')
    return out

def merge_fill_scans(results):
    """One fill-scan result from several (a bias-scan and a width-scan folder):
    the first result, with the bias / width parts the others add."""
    res = None
    for r in results:
        if res is None:
            res = r
            continue
        for k in ('bias', 'width', 'rec_bias', 'rec_width', 'width_scan_w', 'v_cliff', 'bias_of_width_scan'):
            if r.get(k) is not None and res.get(k) is None:
                res[k] = r[k]
        if not np.isfinite(res.get('v_cliff', np.nan)) and np.isfinite(r.get('v_cliff', np.nan)):
            res['v_cliff'] = r['v_cliff']
        res['notes'] += r['notes']
    return res

def fill_scan_report(res):
    L = [f'Fill-pulse scan analysis  (ΔC = C({res["t1"]:g} ms) - C({res["t2"]:g} ms) after the pulse, '
         f'T = {res["T_K"]:g} K)', '',
         f'  N_D = {res["nd"]:.2e} cm⁻³, E_t = {res["Et"]:.3f} eV -> λ = {res["lam"]:.2f} µm,  '
         f'f(r) = {res["f"]:.4f} (r = {res["r"]:.1f})', '']
    b, w = res['bias'], res['width']
    if b is not None:
        L += [f'  Fill-BIAS scan  ({res["width_scan_w"]:g} ms pulse)',
              f'  {"V_fill":>7} {"ΔC(pF)":>8} {"±(pF)":>6} {"rel.0V":>7} {"W_F(µm)":>8} {"g":>6} {"Nt(cm-3)":>10}  flag']
        for _, x in b.iterrows():
            L.append(f'  {x.bias:7.2f} {x.dC:8.2f} {x.err:6.2f} {x.rel0:7.3f} {x.WF:8.2f} '
                     f'{(x.g if np.isfinite(x.g) else np.nan):6.3f} {x.Nt:10.2e}  {x.flag}')
        L += ['', f'  Recommended fill bias: {res["rec_bias"]:+.2f} V'
                  + (f'   (cliff at {res["v_cliff"]:+.1f} V)' if np.isfinite(res.get("v_cliff", np.nan)) else ''), '']
    if w is not None:
        L += [f'  Fill-WIDTH scan  ({res["bias_of_width_scan"]:g} V fill)',
              f'  {"width(ms)":>9} {"ΔC(pF)":>8} {"±(pF)":>6} {"% of longest":>13}']
        for _, x in w.iterrows():
            L.append(f'  {x.width:9.3f} {x.dC:8.2f} {x.err:6.2f} {100 * x.frac:13.1f}')
        L += ['', f'  Recommended fill width: {res["rec_width"]:g} ms  (>= 99 % of the longest pulse)', '']
    L += ['  ' + n for n in res['notes']]
    L += ['', '  Check at the EH₆/₇ temperature as well: the forward-current cliff moves to a lower bias at high T.']
    return '\n'.join(L)
