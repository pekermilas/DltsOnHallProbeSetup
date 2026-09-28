"""Re-run the DLTS_HDF5vsJSON_Evaluation measurements against the implemented code.

Usage: python benchmarks/bench_hdf5.py  (takes a few minutes; writes ~650 MB of
synthetic data to benchmarks/benchdata/, deleted at the end). Results are written to
benchmarks/bench_results.json."""
import os, sys, time, json, shutil, tracemalloc
os.environ.setdefault('LOKY_MAX_CPU_COUNT', str(os.cpu_count()))
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO); sys.path.insert(0, os.path.join(REPO, 'tests'))
import matplotlib; matplotlib.use('Agg')
import numpy as np, h5py
import zurichInstruments_Control as ziC
import impedanceAnalysis_Tools as iaT
import liveDataTab as ldT
import detailedAnalysisTab as daT
from conftest import make_step, step_file_name, SAMPLE_DT_S

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'benchdata')
TEMPS = [float(T) for T in np.arange(-50, 150, 5)]  # 40 temperatures
N = 2**16
dev = ziC.ziDevice.__new__(ziC.ziDevice)
out = {}

def mb(p): return os.path.getsize(p) / 1e6
def folder_mb(d): return sum(os.path.getsize(os.path.join(d, f)) for f in os.listdir(d)) / 1e6

shutil.rmtree(ROOT, ignore_errors=True)
os.makedirs(ROOT)

# --- 2. Write side -----------------------------------------------------------
for n, label in [(2**16, '2^16'), (2**20, '2^20')]:
    data = make_step(25.0, n=n)
    pj, ph = os.path.join(ROOT, f'w{n}.txt'), os.path.join(ROOT, f'w{n}.h5')
    t = time.perf_counter(); dev.writeDataJson(data, pj); tj = time.perf_counter() - t
    t = time.perf_counter(); dev.writeDataH5(data, ph, setpoint_C=25.0); th = time.perf_counter() - t
    with open(pj) as f: back = json.load(f)
    rec = iaT.read_h5_record(ph)
    lossless = all(np.array_equal(np.asarray(back[k]), data[k]) and np.array_equal(rec[k], data[k]) for k in data)
    out[f'write {label}'] = dict(json_MB=mb(pj), h5_MB=mb(ph), json_s=tj, h5_s=th, lossless=lossless)
    os.remove(pj); os.remove(ph)
    print('write', label, out[f'write {label}'], flush=True)

# --- 40-temperature run, both formats ----------------------------------------
files = {}
for ext in ('.txt', '.h5'):
    d = os.path.join(ROOT, ext.strip('.')); os.makedirs(d)
    files[ext] = []
    for i, T in enumerate(TEMPS):
        p = os.path.join(d, step_file_name(T, ext))
        data = make_step(T, n=N, seed=i, rb_ms=500.0)
        dev.writeDataH5(data, p, setpoint_C=T) if ext == '.h5' else dev.writeDataJson(data, p)
        files[ext].append(p)
    dev.writeDataJson({'Number of Reps': 1}, os.path.join(d, 'runParams.txt'))
out['run folder MB'] = {ext: folder_mb(os.path.dirname(files[ext][0])) for ext in files}
print('folder', out['run folder MB'], flush=True)

# --- 3a. Offline run load (stage by stage) -----------------------------------
def offline(paths):
    st = {}
    impd = iaT.impdData(fName=list(paths))
    t = time.perf_counter(); assert impd.read_data() == 0; st['read'] = time.perf_counter() - t
    t = time.perf_counter(); impd.cleanup_data(); st['cleanup'] = time.perf_counter() - t
    t = time.perf_counter(); impd.selected_emissions(emissionIndex=0); st['cluster'] = time.perf_counter() - t
    t = time.perf_counter(); impd.filter_emissions(method='pca', emissionIndex=0, recalculate=True, interactivePlot=False); st['denoise'] = time.perf_counter() - t
    st['total'] = sum(st.values())
    return st, impd

res = {}
for ext in ('.txt', '.h5'):
    res[ext] = offline(files[ext])
    out[f'offline {ext}'] = res[ext][0]
    print('offline', ext, res[ext][0], flush=True)

def same(a, b):
    if isinstance(a, dict): return set(a) == set(b) and all(same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and a and not np.isscalar(a[0]):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, str) or a is None: return a == b
    A, B = np.asarray(a), np.asarray(b)
    return A.shape == B.shape and np.array_equal(A, B, equal_nan=A.dtype.kind == 'f')
out['offline identical'] = same(res['.txt'][1].dataEmissions, res['.h5'][1].dataEmissions)
print('offline identical', out['offline identical'], flush=True)
del res

# --- 3b. Qualitative Extract & Average ---------------------------------------
xa = {}
for ext in ('.txt', '.h5'):
    d = os.path.dirname(files[ext][0]); errs = []
    t = time.perf_counter()
    reg = ldT._compute_legacy_dataset(d, errs)
    tr, e2 = ldT._compute_legacy_transients(sorted(reg), 500.0, 450.0, reg, SAMPLE_DT_S)
    el = time.perf_counter() - t
    xa[ext] = tr
    out[f'extract {ext}'] = dict(s=el, temps=len(tr), errors=errs + e2)
    print('extract', ext, out[f'extract {ext}'], flush=True)
out['extract identical'] = same(xa['.txt'], xa['.h5'])
print('extract identical', out['extract identical'], flush=True)

# --- 3c. Detailed Analysis -> Load Data --------------------------------------
dd = {}
for ext in ('.txt', '.h5'):
    d = os.path.dirname(files[ext][0])
    t = time.perf_counter()
    data, temps, errs = daT._load_detailed_data(d, None, None, None, 500.0, 0.2, 0.9)
    out[f'detailed {ext}'] = dict(s=time.perf_counter() - t, temps=len(temps), errors=errs)
    dd[ext] = data
    print('detailed', ext, out[f'detailed {ext}'], flush=True)
out['detailed identical'] = same(dd['.txt'], dd['.h5'])
del dd, xa

# --- 3d. Live ingest of the 40th temperature (as _ingest_files_async does) ---
for ext in ('.txt', '.h5'):
    paths = files[ext]
    impd = iaT.impdData(fName=[paths[0]]); assert impd.read_data() == 0
    for p in paths[1:-1]: assert impd.append_data(fName=[p]) == 0
    impd.cleanup_data(); impd.selected_emissions(emissionIndex=0)
    st = {}
    t = time.perf_counter(); assert impd.append_data(fName=[paths[-1]]) == 0; st['read'] = time.perf_counter() - t
    t = time.perf_counter(); impd.cleanup_data(); impd.dataEmissionClusterParams = None
    impd.selected_emissions(emissionIndex=0); st['cleanup+cluster'] = time.perf_counter() - t
    t = time.perf_counter(); impd.filter_emissions(method='pca', emissionIndex=0, recalculate=True, interactivePlot=False)
    impd.selected_emissions(emissionIndex=-1); st['denoise+all'] = time.perf_counter() - t
    st['total'] = sum(st.values())
    out[f'live ingest {ext}'] = st
    print('live', ext, st, flush=True)
    del impd

# --- Peak memory, reading one temperature ------------------------------------
for ext in ('.txt', '.h5'):
    tracemalloc.start()
    impd = iaT.impdData(fName=[files[ext][0]]); impd.read_data()
    out[f'peak MB {ext}'] = tracemalloc.get_traced_memory()[1] / 1e6
    tracemalloc.stop(); del impd
    print('peak', ext, out[f'peak MB {ext}'], flush=True)

print('versions', sys.version.split()[0], 'h5py', h5py.__version__, 'HDF5', h5py.version.hdf5_version, 'numpy', np.__version__)
with open(os.path.join(os.path.dirname(ROOT), 'bench_results.json'), 'w') as f:
    json.dump(out, f, indent=2, default=str)
shutil.rmtree(ROOT, ignore_errors=True)
