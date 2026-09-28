"""Verify a hardware benchmark run (hw_run.py) and compare its HDF5 files against
the same data written as JSON .txt, through the application's analysis code.

Usage: python benchmarks/hardware/hw_analyze.py RUN_OUTPUT_FOLDER
  (the folder hw_run.py printed; default: the newest run under output/)
Writes RUN_OUTPUT_FOLDER/analysis.json (for build_report.py) and a JSON copy of
the run in RUN_OUTPUT_FOLDER/json_copy/ -- never inside the data folder.
"""
import os, sys, json, time, csv, re, shutil, tracemalloc, glob
from hw_common import DEFAULT_OUTPUT, REPO
import numpy as np, h5py
import zurichInstruments_Control as ziC
import impedanceAnalysis_Tools as iaT
import liveDataTab as ldT
import detailedAnalysisTab as daT

OUT = sys.argv[1] if len(sys.argv) > 1 else max(glob.glob(os.path.join(DEFAULT_OUTPUT, 'run_*')), key=os.path.getmtime)
meta = json.load(open(os.path.join(OUT, 'run_meta.json')))
RUN = os.path.normpath(meta['dataFolder'])
JSONDIR = os.path.join(OUT, 'json_copy')
dev = ziC.ziDevice.__new__(ziC.ziDevice)
SAMPLE_DT_S = 1.8666666666666665e-05
FP_MS, RB_MS = ldT._legacy_run_timing(RUN) or (1.0, 500.0)
res = dict(runFolder=RUN, fillMs=FP_MS, rbMs=RB_MS)
checks = []
def check(name, ok, detail=''):
    checks.append(dict(name=name, ok=bool(ok), detail=str(detail))); print(('PASS ' if ok else 'FAIL ') + name, detail)

# ---- 1. Verification of the run folder ---------------------------------------
grid = next(e for e in meta['events'] if e['kind'] == 'init')['grid']
stepName = lambda T: ('n' if T < 0 else 'p') + str(abs(float(T))).replace('.', 'p') + '.h5'
listing = sorted(os.listdir(RUN))
check('Run folder has one .h5 per temperature + runParams.txt, nothing else',
      listing == sorted([stepName(T) for T in grid] + ['runParams.txt']), listing)
check('No leftover .h5.tmp files', not any(n.endswith('.tmp') for n in listing))
with open(os.path.join(RUN, 'runParams.txt')) as f:
    res['runParams'] = json.load(f)
nPts, nReps = int(res['runParams']['Number of Points (power of 2)']), int(res['runParams']['Number of Reps'])

files = {T: os.path.join(RUN, stepName(T)) for T in grid}
steps = []
for T, p in files.items():
    with h5py.File(p, 'r') as f:
        attrs = {k: (v.item() if hasattr(v, 'item') else v) for k, v in f.attrs.items()}
        ds = {k: dict(dtype=str(f[k].dtype), shape=f[k].shape, compression=f[k].compression,
                      shuffle=f[k].shuffle) for k in f.keys()}
    rec = iaT.read_h5_record(p)
    steps.append(dict(T=T, file=os.path.basename(p), size_MB=os.path.getsize(p) / 1e6,
                      setpoint=attrs['setpoint_C'], stageT=attrs['stage_temperature_C'],
                      acquired_at=attrs['acquired_at'], nPoints=int(rec['ImpedanceIm'].size),
                      tickUnique=int(np.unique(rec['tickStampImps']).size), datasets=ds))
    check(f'{T:g} C: 8 channels, float64, gzip+shuffle', len(ds) == 8 and all(
        d['dtype'] == 'float64' and d['compression'] == 'gzip' and d['shuffle'] for d in ds.values()))
    check(f'{T:g} C: 2^{nPts} points in every channel', all(d['shape'] == (2 ** nPts,) for d in ds.values()))
    check(f'{T:g} C: tick-stamp time axis intact (not truncated)', steps[-1]['tickUnique'] == 2 ** nPts,
          f"{steps[-1]['tickUnique']} unique values")
    check(f'{T:g} C: setpoint attr = {T:g}, stage T within 0.5 C', attrs['setpoint_C'] == T and
          abs(attrs['stage_temperature_C'] - T) < 0.5, f"stage {attrs['stage_temperature_C']:.3f}")
    rp = json.loads(attrs['run_params'])
    check(f'{T:g} C: run_params attr matches the run', int(rp.get('Number of Points (power of 2)')) == nPts
          and int(rp.get('Number of Reps')) == nReps and rp.get('Data File Format') == 'HDF5', '')
res['steps'] = steps

# Redo / Retake: replaced file differs from the kept original, others untouched
keep = os.path.join(OUT, 'before_redo_retake')
rr, reacquired = {}, set()
for e in meta['events']:
    m = re.match(r'(redo|retake) (-?[\d.]+)C$', str(e.get('label', '')))
    if e['kind'] != 'run' or not m:
        continue
    label, T = ('Redo' if m.group(1) == 'redo' else 'Remove & Retake'), float(m.group(2))
    reacquired.add(T)
    oldPath = os.path.join(keep, os.path.basename(files[T]))
    old, new = iaT.read_h5_record(oldPath), iaT.read_h5_record(files[T])
    with h5py.File(oldPath, 'r') as f: oldAt = f.attrs['acquired_at']
    newAt = next(s for s in steps if s['T'] == T)['acquired_at']
    check(f'{label} at {T:g} C replaced the data (new acquisition time)',
          not np.array_equal(old['ImpedanceIm'], new['ImpedanceIm']) and newAt > oldAt, f'{oldAt} -> {newAt}')
    n = int(3 * (FP_MS + RB_MS) * 1e-3 / SAMPLE_DT_S)
    rr[label] = dict(T=T, oldAt=oldAt, newAt=newAt, t_ms=(old['timeStampImps'][:n] * 1e3).tolist(),
                     oldC=old['ImpedanceIm'][:n].tolist(), newC=new['ImpedanceIm'][:n].tolist())
res['redoRetake'] = rr
for s in steps:
    if s['T'] not in reacquired:
        check(f"{s['T']:g} C written once and untouched by Redo/Retake",
              len([x for x in meta['steps'] if x['setpoint'] == s['T']]) == 1)

# ---- 2. Same data as JSON .txt (what the TXT format would have written) -----------
shutil.rmtree(JSONDIR, ignore_errors=True); os.makedirs(JSONDIR)
writeCmp = []
for T, p in files.items():
    rec = iaT.read_h5_record(p)
    jp = os.path.join(JSONDIR, os.path.basename(p).replace('.h5', '.txt'))
    t = time.perf_counter(); dev.writeDataJson(rec, jp); tj = time.perf_counter() - t
    hp = os.path.join(OUT, 'tmp_rewrite.h5')
    t = time.perf_counter(); dev.writeDataH5(rec, hp, setpoint_C=T); th = time.perf_counter() - t
    os.remove(hp)
    with open(jp) as f: back = json.load(f)
    writeCmp.append(dict(T=T, json_MB=os.path.getsize(jp) / 1e6, h5_MB=os.path.getsize(p) / 1e6,
                         json_write_s=tj, h5_write_s=th,
                         lossless=all(np.array_equal(np.asarray(back[k]), rec[k]) for k in rec)))
shutil.copy(os.path.join(RUN, 'runParams.txt'), JSONDIR)
check('JSON copy of the real data round-trips losslessly', all(w['lossless'] for w in writeCmp))
res['writeCompare'] = writeCmp
res['inRunWrite_s'] = [dict(T=x['setpoint'], phase=x['phase'], write_h5_s=x['write_h5_s']) for x in meta['steps']]

# ---- 3. Read-side comparisons ------------------------------------------------------
def same(a, b):
    if isinstance(a, dict): return set(a) == set(b) and all(same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and a and not np.isscalar(a[0]):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, str) or a is None: return a == b
    A, B = np.asarray(a), np.asarray(b)
    return A.shape == B.shape and np.array_equal(A, B, equal_nan=A.dtype.kind == 'f')

paths = {'.txt': [os.path.join(JSONDIR, os.path.basename(p).replace('.h5', '.txt')) for p in files.values()],
         '.h5': list(files.values())}
off, offObj = {}, {}
for ext in ('.txt', '.h5'):
    st = {}; impd = iaT.impdData(fName=paths[ext])
    t = time.perf_counter(); assert impd.read_data() == 0; st['read'] = time.perf_counter() - t
    t = time.perf_counter(); impd.cleanup_data(); st['cleanup'] = time.perf_counter() - t
    t = time.perf_counter(); impd.selected_emissions(emissionIndex=0); st['cluster'] = time.perf_counter() - t
    t = time.perf_counter(); impd.filter_emissions(method='pca', emissionIndex=0, recalculate=True, interactivePlot=False)
    st['denoise'] = time.perf_counter() - t
    st['total'] = sum(st.values()); off[ext] = st; offObj[ext] = impd
    print('offline', ext, st)
check('Offline load (Live Tools): identical dataValues from JSON and HDF5',
      same(offObj['.txt'].dataValues, offObj['.h5'].dataValues))
check('Offline load (Live Tools): identical emissions + denoised output',
      same(offObj['.txt'].dataEmissions, offObj['.h5'].dataEmissions))
check('Offline load (Live Tools): an emission found at every temperature',
      sorted(offObj['.h5'].dataEmissions) == sorted(offObj['.h5'].dataTemps)
      and all(np.size(e.get('y', [])) > 0 for e in offObj['.h5'].dataEmissions.values()))
emis = {}
for T in offObj['.h5'].dataTemps:
    e = offObj['.h5'].dataEmissions.get(T) or {}
    x = np.asarray(e.get('xTimeStampImps', e.get('x', []))).ravel()
    y = np.asarray(e.get('y', [])).ravel(); yf = np.asarray(e.get('yFiltered', [])).ravel()
    k = max(1, x.size // 400)
    emis[str(T)] = dict(x=x[::k].tolist(), y=y[::k].tolist(),
                        yFiltered=yf[::k].tolist() if yf.size == y.size else [], n=int(x.size))
res['emission0'], res['offline'] = emis, off
del offObj

qa, qaObj = {}, {}
for ext, folder in (('.txt', JSONDIR), ('.h5', RUN)):
    errs = []; t = time.perf_counter()
    reg = ldT._compute_legacy_dataset(folder, errs)
    tr, e2 = ldT._compute_legacy_transients(sorted(reg), RB_MS, 0.9 * RB_MS, reg, SAMPLE_DT_S)
    qa[ext] = dict(s=time.perf_counter() - t, errors=errs + e2); qaObj[ext] = tr
    print('extract', ext, qa[ext]['s'], errs + e2)
check('Qualitative Extract & Average: a transient for every temperature, no errors',
      not qa['.h5']['errors'] and sorted(qaObj['.h5']) == grid
      and all(len(v['avg_cap_pf']) > 0 for v in qaObj['.h5'].values()),
      f"{len(qaObj['.h5'])} transients, reverse bias {RB_MS:g} ms; {qa['.h5']['errors']}")
check('Qualitative Extract & Average: identical transients from JSON and HDF5',
      bool(qaObj['.h5']) and same(qaObj['.txt'], qaObj['.h5']))
res['extract'] = qa
res['transients'] = {str(T): dict(t_ms=np.asarray(v['time_ms']).tolist(), c_pf=np.asarray(v['avg_cap_pf']).tolist(),
                                  cinf=float(v['C_infinity'])) for T, v in qaObj['.h5'].items()}

det = {}
for ext, folder in (('.txt', JSONDIR), ('.h5', RUN)):
    t = time.perf_counter(); d, temps, errs = daT._load_detailed_data(folder, None, None, None, RB_MS, 0.4, 0.9)
    det[ext] = dict(s=time.perf_counter() - t, temps=temps, errors=errs, data=d)
check('Detailed Analysis Load Data: every temperature loaded, identical from JSON and HDF5',
      det['.h5']['temps'] == grid and not det['.h5']['errors'] and same(det['.txt']['data'], det['.h5']['data']),
      f"{len(det['.h5']['temps'])} temperatures")
res['detailed'] = {k: dict(s=v['s'], errors=v['errors']) for k, v in det.items()}

mem = {}
for ext in ('.txt', '.h5'):
    tracemalloc.start(); impd = iaT.impdData(fName=[paths[ext][0]]); impd.read_data()
    mem[ext] = tracemalloc.get_traced_memory()[1] / 1e6; tracemalloc.stop(); del impd
res['peakMemMB'] = mem
res['folderMB'] = {'.txt': sum(w['json_MB'] for w in writeCmp), '.h5': sum(w['h5_MB'] for w in writeCmp)}

# Raw acquisition snippet for the report (first 3 pulse cycles at each T)
n = int(3 * (FP_MS + RB_MS) * 1e-3 / SAMPLE_DT_S)
res['raw'] = {}
for T, p in files.items():
    r = iaT.read_h5_record(p, keys=('timeStampImps', 'AuxInput1', 'ImpedanceIm'))
    res['raw'][str(T)] = dict(t_ms=(r['timeStampImps'][:n] * 1e3).tolist(), aux=r['AuxInput1'][:n].tolist(),
                              c=r['ImpedanceIm'][:n].tolist())

# ---- 4. Run timeline -------------------------------------------------------------------
with open(os.path.join(OUT, 'stage_temperature.csv')) as f:
    res['stageTemps'] = [dict(t=float(r['t_s']), T=float(r['T_C']), phase=r['phase']) for r in csv.DictReader(f)]
res.update(stepTimings=meta['steps'], events=meta['events'], liveIngest=meta['liveIngest'], checks=checks,
           versions=dict(python=sys.version.split()[0], h5py=h5py.__version__, hdf5=h5py.version.hdf5_version,
                         numpy=np.__version__))
json.dump(res, open(os.path.join(OUT, 'analysis.json'), 'w'), default=str)
print(f"\n{sum(c['ok'] for c in checks)}/{len(checks)} checks passed -> {os.path.join(OUT, 'analysis.json')}")
