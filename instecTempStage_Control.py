# -*- coding: utf-8 -*-
"""
Created on Tue Apr 21 13:15:34 2026

@author: spencer
"""

# -*- coding: utf-8 -*-
"""
Created on Wed Jun  8 11:40:12 2022

@author: pekermilas
"""
# EXAMPLE CALLS
# import instecTempStage_Control as tsC
# t = tsC.mK2000B('COM7')
# if t.connect_temp_controller() != 0: print(t.lastError)
# t.go_to_temp(35, 5, 0)
# t.disconnect_temp_controller()


import serial
import serial.tools.list_ports
import threading
import time
import numpy as np
import lmfit
import lmfit.models

# Port used when none is given (the lab PC's controller). The Input Parameters
# tab has a Serial Port box, so this is only the starting choice.
DEFAULT_PORT = 'COM7'

# Longest wait (s) for one serial read or write before read_temp() gives up on
# that reply; it asks READ_RETRIES more times before raising TimeoutError.
SERIAL_TIMEOUT_S = 2.0
READ_RETRIES = 1

# Waits in go_to_temp()/go_to_room_temp() sleep in slices this long (s), so
# abort() takes effect within a fraction of a second instead of after a whole
# 5 s poll, 10 s confirmation or stability delay.
WAIT_SLICE_S = 0.2


def list_serial_ports():
    """Names of the serial ports Windows reports (e.g. ['COM3', 'COM7']), sorted."""
    try:
        return sorted(p.device for p in serial.tools.list_ports.comports())
    except Exception:
        return []

# The Input Parameters tab's temperature defaults (runParamsTab). mK2000B.configure()
# starts from these.
DEFAULT_PARAMS = {'Initial Temperature (C)': 25.0, 'Final Temperature (C)': 25.0,
                  'Temperature Step (C)': 5.0, 'Temperature Ramp (C/min)': 5.0,
                  'Stability Delay (s)': 0.0, 'Room Temperature (C)': 25.0, 'Room Ramp (C/min)': 10.0}


class mK2000B:

    def __init__(self, port = None):
        self.port = port or DEFAULT_PORT
        self.dev = None
        self.rm = None
        self.state = False
        # Why the last connect or disconnect failed ('' when it didn't), so the
        # GUI can show it instead of the reason only reaching the console.
        self.lastError = ''
        self.Tinitial = 25
        self.Tfinal = 25
        self.tempStep = 5
        self.numTemps = 1
        self.tRamp = 5
        self.tStableDelay = 0
        self.tempGrid = 25
        self.Troom = 25        # where the stage is returned to after a run (see go_to_room_temp)
        self.roomRamp = 10     # C/min used for that return
        # The run thread and the GUI's close handler can both talk to the
        # controller at once; every command (and command+response pair) holds
        # this lock so their bytes/replies never interleave on the serial port.
        self._ioLock = threading.RLock()
        # Set by abort() when the GUI is closing: go_to_temp() then refuses to
        # command a new set-point (which would override the room-temperature
        # ramp) and any in-progress wait loop exits.
        self._aborted = False
        pList = ['Initial Temperature (C)', 'Final Temperature (C)',
                 'Temperature Step (C)', 'Temperature Ramp (C/min)',
                 'Stability Delay (s)', 'Room Temperature (C)', 'Room Ramp (C/min)',
                 'Temperature Grid (C)']
        self.params = dict.fromkeys(pList, None)

    # params name -> the attribute go_to_temp()/go_to_room_temp() actually use.
    _PARAM_ATTRS = {'Temperature Ramp (C/min)': 'tRamp', 'Stability Delay (s)': 'tStableDelay',
                    'Room Temperature (C)': 'Troom', 'Room Ramp (C/min)': 'roomRamp'}

    def _sync_attrs_from_params(self):
        """Copy the GUI-set ramp/delay/room values from self.params into the
        attributes the motion methods read. Without this, go_to_temp() kept
        using the constructor defaults (5 C/min, 0 s) no matter what was
        entered in the Input Parameters tab."""
        for pName, attr in self._PARAM_ATTRS.items():
            value = self.params.get(pName)
            if value is not None:
                setattr(self, attr, float(value))

    @staticmethod
    def build_temp_grid(Tinit, Tfin, step):
        """Build a temperature grid from start to stop inclusive, stepping by
        `step` -- rather than a fixed step count -- so start/stop are always
        exactly on-grid regardless of whether the span divides evenly by
        step (the last interval is simply shorter/longer than the rest in
        that case, landing exactly on Tfin instead of overshooting past it
        or stopping short of it).
        """
        Tinit = float(Tinit)
        Tfin = float(Tfin)
        step = abs(float(step))
        if Tinit == Tfin:
            return np.array([Tinit])
        if step <= 0:
            return np.array([Tinit, Tfin])

        direction = 1.0 if Tfin > Tinit else -1.0
        nSteps = max(1, int(round(abs(Tfin - Tinit) / step)))
        grid = Tinit + direction * step * np.arange(nSteps + 1)
        grid[-1] = Tfin
        return grid

    def _require_connection(self):
        if self.dev is None or not self.state:
            raise RuntimeError(f"temperature controller on {self.port} is not connected")

    def read(self):
        """One raw byte from the port (b'' on timeout)."""
        self._require_connection()
        with self._ioLock:
            return self.dev.read()

    def write(self, writeStr = None):
        """Send a raw command (str or bytes, including the trailing newline).
        Returns 0, or -1 if not connected."""
        if self.dev is None or not self.state:
            return -1
        data = writeStr.encode() if isinstance(writeStr, str) else writeStr
        with self._ioLock:
            self.dev.write(data)
        return 0

    def query(self, queryStr = None):
        """Send a command and return the one-line reply as a str ('' if none
        arrived within SERIAL_TIMEOUT_S). A newline is added if missing."""
        self._require_connection()
        if not queryStr.endswith('\n'):
            queryStr += '\n'
        with self._ioLock:
            self.dev.reset_input_buffer()
            self.dev.write(queryStr.encode())
            return self.dev.readline().decode(errors='replace').strip()

    def connect_temp_controller(self):
        """Open self.port. Returns 0 when connected (or already connected),
        -1 on failure, with the reason in self.lastError."""
        if self.state:
            print('Temperature controller is already connected!')
            return 0
        self.lastError = ''
        ser = None
        try:
            ser = serial.Serial()
            ser.port = self.port
            # Without these a controller that stops answering blocks
            # readline() (and every caller: runs, the close dialog) forever.
            ser.timeout = SERIAL_TIMEOUT_S
            ser.write_timeout = SERIAL_TIMEOUT_S
            ser.open()
            time.sleep(0.2)
        except Exception as e:
            # Most often: the port does not exist, or another program (e.g. the
            # Hall probe software) already holds it -- Windows ports are exclusive.
            self.lastError = f"could not open {self.port}: {e}"
            print(f"Error connecting to device: {self.lastError}")
            try:
                if ser is not None and getattr(ser, 'is_open', False):
                    ser.close()
            except Exception:
                pass
            self.state = False
            self.dev = None
            return -1
        self.dev = ser
        self.state = True
        return 0

    def disconnect_temp_controller(self, stopControl=True, lockTimeout=5.0):
        """Close the serial connection. stopControl=True first sends
        TEMPerature:STOP, which ends temperature control (and cancels any
        ramp in progress); pass False to leave the controller running on its
        own -- e.g. still ramping to room temperature after the GUI exits.

        The port is always closed, even if STOP cannot be sent (earlier the
        exception skipped close() and the port stayed held until the program
        exited). Returns 0, or -1 if STOP failed (the controller may still be
        controlling); the reason is in self.lastError."""
        if self.dev is None:
            print("Nothing to do!")
            self.state = False
            return 0
        if not self.state:
            print("Already disconnected!")
            self.dev = None
            return 0
        status = 0
        self.lastError = ''
        locked = self._ioLock.acquire(timeout=lockTimeout)
        try:
            ser = self.dev
            if stopControl:
                try:
                    ser.write(str.encode(":TEMPerature:STOP\n"))
                    time.sleep(0.5)
                except Exception as e:
                    self.lastError = f"STOP not sent on {self.port}: {e}"
                    print(self.lastError)
                    status = -1
            try:
                ser.close()
            except Exception as e:
                self.lastError = (self.lastError + '; ' if self.lastError else '') + \
                                 f"closing {self.port}: {e}"
                print(f"Error closing {self.port}: {e}")
        finally:
            self.state = False
            self.dev = None
            if locked:
                self._ioLock.release()
        return status

    def abort(self):
        """Stop go_to_temp()/go_to_room_temp() from commanding or waiting any
        further (see self._aborted). Used when the GUI is closing. Stays set
        until reset_abort()."""
        self._aborted = True

    def reset_abort(self):
        """Clear abort() so the object can move the stage again (e.g. to run
        the room-temperature return after a watchdog abort)."""
        self._aborted = False

    def _wait(self, seconds):
        """Sleep `seconds` in WAIT_SLICE_S slices. Returns True if abort() was
        called meanwhile (the wait then ends early)."""
        end = time.monotonic() + max(0.0, float(seconds))
        while True:
            if self._aborted:
                return True
            left = end - time.monotonic()
            if left <= 0:
                return False
            time.sleep(min(WAIT_SLICE_S, left))

    def start_ramp(self, T, ramp, lockTimeout=None):
        """Command a ramp to T at `ramp` C/min and return immediately (the
        controller carries it out on its own). lockTimeout: seconds to wait
        for another thread's in-flight command; if it expires the command is
        sent anyway -- used on GUI close, where getting the stage to room
        temperature matters more than a possibly garbled concurrent reply."""
        locked = self._ioLock.acquire(timeout=-1 if lockTimeout is None else lockTimeout)
        try:
            self.dev.write(str.encode('TEMPerature:RAMP '+str(T)+','+str(ramp)+'\n'))
        finally:
            if locked:
                self._ioLock.release()

    def read_temp(self, retries=READ_RETRIES):
        """Current stage temperature (C), as one locked query/response pair.

        Waits at most SERIAL_TIMEOUT_S for each reply and asks again up to
        `retries` times (a missed or garbled reply), then raises TimeoutError,
        so a controller that stops answering fails the step instead of hanging.
        """
        with self._ioLock:
            reply = b''
            for _ in range(retries + 1):
                # Drop a late reply to an earlier query so it isn't read as this one.
                self.dev.reset_input_buffer()
                self.dev.write(str.encode(":TEMPerature:CTEMperature?\n"))
                reply = self.dev.readline()
                try:
                    return float(reply.strip().decode())
                except (ValueError, UnicodeDecodeError):
                    continue
            raise TimeoutError(
                f"temperature controller on {self.port} did not answer the temperature query "
                f"({retries + 1} tries, {SERIAL_TIMEOUT_S:g} s each; last reply {reply!r})")

    def expected_del_t(self, T=25):
        Ttheo = np.array([19.648,100.0,199.990,300.0,400.0,500.0,600.0])
        Tmeas = np.array([19.648,99.679,199.633,299.235,398.980,498.725,598.470])
        
        delT = np.abs(Tmeas-Ttheo)
        linear1 = lmfit.models.LinearModel(prefix='li1_')
        pars = linear1.guess(delT,x=Ttheo)
        out=linear1.fit(delT, pars, x=Ttheo, method='leastsq')
        
        negErrScale = 2.0
        # For mx+n
        mF = out.params['li1_slope'].value
        nF = out.params['li1_intercept'].value
        
        mH = (delT[-1]-delT[0])/(Ttheo[-1]-Ttheo[0])
        nH = delT[-1] - (mH*Ttheo[-1])
        
        mL = (delT[-1]*negErrScale-delT[0])/(-190.0-Ttheo[0])
        nL = delT[-1]*negErrScale - (mL*-190.0)
        
        if T<Ttheo[0]:
            delTEstimate = mL*T+nL
        else:
            if T<=25.0:
                delTEstimate = 0.1
            else:
                delTEstimate = mH*T+nH
            
        return delTEstimate

    def go_to_temp(self, Tf=25, ramp=None, delayTime=None):
        """Ramp to Tf at `ramp` C/min, wait for it to stabilize, then wait
        `delayTime` s. ramp/delayTime default to self.tRamp/self.tStableDelay
        (earlier versions ignored the arguments and always used those).

        Returns 0, or -1 if aborted (abort()) before or during the wait.
        Raises RuntimeError if not connected -- earlier it returned 0 without
        moving the stage, so a run would take data at the wrong temperature."""
        if self._aborted:
            return -1
        self._require_connection()
        ramp = self.tRamp if ramp is None else ramp
        delayTime = self.tStableDelay if delayTime is None else delayTime

        self.start_ramp(Tf, ramp)
        if self._wait(0.5):
            return -1

        # Wait for T stabilization
        print('Wait for T = {} stabilization!'.format(Tf))
        delTmeas, delTtheo = self.measure_proxy_temp(Tf)
        while delTmeas > delTtheo:
            if self._aborted:
                return -1
            delTmeas, delTtheo = self.measure_proxy_temp(Tf)
            if delTmeas < delTtheo:
                if self._wait(10):
                    return -1
                delTmeas, delTtheo = self.measure_proxy_temp(Tf)
            elif self._wait(5):
                return -1

        if self._wait(delayTime):
            return -1
        return 0

    def go_to_room_temp(self, Tr=None, ramp=None, tolerance=0.5, extraWaitS=900):
        """Ramp to room temperature Tr (default self.Troom) at `ramp` C/min
        (default self.roomRamp) and wait until within `tolerance` C of it.

        Returns 0 once there, 1 if it gave up waiting, -1 if not connected.
        Tolerance is a plain 0.5 C: the previous loop replaced it with the
        sensor-calibration tolerance (expected_del_t, ~0.03-0.1 C), which is
        needed for measurement set-points but not for parking the stage, and
        could make this wait forever (e.g. a lab warmer than Tr). The wait is
        also capped at the ramp's expected duration + extraWaitS, since this
        now runs unattended after every run.
        """
        Tr = self.Troom if Tr is None else Tr
        ramp = self.roomRamp if ramp is None else ramp
        if self.dev is None or not self.state:
            print("T-Controller is disconnected!")
            return -1

        self.start_ramp(Tr, ramp)
        time.sleep(0.5)

        currT = self.read_temp()
        deadline = time.time() + abs(Tr - currT) / max(float(ramp), 1e-6) * 60.0 + extraWaitS
        while np.abs(Tr - currT) > tolerance:
            # Aborted = the GUI is closing and its own close handler has taken
            # over the room-temperature return; the ramp keeps going.
            if self._aborted:
                return 1
            if time.time() > deadline:
                print(f"Gave up waiting for room temperature {Tr} C (stage at {currT} C).")
                return 1
            if self._wait(5):
                return 1
            currT = self.read_temp()

        if self._wait(10):
            return 1
        return 0

    def set_temp_grid(self, userInput = False):
        """Build tempGrid from the initial/final/step values (self.params, or
        console prompts with userInput=True). Needs no connection; earlier it
        did nothing unless a port object existed."""
        if userInput:
            Tinit = input("Please enter Initial Temperature (C): ") or self.Tinitial
            Tfin = input("Please enter Final Temperature (C): ") or self.Tfinal
            tStep = input("Please enter Temperature Step (C): ") or self.tempStep
        else:
            Tinit = self.params.get('Initial Temperature (C)')
            Tfin = self.params.get('Final Temperature (C)')
            tStep = self.params.get('Temperature Step (C)')

        self.Tinitial = Tinit
        self.Tfinal = Tfin
        self.tempStep = tStep

        self.tempGrid = self.build_temp_grid(Tinit, Tfin, tStep)
        self.numTemps = len(self.tempGrid)
        return 0

    def set_param_value(self, pName='Initial Temperature (C)', valueDict=None):
        if valueDict is None:
            if pName in list(self.params):
                if pName == 'Initial Temperature (C)':
                    pEntry = input("Initial Temperature (C): ")
                    self.params[pName] = float(pEntry) if not len(pEntry) == 0 else 25
                elif pName == 'Final Temperature (C)':
                    pEntry = input("Final Temperature (C): ")
                    self.params[pName] = float(pEntry) if not len(pEntry) == 0 else 25
                elif pName == 'Temperature Step (C)':
                    pEntry = input("Temperature Step (C): ")
                    self.params[pName] = float(pEntry) if not len(pEntry) == 0 else 5
                elif pName == 'Temperature Ramp (C/min)':
                    pEntry = input("Temperature Ramp (C/min): ")
                    self.params[pName] = float(pEntry) if not len(pEntry) == 0 else 5
                elif pName == 'Stability Delay (s)':
                    pEntry = input("Stability Delay (s): ")
                    self.params[pName] = float(pEntry) if not len(pEntry) == 0 else 0
                elif pName == 'Room Temperature (C)':
                    pEntry = input("Room Temperature (C): ")
                    self.params[pName] = float(pEntry) if not len(pEntry) == 0 else 25
                elif pName == 'Room Ramp (C/min)':
                    pEntry = input("Room Ramp (C/min): ")
                    self.params[pName] = float(pEntry) if not len(pEntry) == 0 else 10
                elif pName == 'Temperature Grid (C)':
                    Tinit = self.params.get('Initial Temperature (C)')
                    Tfin = self.params.get('Final Temperature (C)')
                    tStep = self.params.get('Temperature Step (C)')
                    self.params[pName] = self.build_temp_grid(Tinit, Tfin, tStep)
            else:
                print(f"Unknown Parameter {pName}!!!")
        else:
            if pName in list(self.params):
                if pName=='Temperature Grid (C)':
                    Tinit = valueDict.get('Initial Temperature (C)')
                    Tfin = valueDict.get('Final Temperature (C)')
                    tStep = valueDict.get('Temperature Step (C)')
                    self.params[pName] = self.build_temp_grid(Tinit, Tfin, tStep)
                else:
                    self.params[pName] = valueDict.get(pName)
            else:
                print(f"Unknown Parameter {pName}!!!")
        self._sync_attrs_from_params()
        return 0

    def configure(self, values=None):
        """Set every parameter without the GUI: DEFAULT_PARAMS, overridden by
        values ({parameter name: number}), including the ramp/delay/room
        attributes go_to_temp() and go_to_room_temp() use and the temperature
        grid (self.tempGrid). Needs no connection. Returns the parameters.

        Example: stage.configure({'Initial Temperature (C)': 25, 'Final Temperature (C)': 50})
        """
        unknown = sorted(set(values or {}) - set(DEFAULT_PARAMS))
        if unknown:
            raise KeyError(f"unknown temperature parameter(s): {unknown}")
        merged = {**DEFAULT_PARAMS, **(values or {})}
        self.load_params(merged)
        self.Tinitial = merged['Initial Temperature (C)']
        self.Tfinal = merged['Final Temperature (C)']
        self.tempStep = merged['Temperature Step (C)']
        self.tempGrid = self.build_temp_grid(self.Tinitial, self.Tfinal, self.tempStep)
        self.numTemps = len(self.tempGrid)
        return dict(self.params)

    def load_params(self, valueDict):
        for pName in list(self.params):
            self.set_param_value(pName, valueDict)
        return 0

    def measure_proxy_temp(self, Tf):
        """(|Tf - stage temperature|, tolerance expected_del_t(Tf)), both C.
        Raises RuntimeError if not connected."""
        self._require_connection()
        currT = self.read_temp()
        delTtheo = self.expected_del_t(Tf)
        delTmeas = np.abs(Tf-currT)
        return delTmeas, delTtheo

# if __name__ == '__main__':
#     print("T-controller Lib loaded")
#     # hpc.tControllerPort = 'COM6'
#     # hpc.tControllerOnOff = False
#     # connect_tController()
#     # for i in range(10):
#     #     goToTemp(33.5+i*0.5,5)
#     #     print('Reached to target temperature!')
#     #     time.sleep(60)
#     # disconn_tController()
    