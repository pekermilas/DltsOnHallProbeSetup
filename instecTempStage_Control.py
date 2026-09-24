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
        pList = ['Initial Temperature (C)', 'Final Temperature (C)',
                 'Temperature Step (C)', 'Temperature Ramp (C/min)',
                 'Stability Delay (s)', 'Temperature Grid (C)']
        self.params = dict.fromkeys(pList, None)

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

    def disconnect_temp_controller(self):
        if not self.dev is None:
            if self.state:
                ser = self.dev
                ser.write(str.encode(":TEMPerature:STOP\n"))
                time.sleep(0.5)
                ser.close()
                self.state = False
            else:
                print("Already disconnected!")
        else:
            print("Nothing to do!")
        
        return 0

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
        if not self.dev is None:
            ramp = self.tRamp
            delayTime = self.tStableDelay
            if self.state:
                device = self.dev
                device.write(str.encode('TEMPerature:RAMP '+str(Tf)+','+str(ramp)+'\n'))
                time.sleep(0.5)
        
                # Wait for T stabilization
                print('Wait for T = {} stabilization!'.format(Tf))
                delTmeas, delTtheo = self.measure_proxy_temp(Tf)
                while(delTmeas>delTtheo):
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
        
        return 0

    def go_to_room_temp(self, Tr=25, ramp=5):
        if not self.dev is None:
            if self.state:
                device = self.dev
                device.write(str.encode('TEMPerature:RAMP '+str(Tr)+','+str(ramp)+'\n'))
                time.sleep(0.5)
                
                device.write(str.encode(":TEMPerature:CTEMperature?\n"))
                currT = float(device.readline().strip().decode())
                delTtheo = 0.5
                delTmeas = np.abs(Tr-currT)
            
                while(delTmeas>delTtheo):
                    time.sleep(5)
                    device.write(str.encode(":TEMPerature:CTEMperature?\n"))
                    currT = float(device.readline().strip().decode())
                    delTmeas = np.abs(Tr-currT)
                    
                    delTmeas, delTtheo = self.measure_proxy_temp(Tr)
                    if delTmeas<delTtheo:
                        time.sleep(10)
                        delTmeas, delTtheo = self.measure_proxy_temp(Tr)
                    else:
                        time.sleep(5)
            else:
                print("''T-Controller is disconnected!''")
        else:
            print("Nothing to do!")
        
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
        return 0

    def load_params(self, valueDict):
        for pName in list(self.params):
            self.set_param_value(pName, valueDict)
        return 0

    def measure_proxy_temp(self, Tf):
        if not self.dev is None:
            device = self.dev
            device.write(str.encode(":TEMPerature:CTEMperature?\n"))
            currT = float(device.readline().strip().decode())
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
    