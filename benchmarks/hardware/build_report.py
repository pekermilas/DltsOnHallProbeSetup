"""Build the benchmark report from hw_analyze.py's analysis.json.

Usage: python benchmarks/hardware/build_report.py RUN_OUTPUT_FOLDER [--notes NOTES.html] [--pdf OUT.pdf]
  Writes RUN_OUTPUT_FOLDER/report.html (interactive charts). --notes adds an HTML
  fragment as the report's "Found during the run" section. --pdf also prints the
  report to a PDF with headless Microsoft Edge (light theme, tables expanded).
"""
import argparse, os, re, json, subprocess, tempfile, time
from datetime import datetime
import numpy as np
from hw_common import HERE

EDGE = [r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        r'C:\Program Files\Microsoft\Edge\Application\msedge.exe']


def phase_label(phase):
    m = re.match(r'step:(redo|retake) (-?[\d.]+)C', phase)
    if m:
        return ('Redo ' if m.group(1) == 'redo' else 'Retake ') + m.group(2)
    return {'step:main': 'Main run', 'connect': 'Connect', 'room:emergency': 'Emergency return'}.get(
        phase, 'To room' if phase.startswith('room:') else phase)


def build(A, notesHtml=''):
    grid = [s['T'] for s in A['steps']]
    bands, cur = [], None
    for r in A['stageTemps']:
        if cur is None or r['phase'] != cur['phase']:
            cur = dict(phase=r['phase'], x0=r['t'] / 60, x1=r['t'] / 60); bands.append(cur)
        cur['x1'] = r['t'] / 60
    for i in range(len(bands) - 1):
        bands[i]['x1'] = bands[i + 1]['x0']
    bands = [dict(x0=b['x0'], x1=b['x1'], label=phase_label(b['phase']),
                  fill='--band' if b['phase'].startswith('step') else '--band2') for b in bands]

    rp = A['runParams']
    wc = A['writeCompare']
    inRun = [x['write_h5_s'] for x in A['inRunWrite_s']]
    sumJ, sumH = A['folderMB']['.txt'], A['folderMB']['.h5']
    ex, det, off, mem = A['extract'], A['detailed'], A['offline'], A['peakMemMB']
    live = [r for r in A['liveIngest'] if 'error' not in r]
    last = live[-1] if live else {}
    x = lambda a, b: f'{a / b:.1f}×'
    nPts, nReps = int(rp['Number of Points (power of 2)']), int(rp['Number of Reps'])
    pdfRows = [
        ['Run folder size', '560 → 66 MB (8.5×)', f'{sumJ:.0f} → {sumH:.1f} MB ({x(sumJ, sumH)})'],
        ['Write per step', '0.54 → 0.04 s (2^16 pts)',
         f"{np.mean([w['json_write_s'] for w in wc]):.2f} → {np.mean([w['h5_write_s'] for w in wc]):.2f} s (2^{nPts} pts)"],
        ['Qualitative Extract & Average', '4.06 → 0.14 s (29×)', f"{ex['.txt']['s']:.2f} → {ex['.h5']['s']:.2f} s ({x(ex['.txt']['s'], ex['.h5']['s'])})"],
        ['Detailed Analysis → Load Data', '≈4.1 → 0.2 s (≈25×)', f"{det['.txt']['s']:.2f} → {det['.h5']['s']:.2f} s ({x(det['.txt']['s'], det['.h5']['s'])})"],
        ['Offline run load', '13.2 → 7.5 s (1.8×)', f"{off['.txt']['total']:.2f} → {off['.h5']['total']:.2f} s ({x(off['.txt']['total'], off['.h5']['total'])})"],
        ['Offline: file reading only', '4.3 → 0.6 s', f"{off['.txt']['read']:.2f} → {off['.h5']['read']:.2f} s ({x(off['.txt']['read'], off['.h5']['read'])})"],
        ['Live ingest, last file', '8.2 s; read 0.09 → 0.01 s',
         f"{sum(last.get(k, 0) for k in ('read_s', 'cleanup_s', 'cluster_s', 'denoise_s', 'allEmissions_s')):.2f} s; read {last.get('read_s', 0):.3f} s (HDF5)"],
        ['Peak memory, one step', '42 → 4 MB (10×)', f"{mem['.txt']:.0f} → {mem['.h5']:.0f} MB ({x(mem['.txt'], mem['.h5'])})"],
        ['Analysis results JSON vs HDF5', 'identical',
         'identical' if all(c['ok'] for c in A['checks'] if 'identical' in c['name']) else 'DIFFERENT'],
    ]
    failed = [c['name'] for c in A['checks'] if not c['ok']]
    verdict = ('Every file is complete, correctly typed and carries its attributes; Redo and Remove & Retake replaced '
               'only their own step; every analysis path gives identical results from HDF5 and from the same data '
               'in JSON; and Quick Analysis and Detailed Analysis give the same Arrhenius result on the run.') if not failed else 'Failed: ' + '; '.join(failed) + '.'
    reacq = [(k, v['T']) for k, v in A['redoRetake'].items()]
    first = datetime.fromisoformat(A['steps'][0]['acquired_at'])
    v = A.get('versions', {})
    lo, hi = rp['Aux Output Offset'], rp['Aux Output Offset'] + rp['Aux Output Scale']
    D = dict(analysis=A, grid=grid, bands=bands, runFolder=A['runFolder'].rstrip('\\'), notesHtml=notesHtml,
             dateText=first.strftime('%d %b %Y, from %H:%M'), roomT=rp.get('Room Temperature (C)', ''),
             nPts=nPts, nReps=nReps, meanInRunWrite=float(np.mean(inRun)),
             meanJsonWrite=float(np.mean([w['json_write_s'] for w in wc])), verdictSentence=verdict, pdfRows=pdfRows,
             runSentence=('Driven headless through the GUI\'s own code path: init_experiment → run_experiment → '
                          'finish_experiment, and the Room Temperature return after every run'
                          + (', then ' + ' and '.join(f'a {k} of {T:g} °C' for k, T in reacq)
                             + ', each started from room temperature as the GUI\'s buttons allow.' if reacq else '.')),
             dataSentence=(f"MFIA settings: {rp['Oscillation Frequency'] / 1e3:g} kHz, {rp['Oscillation Amplitude'] * 1e3:g} mV "
                           f"oscillation, {A['rbMs']:g} ms reverse bias and {A['fillMs']:g} ms fill (State Enable / Disable Time), "
                           f"Aux output between {max(lo, hi):g} V and {min(lo, hi):g} V. 2^{nPts} points per step, averaged over "
                           f"{nReps} triggered repetitions."),
             transSentence=(f"Every {A['rbMs']:g} ms reverse-bias cycle in each file, averaged, from the HDF5 files; the JSON "
                            f"copy gives identical curves. Pulses are located midway between the file's own excitation levels."),
             method=('Hardware: Zurich Instruments MFIA DEV32271 and an Instec mK2000B stage. The run used dltsRun from '
                     'runDlts_Tools with a stand-in for the GUI parameter widgets, so every hardware call, file name and '
                     'write went through the application code. Stage temperature was logged every 10 s from a separate '
                     'thread sharing the controller\'s serial lock. Live ingest repeated liveDataTab._ingest_files_async\'s '
                     'calls on each new file. Afterwards each HDF5 file was re-written as JSON with writeDataJson() into '
                     'the benchmark output folder (never the run folder); both copies went through impdData, '
                     '_compute_legacy_transients and _load_detailed_data. The DLTS analysis ran Quick Analysis\' '
                     'functions (dataAnalysisTab._window_peaks, _quick_arrhenius) on the Extract & Average transients '
                     'and Detailed Analysis\' _compute_detailed_analysis on its own Load Data of the HDF5 run. '
                     'Timings are single runs on this PC (Python '
                     f"{v.get('python', '?')}, h5py {v.get('h5py', '?')}, HDF5 {v.get('hdf5', '?')}, numpy {v.get('numpy', '?')}) "
                     'with the OS file cache warm for both formats.'))
    html = open(os.path.join(HERE, 'report_template.html'), encoding='utf-8').read()
    return html.replace('/*DATA*/', json.dumps(D, default=str).replace('</', '<\\/'))


def print_pdf(html, pdfPath):
    edge = next((p for p in EDGE if os.path.exists(p)), None)
    if edge is None:
        raise RuntimeError('Microsoft Edge not found; open report.html and print it to PDF instead.')
    page = ("<!doctype html><html data-theme='light'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width'></head><body>" + html +
            # Print the data tables in plain containers: an opened <details> can be
            # laid out shorter than its content and get overlapped by the next card.
            "<script>document.querySelectorAll('details').forEach(d => { const div = document.createElement('div');"
            " [...d.children].filter(c => c.tagName !== 'SUMMARY').forEach(c => div.appendChild(c));"
            " d.replaceWith(div); });</script></body></html>")
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, 'report_print.html')
        open(src, 'w', encoding='utf-8').write(page)
        subprocess.run([edge, '--headless=new', '--disable-gpu', '--no-pdf-header-footer', '--virtual-time-budget=5000',
                        # Letter paper minus Edge's default margins is ~740 CSS px wide: lay
                        # the page out (and draw the charts) at that width.
                        '--window-size=740,1400', f'--print-to-pdf={os.path.abspath(pdfPath)}',
                        'file:///' + src.replace('\\', '/')], check=True, capture_output=True, timeout=120)
        for _ in range(20):
            if os.path.exists(pdfPath) and os.path.getsize(pdfPath) > 0:
                break
            time.sleep(0.5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Build the benchmark report.')
    parser.add_argument('out', help="hw_run.py's output folder (holds analysis.json)")
    parser.add_argument('--notes', help='HTML fragment for the "Found during the run" section')
    parser.add_argument('--pdf', help='also print the report to this PDF file')
    args = parser.parse_args()
    A = json.load(open(os.path.join(args.out, 'analysis.json')))
    notes = open(args.notes, encoding='utf-8').read() if args.notes else ''
    html = build(A, notes)
    reportPath = os.path.join(args.out, 'report.html')
    open(reportPath, 'w', encoding='utf-8').write(html)
    print(reportPath)
    if args.pdf:
        os.makedirs(os.path.dirname(os.path.abspath(args.pdf)), exist_ok=True)
        print_pdf(html, args.pdf)
        print(args.pdf, f'{os.path.getsize(args.pdf) / 1e6:.2f} MB')
