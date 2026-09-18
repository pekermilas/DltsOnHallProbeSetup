# -*- coding: utf-8 -*-
"""
Created on Fri Sep 18 11:10:00 2026

@author: pekermilas
"""

import sys
import os
import re
import json
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QFileDialog, QLabel,
                             QLineEdit, QTabWidget, QMessageBox, QGroupBox,
                             QFormLayout, QListWidget, QListWidgetItem,
                             QTableWidget, QTableWidgetItem, QHeaderView)
from PyQt6.QtCore import Qt
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar

# Physical Constants for Defect Property Conversions
K_BOLTZMANN = 8.617333262145e-5    # eV / K
C_CONSTANT_SI = 3.256e21            # Pre-factor mapping T^2 emission tracking for Si


class DLTSSuiteApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Offline DLTS Core Transient & Defect Signature Suite (v8 - ZI/SiC Format)")
        self.resize(1400, 900)

        # State Data Management Registries
        # ZI mode: dataset_registry maps temp_C -> chunk_number (int)
        # Legacy mode: temp_C -> abs_file_path OR (abs_file_path, chunk_id)
        self.raw_data_directory = (
            r"C:\Users\ikayi\OneDrive\Desktop"
            r"\DLTS_SiC_PiN_DevR6C7_FP0V1ms_RB-5V500ms_Exc300mV100kHz_BW10kHzOrder4_Col15_Rep100_000"
        )
        self.dataset_registry = {}
        self.processed_transients = {}   # temp -> {'time_ms', 'avg_cap_pf', 'C_infinity'}
        self.rate_window_signals = {}    # rw_index -> {'T_k', 'Signal'}
        self.extracted_peaks = {}        # rw_index -> {'T_peak', 'S_peak', 'e_n'}

        # ZI (Zurich Instruments) format state
        self.zi_mode = False
        self.zi_data_file = None          # path to imps_0_sample_param1_avg data CSV
        self.zi_grid_col_offset = -0.001  # s  (from header)
        self.zi_grid_col_delta = 1.86667e-05  # s  (from header)
        self.zi_chunk_size = 32768        # samples per temperature step

        # Legacy fallback sampling rate
        self.sampling_rate_s = 1.8666666666666665e-05

        self.init_ui()
        if os.path.exists(self.raw_data_directory):
            self.load_directory_path(self.raw_data_directory)

    # ------------------------------------------------------------------
    # UI Initialisation
    # ------------------------------------------------------------------
    def init_ui(self):
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.tab_transients = QWidget()
        self.tab_rate_windows = QWidget()
        self.tab_arrhenius = QWidget()

        self.tabs.addTab(self.tab_transients, "1. Transient Extraction")
        self.tabs.addTab(self.tab_rate_windows, "2. Rate Window Analysis")
        self.tabs.addTab(self.tab_arrhenius, "3. Arrhenius Defect Mapping")

        self.setup_transient_tab()
        self.setup_rate_window_tab()
        self.setup_arrhenius_tab()

    # ==========================================
    # TAB 1 UI & LOGIC: Transient Processing
    # ==========================================
    def setup_transient_tab(self):
        main_layout = QHBoxLayout(self.tab_transients)
        left_panel = QVBoxLayout()
        right_panel = QVBoxLayout()

        io_group = QGroupBox("Directory Loader Config")
        io_lay = QVBoxLayout()
        self.btn_load = QPushButton("Select Source Folder")
        self.btn_load.clicked.connect(self.browse_folder)
        self.lbl_folder = QLabel(f"Source: {self.raw_data_directory}")
        self.lbl_folder.setWordWrap(True)
        io_lay.addWidget(self.btn_load)
        io_lay.addWidget(self.lbl_folder)
        io_group.setLayout(io_lay)

        temp_group = QGroupBox("Available Temperatures Filter")
        temp_lay = QVBoxLayout()
        self.temp_list_widget = QListWidget()
        util_lay = QHBoxLayout()
        btn_all = QPushButton("Select All")
        btn_none = QPushButton("Clear All")
        btn_all.clicked.connect(
            lambda: [self.temp_list_widget.item(i).setCheckState(Qt.CheckState.Checked)
                     for i in range(self.temp_list_widget.count())])
        btn_none.clicked.connect(
            lambda: [self.temp_list_widget.item(i).setCheckState(Qt.CheckState.Unchecked)
                     for i in range(self.temp_list_widget.count())])
        util_lay.addWidget(btn_all)
        util_lay.addWidget(btn_none)
        temp_lay.addWidget(self.temp_list_widget)
        temp_lay.addLayout(util_lay)
        temp_group.setLayout(temp_lay)

        param_group = QGroupBox("Timing Boundaries")
        param_lay = QFormLayout()
        self.inp_fp_ms = QLineEdit("1.0")
        self.inp_rb_ms = QLineEdit("500.0")
        self.inp_slice_start = QLineEdit("2.0")
        self.inp_slice_end = QLineEdit("490.0")
        param_lay.addRow("Filling Duration (ms):", self.inp_fp_ms)
        param_lay.addRow("Reverse Bias (ms):", self.inp_rb_ms)
        param_lay.addRow("Analysis Slice Start (ms):", self.inp_slice_start)
        param_lay.addRow("Analysis Slice End (ms):", self.inp_slice_end)
        param_group.setLayout(param_lay)

        exec_group = QGroupBox("Execution Action")
        exec_lay = QVBoxLayout()
        self.btn_process_trans = QPushButton("Extract & Average Transients")
        self.btn_process_trans.setStyleSheet("font-weight: bold; background-color: #e8f5e9;")
        self.btn_process_trans.clicked.connect(self.process_raw_transients)
        self.lbl_trans_status = QLabel("Status: Idle")
        exec_lay.addWidget(self.btn_process_trans)
        exec_lay.addWidget(self.lbl_trans_status)
        exec_group.setLayout(exec_lay)

        left_panel.addWidget(io_group)
        left_panel.addWidget(temp_group, stretch=2)
        left_panel.addWidget(param_group)
        left_panel.addWidget(exec_group)

        self.fig_trans, self.ax_trans = plt.subplots()
        self.canvas_trans = FigureCanvas(self.fig_trans)
        right_panel.addWidget(NavigationToolbar(self.canvas_trans, self))
        right_panel.addWidget(self.canvas_trans)

        main_layout.addLayout(left_panel, stretch=2)
        main_layout.addLayout(right_panel, stretch=5)

    def browse_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Open DLTS Source Folder",
                                                    self.raw_data_directory)
        if dir_path:
            self.load_directory_path(dir_path)

    # ------------------------------------------------------------------
    # Directory loading — auto-detects ZI vs legacy format
    # ------------------------------------------------------------------
    def load_directory_path(self, dir_path):
        self.raw_data_directory = dir_path
        self.lbl_folder.setText(f"Source: {os.path.basename(dir_path)}")
        self.dataset_registry.clear()
        self.temp_list_widget.clear()
        self.zi_mode = False
        self.zi_data_file = None
        self.zi_header = None

        # --- Detect Zurich Instruments format ---
        # Signature: a header CSV matching *imps_0_sample_param1_avg_header*.csv
        zi_headers = [f for f in os.listdir(dir_path)
                      if re.search(r'imps_0_sample_param1_avg_header', f, re.IGNORECASE)
                      and f.endswith('.csv')]

        if zi_headers:
            self._load_zi_dataset(dir_path, zi_headers[0])
        else:
            self._load_legacy_dataset(dir_path)

        for temp in sorted(self.dataset_registry.keys()):
            item = QListWidgetItem(f"{temp} °C")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, temp)
            self.temp_list_widget.addItem(item)

        fmt = "ZI" if self.zi_mode else "Legacy"
        self.lbl_trans_status.setText(
            f"[{fmt}] Indexed {len(self.dataset_registry)} temperature steps.")

    # ------------------------------------------------------------------
    # ZI (Zurich Instruments) dataset loader
    # ------------------------------------------------------------------
    def _load_zi_dataset(self, dir_path, header_filename):
        """Parse the ZI averaged-data folder.

        File layout (inside dir_path):
          dev*_imps_0_sample_param1_avg_header_*.csv  — metadata per chunk
          dev*_imps_0_sample_param1_avg_*.csv         — capacitance transients
          dev*_demods_0_sample_auxin0_avg_*.csv       — AuxIn0 (temp monitor, optional)
          dev*_demods_0_sample_r_avg_*.csv            — demod R (optional)

        Header columns of interest:
          chunk_number, history_name, grid_col_offset, grid_col_delta, chunk_size
        """
        header_path = os.path.join(dir_path, header_filename)
        try:
            hdr = pd.read_csv(header_path, sep=';')
        except Exception as e:
            QMessageBox.critical(self, "Header Load Error",
                                 f"Cannot read ZI header file:\n{e}")
            return

        # Resolve the companion data file
        data_filename = header_filename.replace('_header_', '_').replace('_header', '')
        # Fallback: find any matching data file
        data_candidates = [f for f in os.listdir(dir_path)
                           if re.search(r'imps_0_sample_param1_avg_\d+\.csv$', f, re.IGNORECASE)
                           and 'header' not in f.lower()]
        if not data_candidates:
            QMessageBox.critical(self, "Data File Missing",
                                 "Cannot locate ZI capacitance data CSV (imps_0_sample_param1_avg_*.csv).")
            return

        self.zi_data_file = os.path.join(dir_path, data_candidates[0])

        # Extract grid parameters from the first data row
        row0 = hdr.iloc[0]
        try:
            self.zi_grid_col_offset = float(row0.get('grid_col_offset', -0.001))
            self.zi_grid_col_delta = float(row0.get('grid_col_delta', 1.86667e-05))
            self.zi_chunk_size = int(row0.get('chunk_size', 32768))
        except Exception:
            pass  # keep defaults

        # Build temperature map: chunk_number -> temperature (°C)
        temp_pattern = re.compile(r'^(\d+)C_', re.IGNORECASE)
        for _, row in hdr.iterrows():
            chunk_num = int(row['chunk_number'])
            name = str(row.get('history_name', ''))
            m = temp_pattern.match(name)
            if m:
                temp_c = float(m.group(1))
                self.dataset_registry[temp_c] = chunk_num

        self.zi_mode = True

        # Update timing defaults if we can parse them from the folder name
        folder_name = os.path.basename(dir_path)
        fp_match = re.search(r'FP\w+?(\d+(?:\.\d+)?)ms', folder_name, re.IGNORECASE)
        rb_match = re.search(r'RB[\w\+\-]+?(\d+(?:\.\d+)?)ms', folder_name, re.IGNORECASE)
        if fp_match:
            self.inp_fp_ms.setText(fp_match.group(1))
        if rb_match:
            rb_ms = float(rb_match.group(1))
            self.inp_rb_ms.setText(str(rb_ms))
            self.inp_slice_end.setText(str(rb_ms * 0.98))

    # ------------------------------------------------------------------
    # Legacy dataset loader (original logic, unchanged)
    # ------------------------------------------------------------------
    def _load_legacy_dataset(self, dir_path):
        filename_pattern = re.compile(
            r'^([npNP])(\d+)(?:[pP](\d+))?[cC]?(?:_\d+)?\.(txt|csv)$')

        for file in os.listdir(dir_path):
            file_path = os.path.join(dir_path, file)
            if not os.path.isfile(file_path):
                continue

            if file.lower().endswith('.csv'):
                try:
                    with open(file_path, 'r') as f:
                        first_line = f.readline().strip().lower()

                    is_semicolon = ';' in first_line
                    has_chunk = 'chunk' in first_line
                    has_smoothed = 'smoothed_value' in first_line or 'timestamp' in first_line

                    if is_semicolon:
                        if has_chunk:
                            df_chunks = pd.read_csv(file_path, sep=';', usecols=[0])
                            unique_chunks = sorted(df_chunks.iloc[:, 0].unique())

                            if "p120C-p160C" in file or len(unique_chunks) > 1:
                                chunk_map = {0: 120.0, 1: 125.0, 2: 130.0, 3: 135.0,
                                             4: 140.0, 5: 145.0, 6: 150.0, 7: 155.0,
                                             8: 160.0}
                                for ch in unique_chunks:
                                    if ch in chunk_map:
                                        self.dataset_registry[chunk_map[ch]] = (file_path, ch)
                            else:
                                match = filename_pattern.search(file)
                                if match:
                                    sign, int_part, frac_part, ext = match.groups()
                                    t_val = float(int_part) + (float(f"0.{frac_part}")
                                                               if frac_part else 0.0)
                                    if sign.lower() == 'n':
                                        t_val = -t_val
                                    self.dataset_registry[t_val] = (file_path,
                                                                     unique_chunks[0])
                            continue
                        elif has_smoothed:
                            match = filename_pattern.search(file)
                            if match:
                                sign, int_part, frac_part, ext = match.groups()
                                t_val = float(int_part) + (float(f"0.{frac_part}")
                                                           if frac_part else 0.0)
                                if sign.lower() == 'n':
                                    t_val = -t_val
                                self.dataset_registry[t_val] = (file_path, None)
                            continue
                except Exception as e:
                    print(f"Skipping CSV pre-scan on {file}: {e}")

            match = filename_pattern.search(file)
            if match:
                sign, integer_part, frac_part, ext = match.groups()
                frac = f"0.{frac_part}" if frac_part else "0.0"
                temp = float(integer_part) + float(frac)
                if sign.lower() == 'n':
                    temp = -temp
                self.dataset_registry[temp] = file_path

    # ------------------------------------------------------------------
    # Transient extraction — handles both ZI and legacy formats
    # ------------------------------------------------------------------
    def process_raw_transients(self):
        if not self.dataset_registry:
            return

        selected_temps = []
        for i in range(self.temp_list_widget.count()):
            item = self.temp_list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_temps.append(item.data(Qt.ItemDataRole.UserRole))

        if not selected_temps:
            QMessageBox.warning(self, "Selection Notice",
                                "Please check at least one temperature trace curve.")
            return

        rb_duration_ms = float(self.inp_rb_ms.text())
        c_inf_target_ms = 0.90 * rb_duration_ms

        self.ax_trans.clear()
        self.processed_transients.clear()
        execution_errors = []

        if self.zi_mode:
            self._process_zi_transients(selected_temps, c_inf_target_ms, execution_errors)
        else:
            self._process_legacy_transients(selected_temps, rb_duration_ms,
                                            c_inf_target_ms, execution_errors)

        self.ax_trans.set_xlabel("Time from Reverse Bias Start (ms)")
        self.ax_trans.set_ylabel("Capacitance (pF)")
        self.ax_trans.set_title("Averaged Capacitance Transients Profile")
        self.ax_trans.grid(True, linestyle=":")

        handles, labels = self.ax_trans.get_legend_handles_labels()
        if labels:
            self.ax_trans.legend(loc='best')
        self.canvas_trans.draw()

        if execution_errors:
            QMessageBox.warning(self, "Data Execution Anomaly",
                                "Errors occurred while plotting some curves:\n\n"
                                + "\n".join(execution_errors))
            self.lbl_trans_status.setText("Completed with processing errors.")
        else:
            self.lbl_trans_status.setText(
                f"Transients ensembled completely — {len(self.processed_transients)} traces.")

    def _process_zi_transients(self, selected_temps, c_inf_target_ms, execution_errors):
        """Read the single ZI data CSV once, then extract each selected chunk."""
        self.lbl_trans_status.setText("Loading ZI data file — please wait…")
        QApplication.processEvents()

        try:
            df_all = pd.read_csv(self.zi_data_file, sep=';')
        except Exception as e:
            QMessageBox.critical(self, "File Load Error",
                                 f"Failed to read ZI data CSV:\n{e}")
            return

        # Time axis (relative to reverse-bias start at t = 0 ms)
        # grid_col_offset is typically -FP_duration (e.g. -0.001 s for 1 ms FP)
        time_axis_ms = (self.zi_grid_col_offset
                        + np.arange(self.zi_chunk_size) * self.zi_grid_col_delta) * 1000.0

        for temp in sorted(selected_temps):
            chunk_id = self.dataset_registry[temp]
            try:
                chunk_rows = df_all[df_all['chunk'] == chunk_id]['value'].to_numpy()

                if len(chunk_rows) == 0:
                    execution_errors.append(f"{temp}°C: No data for chunk {chunk_id}")
                    continue

                # Trim to nominal chunk size
                n = min(len(chunk_rows), self.zi_chunk_size)
                avg_curve = chunk_rows[:n].astype(np.float64)
                t_axis = time_axis_ms[:n]

                # Unit conversion: Farads → pF
                if np.nanmax(np.abs(avg_curve)) < 1e-3:
                    avg_curve = avg_curve * 1e12

                c_inf_idx = np.argmin(np.abs(t_axis - c_inf_target_ms))
                c_infinity = avg_curve[c_inf_idx]

                self.processed_transients[temp] = {
                    'time_ms': t_axis,
                    'avg_cap_pf': avg_curve,
                    'C_infinity': c_infinity
                }
                self.ax_trans.plot(t_axis, avg_curve, label=f"{temp}°C")

            except Exception as e:
                execution_errors.append(f"{temp}°C: {str(e)}")

    def _process_legacy_transients(self, selected_temps, rb_duration_ms,
                                   c_inf_target_ms, execution_errors):
        """Original transient extraction for legacy file formats."""
        for temp in sorted(selected_temps):
            target_source = self.dataset_registry[temp]
            try:
                if isinstance(target_source, tuple):
                    file_path, chunk_id = target_source
                    df = pd.read_csv(file_path, sep=';')

                    if chunk_id is not None:
                        df_target = df[df.iloc[:, 0] == chunk_id].dropna()
                    else:
                        df_target = df.dropna()

                    val_cols = [c for c in df_target.columns
                                if any(k in c.lower()
                                       for k in ['value', 'smoothed', 'cap', 'impedance'])]
                    target_col = val_cols[-1] if val_cols else df_target.columns[-1]
                    avg_curve = df_target[target_col].to_numpy()

                    if np.nanmax(np.abs(avg_curve)) < 1e-3:
                        avg_curve = avg_curve * 1e12

                    time_axis_ms = np.arange(len(avg_curve)) * self.sampling_rate_s * 1000

                else:
                    file_path = target_source
                    ext = os.path.splitext(file_path)[1].lower()

                    if ext == '.txt':
                        with open(file_path, 'r') as f:
                            data = json.load(f)
                        aux_v = np.array(data['AuxInput1'], dtype=np.float32)
                        raw_cap = np.array(data['ImpedanceIm'], dtype=np.float32) * 1e12

                        is_forward = aux_v > -2.5
                        transitions = np.diff(is_forward.astype(int))
                        falling_triggers = np.where(transitions == -1)[0]

                        cycle_len = int((rb_duration_ms * 1e-3) / self.sampling_rate_s)
                        valid_blocks = [raw_cap[trig:trig + cycle_len]
                                        for trig in falling_triggers
                                        if trig + cycle_len <= len(raw_cap)]
                        if not valid_blocks:
                            continue
                        avg_curve = np.mean(np.array(valid_blocks), axis=0)
                        time_axis_ms = np.arange(len(avg_curve)) * self.sampling_rate_s * 1000

                    elif ext == '.csv':
                        df = pd.read_csv(file_path)
                        time_axis_ms = df.iloc[:, 0].to_numpy()
                        avg_curve = df.iloc[:, 1].to_numpy()

                c_inf_idx = np.argmin(np.abs(time_axis_ms - c_inf_target_ms))
                c_infinity = avg_curve[c_inf_idx]

                self.processed_transients[temp] = {
                    'time_ms': time_axis_ms,
                    'avg_cap_pf': avg_curve,
                    'C_infinity': c_infinity
                }
                self.ax_trans.plot(time_axis_ms, avg_curve, label=f"{temp}°C")

            except Exception as e:
                execution_errors.append(f"{temp}°C: {str(e)}")

    # ==========================================
    # TAB 2 UI & LOGIC: Rate Window Dashboard
    # ==========================================
    def setup_rate_window_tab(self):
        main_layout = QHBoxLayout(self.tab_rate_windows)
        left_panel = QVBoxLayout()
        right_panel = QVBoxLayout()

        rw_group = QGroupBox("Configure Rate Windows (Double Boxcar)")
        rw_lay = QFormLayout()

        self.rw_inputs = [
            (QLineEdit("10.0"),  QLineEdit("50.0")),
            (QLineEdit("20.0"),  QLineEdit("100.0")),
            (QLineEdit("50.0"),  QLineEdit("250.0")),
            (QLineEdit("100.0"), QLineEdit("490.0")),
        ]

        for i, (t1_w, t2_w) in enumerate(self.rw_inputs):
            row_lay = QHBoxLayout()
            row_lay.addWidget(QLabel("t1 (ms):"))
            row_lay.addWidget(t1_w)
            row_lay.addWidget(QLabel("t2 (ms):"))
            row_lay.addWidget(t2_w)
            rw_lay.addRow(f"Window Set {i + 1}:", row_lay)

        rw_group.setLayout(rw_lay)

        calc_btn = QPushButton("Compute Boxcar Spectrums")
        calc_btn.setStyleSheet("font-weight: bold; background-color: #bbdefb;")
        calc_btn.clicked.connect(self.calculate_rate_windows)

        self.peak_table = QTableWidget(4, 4)
        self.peak_table.setHorizontalHeaderLabels(
            ["Window", "Emission e_n (s⁻¹)", "T_peak (K)", "Max Extrema ΔC/C∞"])
        self.peak_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)

        left_panel.addWidget(rw_group)
        left_panel.addWidget(calc_btn)
        left_panel.addWidget(self.peak_table)

        self.fig_rw, self.ax_rw = plt.subplots()
        self.canvas_rw = FigureCanvas(self.fig_rw)
        right_panel.addWidget(NavigationToolbar(self.canvas_rw, self))
        right_panel.addWidget(self.canvas_rw)

        main_layout.addLayout(left_panel, stretch=3)
        main_layout.addLayout(right_panel, stretch=4)

    def _pseudo_voigt(self, x, amp, center, fwhm, eta, offset):
        gamma = fwhm / 2
        lorentzian = 1 / (1 + ((x - center) / gamma) ** 2)
        gaussian = np.exp(-np.log(2) * ((x - center) / gamma) ** 2)
        return offset + amp * (eta * lorentzian + (1 - eta) * gaussian)

    def calculate_rate_windows(self):
        if not self.processed_transients:
            QMessageBox.warning(self, "Data Missing",
                                "Please run step 1 transient extraction first.")
            return

        self.ax_rw.clear()
        self.rate_window_signals.clear()
        self.extracted_peaks.clear()

        temperatures_c = sorted(list(self.processed_transients.keys()))

        for i, (t1_w, t2_w) in enumerate(self.rw_inputs):
            try:
                t1 = float(t1_w.text())
                t2 = float(t2_w.text())

                if t2 <= t1:
                    QMessageBox.critical(self, "Value Contradiction",
                                         f"Window Set {i + 1}: t2 must be larger than t1.")
                    return

                e_n = np.log(t2 / t1) / ((t2 - t1) * 1e-3)

                dlts_profile = []
                valid_temps_k = []

                for t_c in temperatures_c:
                    data = self.processed_transients[t_c]
                    t_axis = data['time_ms']
                    c_axis = data['avg_cap_pf']
                    c_inf = data['C_infinity']

                    idx1 = np.argmin(np.abs(t_axis - t1))
                    idx2 = np.argmin(np.abs(t_axis - t2))

                    signal = (c_axis[idx2] - c_axis[idx1]) / c_inf
                    dlts_profile.append(signal)
                    valid_temps_k.append(t_c + 273.15)

                y = np.array(dlts_profile, dtype=np.float64)
                x = np.array(valid_temps_k, dtype=np.float64)

                max_idx = np.argmax(np.abs(y))
                p0 = [y[max_idx], x[max_idx], 20.0, 0.5, np.mean(y)]
                bounds = ([-np.inf, -np.inf, 0.1, 0, -np.inf],
                          [np.inf,  np.inf, 500, 1,  np.inf])

                try:
                    popt, _ = curve_fit(self._pseudo_voigt, x, y, p0=p0, bounds=bounds)
                    amp_fit, t_peak, fwhm_fit, eta_fit, offset_fit = popt
                    s_peak = self._pseudo_voigt(t_peak, *popt)
                    x_fit = np.linspace(min(x), max(x), 200)
                    y_fit = self._pseudo_voigt(x_fit, *popt)
                    self.ax_rw.plot(x_fit, y_fit, '--', alpha=0.5, label=f"Fit {i + 1}")
                except Exception:
                    t_peak = x[max_idx]
                    s_peak = y[max_idx]

                self.rate_window_signals[i] = {'T_k': x, 'Signal': y}
                self.extracted_peaks[i] = {'T_peak': t_peak, 'S_peak': s_peak, 'e_n': e_n}

                self.peak_table.setItem(i, 0, QTableWidgetItem(f"Set {i + 1}"))
                self.peak_table.setItem(i, 1, QTableWidgetItem(f"{e_n:.2f}"))
                self.peak_table.setItem(i, 2, QTableWidgetItem(f"{t_peak:.2f}"))
                self.peak_table.setItem(i, 3, QTableWidgetItem(f"{s_peak:.5f}"))

                self.ax_rw.plot(x, y, 'o', label=f"RW {i + 1}")
                self.ax_rw.plot(t_peak, s_peak, 'kx', markersize=10)

            except Exception as ex:
                QMessageBox.critical(self, "Calculation Error",
                                     f"Failed computing set {i + 1}: {str(ex)}")
                return

        self.ax_rw.set_xlabel("Temperature (K)")
        self.ax_rw.set_ylabel("DLTS Signal (ΔC / C∞)")
        self.ax_rw.set_title("Multi-Window DLTS Signal Spectrum (Pseudo-Voigt Refinement)")
        self.ax_rw.grid(True, linestyle=":")

        handles, labels = self.ax_rw.get_legend_handles_labels()
        if labels:
            self.ax_rw.legend()
        self.canvas_rw.draw()

    # ==========================================
    # TAB 3 UI & LOGIC: Arrhenius Analysis
    # ==========================================
    def setup_arrhenius_tab(self):
        main_layout = QHBoxLayout(self.tab_arrhenius)
        left_panel = QVBoxLayout()
        right_panel = QVBoxLayout()

        material_group = QGroupBox("Material Parameters")
        mat_lay = QFormLayout()
        self.inp_nd = QLineEdit("1.5e15")
        mat_lay.addRow("Background Doping Nd (cm⁻³):", self.inp_nd)
        material_group.setLayout(mat_lay)

        calc_btn = QPushButton("Execute Arrhenius Signature Solver")
        calc_btn.setStyleSheet(
            "font-weight: bold; background-color: #ffe082; min-height: 40px;")
        calc_btn.clicked.connect(self.run_arrhenius_solver)

        output_group = QGroupBox("Extracted Microscopic Trap Signatures")
        out_lay = QFormLayout()
        self.lbl_energy = QLabel("Waiting...")
        self.lbl_capture = QLabel("Waiting...")
        self.lbl_density = QLabel("Waiting...")
        out_lay.addRow("Defect Activation Energy Et (eV):", self.lbl_energy)
        out_lay.addRow("Apparent Capture Cross-Sec σ (cm²):", self.lbl_capture)
        out_lay.addRow("Calculated Trap Density Nt (cm⁻³):", self.lbl_density)
        output_group.setLayout(out_lay)

        left_panel.addWidget(material_group)
        left_panel.addWidget(calc_btn)
        left_panel.addWidget(output_group)
        left_panel.addStretch()

        self.fig_arr, self.ax_arr = plt.subplots()
        self.canvas_arr = FigureCanvas(self.fig_arr)
        right_panel.addWidget(NavigationToolbar(self.canvas_arr, self))
        right_panel.addWidget(self.canvas_arr)

        main_layout.addLayout(left_panel, stretch=2)
        main_layout.addLayout(right_panel, stretch=3)

    def run_arrhenius_solver(self):
        if len(self.extracted_peaks) < 2:
            QMessageBox.warning(self, "Execution Error",
                                "Please ensure at least 2 or more complete rate windows "
                                "are populated from Tab 2.")
            return

        try:
            try:
                n_background_doping = float(self.inp_nd.text().strip())
                if n_background_doping <= 0:
                    raise ValueError()
            except ValueError:
                QMessageBox.critical(self, "Input Error",
                                     "Please enter a valid positive number for "
                                     "Background Doping (Nd).")
                return

            x_inv_t = []
            y_ln_en_t2 = []
            signals_max = []

            for i in sorted(self.extracted_peaks.keys()):
                peak = self.extracted_peaks[i]
                tk = peak['T_peak']
                en = peak['e_n']

                x_inv_t.append(1000.0 / tk)
                y_ln_en_t2.append(np.log(en / (tk ** 2)))
                signals_max.append(abs(peak['S_peak']))

            x_inv_t = np.array(x_inv_t, dtype=np.float64)
            y_ln_en_t2 = np.array(y_ln_en_t2, dtype=np.float64)

            def linear_fit(x, m, c): return m * x + c

            popt, pcov = curve_fit(linear_fit, x_inv_t, y_ln_en_t2)
            slope, intercept = popt

            activation_energy_ev = -slope * 1000.0 * K_BOLTZMANN
            apparent_sigma_cm2 = np.exp(intercept) / C_CONSTANT_SI

            max_signal_amplitude = np.max(signals_max)
            trap_density_cm3 = 2.0 * max_signal_amplitude * n_background_doping

            self.lbl_energy.setText(f"<b>{activation_energy_ev:.3f} eV</b>")
            self.lbl_capture.setText(f"<b>{apparent_sigma_cm2:.2e} cm²</b>")
            self.lbl_density.setText(f"<b>{trap_density_cm3:.2e} cm⁻³</b>")

            self.ax_arr.clear()
            self.ax_arr.plot(x_inv_t, y_ln_en_t2, 'rs', markersize=8,
                             label="Experimental Extrema Points")
            x_fit_line = np.linspace(min(x_inv_t) * 0.95, max(x_inv_t) * 1.05, 50)
            self.ax_arr.plot(x_fit_line, linear_fit(x_fit_line, slope, intercept),
                             'b-', label="Linear Fit Reference")

            self.ax_arr.set_xlabel("Reciprocal Temperature (1000 / T) (K⁻¹)")
            self.ax_arr.set_ylabel("ln(e_n / T²)")
            self.ax_arr.set_title(
                "Arrhenius Plot Representation for Trap Signature Extraction")
            self.ax_arr.grid(True, linestyle=":")

            handles, labels = self.ax_arr.get_legend_handles_labels()
            if labels:
                self.ax_arr.legend()
            self.canvas_arr.draw()

        except Exception as e:
            QMessageBox.critical(self, "Arrhenius Failure",
                                 f"Linear fitting matrix criteria failed: {str(e)}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    suite = DLTSSuiteApp()
    suite.show()
    sys.exit(app.exec())