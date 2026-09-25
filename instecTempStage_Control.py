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
# import temperatureTools as tT
# t = tT.mK2000B()
# t.connectTempController()
# t.goToTemp(Tf=35)
# t.disconnTController()


import serial
import serial.tools.list_ports
import threading
import time
import numpy as np
import matplotlib.pyplot as plt
import lmfit
from lmfit.models import *

class mK2000B:

    def __init__(self, port = None):
        # self.port = port or "COM3"
        self.port = port or 'COM7'
        self.dev = None
        self.rm = None
        self.state = False
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

    def read(self):
        return self.dev.read()
    
    def write(self, writeStr = None):
        if not self.dev is None:
            self.dev.write(writeStr)
            returnVal = 0
        else:
            returnVal = -1
        return returnVal
    
    def query(self, queryStr = None):
        if not self.dev is None:
            return self.dev.query(queryStr)

    def connect_temp_controller(self):
        if not self.state:
            try:
                self.dev = serial.Serial()
                self.dev.port = self.port
                # self.dev.baudrate = 9600
                # self.dev.timeout = None
                # self.dev.dsrdtr=True
                self.dev.open()
                time.sleep(0.2)
                self.state = True
            except IndexError:
                print('Could not find Temperature Controller!' )
                self.state = False
                self.dev = None
                self.rm = None
            except Exception as e:
                print(f"Error connecting to device: {e}")
                self.state = False
                self.dev = None
                self.rm = None
        else:
            print('Temperature controller is already connected!')
        # maxTimeDelay=2.0
        return 0

    def disconnect_temp_controller(self, stopControl=True, lockTimeout=5.0):
        """Close the serial connection. stopControl=True first sends
        TEMPerature:STOP, which ends temperature control (and cancels any
        ramp in progress); pass False to leave the controller running on its
        own -- e.g. still ramping to room temperature after the GUI exits."""
        if not self.dev is None:
            if self.state:
                locked = self._ioLock.acquire(timeout=lockTimeout)
                try:
                    ser = self.dev
                    if stopControl:
                        ser.write(str.encode(":TEMPerature:STOP\n"))
                        time.sleep(0.5)
                    ser.close()
                    self.state = False
                finally:
                    if locked:
                        self._ioLock.release()
            else:
                print("Already disconnected!")
        else:
            print("Nothing to do!")

        return 0

    def abort(self):
        """Stop go_to_temp()/go_to_room_temp() from commanding or waiting any
        further (see self._aborted). Used when the GUI is closing."""
        self._aborted = True

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

    def read_temp(self):
        """Current stage temperature (C), as one locked query/response pair."""
        with self._ioLock:
            self.dev.write(str.encode(":TEMPerature:CTEMperature?\n"))
            return float(self.dev.readline().strip().decode())

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

    def go_to_temp(self, Tf=25, ramp=5, delayTime = 0):
        """Ramp to Tf and wait for it to stabilize. Returns 0, or -1 if
        aborted (abort() -- the GUI is closing) before or during the wait."""
        if self._aborted:
            return -1
        if not self.dev is None:
            ramp = self.tRamp
            delayTime = self.tStableDelay
            if self.state:
                self.start_ramp(Tf, ramp)
                time.sleep(0.5)

                # Wait for T stabilization
                print('Wait for T = {} stabilization!'.format(Tf))
                delTmeas, delTtheo = self.measure_proxy_temp(Tf)
                while(delTmeas>delTtheo):
                    if self._aborted:
                        return -1
                    delTmeas, delTtheo = self.measure_proxy_temp(Tf)
                    if delTmeas<delTtheo:
                        time.sleep(10)
                        delTmeas, delTtheo = self.measure_proxy_temp(Tf)
                    else:
                        time.sleep(5)
            else:
                print("T-Controller is disconnected!")
        else:
            print("Nothing to do!")

        time.sleep(delayTime)

        return -1 if self._aborted else 0

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
            time.sleep(5)
            currT = self.read_temp()

        time.sleep(10)
        return 0

    def set_temp_grid(self, userInput = False):
        if not self.dev is None:
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
        else:
           print("Nothing to do!")

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

    def load_params(self, valueDict):
        for pName in list(self.params):
            self.set_param_value(pName, valueDict)
        return 0

    def measure_proxy_temp(self, Tf):
        if not self.dev is None:
            currT = self.read_temp()
            delTtheo = self.expected_del_t(Tf)
            delTmeas = np.abs(Tf-currT)
        else:
            print("Nothing to do!")
    
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
    