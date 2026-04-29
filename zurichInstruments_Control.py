# -*- coding: utf-8 -*-
"""
Created on Fri Apr 17 16:06:33 2026

@author: pekermilas
"""
# EXAMPLE CALLS
# import zurichInstruments_Control as ziC
# t = ziC.ziDevice()
# t.connectDevice()
# t.setConstants()
# t.close()

# # Below is Zhinst Toolkit convention!!!!
# devs = list(t.device)
# pars = [0] * len(devs)
# for i in range(len(devs)):
#     pars[i] = devs[i][1]['Node'].split('/')[1:]

# pars = pd.DataFrame(pars)
# tabs = list(set(pars.iloc[:,1]))

# a = [list(device.tu)[i][1]['Options'] for i in range(len(list(device.tu))) 
#  if str(list(device.tu)[i][0])=='/dev32271/tu/thresholds/0/input']

# For getting the parameter values one can check the 
# Node values for a parameter as below
# # a = list(device.tu)
# # b = list(device.triggers)

import time
import zhinst.core
import zhinst.toolkit as zt
import zhinst.ziPython as zi
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd


class ziDevice:

    def __init__(self, devSerial = None):
        self.devSerial = devSerial or 'dev32271'
        self.session = None
        self.device = None
        self.rm = None
        self.consts = dict()
        
    def connectDevice(self):
        discovery = zi.ziDiscovery()
        device_id = discovery.find(self.devSerial)
        device_props = discovery.get(device_id)
        
        # Session definition and settings!!! 
        self.session = zt.session.Session(server_host=device_props['serveraddress'], 
                                          server_port=device_props['serverport'], 
                                          allow_version_mismatch=True)

        # Device definition and settings!!! 
        self.device = self.session.connect_device(self.devSerial)
        
        return 0
        
    def getConstants(self):
        self.consts['Oscillation Frequency'] = \
            input("Please enter Oscillation Frequency (Hz): ") or 501000
        self.consts['Max bandwidth'] = \
            input("Please enter Maximum Bandwidth (Hz): ") or 10000
        self.consts['Input Control'] = \
            input("Please enter Input Control (0:Manual, 1:Auto, 2:Current Zone): ") or 0
        self.consts['Current Range'] = \
            input("Please enter Input Current Range (A): ") or 0.010
        self.consts['Voltage Range'] = \
            input("Please enter Input Voltage Range (V): ") or 3
        self.consts['Omega Suppression'] = \
            input("Please enter Omega Suppression (dB): ") or 80
        self.consts['Data Transfer Rate'] = \
            input("Please enter Data Transfer Rate (Sa/s): ") or 60000
        self.consts['Equivalent Circuit Mode'] = \
            input("Please enter Equivalent Circuit Mode (0: 4-Terminal, 1: 2-Terminal): ") or 0

        options = ['59: TU Output Value, 58: Aux Output Overload, 56: Aux Input Overload, 55: Output Overload', 
                   '54: Input(I) Overload, 53: Input(V) Overload, 52: Trigger Out, 51: Trigger In, 50: DIO', 
                   '3: Demod Theta, 2: Demod R, 1: Demod Y, 0: Demod X']
        self.consts['Threshold Input Signal'] = \
            input("Please enter Threshold Input Signal (\n" +"\n".join(options) + "): ") or 59

        self.consts['State Enable Time'] = \
            input("Please enter State Enable Time (s): ") or 0.006
        self.consts['State Disable Time'] = \
            input("Please enter State Disable Time (s): ") or 0.003
        self.consts['Logic Unit Not'] = \
            input("Please enter Logic Unit Not (0: Off, 1: On): ") or 1

        options = ['0: Demod X, 1: Demod Y,2: Demod R, 3: Demod Theta',
                   '11: TU Filtered Value, 12: Manual, 13: TU Output Value']
        self.consts['Aux Output Signal'] = \
            input("Please enter Aux Output Signal (\n" +"\n".join(options) + "): ") or 13
            
        self.consts['Aux Output Scale'] = \
            input("Please enter Aux Output Scale (V): ") or -2
        self.consts['Aux Output Offset'] = \
            input("Please enter Aux Output Offset (V): ") or -2
        self.consts['Aux Output Lower Limit'] = \
            input("Please enter Aux Output Lower Limit (V): ") or -10
        self.consts['Aux Output Upper Limit'] = \
            input("Please enter Aux Output Upper Limit (V): ") or 0

        self.consts['Signal Output Add'] = \
            input("Please enter Signal Output Add (0: False, 1: True): ") or 1

        options = ['0: Off, 1: Osc Phi Demod 2, 36: Threshold 1, 37: Threshold 2',
                   '38: Threshold 3, 39: Threshold 4, 52: MDS Sync Out']
        self.consts['Aux Output Signal'] = \
            input("Please enter Aux Output Signal (\n" +"\n".join(options) + "): ") or 36

        self.consts['Demodulation rate'] = \
            input("Please enter Demodulation Rate: ") or 60000

        return 0
    
    def setConstants(self):
        self.session.daq_server.set('/dev32271/imps/0/freq', 
                                    self.consts['Oscillation Frequency'])
        self.session.daq_server.set('/dev32271/imps/0/maxbandwidth', 
                                    self.consts['Max bandwidth'])
        self.session.daq_server.set('/dev32271/imps/0/auto/inputrange', 
                                    self.consts['Input Control'])
        self.session.daq_server.set('/dev32271/imps/0/current/range', 
                                    self.consts['Current Range'])
        self.session.daq_server.set('/dev32271/imps/0/voltage/range', 
                                    self.consts['Voltage Range'])
        self.session.daq_server.set('/dev32271/imps/0/omegasuppression', 
                                    self.consts['Omega Suppression'])
        self.session.daq_server.set('/dev32271/imps/0/demod/rate', 
                                    self.consts['Data Transfer Rate'])
        self.session.daq_server.set('/dev32271/imps/0/mode', 
                                    self.consts['Equivalent Circuit Mode'])
        
        self.session.daq_server.set('/dev32271/tu/thresholds/0/input', 
                                    self.consts['Threshold Input Signal'])
        self.session.daq_server.set('/dev32271/tu/thresholds/0/activationtime', 
                                    self.consts['State Enable Time'])
        self.session.daq_server.set('/dev32271/tu/thresholds/0/deactivationtime', 
                                    self.consts['State Disable Time'])
        self.session.daq_server.set('/dev32271/tu/logicunits/0/inputs/0/not', 
                                    self.consts['Logic Unit Not'])
        
        self.session.daq_server.set('/dev32271/auxouts/0/outputselect', 
                                    self.consts['Aux Output Signal'])
        self.session.daq_server.set('/dev32271/auxouts/0/scale', 
                                    self.consts['Aux Output Scale'])
        self.session.daq_server.set('/dev32271/auxouts/0/offset', 
                                    self.consts['Aux Output Offset'])
        self.session.daq_server.set('/dev32271/auxouts/0/limitlower', 
                                    self.consts['Aux Output Lower Limit'])
        self.session.daq_server.set('/dev32271/auxouts/0/limitupper', 
                                    self.consts['Aux Output Upper Limit'])
        
        self.session.daq_server.set('/dev32271/sigouts/0/add', 
                                    self.consts['Signal Output Add'])

        self.session.daq_server.set('/dev32271/triggers/out/0/source', 
                                    self.consts['Aux Output Signal'])
                
        self.session.daq_server.set('/dev32271/imps/0/demod/rate', 
                                    self.consts['Demodulation rate'])
        
        return 0
    
    def pullData(self, plot=True, trigger=False):
        data = None
        if trigger:
            daq_module = self.session.modules.daq
            
            daq_module.type(6)
            daq_module.triggernode('/dev32271/demods/0/sample.TrigOut1')
            daq_module.clearhistory(1)
            daq_module.bandwidth(0)
            # daq_module.grid.cols(2**16)
            daq_module.grid.cols(1024)
            daq_module.grid.repetitions(1)
            daq_module.endless(0)
            self.device.imps[0].enable(True)
            daq_module.subscribe('/dev32271/demods/0/sample.AuxIn0.avg')
            daq_module.subscribe('/dev32271/demods/0/sample.R.avg')
            daq_module.subscribe('/dev32271/imps/0/sample.Param0.avg')
            daq_module.subscribe('/dev32271/imps/0/sample.Param1.avg')
            daq_module.forcetrigger()
            time.sleep(1)
            
            daq_module.execute()
            time.sleep(10)
            
            allData = daq_module.read()
            time.sleep(5)
            
            daq_module.unsubscribe('*')
            # print(list(allData))
            # print(allData)
            # data = allData
            
            data = dict()
            data['timestampImps'] = np.array(list(allData['/dev32271/imps/0/sample.param1.avg'][0])[-3])
            data['timestampDemods'] = np.array(list(allData['/dev32271/imps/0/sample.param1.avg'][0])[-3])
            data['ImpedanceRe'] = np.array(list(allData['/dev32271/imps/0/sample.param0.avg'][0])[-4][0], copy=True)
            data['ImpedanceIm'] = np.array(list(allData['/dev32271/imps/0/sample.param1.avg'][0])[-4][0], copy=True)
            data['AuxInput1'] = np.array(list(allData['/dev32271/demods/0/sample.auxin0.avg'][0])[-4][0], copy=True)
            data['AbsZ'] = np.sqrt(data['ImpedanceRe']**2 + data['ImpedanceIm']**2)
        else:
            self.device.demods[0].enable(True)
            time.sleep(2)
            self.device.imps[0].enable(True)
            time.sleep(2)
        
            self.device.demods[0].sample.subscribe()
            dataDemods = self.session.poll()
            self.device.demods[0].sample.unsubscribe()
            time.sleep(2)
            
            self.device.imps[0].sample.subscribe()
            dataImps = self.session.poll()
            self.device.imps[0].sample.unsubscribe()
            time.sleep(2)
            
            #  60 x 10^6 samples/s
            data = dict()
            data['timestampImps'] = np.array(dataImps[self.device.imps[0].sample]['timestamp'], copy=True)
            data['timestampDemods'] = np.array(dataDemods[self.device.demods[0].sample]['timestamp'], copy=True)
            data['ImpedanceRe'] = np.array(dataImps[self.device.imps[0].sample]['param0'], copy=True)
            data['ImpedanceIm'] = np.array(dataImps[self.device.imps[0].sample]['param1'], copy=True) 
            data['AbsZ'] = np.array(np.abs(dataImps[self.device.imps[0].sample]['z']), copy=True)
            data['AuxInput1'] = np.array(dataDemods[self.device.demods[0].sample]['auxin0'], copy=True)
            
        if plot:
            fig, ax = plt.subplots(ncols=2, nrows=2)
            ax[0,0].plot(dataImps[self.device.imps[0].sample]['timestamp'],dataImps[self.device.imps[0].sample]['param0']) # Impedance (Re)
            ax[0,1].plot(dataImps[self.device.imps[0].sample]['timestamp'],dataImps[self.device.imps[0].sample]['param1']) # Impedance (Im)
            ax[1,0].plot(dataImps[self.device.imps[0].sample]['timestamp'],np.abs(dataImps[self.device.imps[0].sample]['z']))      # Abs(Z)
            ax[1,1].plot(dataDemods[self.device.demods[0].sample]['timestamp'],dataDemods[self.device.demods[0].sample]['auxin0']) # Aux Input 1
            # plt.plot(dataDemods[device.demods[0].sample]['timestamp'],dataDemods[device.demods[0].sample]['phase']) # Not sure!
            # plt.plot(dataDemods[device.demods[0].sample]['timestamp'],dataDemods[device.demods[0].sample]['y']) # Not sure!
            plt.show()
        
        return data


# MFIA DLTS Configuration

# Set up
# Connect Aux Input 1 to Aux Output 1 (BNC cable)
# Connect Aux Output 2 to Trigger In (Back side) (BNC cable)
# Connect the DUT using a breadboard or test fixture MFITF.
# Connect data to USB

# LabOne Software settings

# Start LabOne Softwarwe
# On Impedance Analyzer window, under Measurement Control
# 	Change Mode to Advance by toggling 
# 	+Set "Osc Frequency" to the maximum value. For our instrument it is "510.00000000k"
# 	+Go to "Bandwidth Control" and set it to 10KHz.
# 	+Go to Range Control and select "Manual" from drop down menu. 
#   +Set the limits to Current range = 10m and Voltage range = 3V.
# 	+Set Max Bandwidth (Hz) = 10k, 
#   +w (omega) suppression = 80dB.
# 	+Set Rate (Sa/s) = 60k.
# 	+Go to "Equivalent Circuit" and select "4 Terminal"
# 	
# Open TU (Threshold Unit) tab from the menu on the left edge of the screen.
# 	+On signal selecton select "TU Output Value" from the dropdown list.
# 	+Set pulse values as seconds using State Enable and State Disable options (example 6ms/2ms).
# 	+On the right hand side from "Logic Units" tab turn on the option-1 corresponding to "TU Output Value".
# 	
# Open Aux tab from the menu on the left edge of the screen.
# 	+Go to Aux Output tab and select "TU Output Value".
# 	+Set voltage (pulse) depth by inserting a value in "Scale" (example: -2V)
# 	+Set offset by entering a value to Offset. (Note: Total pulse depth is determined by scale. If you add offset, the pulse level will be Scale + Offset values.
# 	+Set lower and upper voltage limits (example:-10V,0V)
# 	
# Open Lock-in tab from the menu on the left edge of the screen.
# 	+On the right hand side, under "Signal Outputs" turn on "Add" option to generate square pulse.
# 	
# Open DIO tab from the menu on the left edge of the screen.
# 	+Go to Trigger Out section, select Threshold 1 under signal option.
# 	
# Open Plotter tab from the menu on the left edge of the screen.
# 	Select the desired channels to view.
# 		For capacitance: Impedance 1 Sample Rep in F.
# 		For square pulse: Select "Auxiliary Input 1" and click on "Add Signal" and click on the box to add to the plotter.
# 		
# Open DAQ tab from the menu on the left edge of the screen.
# 	Go to Control
# 	Select the desired channels to view.
# 		For capacitance: Impedance 1 Sample Rep in F.
# 		For square pulse: Select "Auxiliary Input 1" and click on "Add Signal" and click on the box to add to the plotter.
# 	Go to Settings
# 		Trigger Settings --> Select Demod 1 Trig Out 1, Trigger Type: HW Trigger, Trigger Edge: Positive
# 		Horizontal --> Hold off time(s): 200um, Hold off count: 0, Delay (s): -1m, Refresh rate (Hz): 5
# 	Go to Grid
# 		Grid Settings --> Mode: Exact (on-grid), Operation: Average, Columns: 2048, Repetions: Depends on the desired averaging count (Example: 20)
# 	Data is shown under History. Can be saved in different formats.	

# Note:
# Test Sample: Schottky diode connection -->
# 	Use MFITF test fixture.
# 	Attach the silver band side to the LCUR and the other lead to HCUR.
# 	Expected capacitance value is around 100pF at -2V bias (V_R = 2V)

# Test Sample: BPW 21 Photodiode -->
# 	Use a breadboard for 4-terminal connection.
# 	Attach the lead close to the tab on the package to the HCUR. Attach the other lead to LCUR.MFIA DLTS Configuration

# Set up
# Connect Aux Input 1 to Aux Output 1 (BNC cable)
# Connect Aux Output 2 to Trigger In (Back side) (BNC cable)
# Connect the DUT using a breadboard or test fixture MFITF.
# Connect data to USB

# LabOne Software settings

# Start LabOne Softwarwe
# On Impedance Analyzer window, under Measurement Control
# 	Change Mode to Advance by toggling 
# 	Set "Osc Frequency" to the maximum value. For our instrument it is "510.00000000k"
# 	Go to "Bandwidth Control" and set it to 10KHz.
# 	Go to Range Control and select "Manual" from drop down menu. Set the limits to Current range = 10m and Voltage range = 3V.
# 	Set Max Bandwidth (Hz) = 10k, w (omega) suppression = 80dB.
# 	Set Rate (Sa/s) = 60k.
# 	Go to "Equivalent Circuit" and select "4 Terminal"
# 	
# Open TU (Threshold Unit) tab from the menu on the left edge of the screen.
# 	On signal selecton select "TU Output Value" from the dropdown list.
# 	Set pulse values as seconds using State Enable and State Disable options (example 6ms/2ms).
# 	On the right hand side from "Logic Units" tab turn on the option-1 corresponding to "TU Output Value".
# 	
# Open Aux tab from the menu on the left edge of the screen.
# 	Go to Aux Output tab and select "TU Output Value".
# 	Set voltage (pulse) depth by inserting a value in "Scale" (example: -2V)
# 	Set offset by entering a value to Offset. (Note: Total pulse depth is determined by scale. If you add offset, the pulse level will be Scale + Offset values.
# 	Set lower and upper voltage limits (example:-10V,0V)
# 	
# Open Lock-in tab from the menu on the left edge of the screen.
# 	On the right hand side, under "Signal Outputs" turn on "Add" option to generate square pulse.
# 	
# Open DIO tab from the menu on the left edge of the screen.
# 	Go to Trigger Out section, select Threshold 1 under signal option.
# 	
# Open Plotter tab from the menu on the left edge of the screen.
# 	Select the desired channels to view.
# 		For capacitance: Impedance 1 Sample Rep in F.
# 		For square pulse: Select "Auxiliary Input 1" and click on "Add Signal" and click on the box to add to the plotter.
# 		
# Open DAQ tab from the menu on the left edge of the screen.
# 	Go to Control
# 	Select the desired channels to view.
# 		For capacitance: Impedance 1 Sample Rep in F.
# 		For square pulse: Select "Auxiliary Input 1" and click on "Add Signal" and click on the box to add to the plotter.
# 	Go to Settings
# 		Trigger Settings --> Select Demod 1 Trig Out 1, Trigger Type: HW Trigger, Trigger Edge: Positive
# 		Horizontal --> Hold off time(s): 200um, Hold off count: 0, Delay (s): -1m, Refresh rate (Hz): 5
# 	Go to Grid
# 		Grid Settings --> Mode: Exact (on-grid), Operation: Average, Columns: 2048, Repetions: Depends on the desired averaging count (Example: 20)
# 	Data is shown under History. Can be saved in different formats.	

# Note:
# Test Sample: Schottky diode connection -->
# 	Use MFITF test fixture.
# 	Attach the silver band side to the LCUR and the other lead to HCUR.
# 	Expected capacitance value is around 100pF at -2V bias (V_R = 2V)

# Test Sample: BPW 21 Photodiode -->
# 	Use a breadboard for 4-terminal connection.
# 	Attach the lead close to the tab on the package to the HCUR. Attach the other lead to LCUR.





