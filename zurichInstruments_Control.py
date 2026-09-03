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
import json
import os
from pathlib import Path
import h5py

class ziDevice:

    def __init__(self, devSerial = None):
        self.devSerial = devSerial or 'dev32271'
        self.session = None
        self.device = None
        self.rm = None
        pList = ['Oscillation Amplitude', 'Oscillation Frequency', 'Oscillation ON/OFF', 'Max bandwidth', 
                 'Input Control', 'Current Range', 'Voltage Range', 'Omega Suppression', 'Filter Harmonic', 
                 'Filter Bandwidth', 'Data Transfer Rate', 'Equivalent Circuit Mode', 'Threshold Input Signal', 
                 'State Enable Time', 'State Disable Time', 'Logic Unit Not', 'Aux Output Signal', 
                 'Aux Output Scale', 'Aux Output Offset', 'Aux Output Lower Limit',
                 'Aux Output Upper Limit', 'Signal Output Add', 'Trigger Source Signal']
        self.params = dict.fromkeys(pList, 0)
        
    def connect_device(self):
        discovery = zi.ziDiscovery()
        device_id = discovery.find(self.devSerial)
        device_props = discovery.get(device_id)
        
        # Session definition and settings!!! 
        try:
            self.session = zt.session.Session(server_host=device_props['serveraddress'],
                                              server_port=device_props['serverport'],
                                              allow_version_mismatch=True)

            # Device definition and settings!!!
            self.device = self.session.connect_device(self.devSerial)
        except Exception as e:
            print(f"Error connecting to device: {e}")
            self.session = None
            self.device = None
        return 0

    def set_param_value(self, pName='Oscillation Frequency', valueDict=None):
        if valueDict is None:
            if pName in list(self.params):
                if pName == 'Oscillation Amplitude':
                    pEntry = input("Please enter Oscillation Amplitude (V): ")
                    self.params[pName] = float(pEntry) if not len(pEntry)==0 else 0.300
                if pName == 'Oscillation Frequency':
                    pEntry = input("Please enter Oscillation Frequency (Hz): ")
                    self.params[pName] = float(pEntry) if not len(pEntry)==0 else 501000
                if pName == 'Oscillation ON/OFF':
                    pEntry = input("Please enter Oscillation ON/OFF (0:OFF, 1:ON): ")
                    self.params[pName] = int(pEntry) if not len(pEntry)==0 else 1
                if pName == 'Max bandwidth':
                    pEntry = input("Please enter Maximum Bandwidth (Hz): ")
                    self.params[pName] = float(pEntry) if not len(pEntry)==0 else 10000
                if pName == 'Input Control':
                    pEntry = input("Please enter Input Control (0:Manual, 1:Auto, 2:Current Zone): ")
                    self.params[pName] = int(pEntry) if not len(pEntry)==0 else 0
                if pName == 'Current Range':
                    pEntry = input("Please enter Input Current Range (A): ")
                    self.params[pName] = float(pEntry) if not len(pEntry)==0 else 0.010
                if pName == 'Voltage Range':
                    pEntry = input("Please enter Input Voltage Range (V): ")
                    self.params[pName] = float(pEntry) if not len(pEntry)==0 else 3
                if pName == 'Omega Suppression':
                    pEntry = input("Please enter Omega Suppression (dB): ")
                    self.params[pName] = float(pEntry) if not len(pEntry)==0 else 80
                if pName == 'Filter Harmonic':
                    pEntry = input("Please enter Filter Harmonic: ")
                    self.params[pName] = int(pEntry) if not len(pEntry)==0 else 1
                if pName == 'Filter Bandwidth':
                    pEntry = input("Please enter Filter Order Bandwidth: ")
                    self.params[pName] = int(pEntry) if not len(pEntry)==0 else 2
                if pName == 'Data Transfer Rate':
                    pEntry = input("Please enter Data Transfer Rate (Sa/s): ")
                    self.params[pName] = float(pEntry) if not len(pEntry)==0 else 60000
                if pName == 'Equivalent Circuit Mode':
                    pEntry = input("Please enter Equivalent Circuit Mode (0: 4-Terminal, 1: 2-Terminal): ")
                    self.params[pName] = int(pEntry) if not len(pEntry)==0 else 0
                if pName == 'Threshold Input Signal':
                    options = ['59: TU Output Value, 58: Aux Output Overload, 56: Aux Input Overload',
                               '55: Output Overload, 54: Input(I) Overload, 53: Input(V) Overload',
                               '52: Trigger Out, 51: Trigger In, 50: DIO, 3: Demod Theta, 2: Demod R',
                               '1: Demod Y, 0: Demod X']
                    pEntry = input("Please enter Threshold Input Signal (\n" +"\n".join(options) + "): ")
                    self.params[pName] = int(pEntry) if not len(pEntry)==0 else 59
                if pName == 'State Enable Time':
                    pEntry = input("Please enter State Enable Time (s): ")
                    self.params[pName] = float(pEntry) if not len(pEntry)==0 else 0.006
                if pName == 'State Disable Time':
                    pEntry = input("Please enter State Disable Time (s): ")
                    self.params[pName] = float(pEntry) if not len(pEntry)==0 else 0.003
                if pName == 'Logic Unit Not':
                    pEntry = input("Please enter Logic Unit Not (0: Off, 1: On): ")
                    self.params[pName] = int(pEntry) if not len(pEntry)==0 else 1
                if pName == 'Aux Output Signal':
                    options = ['0: Demod X, 1: Demod Y,2: Demod R, 3: Demod Theta',
                               '11: TU Filtered Value, 12: Manual, 13: TU Output Value']
                    pEntry = input("Please enter Aux Output Signal (\n" +"\n".join(options) + "): ")
                    self.params[pName] = int(pEntry) if not len(pEntry)==0 else 13
                if pName == 'Aux Output Scale':
                    pEntry = input("Please enter Aux Output Scale (V): ")
                    self.params[pName] = float(pEntry) if not len(pEntry)==0 else -1
                if pName == 'Aux Output Offset':
                    pEntry = input("Please enter Aux Output Offset (V): ")
                    self.params[pName] = float(pEntry) if not len(pEntry)==0 else -0.5
                if pName == 'Aux Output Lower Limit':
                    pEntry = input("Please enter Aux Output Lower Limit (V): ")
                    self.params[pName] = float(pEntry) if not len(pEntry)==0 else -10
                if pName == 'Aux Output Upper Limit':
                    pEntry = input("Please enter Aux Output Upper Limit (V): ")
                    self.params[pName] = float(pEntry) if not len(pEntry)==0 else 0
                if pName == 'Signal Output Add':
                    pEntry = input("Please enter Signal Output Add (0: False, 1: True): ")
                    self.params[pName] = int(pEntry) if not len(pEntry)==0 else 1
                if pName == 'Trigger Source Signal':
                    options = ['0: Off, 1: Osc Phi Demod 2, 36: Threshold 1, 37: Threshold 2',
                               '38: Threshold 3, 39: Threshold 4, 52: MDS Sync Out']
                    pEntry = input("Please enter Trigger Source Signal (\n" +"\n".join(options) + "): ")
                    self.params[pName] = int(pEntry) if not len(pEntry)==0 else 36
            else:
                print(f"Unknown Parameter {pName}!!!")
        else:
            if pName in list(self.params):
                # self.params[pName] = valueDict.get(pName)
                self.params[pName] = valueDict[pName].get()
            else:
                print(f"Parameter {pName} not found!")
        return 0
    
    def push_param_to_device(self, pName='Oscillation Frequency'):
        if pName in list(self.params):
            if pName == 'Oscillation Amplitude':
                self.session.daq_server.set('/dev32271/imps/0/output/amplitude', self.params[pName])
            if pName == 'Oscillation Frequency':
                self.session.daq_server.set('/dev32271/imps/0/freq', self.params[pName])
            if pName == 'Oscillation ON/OFF':
                self.session.daq_server.set('/dev32271/imps/0/auto/output', self.params[pName])
            if pName == 'Max bandwidth':
                self.session.daq_server.set('/dev32271/imps/0/maxbandwidth', self.params[pName])
            if pName == 'Input Control':
                self.session.daq_server.set('/dev32271/imps/0/auto/inputrange', self.params[pName])
            if pName == 'Current Range':
                self.session.daq_server.set('/dev32271/imps/0/current/range', self.params[pName])
            if pName == 'Voltage Range':
                self.session.daq_server.set('/dev32271/imps/0/voltage/range', self.params[pName])
            if pName == 'Omega Suppression':
                self.session.daq_server.set('/dev32271/imps/0/omegasuppression', self.params[pName])
            if pName == 'Filter Harmonic':
                self.session.daq_server.set('/dev32271/imps/0/demod/harmonic', self.params[pName])
            if pName == 'Filter Bandwidth':
                self.session.daq_server.set('/dev32271/imps/0/demod/order', self.params[pName])
            if pName == 'Data Transfer Rate':
                self.session.daq_server.set('/dev32271/imps/0/demod/rate', self.params[pName])
            if pName == 'Equivalent Circuit Mode':
                self.session.daq_server.set('/dev32271/imps/0/mode', self.params[pName])
            if pName == 'Threshold Input Signal':
                self.session.daq_server.set('/dev32271/tu/thresholds/0/input', self.params[pName])
            if pName == 'State Enable Time':
                self.session.daq_server.set('/dev32271/tu/thresholds/0/activationtime', self.params[pName])
            if pName == 'State Disable Time':
                self.session.daq_server.set('/dev32271/tu/thresholds/0/deactivationtime', self.params[pName])
            if pName == 'Logic Unit Not':
                self.session.daq_server.set('/dev32271/tu/logicunits/0/inputs/0/not', self.params[pName])
            if pName == 'Aux Output Signal':
                self.session.daq_server.set('/dev32271/auxouts/0/outputselect', self.params[pName])
            if pName == 'Aux Output Scale':
                self.session.daq_server.set('/dev32271/auxouts/0/scale', self.params[pName])
            if pName == 'Aux Output Offset':
                self.session.daq_server.set('/dev32271/auxouts/0/offset', self.params[pName])
            if pName == 'Aux Output Lower Limit':
                self.session.daq_server.set('/dev32271/auxouts/0/limitlower', self.params[pName])
            if pName == 'Aux Output Upper Limit':
                self.session.daq_server.set('/dev32271/auxouts/0/limitupper', self.params[pName])
            if pName == 'Signal Output Add':
                self.session.daq_server.set('/dev32271/sigouts/0/add', self.params[pName])
            if pName == 'Trigger Source Signal':
                self.session.daq_server.set('/dev32271/triggers/out/0/source', self.params[pName])
        else:
            print("Unknown Parameter!!!")
        return 0

    def check_param(self, pName='Oscillation Frequency'):
        if pName in list(self.params):
            if pName =='Oscillation Amplitude':
                returnVal = np.isclose(self.params[pName], 
                                       self.session.daq_server.get('*')['dev32271']['imps']['0']['output']['amplitude']['value'][0],
                                       rtol=1e-03)
            if pName =='Oscillation Frequency':
                returnVal = np.isclose(self.params[pName],
                                       self.session.daq_server.get('*')['dev32271']['imps']['0']['freq']['value'][0],
                                       rtol=1e-03)
            if pName =='Oscillation ON/OFF':
                returnVal = np.isclose(self.params[pName],
                                       self.session.daq_server.get('*')['dev32271']['imps']['0']['auto']['output']['value'][0],
                                       rtol=1e-03)
            if pName == 'Max bandwidth':
                returnVal = np.isclose(self.params[pName], 
                                       self.session.daq_server.get('*')['dev32271']['imps']['0']['maxbandwidth']['value'][0], 
                                       rtol=1e-03)
            if pName == 'Input Control':
                returnVal = np.isclose(self.params[pName], 
                                       self.session.daq_server.get('*')['dev32271']['imps']['0']['auto']['inputrange']['value'][0], 
                                       rtol=1e-03)
            if pName == 'Current Range':
                returnVal = np.isclose(self.params[pName], 
                                       self.session.daq_server.get('*')['dev32271']['imps']['0']['current']['range']['value'][0], 
                                       rtol=1e-03)
            if pName == 'Voltage Range':
                returnVal = np.isclose(self.params[pName], 
                                       self.session.daq_server.get('*')['dev32271']['imps']['0']['voltage']['range']['value'][0],
                                       rtol=1e-03)
            if pName == 'Omega Suppression':
                returnVal = np.isclose(self.params[pName], 
                                       self.session.daq_server.get('*')['dev32271']['imps']['0']['omegasuppression']['value'][0], 
                                       rtol=1e-03)
            if pName == 'Filter Harmonic':
                returnVal = np.isclose(self.params[pName], 
                                       self.session.daq_server.get('*')['dev32271']['imps']['0']['demod']['harmonic']['value'][0], 
                                       rtol=1e-03)
            if pName == 'Filter Bandwidth':
                returnVal = np.isclose(self.params[pName], 
                                       self.session.daq_server.get('*')['dev32271']['imps']['0']['demod']['order']['value'][0], 
                                       rtol=1e-03)
            if pName == 'Data Transfer Rate':
                returnVal = np.isclose(self.params[pName], 
                                       self.session.daq_server.get('*')['dev32271']['imps']['0']['demod']['rate']['value'][0], 
                                       rtol=1e-03)
            if pName == 'Equivalent Circuit Mode':
                returnVal = np.isclose(self.params[pName], 
                                       self.session.daq_server.get('*')['dev32271']['imps']['0']['mode']['value'][0],
                                       rtol=1e-03)
            if pName == 'Threshold Input Signal':
                returnVal = np.isclose(self.params[pName], 
                                       self.session.daq_server.get('*')['dev32271']['tu']['thresholds']['0']['input']['value'][0], 
                                       rtol=1e-03)
            if pName == 'State Enable Time':
                returnVal = np.isclose(self.params[pName], 
                                       self.session.daq_server.get('*')['dev32271']['tu']['thresholds']['0']['activationtime']['value'][0], 
                                       rtol=1e-03)
            if pName == 'State Disable Time':
                returnVal = np.isclose(self.params[pName], 
                                       self.session.daq_server.get('*')['dev32271']['tu']['thresholds']['0']['deactivationtime']['value'][0], 
                                       rtol=1e-03)
            if pName == 'Logic Unit Not':
                returnVal = np.isclose(self.params[pName], 
                                       self.session.daq_server.get('*')['dev32271']['tu']['logicunits']['0']['inputs']['0']['not']['value'][0], 
                                       rtol=1e-03)
            if pName == 'Aux Output Signal':
                returnVal = np.isclose(self.params[pName], 
                                       self.session.daq_server.get('*')['dev32271']['auxouts']['0']['outputselect']['value'][0], 
                                       rtol=1e-03)
            if pName == 'Aux Output Scale':
                returnVal = np.isclose(self.params[pName], 
                                       self.session.daq_server.get('*')['dev32271']['auxouts']['0']['scale']['value'][0], 
                                       rtol=1e-03)
            if pName == 'Aux Output Offset':
                returnVal = np.isclose(self.params[pName], 
                                       self.session.daq_server.get('*')['dev32271']['auxouts']['0']['offset']['value'][0], 
                                       rtol=1e-03)
            if pName == 'Aux Output Lower Limit':
                returnVal = np.isclose(self.params[pName], 
                                       self.session.daq_server.get('*')['dev32271']['auxouts']['0']['limitlower']['value'][0], 
                                       rtol=1e-03)
            if pName == 'Aux Output Upper Limit':
                returnVal = np.isclose(self.params[pName], 
                                       self.session.daq_server.get('*')['dev32271']['auxouts']['0']['limitupper']['value'][0], 
                                       rtol=1e-03)
            if pName == 'Signal Output Add':
                returnVal = np.isclose(self.params[pName], 
                                       self.session.daq_server.get('*')['dev32271']['sigouts']['0']['add']['value'][0], 
                                       rtol=1e-03)
            if pName == 'Trigger Source Signal':
                returnVal = np.isclose(self.params[pName], 
                                       self.session.daq_server.get('*')['dev32271']['triggers']['out']['0']['source']['value'][0], 
                                       rtol=1e-03)
        else:
            print("Unknown Parameter!!!")
            returnVal = False
        return returnVal

    def load_params(self):
        for pName in list(self.params):
            self.set_param_value(pName)
            self.push_param_to_device(pName)
        return 0
    
    def reload_params(self):
        for pName in list(self.params):
            if not self.check_param(pName):
                self.set_param_value(pName)
                self.push_param_to_device(pName)
        return 0
    
    def pull_data(self, plot=True, trigger=False, numPoints=1024, numReps=1):
        data = None
        if trigger:
            daq_module = self.session.modules.daq
            
            daq_module.type(6)
            daq_module.triggernode('/dev32271/demods/0/sample.TrigOut1')
            daq_module.clearhistory(1)
            daq_module.bandwidth(0)
            
            daq_module.grid.mode(4)
            daq_module.grid.cols(numPoints)
            daq_module.grid.repetitions(numReps)
            
            daq_module.endless(0)
            self.device.imps[0].enable(True)
            daq_module.subscribe('/dev32271/demods/0/sample.AuxIn0.avg')
            daq_module.subscribe('/dev32271/demods/0/sample.R.avg')
            daq_module.subscribe('/dev32271/imps/0/sample.Param0.avg')
            daq_module.subscribe('/dev32271/imps/0/sample.Param1.avg')
            daq_module.forcetrigger()
            time.sleep(1)
            
            daq_module.execute()
            while daq_module.progress() < 1.0:
                pass
            time.sleep(1)
            
            allData = daq_module.read()
            time.sleep(5)
            
            daq_module.unsubscribe('*')
            
            data = dict()
            data['tickStampImps'] = np.array(list(allData['/dev32271/imps/0/sample.param1.avg'][0])[-3])
            data['tickStampDemods'] = np.array(list(allData['/dev32271/imps/0/sample.param1.avg'][0])[-3])
            data['timeStampImps'] = np.array(data['tickStampImps'], copy=True)
            data['timeStampDemods'] = np.array(data['tickStampDemods'], copy=True)
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

    def defaultJsonConverter(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
        return 0
    
    def writeDataJson(self, data, fName):
        fileName = Path(fName)
        fileName.parent.mkdir(parents=True, exist_ok=True)
        with open(fileName, 'w') as f:
            json.dump(data, f, indent=4, default=self.defaultJsonConverter)
        return 0

    def writeDataH5(self, data, fName, idx, shape=[1,6,1], start=False, finish=False):

        [d1, d2, d3] = shape
        if start:
            f = h5py.File(fName, 'w')
            dltsData = f.create_dataset('dlts', shape=(d1, d2, d3), 
                                        dtype='float32', compression="gzip", 
                                        compression_opts=9)
        dltsData[idx,0] = data['tickStampImps']
        dltsData[idx,1] = data['tickStampDemods']
        dltsData[idx,2] = data['timeStampImps']
        dltsData[idx,3] = data['timeStampDemods']
        dltsData[idx,4] = data['ImpedanceRe']
        dltsData[idx,5] = data['ImpedanceIm']
        dltsData[idx,6] = data['AbsZ']
        dltsData[idx,7] = data['AuxInput1']
        if finish:
            f.close()
        return 0
    
    def runSweep(self, sweepType='freq'):
        data = None
        sweep_module = self.session.modules.sweeper
        sweep_module.device('dev32271')
        
        if sweepType=='freq':
            sweep_module.gridnode('/dev32271/oscs/0/freq')
            sweep_module.start(10)
            sweep_module.stop(510000)
        if sweepType=='cv':
            sweep_module.gridnode('/dev32271/auxouts/0/offset')
            sweep_module.start(0)
            sweep_module.stop(1)
        
        sweep_module.samplecount(200)
        sweep_module.xmapping(0)
        sweep_module.filtermode(0)
        sweep_module.endless(0)
        sweep_module.settling.inaccuracy(0.01)
        sweep_module.averaging.sample(20)
        sweep_module.averaging.tc(15)
        sweep_module.averaging.time(0.1)
        sweep_module.bandwidth(10)
        sweep_module.maxbandwidth(100)
        sweep_module.bandwidthoverlap(1)
        sweep_module.omegasuppression(80)
        sweep_module.order(8)

        self.device.imps[0].enable(True)
        
        sweep_module.subscribe('/dev32271/oscs/0/freq')
        sweep_module.subscribe('/dev32271/auxouts/0/offset')
        sweep_module.subscribe('/dev32271/imps/0/sample')
        sweep_module.execute()
        
        while sweep_module.progress()<1.0:
            print(sweep_module.progress())
            time.sleep(1)
        allData = sweep_module.read()
        time.sleep(1)
        # sweep_module.finish()
        sweep_module.unsubscribe('*')

        # list(a['/dev32271/imps/0/sample'][0][0])
        # a['/dev32271/imps/0/sample'][0][0]['frequency']
        
        d = allData['/dev32271/imps/0/sample'][0][0]
        
        data = allData
        
        # CREATE A CSV FILE FROM SWEEP DATA AND COMPARE IT WITH THIS!!!
        return data, d






