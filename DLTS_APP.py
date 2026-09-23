# -*- coding: utf-8 -*-
"""
DLTS Multiwindow Analysis  -  Interactive GUI App  v1.3
========================================================
Load your ZI MFIA temperature-sweep data, tune every parameter
with sliders / spinboxes, and get the Arrhenius result instantly.

Changes in v1.3
---------------
  - Draggable legends AND annotation now actually work (deferred
    until after the matplotlib canvas is connected to tkinter)
  - "Edit Labels & Legends" dialog: edit any axis title, x/y label,
    legend entry text, and font sizes without re-running the analysis
  - Minor gridlines removed from Arrhenius and Spectra panels for
    a cleaner, more readable look

Changes in v1.2
---------------
  - Arrhenius results box is now a draggable annotation
  - Arrhenius panel legend + annotation are both draggable
  - New Rate-Window Analysis map panel: Nₜ/N_D (log color) in
    (1/kT, T²/eₙ) space with Arrhenius line and Z₁/₂ marker
  - Layout adapts to which combination of panels is enabled

Changes in v1.1
---------------
  - Draggable legends on all plot panels (drag with mouse)
  - ΔC/C unicode label throughout (was dC/C)
  - New 2D Transient Map panel: filled contour of ΔC/C₀(t,T)
    with optional τ(T) = 1/eₙ(T) overlay from Arrhenius fit
  - GridSpec-based layout adapts to which panels are enabled

Requirements
------------
  pip install numpy pandas scipy matplotlib

Run
---
  python DLTS_App.py
"""

import os
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

import numpy as np
import pandas as pd
from scipy.stats import linregress
from scipy.interpolate import griddata

import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.gridspec as mgridspec
from matplotlib.colors import Normalize, LogNorm
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

# ── Palette ───────────────────────────────────────────────────────────────────
C0       = '#2a78d6'
C1       = '#eb6834'
SURFACE  = '#fcfcfb'
TEXT_PRI = '#0b0b0b'
TEXT_SEC = '#52514e'
TEXT_MUT = '#898781'
GRIDLINE = '#e1e0d9'
BASELINE = '#c3c2b7'

# ── ZI grid defaults ──────────────────────────────────────────────────────────
DEFAULT_GRID_OFF   = -0.001
DEFAULT_GRID_DT    = 1.86667e-5
DEFAULT_CHUNK_SIZE = 32768
DEFAULT_RB_MS      = 500.0

# ─────────────────────────────────────────────────────────────────────────────
#  Analysis helpers  (pure functions, no GUI dependency)
# ─────────────────────────────────────────────────────────────────────────────

# Matches both old-style  "25C_001"  and new-style  "85C" / "n10C"
_folder_re = re.compile(r'^(n?)(\d+)C(?:_\d+)?$', re.IGNORECASE)

def folder_to_tempC(name):
    m = _folder_re.match(name)
    if not m:
        return None
    tc = float(m.group(2))
    return -tc if m.group(1).lower() == 'n' else tc

def cap_at(t_ms, cap, tv_ms):
    return float(np.interp(tv_ms, t_ms, cap))

def find_peak_parabolic(T_arr, S_arr, hw=2):
    ip = int(np.argmax(S_arr))
    lo, hi = max(ip - hw, 0), min(ip + hw + 1, len(T_arr))
    T_c, S_c = T_arr[lo:hi], S_arr[lo:hi]
    if len(T_c) < 3:
        return float(T_arr[ip])
    cf = np.polyfit(T_c, S_c, 2)
    if cf[0] < 0:
        Tp = -cf[1] / (2.0 * cf[0])
        lo_b = T_arr[max(ip - hw, 0)]
        hi_b = T_arr[min(ip + hw, len(T_arr) - 1)]
        if lo_b <= Tp <= hi_b:
            return float(Tp)
    return float(T_arr[ip])

def load_data(base, grid_off, grid_dt, chunk_size, rb_ms, cinf_lo, cinf_hi):
    """Load all temperature subfolders.  Returns (data_dict, temps_list)."""
    t_ax = grid_off + np.arange(chunk_size) * grid_dt
    data = {}
    for entry in sorted(os.listdir(base)):
        sub = os.path.join(base, entry)
        if not os.path.isdir(sub):
            continue
        tc = folder_to_tempC(entry)
        if tc is None:
            continue
        fp = os.path.join(sub, 'dev32271_imps_0_sample_param1_avg_00000.csv')
        if not os.path.isfile(fp):
            continue
        df = pd.read_csv(fp, sep=';', header=0,
                         names=['chunk', 'timestamp', 'value'])
        rows = df[df['chunk'] == 0]
        if len(rows) < 100:
            continue
        cap  = rows['value'].values * 1e12
        t_ms = t_ax[:len(rows)] * 1e3
        mi   = (t_ms >= cinf_lo * rb_ms) & (t_ms <= cinf_hi * rb_ms)
        c_inf = float(np.nanmean(cap[mi])) if mi.any() else float(np.nanmean(cap))
        data[tc] = (t_ms, cap, c_inf)
    return data, sorted(data.keys())

def compute_arrhenius(windows, temps, data, gamma, t_peak_lo, t_peak_hi,
                      peak_min_frac=0.05):
    T_K  = np.array([tc + 273.15 for tc in temps])
    mask = (T_K >= t_peak_lo) & (T_K <= t_peak_hi)
    T_m  = T_K[mask]

    en_list, Tp_list, Sp_list = [], [], []
    rows_detail = []

    for (t1, t2) in windows:
        S_full = np.array([
            (cap_at(data[tc][0], data[tc][1], t2)
             - cap_at(data[tc][0], data[tc][1], t1))
            / data[tc][2]
            for tc in temps
        ])
        S_m = S_full[mask]
        if np.max(S_m) < abs(np.min(S_m)):
            S_m = -S_m
        peak_val = np.max(S_m)
        if peak_val <= peak_min_frac * np.max(np.abs(S_full)):
            continue
        Tp = find_peak_parabolic(T_m, S_m)
        en = np.log(t2 / t1) / ((t2 - t1) * 1e-3)
        en_list.append(en); Tp_list.append(Tp); Sp_list.append(peak_val)
        rows_detail.append((t1, t2, en, Tp - 273.15, peak_val))

    en_arr = np.array(en_list)
    Tp_arr = np.array(Tp_list)
    Sp_arr = np.array(Sp_list)
    if len(en_arr) < 2:
        return None

    x = 1000.0 / Tp_arr
    y = np.log(en_arr / Tp_arr**2)
    sl, ic, r, _, se = linregress(x, y)
    kB    = 8.617333e-5
    Et    = -sl * 1000.0 * kB
    Et_se = se  * 1000.0 * kB
    sigma = np.exp(ic) / gamma
    R2    = r**2
    return dict(en_arr=en_arr, Tp_arr=Tp_arr, Sp_arr=Sp_arr,
                Et=Et, Et_se=Et_se, sigma=sigma, R2=R2, N=len(en_arr),
                slope=sl, intercept=ic, x=x, y=y, detail=rows_detail)


# ─────────────────────────────────────────────────────────────────────────────
#  Main application class
# ─────────────────────────────────────────────────────────────────────────────

class DLTSApp:

    def __init__(self, root):
        self.root = root
        self.root.title('DLTS Multiwindow Analysis')
        self.root.configure(bg='#f0f0f0')
        try:
            self.root.state('zoomed')
        except Exception:
            self.root.attributes('-zoomed', True)

        self.data  = {}
        self.temps = []
        self._fig  = None
        self._canvas = None

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # Top banner
        banner = tk.Frame(self.root, bg='#1a3a5c', height=48)
        banner.pack(side='top', fill='x')
        banner.pack_propagate(False)
        tk.Label(banner,
                 text='DLTS Multiwindow Analysis',
                 bg='#1a3a5c', fg='white',
                 font=('Segoe UI', 16, 'bold')).pack(side='left', padx=18, pady=8)
        tk.Label(banner,
                 text='SiC PiN Diode Deep Level Transient Spectroscopy',
                 bg='#1a3a5c', fg='#8fb4d8',
                 font=('Segoe UI', 10)).pack(side='left', padx=4)

        # Main paned window
        paned = ttk.PanedWindow(self.root, orient='horizontal')
        paned.pack(fill='both', expand=True)

        # Left control panel (scrollable)
        ctrl_outer = tk.Frame(paned, bg='#f0f0f0', width=310)
        ctrl_outer.pack_propagate(False)
        paned.add(ctrl_outer, weight=0)

        canvas_ctrl = tk.Canvas(ctrl_outer, bg='#f0f0f0',
                                highlightthickness=0, width=300)
        vscroll = ttk.Scrollbar(ctrl_outer, orient='vertical',
                                command=canvas_ctrl.yview)
        canvas_ctrl.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side='right', fill='y')
        canvas_ctrl.pack(side='left', fill='both', expand=True)

        self.ctrl = tk.Frame(canvas_ctrl, bg='#f0f0f0', padx=10, pady=8)
        canvas_ctrl.create_window((0, 0), window=self.ctrl, anchor='nw')
        self.ctrl.bind('<Configure>',
            lambda e: canvas_ctrl.configure(
                scrollregion=canvas_ctrl.bbox('all')))
        canvas_ctrl.bind('<Enter>',
            lambda e: canvas_ctrl.bind_all('<MouseWheel>',
                lambda ev: canvas_ctrl.yview_scroll(
                    int(-1 * (ev.delta / 120)), 'units')))
        canvas_ctrl.bind('<Leave>',
            lambda e: canvas_ctrl.unbind_all('<MouseWheel>'))

        # Right panel (figure top, results log bottom)
        right = tk.Frame(paned, bg='#f0f0f0')
        paned.add(right, weight=1)

        self.fig_frame = tk.Frame(right, bg='#f0f0f0')
        self.fig_frame.pack(fill='both', expand=True)

        results_frame = tk.LabelFrame(right, text=' Results ',
                                      bg='#f0f0f0', fg=TEXT_SEC,
                                      font=('Consolas', 9))
        results_frame.pack(fill='x', padx=6, pady=(0, 4))
        self.results_text = tk.scrolledtext.ScrolledText(
            results_frame, height=8, font=('Consolas', 9),
            bg='#1e1e2e', fg='#cdd6f4', insertbackground='white',
            state='disabled', wrap='word', relief='flat')
        self.results_text.pack(fill='both', expand=True, padx=4, pady=4)

        # Status bar
        self.status_var = tk.StringVar(value='Load a data folder to begin.')
        tk.Label(self.root, textvariable=self.status_var,
                 anchor='w', bg='#1a3a5c', fg='#8fb4d8',
                 font=('Segoe UI', 9), padx=10).pack(side='bottom', fill='x')

        self._build_controls()

    def _section(self, title):
        tk.Frame(self.ctrl, bg='#1a3a5c', height=2).pack(fill='x', pady=(10, 2))
        tk.Label(self.ctrl, text=title.upper(),
                 bg='#f0f0f0', fg='#1a3a5c',
                 font=('Segoe UI', 8, 'bold')).pack(anchor='w')

    def _row(self, label, widget_factory, **kw):
        f = tk.Frame(self.ctrl, bg='#f0f0f0')
        f.pack(fill='x', pady=2)
        tk.Label(f, text=label, bg='#f0f0f0', fg=TEXT_PRI,
                 font=('Segoe UI', 9), width=18, anchor='w').pack(side='left')
        w = widget_factory(f, **kw)
        w.pack(side='left', fill='x', expand=True)
        return w

    def _spinbox(self, parent, var, lo, hi, inc, fmt='%g', width=9):
        return ttk.Spinbox(parent, textvariable=var,
                           from_=lo, to=hi, increment=inc,
                           format=fmt, width=width, font=('Segoe UI', 9))

    def _build_controls(self):
        p = self.ctrl

        # ── Data ──────────────────────────────────────────────────────────────
        self._section('Data')
        self.base_var = tk.StringVar(value='')
        tk.Label(p, text='Data folder:', bg='#f0f0f0', fg=TEXT_PRI,
                 font=('Segoe UI', 9), anchor='w').pack(fill='x')
        f_path = tk.Frame(p, bg='#f0f0f0')
        f_path.pack(fill='x', pady=2)
        tk.Entry(f_path, textvariable=self.base_var,
                 font=('Segoe UI', 8), relief='solid',
                 fg=TEXT_SEC).pack(side='left', fill='x', expand=True)
        ttk.Button(f_path, text='Browse',
                   command=self._browse).pack(side='left', padx=(4, 0))

        self.load_btn = ttk.Button(p, text='Load Data', command=self._load_data)
        self.load_btn.pack(fill='x', pady=(4, 0))
        self.load_info = tk.Label(p, text='No data loaded.',
                                  bg='#f0f0f0', fg=TEXT_MUT,
                                  font=('Segoe UI', 8), anchor='w')
        self.load_info.pack(fill='x')

        # ── ZI MFIA Grid ──────────────────────────────────────────────────────
        self._section('ZI MFIA Grid')
        self.grid_off_var   = tk.DoubleVar(value=DEFAULT_GRID_OFF)
        self.grid_dt_var    = tk.DoubleVar(value=DEFAULT_GRID_DT)
        self.chunk_size_var = tk.IntVar(value=DEFAULT_CHUNK_SIZE)
        self.rb_ms_var      = tk.DoubleVar(value=DEFAULT_RB_MS)

        self._row('Grid offset (s)',
                  lambda p, **k: self._spinbox(p, self.grid_off_var,
                                               -0.01, 0, 0.0001, '%.6f'))
        self._row('Grid dt (s)',
                  lambda p, **k: self._spinbox(p, self.grid_dt_var,
                                               1e-6, 1e-3, 1e-6, '%.2e'))
        self._row('Chunk size',
                  lambda p, **k: self._spinbox(p, self.chunk_size_var,
                                               1024, 131072, 1024, '%d'))
        self._row('RB duration (ms)',
                  lambda p, **k: self._spinbox(p, self.rb_ms_var,
                                               10, 2000, 10))

        # ── C₀ Estimation ─────────────────────────────────────────────────────
        self._section('C₀ Estimation Window')
        self.cinf_lo_var = tk.DoubleVar(value=0.40)
        self.cinf_hi_var = tk.DoubleVar(value=0.90)

        self._row('Start  (frac RB)',
                  lambda p, **k: self._spinbox(p, self.cinf_lo_var,
                                               0.1, 0.8, 0.05, '%.2f'))
        self._row('End    (frac RB)',
                  lambda p, **k: self._spinbox(p, self.cinf_hi_var,
                                               0.3, 0.99, 0.05, '%.2f'))

        # ── Physical constants ────────────────────────────────────────────────
        self._section('Physical Constants (4H-SiC)')
        self.gamma_var = tk.DoubleVar(value=1.66e21)
        self.nd_var    = tk.DoubleVar(value=3.2e14)

        self._row('γ (cm⁻²s⁻¹K⁻²)',
                  lambda p, **k: self._spinbox(p, self.gamma_var,
                                               1e20, 1e22, 1e20, '%.2e'))
        self._row('Nᵈ (cm⁻³)',
                  lambda p, **k: self._spinbox(p, self.nd_var,
                                               1e12, 1e17, 1e13, '%.2e'))

        # ── Peak search range ─────────────────────────────────────────────────
        self._section('Peak Search Range')
        self.tpeak_lo_var = tk.DoubleVar(value=250.0)
        self.tpeak_hi_var = tk.DoubleVar(value=400.0)

        self._row('T min (K)',
                  lambda p, **k: self._spinbox(p, self.tpeak_lo_var,
                                               100, 350, 5))
        self._row('T max (K)',
                  lambda p, **k: self._spinbox(p, self.tpeak_hi_var,
                                               200, 600, 5))

        # ── Multi-window parameters ───────────────────────────────────────────
        self._section('Multi-Window Parameters')
        self.n_win_var  = tk.IntVar(value=16)
        self.t1_min_var = tk.DoubleVar(value=5.0)
        self.t1_max_var = tk.DoubleVar(value=90.0)
        self.ratio_var  = tk.DoubleVar(value=5.0)

        self._row('N windows',
                  lambda p, **k: self._spinbox(p, self.n_win_var, 3, 60, 1, '%d'))
        self._row('t₁ min (ms)',
                  lambda p, **k: self._spinbox(p, self.t1_min_var, 1, 200, 1))
        self._row('t₁ max (ms)',
                  lambda p, **k: self._spinbox(p, self.t1_max_var, 5, 450, 5))
        self._row('Ratio t₂/t₁',
                  lambda p, **k: self._spinbox(p, self.ratio_var, 2, 20, 0.5))

        # ── Standard 5 windows ────────────────────────────────────────────────
        self._section('Standard Windows (reference)')
        self.std_wins_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(p, text='Show 5-window comparison',
                        variable=self.std_wins_var).pack(anchor='w', pady=2)

        tk.Label(p, text='t1 / t2  (ms):', bg='#f0f0f0', fg=TEXT_SEC,
                 font=('Segoe UI', 8)).pack(anchor='w')
        self.std_entries = []
        for t1, t2 in [(5, 25), (10, 50), (20, 100), (50, 250), (100, 490)]:
            fr = tk.Frame(p, bg='#f0f0f0')
            fr.pack(fill='x', pady=1)
            v1, v2 = tk.DoubleVar(value=t1), tk.DoubleVar(value=t2)
            ttk.Spinbox(fr, textvariable=v1, from_=1, to=490,
                        increment=1, width=5,
                        font=('Segoe UI', 9)).pack(side='left')
            tk.Label(fr, text=' / ', bg='#f0f0f0',
                     font=('Segoe UI', 9)).pack(side='left')
            ttk.Spinbox(fr, textvariable=v2, from_=2, to=499,
                        increment=1, width=5,
                        font=('Segoe UI', 9)).pack(side='left')
            self.std_entries.append((v1, v2))

        # ── Display options ───────────────────────────────────────────────────
        self._section('Display')

        self.show_spectra_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(p, text='Show DLTS spectra panel',
                        variable=self.show_spectra_var).pack(anchor='w')
        self.n_spectra_var = tk.IntVar(value=5)
        self._row('Spectra to plot',
                  lambda p, **k: self._spinbox(p, self.n_spectra_var,
                                               2, 16, 1, '%d'))

        self.show_tmap_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(p, text='Show 2D transient map',
                        variable=self.show_tmap_var).pack(anchor='w', pady=(6, 0))

        self.show_tau_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(p, text='  Overlay τ(T) curve on map',
                        variable=self.show_tau_var).pack(anchor='w')

        self.show_rwm_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(p, text='Show Rate-Window Analysis map',
                        variable=self.show_rwm_var).pack(anchor='w', pady=(6, 0))

        # ── Actions ───────────────────────────────────────────────────────────
        self._section('')
        btn_frame = tk.Frame(p, bg='#f0f0f0')
        btn_frame.pack(fill='x', pady=6)

        self.run_btn = ttk.Button(btn_frame, text='Run Analysis',
                                  command=self._run, state='disabled')
        self.run_btn.pack(fill='x', pady=2)
        ttk.Button(btn_frame, text='Edit Labels & Legends',
                   command=self._open_label_editor).pack(fill='x', pady=2)
        ttk.Button(btn_frame, text='Save Figure as PNG',
                   command=self._save_png).pack(fill='x', pady=2)
        ttk.Button(btn_frame, text='Export Results to TXT',
                   command=self._export_txt).pack(fill='x', pady=2)

    # ── Event handlers ────────────────────────────────────────────────────────

    def _browse(self):
        path = filedialog.askdirectory(title='Select data folder')
        if path:
            self.base_var.set(path)

    def _set_status(self, msg, color='#8fb4d8'):
        self.status_var.set(msg)
        self.root.update_idletasks()

    def _log(self, text):
        self.results_text.configure(state='normal')
        self.results_text.delete('1.0', 'end')
        self.results_text.insert('end', text)
        self.results_text.configure(state='disabled')

    def _load_data(self):
        base = self.base_var.get().strip()
        if not base or not os.path.isdir(base):
            messagebox.showerror('Error', 'Please select a valid data folder.')
            return
        self._set_status('Loading data...')
        try:
            self.data, self.temps = load_data(
                base,
                self.grid_off_var.get(),
                self.grid_dt_var.get(),
                self.chunk_size_var.get(),
                self.rb_ms_var.get(),
                self.cinf_lo_var.get(),
                self.cinf_hi_var.get()
            )
            n = len(self.temps)
            if n == 0:
                raise ValueError('No valid temperature folders found.')
            msg = (f'{n} temperatures loaded: '
                   f'{self.temps[0]:.0f} °C to {self.temps[-1]:.0f} °C')
            self.load_info.configure(text=msg, fg='#2a78d6')
            self._set_status(msg)
            self.run_btn.configure(state='normal')
        except Exception as exc:
            messagebox.showerror('Load Error', str(exc))
            self._set_status(f'Load failed: {exc}', '#eb6834')

    def _run(self):
        if not self.data:
            messagebox.showwarning('No data', 'Load data first.')
            return
        self._set_status('Running analysis...')
        try:
            n   = self.n_win_var.get()
            t1a = self.t1_min_var.get()
            t1b = self.t1_max_var.get()
            r   = self.ratio_var.get()
            t1_arr = np.logspace(np.log10(t1a), np.log10(t1b), n)
            mw = [(float(t1), float(r * t1)) for t1 in t1_arr]

            std_wins = [(v1.get(), v2.get()) for v1, v2 in self.std_entries]

            gamma = self.gamma_var.get()
            nd    = self.nd_var.get()
            tplo  = self.tpeak_lo_var.get()
            tphi  = self.tpeak_hi_var.get()

            res_mw  = compute_arrhenius(mw,       self.temps, self.data,
                                        gamma, tplo, tphi)
            res_std = compute_arrhenius(std_wins, self.temps, self.data,
                                        gamma, tplo, tphi)

            if res_mw is None:
                raise ValueError('Multi-window: no peaks found. '
                                  'Check t1 range and temperature bounds.')

            T_K = np.array([tc + 273.15 for tc in self.temps])
            S_ref = np.array([
                (cap_at(self.data[tc][0], self.data[tc][1],
                        self.rb_ms_var.get())
                 - cap_at(self.data[tc][0], self.data[tc][1], 2.0))
                / self.data[tc][2]
                for tc in self.temps
            ])
            Nt = 2.0 * float(np.nanmax(np.abs(S_ref))) * nd

            self._plot(res_mw, res_std, mw, std_wins, T_K, Nt)
            self._write_results(res_mw, res_std, Nt)
            self._set_status(
                f'Done.   Et = {res_mw["Et"]:.3f} +/- {res_mw["Et_se"]:.3f} eV   '
                f'Nt = {Nt:.2e} cm⁻³'
            )
            self._last_res_mw  = res_mw
            self._last_res_std = res_std
            self._last_nt      = Nt

        except Exception as exc:
            import traceback
            messagebox.showerror('Analysis Error', str(exc))
            self._set_status(f'Error: {exc}', '#eb6834')
            traceback.print_exc()

    # ── Plotting ──────────────────────────────────────────────────────────────

    def _plot(self, res_mw, res_std, mw, std_wins, T_K, Nt):
        show_spectra = self.show_spectra_var.get()
        show_tmap    = self.show_tmap_var.get()
        show_rwm     = self.show_rwm_var.get()
        n_spectra    = self.n_spectra_var.get()

        # Clear previous canvas
        for w in self.fig_frame.winfo_children():
            w.destroy()
        if self._fig:
            plt.close(self._fig)
            self._fig = None

        # Reset stored axes/legend refs (used by label editor)
        self._ax1 = self._ax2 = self._ax3 = self._ax4 = None
        self._leg1 = self._leg2 = self._leg_m = self._leg_rw = None
        self._ann_box = None
        # Draggable artists — applied AFTER canvas is connected to tkinter
        _pending_drags = []   # list of ('legend'|'annot', obj)

        # ── Figure / GridSpec layout ──────────────────────────────────────────
        # ax1=Arrhenius (always), ax2=Spectra, ax3=Transient map, ax4=RW map
        ax2 = ax3 = ax4 = None

        # constrained_layout=True lets matplotlib account for colorbars and axis
        # labels automatically — far more reliable than tight_layout for mixed
        # black/white panels with colorbars on different sides.
        CL = dict(constrained_layout=True)

        if show_spectra and show_tmap and show_rwm:
            # All four: 2×2 grid
            fig = plt.figure(figsize=(14, 11.0), facecolor=SURFACE, **CL)
            gs  = mgridspec.GridSpec(
                2, 2, figure=fig,
                height_ratios=[1.0, 0.9],
                width_ratios=[1.0, 1.0])
            ax1 = fig.add_subplot(gs[0, 0])
            ax2 = fig.add_subplot(gs[0, 1])
            ax3 = fig.add_subplot(gs[1, 0])
            ax4 = fig.add_subplot(gs[1, 1])

        elif show_spectra and show_tmap and not show_rwm:
            # Arrhenius + Spectra top, Transient map full-width bottom
            fig = plt.figure(figsize=(13, 10.5), facecolor=SURFACE, **CL)
            gs  = mgridspec.GridSpec(
                2, 2, figure=fig,
                height_ratios=[1.0, 0.85],
                width_ratios=[1.5, 1.0])
            ax1 = fig.add_subplot(gs[0, 0])
            ax2 = fig.add_subplot(gs[0, 1])
            ax3 = fig.add_subplot(gs[1, :])

        elif show_spectra and not show_tmap and show_rwm:
            # Arrhenius + Spectra top, RW map full-width bottom
            fig = plt.figure(figsize=(13, 10.5), facecolor=SURFACE, **CL)
            gs  = mgridspec.GridSpec(
                2, 2, figure=fig,
                height_ratios=[1.0, 0.85],
                width_ratios=[1.5, 1.0])
            ax1 = fig.add_subplot(gs[0, 0])
            ax2 = fig.add_subplot(gs[0, 1])
            ax4 = fig.add_subplot(gs[1, :])

        elif not show_spectra and show_tmap and show_rwm:
            # Arrhenius full-width top, Transient map + RW map side by side bottom
            fig = plt.figure(figsize=(14, 10.5), facecolor=SURFACE, **CL)
            gs  = mgridspec.GridSpec(
                2, 2, figure=fig,
                height_ratios=[1.0, 0.9])
            ax1 = fig.add_subplot(gs[0, :])
            ax3 = fig.add_subplot(gs[1, 0])
            ax4 = fig.add_subplot(gs[1, 1])

        elif show_spectra and not show_tmap and not show_rwm:
            # Arrhenius + Spectra side by side
            fig, axes = plt.subplots(
                1, 2, figsize=(13, 5.4), facecolor=SURFACE,
                gridspec_kw={'width_ratios': [1.5, 1]}, **CL)
            ax1, ax2 = axes

        elif not show_spectra and show_tmap and not show_rwm:
            # Arrhenius top, Transient map bottom
            fig = plt.figure(figsize=(10, 10.5), facecolor=SURFACE, **CL)
            gs  = mgridspec.GridSpec(
                2, 1, figure=fig,
                height_ratios=[1.0, 0.85])
            ax1 = fig.add_subplot(gs[0])
            ax3 = fig.add_subplot(gs[1])

        elif not show_spectra and not show_tmap and show_rwm:
            # Arrhenius top, RW map bottom
            fig = plt.figure(figsize=(10, 10.5), facecolor=SURFACE, **CL)
            gs  = mgridspec.GridSpec(
                2, 1, figure=fig,
                height_ratios=[1.0, 0.85])
            ax1 = fig.add_subplot(gs[0])
            ax4 = fig.add_subplot(gs[1])

        else:   # Arrhenius only
            fig, ax1 = plt.subplots(1, 1, figsize=(8, 5.4),
                                    facecolor=SURFACE, **CL)

        self._fig = fig
        self._ax1 = ax1; self._ax2 = ax2
        self._ax3 = ax3; self._ax4 = ax4
        # Light background for all non-RW axes; ax4 gets black background below
        for ax in filter(None, [ax1, ax2, ax3]):
            ax.set_facecolor(SURFACE)

        # ── Arrhenius panel ───────────────────────────────────────────────────
        x_all = np.concatenate([res_mw['x'],
                                 res_std['x'] if res_std else res_mw['x']])
        x_lo  = x_all.min() * 0.97
        x_hi  = x_all.max() * 1.03
        x_line = np.linspace(x_lo, x_hi, 400)

        # CI band + fit line
        y_lm = res_mw['slope'] * x_line + res_mw['intercept']
        xmw  = res_mw['x'];  n_mw = len(xmw);  xb = xmw.mean()
        Sxx  = ((xmw - xb)**2).sum()
        ss   = np.sum((res_mw['y'] - (res_mw['slope']*xmw
                                       + res_mw['intercept']))**2)
        se_y = np.sqrt(ss / max(n_mw - 2, 1))
        half = 2.0 * se_y * np.sqrt(1/n_mw + (x_line - xb)**2 / Sxx)
        ax1.fill_between(x_line, y_lm - half, y_lm + half,
                         color=C0, alpha=0.13, zorder=1)
        ax1.plot(x_line, y_lm, color=C0, lw=2.0, zorder=3,
                 label=(f'Multi ({res_mw["N"]} win)  '
                        f'Et={res_mw["Et"]:.3f}±{res_mw["Et_se"]:.3f} eV  '
                        f'R²={res_mw["R2"]:.4f}'))

        # Standard windows fit
        if res_std and self.std_wins_var.get():
            y_ls = res_std['slope'] * x_line + res_std['intercept']
            ax1.plot(x_line, y_ls, color=C1, lw=1.5, ls='--', zorder=3,
                     label=(f'Standard ({res_std["N"]} win)  '
                            f'Et={res_std["Et"]:.3f}±{res_std["Et_se"]:.3f} eV  '
                            f'R²={res_std["R2"]:.4f}'))
            ax1.scatter(res_std['x'], res_std['y'],
                        color=C1, s=100, zorder=5, marker='D',
                        edgecolors=TEXT_PRI, lw=0.7, label='Standard windows')

        # Multi-window scatter coloured by log10(en)
        cmap_arr = plt.cm.plasma
        norm_arr = Normalize(np.log10(res_mw['en_arr'].min()),
                             np.log10(res_mw['en_arr'].max()))
        sc = ax1.scatter(res_mw['x'], res_mw['y'],
                         c=np.log10(res_mw['en_arr']),
                         cmap=cmap_arr, norm=norm_arr,
                         s=55, zorder=4, edgecolors=C0, lw=0.5)
        cb = fig.colorbar(sc, ax=ax1, pad=0.01, fraction=0.025, aspect=28)
        cb.set_label('log₁₀ eₙ  (s⁻¹)',
                     fontsize=8, color=TEXT_SEC)
        cb.ax.tick_params(labelsize=7.5, colors=TEXT_MUT)
        cb.outline.set_edgecolor(BASELINE)

        # Results box
        res_txt = (
            f'Multi-window  ({res_mw["N"]} pts)\n'
            f'Et = {res_mw["Et"]:.3f} ± {res_mw["Et_se"]:.3f} eV\n'
            f'σⁿ = {res_mw["sigma"]:.2e} cm²\n'
            f'Nt = {Nt:.2e} cm⁻³\n'
            f'R² = {res_mw["R2"]:.4f}'
        )
        ann_box = ax1.annotate(
            res_txt,
            xy=(0.42, 0.98), xycoords='axes fraction',
            xytext=(0.42, 0.98), textcoords='axes fraction',
            fontsize=8, va='top', ha='left', color=TEXT_PRI,
            fontfamily='monospace', annotation_clip=False,
            bbox=dict(boxstyle='round,pad=0.45', facecolor='#fffbe6',
                      edgecolor=GRIDLINE, alpha=0.96))
        self._ann_box = ann_box
        _pending_drags.append(('annot', ann_box))   # deferred until canvas connected

        # Dual temperature axis
        ax1b = ax1.twiny()
        ax1b.set_xlim(ax1.get_xlim())
        K_ticks = np.arange(240, 370, 10)
        K_ok = K_ticks[(1000/K_ticks >= x_lo) & (1000/K_ticks <= x_hi)]
        if len(K_ok):
            ax1b.set_xticks(1000 / K_ok)
            ax1b.set_xticklabels([f'{k-273:.0f}°C' for k in K_ok],
                                  fontsize=7.5)
        ax1b.tick_params(colors=TEXT_MUT, labelsize=7.5)
        ax1b.spines[['top', 'left', 'right']].set_color(BASELINE)

        ax1.set_xlabel('1000 / T  (K⁻¹)', fontsize=10,
                       color=TEXT_PRI, labelpad=5)
        ax1.set_ylabel('ln(eₙ / T²)  (s⁻¹ K⁻²)',
                       fontsize=10, color=TEXT_PRI, labelpad=5)
        ax1.set_title('Arrhenius Plot', fontsize=11, color=TEXT_PRI,
                      fontweight='bold', pad=8)
        ax1.grid(which='major', color=GRIDLINE, lw=0.55)
        ax1.minorticks_off()   # no minor gridlines — cleaner look
        ax1.spines[['top', 'right']].set_visible(False)
        ax1.spines[['left', 'bottom']].set_color(BASELINE)
        ax1.tick_params(colors=TEXT_MUT, labelsize=9)

        leg1 = ax1.legend(loc='upper right', fontsize=7.5, frameon=True,
                          framealpha=0.92, edgecolor=GRIDLINE, facecolor=SURFACE,
                          labelcolor=TEXT_PRI, handlelength=2.0)
        self._leg1 = leg1
        _pending_drags.append(('legend', leg1))   # deferred

        # ── DLTS spectra panel ────────────────────────────────────────────────
        if ax2 is not None:
            idx_show = np.round(
                np.linspace(0, len(mw) - 1, min(n_spectra, len(mw)))
            ).astype(int)
            cmap_w = plt.cm.cool
            norm_w = Normalize(0, len(mw) - 1)

            ax2.axhline(0, color=BASELINE, lw=0.7)

            for k in idx_show:
                t1, t2 = mw[k]
                S = np.array([
                    (cap_at(self.data[tc][0], self.data[tc][1], t2)
                     - cap_at(self.data[tc][0], self.data[tc][1], t1))
                    / self.data[tc][2] * 1e3
                    for tc in self.temps
                ])
                en  = np.log(t2 / t1) / ((t2 - t1) * 1e-3)
                col = cmap_w(norm_w(k))
                ax2.plot(T_K - 273.15, S, color=col, lw=1.4,
                         label=f't={t1:.0f}/{t2:.0f} ms  eₙ={en:.1f} s⁻¹')

            for Tp_v in res_mw['Tp_arr']:
                ax2.axvline(Tp_v - 273.15, color=TEXT_MUT,
                            lw=0.4, ls=':', alpha=0.5)

            ax2.set_xlabel('Temperature  (°C)', fontsize=10, color=TEXT_PRI)
            ax2.set_ylabel('ΔC/C₀  (×10⁻³)', fontsize=10,
                           color=TEXT_PRI)
            ax2.set_title('DLTS Spectra', fontsize=11, color=TEXT_PRI,
                          fontweight='bold', pad=8)
            ax2.grid(which='major', color=GRIDLINE, lw=0.55)
            ax2.minorticks_off()   # no minor gridlines
            ax2.spines[['top', 'right']].set_visible(False)
            ax2.spines[['left', 'bottom']].set_color(BASELINE)
            ax2.tick_params(colors=TEXT_MUT, labelsize=9)

            leg2 = ax2.legend(loc='upper left', fontsize=7, frameon=True,
                              framealpha=0.90, edgecolor=GRIDLINE, facecolor=SURFACE,
                              labelcolor=TEXT_PRI)
            self._leg2 = leg2
            _pending_drags.append(('legend', leg2))   # deferred

        # ── 2D transient map ──────────────────────────────────────────────────
        if ax3 is not None:
            leg_m = self._plot_transient_map(ax3, res_mw, T_K)
            if leg_m is not None:
                self._leg_m = leg_m
                _pending_drags.append(('legend', leg_m))

        # ── Rate-Window Analysis map ───────────────────────────────────────────
        if ax4 is not None:
            leg_rw = self._plot_rate_window_map(ax4, res_mw)
            if leg_rw is not None:
                self._leg_rw = leg_rw
                _pending_drags.append(('legend', leg_rw))

        # Finalize
        fig.suptitle('DLTS Multiwindow Analysis',
                     fontsize=12, color=TEXT_PRI, fontweight='bold', y=1.001)
        # constrained_layout (set at figure creation) handles spacing automatically.

        # Embed in tkinter FIRST — this connects fig.canvas, which draggable needs
        self._canvas = FigureCanvasTkAgg(fig, master=self.fig_frame)
        self._canvas.draw()
        toolbar = NavigationToolbar2Tk(self._canvas, self.fig_frame,
                                       pack_toolbar=False)
        toolbar.update()
        toolbar.pack(side='bottom', fill='x')
        self._canvas.get_tk_widget().pack(fill='both', expand=True)

        # ── Drag installation ─────────────────────────────────────────────────
        # matplotlib 3.10 changed DraggableBase to use pick_event, which
        # requires legendPatch.contains() to use an up-to-date renderer
        # transform.  After pack(fill='both'), tkinter resizes the canvas and
        # the transform is stale.  Bypass the built-in draggable system
        # entirely: wire button_press/motion/release events directly so we
        # re-fetch the artist bbox at click time.
        _drag_snapshot = list(_pending_drags)

        def _apply_draggable():
            if self._canvas is None:
                return
            # Redraw with the current (resized) canvas so all transforms are fresh.
            self._canvas.draw()
            canvas_ = self._canvas
            fig_    = fig

            for kind, obj in _drag_snapshot:
                DLTSApp._install_drag(canvas_, fig_, obj, kind)

        self.root.after(300, _apply_draggable)

    # ── Custom drag installer ─────────────────────────────────────────────────

    @staticmethod
    def _install_drag(canvas, fig, artist, kind):
        """
        Wire button_press/motion/release drag to a Legend or Annotation.

        Bypasses matplotlib's pick_event-based DraggableBase so that dragging
        works even when the canvas has been resized after the initial draw().
        The legend's _loc tuple and the annotation's xyann are updated in the
        correct coordinate spaces so the artists persist at their new positions.

        kind : 'legend' | 'annot'
        """
        from matplotlib.transforms import BboxTransformFrom

        s = {'on': False, 'mx0': 0.0, 'my0': 0.0,
             'ax': 0.0, 'ay': 0.0}        # saved anchor in display px

        def _on_press(evt):
            if evt.button != 1:
                return
            # Re-draw to refresh transforms before hit-testing.
            canvas.draw()
            try:
                hit, _ = artist.contains(evt)
            except Exception:
                return
            if not hit:
                return
            s['on']  = True
            s['mx0'] = evt.x
            s['my0'] = evt.y
            if kind == 'annot':
                # Text anchor in display coords
                s['ax'], s['ay'] = (
                    artist.get_transform().transform(artist.xyann))
            else:                                   # legend
                try:
                    rend = fig._get_renderer()
                    bb   = artist.get_window_extent(rend)
                    s['ax'], s['ay'] = bb.x0, bb.y0
                except Exception:
                    s['on'] = False

        def _on_motion(evt):
            if not s['on'] or evt.x is None or evt.y is None:
                return
            dx = evt.x - s['mx0']
            dy = evt.y - s['my0']
            try:
                if kind == 'annot':
                    t = artist.get_transform()
                    artist.xyann = t.inverted().transform(
                        (s['ax'] + dx, s['ay'] + dy))
                else:                               # legend
                    new_x = s['ax'] + dx
                    new_y = s['ay'] + dy
                    # Convert display px → _loc space
                    # (normalised relative to the legend's bbox_to_anchor)
                    bbox = artist.get_bbox_to_anchor()
                    x_loc, y_loc = BboxTransformFrom(bbox).transform(
                        (new_x, new_y))
                    artist._loc = (float(x_loc), float(y_loc))
            except Exception:
                return
            canvas.draw_idle()

        def _on_release(evt):
            s['on'] = False

        canvas.mpl_connect('button_press_event',   _on_press)
        canvas.mpl_connect('motion_notify_event',  _on_motion)
        canvas.mpl_connect('button_release_event', _on_release)

    # ── 2D transient map helper ───────────────────────────────────────────────

    def _plot_transient_map(self, ax, res_mw, T_K):
        """Filled contour plot: ΔC/C₀(t, T) on log-time y-axis.
        Returns the legend object (or None) so the caller can make it draggable."""
        rb_ms  = self.rb_ms_var.get()
        temps  = self.temps
        data   = self.data

        # Time axis from the first loaded temperature
        t_ms_ref = data[temps[0]][0]          # full axis in ms
        t_lo_ms  = max(2.0, t_ms_ref[1])      # skip pre-pulse / first point
        t_hi_ms  = rb_ms * 0.95

        mask_t     = (t_ms_ref >= t_lo_ms) & (t_ms_ref <= t_hi_ms)
        t_ms_full  = t_ms_ref[mask_t]

        if len(t_ms_full) < 10:
            ax.text(0.5, 0.5, 'Not enough time points',
                    transform=ax.transAxes, ha='center', fontsize=11,
                    color=TEXT_MUT)
            return None

        # Subsample to ~250 log-spaced points for smooth rendering
        n_t   = min(250, len(t_ms_full))
        idx_l = np.unique(
            np.round(np.logspace(0, np.log10(len(t_ms_full) - 1), n_t)).astype(int)
        )
        idx_l = np.clip(idx_l, 0, len(t_ms_full) - 1)
        t_ms  = t_ms_full[idx_l]
        t_s   = t_ms * 1e-3                    # seconds

        # Build ΔC/C₀ matrix  shape: (n_time, n_temp)
        Z = np.empty((len(t_ms), len(temps)))
        for j, tc in enumerate(temps):
            t_j, cap_j, cinf_j = data[tc]
            if abs(cinf_j) < 1e-30:
                Z[:, j] = 0.0
                continue
            cap_interp = np.interp(t_ms, t_j, cap_j)
            Z[:, j] = (cap_interp - cinf_j) / cinf_j

        # Signed ΔC/C₀ — keep the sign so the direction of the transient is preserved.
        # For n-type SiC DLTS, majority-carrier emission gives a negative ΔC/C₀
        # (capacitance recovers upward from the pulse), so the peak amplitude is
        # the most-negative region.  jet maps min → blue, max → red/yellow.
        # Scale ×10⁵ so colorbar reads in units of ×10⁻⁵ (raw values ~1e-5).
        Z_disp = Z * 1e5

        # Colour limits: robust 1st–99th percentile to avoid outlier saturation.
        vlo = float(np.nanpercentile(Z_disp, 1))
        vhi = float(np.nanpercentile(Z_disp, 99))
        if vhi <= vlo:
            vlo, vhi = -1e-4, 1e-4
        n_lev = 64
        levels = np.linspace(vlo, vhi, n_lev)

        # Meshgrid
        Tm, tm = np.meshgrid(T_K, t_s)

        # Filled contour + thin contour lines
        cf = ax.contourf(Tm, tm, Z_disp, levels=levels,
                         cmap='jet', extend='both')
        ax.contour(Tm, tm, Z_disp, levels=levels[::6],
                   colors='k', linewidths=0.25, alpha=0.35)

        ax.set_yscale('log')

        # Axis styling
        ax.set_xlabel('Temperature  (K)', fontsize=10, color=TEXT_PRI, labelpad=5)
        ax.set_ylabel('Time  (s)', fontsize=10, color=TEXT_PRI, labelpad=5)
        ax.set_title('ΔC/C₀  Transient Map', fontsize=11,
                     color=TEXT_PRI, fontweight='bold', pad=8)
        ax.spines[['top', 'right']].set_visible(False)
        ax.spines[['left', 'bottom']].set_color(BASELINE)
        ax.tick_params(colors=TEXT_MUT, labelsize=9)

        # Colorbar
        cbar = self._fig.colorbar(cf, ax=ax, pad=0.01,
                                   fraction=0.015, aspect=42)
        cbar.set_label('ΔC/C₀  (×10⁻⁵)', fontsize=9, color=TEXT_SEC)
        cbar.ax.tick_params(labelsize=8, colors=TEXT_MUT)
        cbar.outline.set_edgecolor(BASELINE)

        # ── τ(T) = 1/eₙ(T) overlay ───────────────────────────────────────────
        if self.show_tau_var.get() and res_mw is not None:
            kB    = 8.617333e-5
            gamma = self.gamma_var.get()
            Et    = res_mw['Et']
            sigma = res_mw['sigma']

            T_line  = np.linspace(T_K.min() - 20, T_K.max() + 20, 600)
            en_T    = gamma * sigma * T_line**2 * np.exp(-Et / (kB * T_line))
            tau_T   = 1.0 / en_T              # seconds

            # Keep only the portion visible on the plot
            vis = (tau_T >= t_s.min() * 0.5) & (tau_T <= t_s.max() * 2.0)
            if vis.any():
                T_vis   = T_line[vis]
                tau_vis = np.clip(tau_T[vis], t_s.min(), t_s.max())
                ax.plot(T_vis, tau_vis,
                        color='white', lw=2.2, ls='-', zorder=6,
                        label=f'Z₁₂  τ(T)  '
                              f'Et={Et:.3f} eV')

                # Mark each rate-window DLTS peak on the map.
                # For window i: circle at (Tp_arr[i], τᵢ = 1/en_arr[i]).
                # These are the actual measured (T_peak, τ) pairs — they lie
                # ON the τ(T) curve by construction but are spaced along it
                # according to each window's emission rate.
                Tp_all  = res_mw['Tp_arr']           # K, one per window
                tau_all = 1.0 / res_mw['en_arr']     # s, one per window

                # Keep only circles whose τ falls within the plotted time range
                vis_c = ((tau_all >= t_s.min() * 0.5) &
                         (tau_all <= t_s.max() * 2.0))
                Tp_plot  = Tp_all[vis_c]
                tau_plot = np.clip(tau_all[vis_c], t_s.min(), t_s.max())

                if len(Tp_plot):
                    ax.scatter(Tp_plot, tau_plot,
                               marker='o', s=70,
                               facecolors='none', edgecolors='cyan',
                               lw=1.8, zorder=8,
                               label='Rate-window peaks  (Tₚ, 1/eₙ)')

                    # Annotate at the median circle to avoid clutter
                    mid = len(Tp_plot) // 2
                    ax.annotate(
                        f'  Z₁₂\n  defect',
                        xy=(Tp_plot[mid], tau_plot[mid]),
                        xytext=(Tp_plot[mid] + (T_K.max() - T_K.min()) * 0.07,
                                tau_plot[mid]),
                        color='cyan', fontsize=9, fontweight='bold',
                        va='center', zorder=9,
                        arrowprops=dict(arrowstyle='->', color='cyan', lw=1.2)
                    )

                leg_m = ax.legend(
                    loc='upper right', fontsize=8.5, frameon=True,
                    framealpha=0.85, edgecolor='#8fb4d8',
                    facecolor='#1a3a5c', labelcolor='white')
                return leg_m   # caller adds to pending_drags after canvas connects

        return None   # τ overlay off, or no visible portion

    # ── Rate-Window Analysis map ──────────────────────────────────────────────

    def _plot_rate_window_map(self, ax, res_mw):
        """
        Plot Nₜ/N_D in (1/kT [eV⁻¹], T²/eₙ [K²s]) space.
        Color = 2|ΔC/C₀| on a log scale.  Black background.
        Overlays the Arrhenius line and a Z₁/₂ marker.
        """
        kB    = 8.617333e-5   # eV/K
        gamma = self.gamma_var.get()
        nd    = self.nd_var.get()
        temps = self.temps
        data  = self.data
        ratio = self.ratio_var.get()

        # Build a dense set of windows for the map (independent of UI setting)
        t1_min = self.t1_min_var.get()
        t1_max = self.t1_max_var.get()
        n_map  = 100
        t1_arr = np.logspace(np.log10(t1_min), np.log10(t1_max), n_map)

        T_K = np.array([tc + 273.15 for tc in temps])

        x_pts, y_pts, z_pts = [], [], []

        for t1 in t1_arr:
            t2 = ratio * t1
            # Emission rate for this window [s⁻¹]
            en = np.log(t2 / t1) / ((t2 - t1) * 1e-3)
            for j, tc in enumerate(temps):
                T = T_K[j]
                t_ms, cap, cinf = data[tc]
                if abs(cinf) < 1e-30:
                    continue
                S = (np.interp(t2, t_ms, cap) -
                     np.interp(t1, t_ms, cap)) / cinf
                nt_nd = 2.0 * abs(S)
                if nt_nd < 1e-8:
                    continue
                x_pts.append(1.0 / (kB * T))          # eV⁻¹
                y_pts.append(T**2 / en)                # K²s
                z_pts.append(nt_nd)

        ax.set_facecolor('black')

        if len(x_pts) < 6:
            ax.text(0.5, 0.5, 'Insufficient data for Rate-Window map',
                    transform=ax.transAxes, ha='center',
                    color='white', fontsize=10)
            self._style_rwm_axes(ax)
            return None

        x_pts = np.array(x_pts)
        y_pts = np.array(y_pts)
        z_pts = np.array(z_pts)

        # Colour limits (robust percentiles, log-safe)
        z_lo = max(float(np.nanpercentile(z_pts, 2)),  1e-8)
        z_hi = max(float(np.nanpercentile(z_pts, 98)), z_lo * 10)

        # Interpolate scattered (x, log10_y) → regular grid
        xi   = np.linspace(x_pts.min(), x_pts.max(), 220)
        log_y_min = np.log10(max(y_pts.min(), 1e-20))
        log_y_max = np.log10(y_pts.max())
        yi_log = np.linspace(log_y_min, log_y_max, 220)
        Xi, Yi_log = np.meshgrid(xi, yi_log)
        Yi = 10.0**Yi_log

        Zi = griddata((x_pts, np.log10(y_pts)), z_pts,
                      (Xi, Yi_log), method='linear')
        Zi = np.ma.masked_invalid(Zi)
        Zi = np.ma.masked_less_equal(Zi, 0.0)

        pm = ax.pcolormesh(Xi, Yi, Zi,
                           cmap='jet',
                           norm=LogNorm(vmin=z_lo, vmax=z_hi),
                           shading='auto', zorder=2)
        ax.set_yscale('log')

        # ── Colorbar — right axis showing Nₜ/N_D scale ───────────────────────
        cbar = self._fig.colorbar(pm, ax=ax, pad=0.02,
                                   fraction=0.026, aspect=30)
        cbar.set_label('Nₜ / N_D', fontsize=10, labelpad=14)
        # Force label and tick colours via text artists (robust across mpl versions)
        cbar.ax.yaxis.label.set_color('white')
        cbar.ax.yaxis.set_major_formatter(mticker.LogFormatterMathtext())
        cbar.ax.tick_params(labelsize=8, colors='white', which='both',
                            length=4, width=0.8)
        for lbl in cbar.ax.get_yticklabels():
            lbl.set_color('white')
        cbar.outline.set_edgecolor('#777777')
        cbar.outline.set_linewidth(0.8)

        # ── Arrhenius line: y = (1/γσ) × exp(Et × x) ─────────────────────────
        if res_mw is not None:
            Et    = res_mw['Et']
            sigma = res_mw['sigma']

            x_line = np.linspace(x_pts.min() * 0.97, x_pts.max() * 1.03, 400)
            y_line = (1.0 / (gamma * sigma)) * np.exp(Et * x_line)
            vis    = (y_line >= Yi.min() * 0.2) & (y_line <= Yi.max() * 5.0)
            if vis.any():
                ax.plot(x_line[vis], y_line[vis],
                        color='white', lw=1.8, ls='--',
                        zorder=5, label=f'Arrhenius  Eₜ={Et:.3f} eV')

            # ── Z₁/₂ overlay: open circles along the full Arrhenius trajectory
            # (matches the reference "Rate-Window Analysis" map style where the
            # defect signature appears as a chain of open markers through the
            # data space — slope = Et, intercept = 1/(γσ))
            n_circles = 22
            x_circ = np.linspace(x_pts.min() * 0.98, x_pts.max() * 1.02,
                                  n_circles)
            y_circ = (1.0 / (gamma * sigma)) * np.exp(Et * x_circ)
            vis_c  = ((y_circ >= Yi.min() * 0.5) &
                      (y_circ <= Yi.max() * 2.0))
            if vis_c.any():
                ax.scatter(x_circ[vis_c], y_circ[vis_c],
                           s=55, facecolors='none', edgecolors='#00cfff',
                           lw=1.6, zorder=8, label='Z₁/₂ (fitted)')

        leg_rw = ax.legend(
            loc='upper left', fontsize=8.5, frameon=True,
            framealpha=0.85, edgecolor='#8fb4d8',
            facecolor='#0d1b2a', labelcolor='white')

        self._style_rwm_axes(ax)
        return leg_rw   # caller makes it draggable after canvas connects

    def _style_rwm_axes(self, ax):
        """Apply black-background axis styling for the Rate-Window map."""
        ax.set_xlabel('1/kT  (eV⁻¹)', fontsize=10, labelpad=12)
        ax.set_ylabel('T²/eₙ  (K²s)', fontsize=10, labelpad=14)
        ax.set_title('Rate-Window Analysis Map', fontsize=11,
                     color='white', fontweight='bold', pad=8)
        # Force label colours via the text artists (reliable across mpl versions)
        ax.xaxis.label.set_color('white')
        ax.yaxis.label.set_color('white')
        # Force tick label colours for both axes explicitly
        ax.tick_params(axis='both', which='both',
                       colors='white', labelcolor='white',
                       labelsize=9, length=4, width=0.8)
        for spine in ax.spines.values():
            spine.set_color('#555555')
        ax.yaxis.set_minor_locator(mticker.NullLocator())
        ax.yaxis.set_major_formatter(mticker.LogFormatterMathtext())

    # ── Label / legend editor ─────────────────────────────────────────────────

    def _open_label_editor(self):
        """Popup dialog to edit axis labels, titles, and legend text/font sizes."""
        if self._fig is None:
            messagebox.showinfo('No plot', 'Run the analysis first.')
            return

        dlg = tk.Toplevel(self.root)
        dlg.title('Edit Labels & Legends')
        dlg.configure(bg='#f0f0f0')
        dlg.minsize(460, 340)
        dlg.geometry('500x580')

        # ── Scrollable inner frame ────────────────────────────────────────────
        outer = tk.Frame(dlg, bg='#f0f0f0')
        outer.pack(fill='both', expand=True)
        cvs = tk.Canvas(outer, bg='#f0f0f0', highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient='vertical', command=cvs.yview)
        cvs.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y')
        cvs.pack(side='left', fill='both', expand=True)
        inner = tk.Frame(cvs, bg='#f0f0f0', padx=12, pady=8)
        cvs.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>',
                   lambda e: cvs.configure(scrollregion=cvs.bbox('all')))

        def section(title):
            tk.Frame(inner, bg='#1a3a5c', height=2).pack(fill='x', pady=(10, 2))
            tk.Label(inner, text=title, bg='#f0f0f0', fg='#1a3a5c',
                     font=('Segoe UI', 9, 'bold')).pack(anchor='w')

        # Collectors for Apply
        axis_updates  = []   # (setter_fn, text_var, size_var)
        legend_sizes  = []   # (legend_obj, size_var)
        legend_texts  = []   # (text_obj, text_var)

        def axis_row(parent, label, current_text, current_size, setter_fn):
            f = tk.Frame(parent, bg='#f0f0f0')
            f.pack(fill='x', pady=2)
            tk.Label(f, text=label, bg='#f0f0f0', fg=TEXT_PRI,
                     font=('Segoe UI', 9), width=9, anchor='w').pack(side='left')
            tv = tk.StringVar(value=current_text)
            tk.Entry(f, textvariable=tv, font=('Segoe UI', 9),
                     width=26, relief='solid').pack(side='left', padx=(4, 8))
            tk.Label(f, text='pt', bg='#f0f0f0', fg=TEXT_SEC,
                     font=('Segoe UI', 8)).pack(side='right')
            sv = tk.IntVar(value=max(6, int(current_size)))
            ttk.Spinbox(f, textvariable=sv, from_=6, to=28, increment=1,
                        width=4, font=('Segoe UI', 9)).pack(side='right', padx=(0, 4))
            axis_updates.append((setter_fn, tv, sv))

        # ── Per-panel axis label editor ───────────────────────────────────────
        panel_defs = [
            ('Arrhenius Panel',       self._ax1),
            ('DLTS Spectra Panel',    self._ax2),
            ('Transient Map Panel',   self._ax3),
            ('Rate-Window Map Panel', self._ax4),
        ]
        for pname, ax in panel_defs:
            if ax is None:
                continue
            section(pname)
            axis_row(inner, 'Title',
                     ax.title.get_text(), ax.title.get_fontsize(),
                     ax.set_title)
            axis_row(inner, 'X label',
                     ax.xaxis.label.get_text(),
                     ax.xaxis.label.get_fontsize() or 10,
                     ax.set_xlabel)
            axis_row(inner, 'Y label',
                     ax.yaxis.label.get_text(),
                     ax.yaxis.label.get_fontsize() or 10,
                     ax.set_ylabel)

        # ── Per-legend editor ─────────────────────────────────────────────────
        legend_defs = [
            ('Arrhenius Legend',      self._ax1, self._leg1),
            ('Spectra Legend',        self._ax2, self._leg2),
            ('Transient Map Legend',  self._ax3, self._leg_m),
            ('Rate-Window Legend',    self._ax4, self._leg_rw),
        ]
        for lname, ax, leg in legend_defs:
            if ax is None or leg is None:
                continue
            texts = leg.get_texts()
            if not texts:
                continue
            section(lname)

            # Font size for whole legend
            f_sz = tk.Frame(inner, bg='#f0f0f0')
            f_sz.pack(fill='x', pady=2)
            tk.Label(f_sz, text='Font size', bg='#f0f0f0', fg=TEXT_PRI,
                     font=('Segoe UI', 9), width=9, anchor='w').pack(side='left')
            tk.Label(f_sz, text='pt', bg='#f0f0f0', fg=TEXT_SEC,
                     font=('Segoe UI', 8)).pack(side='right')
            fsv = tk.IntVar(value=max(6, int(texts[0].get_fontsize())))
            ttk.Spinbox(f_sz, textvariable=fsv, from_=6, to=18, increment=1,
                        width=4, font=('Segoe UI', 9)).pack(side='right', padx=(0, 4))
            legend_sizes.append((leg, fsv))

            # Individual entry texts
            for i, txt_obj in enumerate(texts):
                fe = tk.Frame(inner, bg='#f0f0f0')
                fe.pack(fill='x', pady=1)
                tk.Label(fe, text=f'  Entry {i+1}', bg='#f0f0f0', fg=TEXT_SEC,
                         font=('Segoe UI', 8), width=9, anchor='w').pack(side='left')
                ltv = tk.StringVar(value=txt_obj.get_text())
                tk.Entry(fe, textvariable=ltv, font=('Segoe UI', 9),
                         width=32, relief='solid').pack(side='left', padx=4)
                legend_texts.append((txt_obj, ltv))

        # ── Apply / Close buttons ─────────────────────────────────────────────
        def apply_all():
            for setter, tv, sv in axis_updates:
                setter(tv.get(), fontsize=sv.get())
            for leg, fsv in legend_sizes:
                for t in leg.get_texts():
                    t.set_fontsize(fsv.get())
            for txt_obj, ltv in legend_texts:
                txt_obj.set_text(ltv.get())
            if self._canvas:
                self._canvas.draw_idle()

        btn_f = tk.Frame(dlg, bg='#f0f0f0')
        btn_f.pack(fill='x', padx=12, pady=8)
        ttk.Button(btn_f, text='Apply',
                   command=apply_all).pack(side='left', padx=4)
        ttk.Button(btn_f, text='Apply & Close',
                   command=lambda: [apply_all(), dlg.destroy()]).pack(side='left', padx=4)
        ttk.Button(btn_f, text='Close',
                   command=dlg.destroy).pack(side='right', padx=4)

    # ── Results text ──────────────────────────────────────────────────────────

    def _write_results(self, res_mw, res_std, Nt):
        lines = []
        lines.append('=' * 60)
        lines.append('  DLTS Multiwindow Analysis  —  Results')
        lines.append('=' * 60)
        lines.append('')
        lines.append(f'  Multi-window  ({res_mw["N"]} windows)')
        lines.append(f'    Et   = {res_mw["Et"]:.4f} +/- {res_mw["Et_se"]:.4f} eV')
        lines.append(f'    sn   = {res_mw["sigma"]:.3e} cm2')
        lines.append(f'    R2   = {res_mw["R2"]:.5f}')
        lines.append(f'    Nt   ~ {Nt:.3e} cm-3')
        if res_std:
            lines.append('')
            lines.append(f'  Standard  ({res_std["N"]} windows)')
            lines.append(f'    Et   = {res_std["Et"]:.4f} +/- {res_std["Et_se"]:.4f} eV')
            lines.append(f'    sn   = {res_std["sigma"]:.3e} cm2')
            lines.append(f'    R2   = {res_std["R2"]:.5f}')
            if res_std['Et_se'] > 0:
                impr = res_std['Et_se'] / res_mw['Et_se']
                lines.append(f'    Et uncertainty improvement: {impr:.1f}x')
        lines.append('')
        lines.append('  Window detail  (multi):')
        lines.append(f'  {"t1(ms)":>8}  {"t2(ms)":>8}  '
                     f'{"en(s-1)":>10}  {"Tpeak(C)":>10}')
        lines.append('  ' + '-' * 44)
        for t1, t2, en, tp, sp in res_mw['detail']:
            lines.append(f'  {t1:8.1f}  {t2:8.1f}  {en:10.2f}  {tp:10.2f}')
        self._log('\n'.join(lines))

    # ── File I/O ──────────────────────────────────────────────────────────────

    def _save_png(self):
        if self._fig is None:
            messagebox.showinfo('Nothing to save', 'Run the analysis first.')
            return
        path = filedialog.asksaveasfilename(
            defaultextension='.png',
            filetypes=[('PNG image', '*.png'), ('All files', '*.*')],
            initialfile='DLTS_MultiWindow.png'
        )
        if path:
            self._fig.savefig(path, dpi=180, bbox_inches='tight',
                              facecolor=SURFACE)
            self._set_status(f'Figure saved: {path}')

    def _export_txt(self):
        txt = self.results_text.get('1.0', 'end').strip()
        if not txt:
            messagebox.showinfo('Nothing to export', 'Run the analysis first.')
            return
        path = filedialog.asksaveasfilename(
            defaultextension='.txt',
            filetypes=[('Text file', '*.txt'), ('All files', '*.*')],
            initialfile='DLTS_Results.txt'
        )
        if path:
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(txt)
            self._set_status(f'Results exported: {path}')


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    root = tk.Tk()
    root.minsize(1000, 640)
    app  = DLTSApp(root)
    root.mainloop()
