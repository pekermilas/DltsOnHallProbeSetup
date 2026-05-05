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
        self.params = dict()
        
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
        
    def assignParam(self, pName='Oscillation Frequency'):
        pList = ['Oscillation Frequency', 'Max bandwidth', 'Input Control', 'Current Range',
                 'Voltage Range', 'Omega Suppression', 'Data Transfer Rate', 'Equivalent Circuit Mode',
                 'Threshold Input Signal', 'State Enable Time', 'State Disable Time', 'Logic Unit Not',
                 'Aux Output Signal', 'Aux Output Scale', 'Aux Output Offset', 'Aux Output Lower Limit',
                 'Aux Output Upper Limit', 'Signal Output Add']
        if pName in pList:
            if pName == 'Oscillation Frequency':
                self.params[pName] = input("Please enter Oscillation Frequency (Hz): ") or 501000
            if pName == 'Max bandwidth':
                self.params[pName] = input("Please enter Maximum Bandwidth (Hz): ") or 10000
            if pName == 'Input Control':
                self.params[pName] = input("Please enter Input Control (0:Manual, 1:Auto, 2:Current Zone): ") or 0
            if pName == 'Current Range':
                self.params[pName] = input("Please enter Input Current Range (A): ") or 0.010
            if pName == 'Voltage Range':
                self.params[pName] = input("Please enter Input Voltage Range (V): ") or 3
            if pName == 'Omega Suppression':
                self.params[pName] = input("Please enter Omega Suppression (dB): ") or 80
            if pName == 'Data Transfer Rate':
                self.params[pName] = input("Please enter Data Transfer Rate (Sa/s): ") or 60000
            if pName == 'Equivalent Circuit Mode':
                self.params[pName] = input("Please enter Equivalent Circuit Mode (0: 4-Terminal, 1: 2-Terminal): ") or 0
            if pName == 'Threshold Input Signal':
                options = ['59: TU Output Value, 58: Aux Output Overload, 56: Aux Input Overload, 55: Output Overload', 
                           '54: Input(I) Overload, 53: Input(V) Overload, 52: Trigger Out, 51: Trigger In, 50: DIO', 
                           '3: Demod Theta, 2: Demod R, 1: Demod Y, 0: Demod X']
                self.params[pName] = input("Please enter Threshold Input Signal (\n" +"\n".join(options) + "): ") or 59
            if pName == 'State Enable Time':
                self.params[pName] = input("Please enter State Enable Time (s): ") or 0.006
            if pName == 'State Disable Time':
                self.params[pName] = input("Please enter State Disable Time (s): ") or 0.003
            if pName == 'Logic Unit Not':
                self.params[pName] = input("Please enter Logic Unit Not (0: Off, 1: On): ") or 1
            if pName == 'Aux Output Signal':
                options = ['0: Demod X, 1: Demod Y,2: Demod R, 3: Demod Theta',
                           '11: TU Filtered Value, 12: Manual, 13: TU Output Value']
                self.params[pName] = input("Please enter Aux Output Signal (\n" +"\n".join(options) + "): ") or 13
            if pName == 'Aux Output Scale':
                self.params[pName] = input("Please enter Aux Output Scale (V): ") or -1
            if pName == 'Aux Output Offset':
                self.params[pName] = input("Please enter Aux Output Offset (V): ") or -0.5
            if pName == 'Aux Output Lower Limit':
                self.params[pName] = input("Please enter Aux Output Lower Limit (V): ") or -10
            if pName == 'Aux Output Upper Limit':
                self.params[pName] = input("Please enter Aux Output Upper Limit (V): ") or 0
            if pName == 'Signal Output Add':
                self.params[pName] = input("Please enter Signal Output Add (0: False, 1: True): ") or 1
            if pName == 'Trigger Source Signal':
                options = ['0: Off, 1: Osc Phi Demod 2, 36: Threshold 1, 37: Threshold 2',
                           '38: Threshold 3, 39: Threshold 4, 52: MDS Sync Out']
                self.params[pName] = input("Please enter Trigger Source Signal (\n" +"\n".join(options) + "): ") or 36

        return 0
    
    # def setParams(self):
    #     if len(self.params)>0:
    #         self.session.daq_server.set('/dev32271/imps/0/freq', 
    #                                     self.params['Oscillation Frequency'])
    #         self.session.daq_server.set('/dev32271/imps/0/maxbandwidth', 
    #                                     self.params['Max bandwidth'])
    #         self.session.daq_server.set('/dev32271/imps/0/auto/inputrange', 
    #                                     self.params['Input Control'])
    #         self.session.daq_server.set('/dev32271/imps/0/current/range', 
    #                                     self.params['Current Range'])
    #         self.session.daq_server.set('/dev32271/imps/0/voltage/range', 
    #                                     self.params['Voltage Range'])
    #         self.session.daq_server.set('/dev32271/imps/0/omegasuppression', 
    #                                     self.params['Omega Suppression'])
    #         self.session.daq_server.set('/dev32271/imps/0/demod/rate', 
    #                                     self.params['Data Transfer Rate'])
    #         self.session.daq_server.set('/dev32271/imps/0/mode', 
    #                                     self.params['Equivalent Circuit Mode'])
    #         self.session.daq_server.set('/dev32271/tu/thresholds/0/input', 
    #                                     self.params['Threshold Input Signal'])
    #         self.session.daq_server.set('/dev32271/tu/thresholds/0/activationtime', 
    #                                     self.params['State Enable Time'])
    #         self.session.daq_server.set('/dev32271/tu/thresholds/0/deactivationtime', 
    #                                     self.params['State Disable Time'])
    #         self.session.daq_server.set('/dev32271/tu/logicunits/0/inputs/0/not', 
    #                                     self.params['Logic Unit Not'])
    #         self.session.daq_server.set('/dev32271/auxouts/0/outputselect', 
    #                                     self.params['Aux Output Signal'])
    #         self.session.daq_server.set('/dev32271/auxouts/0/scale', 
    #                                     self.params['Aux Output Scale'])
    #         self.session.daq_server.set('/dev32271/auxouts/0/offset', 
    #                                     self.params['Aux Output Offset'])
    #         self.session.daq_server.set('/dev32271/auxouts/0/limitlower', 
    #                                     self.params['Aux Output Lower Limit'])
    #         self.session.daq_server.set('/dev32271/auxouts/0/limitupper', 
    #                                     self.params['Aux Output Upper Limit'])
    #         self.session.daq_server.set('/dev32271/sigouts/0/add', 
    #                                     self.params['Signal Output Add'])
    #         self.session.daq_server.set('/dev32271/triggers/out/0/source', 
    #                                     self.params['Trigger Source Signal'])
    #     else:
    #         print("Run getConstants first!")
            
    #     return 0

    # def checkParams(self):
    #     givenParams = self.params.copy()
    #     inuseParams = dict.fromkeys(givenParams.keys(), 0)
    #     if len(self.params)>0:
    #         inuseParams[list(givenParams.keys())[0]] = \
    #             self.session.daq_server.get('*')['dev32271']['imps']['0']['freq']['value'][0]
    #         inuseParams[list(givenParams.keys())[1]] = \
    #             self.session.daq_server.get('*')['dev32271']['imps']['0']['maxbandwidth']['value'][0]
    #         inuseParams[list(givenParams.keys())[2]] = \
    #             self.session.daq_server.get('*')['dev32271']['imps']['0']['auto']['inputrange']['value'][0]
    #         inuseParams[list(givenParams.keys())[3]] = \
    #             self.session.daq_server.get('*')['dev32271']['imps']['0']['current']['range']['value'][0]
    #         inuseParams[list(givenParams.keys())[4]] = \
    #             self.session.daq_server.get('*')['dev32271']['imps']['0']['voltage']['range']['value'][0]
    #         inuseParams[list(givenParams.keys())[5]] = \
    #             self.session.daq_server.get('*')['dev32271']['imps']['0']['omegasuppression']['value'][0]
    #         inuseParams[list(givenParams.keys())[6]] = \
    #             self.session.daq_server.get('*')['dev32271']['imps']['0']['demod']['rate']['value'][0]
    #         inuseParams[list(givenParams.keys())[7]] = \
    #             self.session.daq_server.get('*')['dev32271']['imps']['0']['mode']['value'][0]
    #         inuseParams[list(givenParams.keys())[8]] = \
    #             self.session.daq_server.get('*')['dev32271']['tu']['thresholds']['0']['input']['value'][0]
    #         inuseParams[list(givenParams.keys())[9]] = \
    #             self.session.daq_server.get('*')['dev32271']['tu']['thresholds']['0']['activationtime']['value'][0]
    #         inuseParams[list(givenParams.keys())[10]] = \
    #             self.session.daq_server.get('*')['dev32271']['tu']['thresholds']['0']['deactivationtime']['value'][0]
    #         inuseParams[list(givenParams.keys())[11]] = \
    #             self.session.daq_server.get('*')['dev32271']['tu']['logicunits']['0']['inputs']['0']['not']['value'][0]
    #         inuseParams[list(givenParams.keys())[12]] = \
    #             self.session.daq_server.get('*')['dev32271']['auxouts']['0']['outputselect']['value'][0]
    #         inuseParams[list(givenParams.keys())[13]] = \
    #             self.session.daq_server.get('*')['dev32271']['auxouts']['0']['scale']['value'][0]
    #         inuseParams[list(givenParams.keys())[14]] = \
    #             self.session.daq_server.get('*')['dev32271']['auxouts']['0']['offset']['value'][0]
    #         inuseParams[list(givenParams.keys())[15]] = \
    #             self.session.daq_server.get('*')['dev32271']['auxouts']['0']['limitlower']['value'][0]
    #         inuseParams[list(givenParams.keys())[16]] = \
    #             self.session.daq_server.get('*')['dev32271']['auxouts']['0']['limitupper']['value'][0]
    #         inuseParams[list(givenParams.keys())[17]] = \
    #             self.session.daq_server.get('*')['dev32271']['sigouts']['0']['add']['value'][0]
    #         inuseParams[list(givenParams.keys())[18]] = \
    #             self.session.daq_server.get('*')['dev32271']['triggers']['out']['0']['source']['value'][0]
    #     else:
    #         print("Assign paramters first!")
        
    #     match = np.array([True] * len(list(givenParams.keys())))
    #     for i in range(len(list(givenParams.keys()))):
    #         k = list(givenParams.keys())[i]
    #         if not np.isclose(inuseParams[k], givenParams[k], rtol=1e-03):
    #             match[i] = False
        
    #     return match, givenParams, inuseParams

    # # def reloadParams(self):
    # #     if len(self.consts)>0:
    # #         if not self.session.daq_server.get('/dev32271/imps/0/freq') == self.consts['Oscillation Frequency']:
    # #             self.session.daq_server.set('/dev32271/imps/0/freq', 
    # #                                         self.consts['Oscillation Frequency'])
    # #         if not self.session.daq_server.get('/dev32271/imps/0/maxbandwidth') == self.consts['Max bandwidth']:
    # #             self.session.daq_server.set('/dev32271/imps/0/maxbandwidth', 
    # #                                         self.consts['Max bandwidth'])
    # #         if not self.session.daq_server.get('/dev32271/imps/0/auto/inputrange') == self.consts['Input Control']:
    # #             self.session.daq_server.set('/dev32271/imps/0/auto/inputrange', 
    # #                                         self.consts['Input Control'])
    # #         if not self.session.daq_server.get('/dev32271/imps/0/current/range') == self.consts['Current Range']:
    # #             self.session.daq_server.set('/dev32271/imps/0/current/range', 
    # #                                         self.consts['Current Range'])
    # #         if not self.session.daq_server.get('/dev32271/imps/0/voltage/range') == self.consts['Voltage Range']:
    # #             self.session.daq_server.set('/dev32271/imps/0/voltage/range', 
    # #                                         self.consts['Voltage Range'])
    # #         if not self.session.daq_server.get('/dev32271/imps/0/omegasuppression') == self.consts['Omega Suppression']:
    # #             self.session.daq_server.set('/dev32271/imps/0/omegasuppression', 
    # #                                         self.consts['Omega Suppression'])
    # #         if not self.session.daq_server.get('/dev32271/imps/0/demod/rate') == self.consts['Data Transfer Rate']:
    # #             self.session.daq_server.set('/dev32271/imps/0/demod/rate', 
    # #                                         self.consts['Data Transfer Rate'])
    # #         if not self.session.daq_server.get('/dev32271/imps/0/mode') == self.consts['Equivalent Circuit Mode']:
    # #             self.session.daq_server.set('/dev32271/imps/0/mode', 
    # #                                         self.consts['Equivalent Circuit Mode'])
    # #         if not self.session.daq_server.get('/dev32271/tu/thresholds/0/input') == self.consts['Threshold Input Signal']:
    # #             self.session.daq_server.set('/dev32271/tu/thresholds/0/input', 
    # #                                         self.consts['Threshold Input Signal'])
    # #         if not self.session.daq_server.get('/dev32271/tu/thresholds/0/activationtime') == self.consts['State Enable Time']:
    # #             self.session.daq_server.set('/dev32271/tu/thresholds/0/activationtime', 
    # #                                         self.consts['State Enable Time'])
    # #         if not self.session.daq_server.get('/dev32271/tu/thresholds/0/deactivationtime') == self.consts['State Disable Time']:
    # #             self.session.daq_server.set('/dev32271/tu/thresholds/0/deactivationtime', 
    # #                                         self.consts['State Disable Time'])
    # #         if not self.session.daq_server.get('/dev32271/tu/logicunits/0/inputs/0/not') == self.consts['Logic Unit Not']:
    # #             self.session.daq_server.set('/dev32271/tu/logicunits/0/inputs/0/not', 
    # #                                         self.consts['Logic Unit Not'])
    # #         if not self.session.daq_server.get('/dev32271/auxouts/0/outputselect') == self.consts['Aux Output Signal']:
    # #             self.session.daq_server.set('/dev32271/auxouts/0/outputselect', 
    # #                                         self.consts['Aux Output Signal'])
    # #         if not self.session.daq_server.get('/dev32271/auxouts/0/scale') == self.consts['Aux Output Scale']:
    # #             self.session.daq_server.set('/dev32271/auxouts/0/scale', 
    # #                                         self.consts['Aux Output Scale'])
    # #         if not self.session.daq_server.get('/dev32271/auxouts/0/offset') == self.consts['Aux Output Offset']:
    # #             self.session.daq_server.set('/dev32271/auxouts/0/offset', 
    # #                                         self.consts['Aux Output Offset'])
    # #         if not self.session.daq_server.get('/dev32271/auxouts/0/limitlower') == self.consts['Aux Output Lower Limit']:
    # #             self.session.daq_server.set('/dev32271/auxouts/0/limitlower', 
    # #                                         self.consts['Aux Output Lower Limit'])
    # #         if not self.session.daq_server.get('/dev32271/auxouts/0/limitupper') == self.consts['Aux Output Upper Limit']:
    # #             self.session.daq_server.set('/dev32271/auxouts/0/limitupper', 
    # #                                         self.consts['Aux Output Upper Limit'])
    # #         if not self.session.daq_server.get('/dev32271/sigouts/0/add') == self.consts['Signal Output Add']:
    # #             self.session.daq_server.set('/dev32271/sigouts/0/add', 
    # #                                         self.consts['Signal Output Add'])
    # #         if not self.session.daq_server.get('/dev32271/triggers/out/0/source') == self.consts['Trigger Source Signal']:
    # #             self.session.daq_server.set('/dev32271/triggers/out/0/source', 
    # #                                         self.consts['Trigger Source Signal'])
    # #         if not self.session.daq_server.get('/dev32271/imps/0/demod/rate') == self.consts['Demodulation rate']:
    # #             self.session.daq_server.set('/dev32271/imps/0/demod/rate', 
    # #                                         self.consts['Demodulation rate'])
    # #     else:
    # #         print("Assign constants first!")
            
    # #     return 0
    
    def pullData(self, plot=True, trigger=False, numPoints=1024):
        data = None
        if trigger:
            daq_module = self.session.modules.daq
            
            daq_module.type(6)
            daq_module.triggernode('/dev32271/demods/0/sample.TrigOut1')
            daq_module.clearhistory(1)
            daq_module.bandwidth(0)
            daq_module.grid.cols(numPoints)
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
            
            data = dict()
            # FIX ticks here. Triggered data doesn't report ticks. It reports actual times in seconds!!!
            data['tickStampImps'] = np.array(list(allData['/dev32271/imps/0/sample.param1.avg'][0])[-3])
            data['tickStampDemods'] = np.array(list(allData['/dev32271/imps/0/sample.param1.avg'][0])[-3])
            data['timeStampImps'] = (data['tickStampImps']/(60*10**6)) - (data['tickStampImps']/(60*10**6))[0]
            data['timeStampDemods'] = (data['tickStampDemods']/(60*10**6)) - (data['tickStampDemods']/(60*10**6))[0]
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
            data['tickStampImps'] = np.array(dataImps[self.device.imps[0].sample]['timestamp'], copy=True)
            data['tickStampDemods'] = np.array(dataDemods[self.device.demods[0].sample]['timestamp'], copy=True)
            data['timeStampImps'] = (data['tickStampImps']/(60*10**6)) - (data['tickStampImps']/(60*10**6))[0]
            data['timeStampDemods'] = (data['tickStampDemods']/(60*10**6)) - (data['tickStampDemods']/(60*10**6))[0]
            data['ImpedanceRe'] = np.array(dataImps[self.device.imps[0].sample]['param0'], copy=True)
            data['ImpedanceIm'] = np.array(dataImps[self.device.imps[0].sample]['param1'], copy=True) 
            data['AbsZ'] = np.array(np.abs(dataImps[self.device.imps[0].sample]['z']), copy=True)
            data['AuxInput1'] = np.array(dataDemods[self.device.demods[0].sample]['auxin0'], copy=True)
            
        if plot:
            fig, ax = plt.subplots(ncols=2, nrows=2)
            ax[0,0].plot(data['timeStampDemods'],data['AuxInput1']) # Input
            ax[0,1].plot(data['timeStampImps'],data['ImpedanceRe']) # Impedance (Re)
            ax[1,0].plot(data['timeStampImps'],data['ImpedanceIm']) # Impedance (Im)
            ax[1,1].plot(data['timeStampImps'],data['AbsZ']) # Impedance (Im)
            
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





