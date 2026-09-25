import time
import numpy as np
import os

from datetime import datetime

import warnings
warnings.filterwarnings("ignore", category=FutureWarning, module="uncertainties")

import dltsConfig as dltsc


def _get_runtime_param_value(param_vars, param_name, fallback_bucket=None):
    """Read the current value from either the UI variables or the synced plain-value dict."""
    if fallback_bucket is not None and param_name in fallback_bucket:
        return fallback_bucket[param_name]

    if param_vars is None or param_name not in param_vars:
        return None

    try:
        return param_vars[param_name].get()
    except Exception:
        return param_vars[param_name]

class dltsRun:
    def __init__(self, fName=None):
        self.impDevice = None
        self.tempDevice = None
        self.impDeviceParams = None
        self.tempDeviceParams = None
        self.outputParams = None
        self.dataFolder = None
        self.runOutputFileType = None
        self.dataFileNames = None
        self.paramsFileName = None
        # self.livePlot = True
        # self.senseRunFailure = True
        # self.excludedRuns = []

        # Pause/resume/redo/retake bookkeeping.
        self.currentStepIndex = 0   # next tempGrid index the main sequence will run (resume point)
        self.stepStatus = {}        # tempGrid index -> 'pending'/'running'/'done'/'failed'/'paused'
        self._everPulled = False    # tracks whether ANY pull has happened yet on this device
                                     # connection, regardless of which tempGrid index it was --
                                     # factory_reset() is skipped only for the very first one

    def check_device_connections(self):
        if hasattr(dltsc, 'impDev') and hasattr(dltsc, 'tempDev'):
            if dltsc.impDev is None and dltsc.tempDev is None:
                print("Error: Impedance Analyzer device and temperature stage device are not connected.")
                returnVal = [0, 0]
            if not dltsc.impDev is None and dltsc.tempDev is None:
                print("Error: Temperature controller device is not connected.")
                returnVal = [1, 0]
            if dltsc.impDev is None and not dltsc.tempDev is None:
                print("Error: Impedance Analyzer device is not connected.")
                returnVal = [0, 1]
            if not dltsc.impDev is None and not dltsc.tempDev is None:
                print("Impedance Analyzer device and temperature stage device are connected.")
                self.impDevice = dltsc.impDev
                self.tempDevice = dltsc.tempDev
                returnVal = [1, 1]

        if hasattr(dltsc, 'impDev') and not hasattr(dltsc, 'tempDev'):
            if dltsc.impDev is None:
                print("Error: Impedance Analyzer device is not connected and "
                      "temperature stage device does not exist.")
                returnVal = [0, -1]
            if not dltsc.impDev is None:
                print("Error: Temperature controller device does not exist.")
                returnVal = [1, -1]

        if not hasattr(dltsc, 'impDev') and hasattr(dltsc, 'tempDev'):
            if dltsc.tempDev is None:
                print("Error: Temperature controller device is not connected and "
                      "impedance analyzer device does not exist.")
                returnVal = [-1, 0]
            if not dltsc.tempDev is None:
                print("Error: Impedance analyzer device does not exist.")
                returnVal = [-1, 1]

        if not hasattr(dltsc, 'impDev') and not hasattr(dltsc, 'tempDev'):
            print("Error: Impedance Analyzer device and Temperature controller device do not exist.")
            returnVal = [-1, -1]

        return returnVal

    def check_device_parameters(self, device='impDev'):
        if device == 'impDev':
            self.impDeviceParams = dict()
            impfail = []
            param_vars = getattr(dltsc, 'z_params_vars', {})
            push_values = getattr(dltsc, 'z_params_for_push', {})
            if hasattr(dltsc, 'z_params_vars'):
                for p in param_vars:
                    value = _get_runtime_param_value(param_vars, p, push_values)
                    self.impDeviceParams[p] = value
                    if value is None:
                        impfail.append(p)
            else:
                dltsc.log_to_textbox("Error: Impedance analyzer parameters do not exist.")

            if len(impfail)>0:
                for f in impfail:
                    dltsc.log_to_textbox("Error: Parameter " + str(f) + " does not exist.")
            return len(impfail)

        if device == 'tempDev':
            self.tempDeviceParams = dict()
            tempfail = []
            param_vars = getattr(dltsc, 't_params_vars', {})
            push_values = getattr(dltsc, 't_params_for_push', {})
            if hasattr(dltsc, 't_params_vars'):
                for p in param_vars:
                    value = _get_runtime_param_value(param_vars, p, push_values)
                    self.tempDeviceParams[p] = value
                    if value is None:
                        tempfail.append(p)
            else:
                dltsc.log_to_textbox("Error: Temperature controller parameters do not exist.")

            if len(tempfail) > 0:
                for f in tempfail:
                    dltsc.log_to_textbox("Error: Parameter " + str(f) + " does not exist.")
            return len(tempfail)

        if device == 'output':
            self.outputParams = dict()
            outputfail = []
            param_vars = getattr(dltsc, 'd_params_vars', {})
            if hasattr(dltsc, 'd_params_vars'):
                for p in param_vars:
                    value = _get_runtime_param_value(param_vars, p)
                    self.outputParams[p] = value
                    if value is None:
                        outputfail.append(p)
            else:
                dltsc.log_to_textbox("Error: Output parameters do not exist.")
            if len(outputfail) > 0:
                for f in outputfail:
                    dltsc.log_to_textbox("Error: Parameter " + str(f) + " does not exist.")
            return len(outputfail)

    def check_setup(self):
        returnVal = 0
        # 1. Check if devices exists, if not report error
        device_status = self.check_device_connections()
        if sum(device_status) < 2:
            dltsc.log_to_textbox("Error: One or more devices are not connected.")
            returnVal -= 1
        else:
            dltsc.log_to_textbox("All devices are connected.")
            returnVal += 1
        # 2. Check device parameters and I/O parameters, report the errors if any
        param_status = self.check_device_parameters('impDev')
        param_status += self.check_device_parameters('tempDev')
        param_status += self.check_device_parameters('output')
        if param_status > 0:
            dltsc.log_to_textbox("Error: One or more device parameters are not set.")
            returnVal -= 1
        else:
            dltsc.log_to_textbox("All device parameters are set.")
            returnVal += 1

        return returnVal

    def init_experiment(self):
        hardware_status = self.check_setup()
        if hardware_status < 2:
            dltsc.log_to_textbox("Error: Cannot initialize experiment. Hardware is not ready.")
            return -1
        else:
            dltsc.log_to_textbox("1. Hardware initialized.")
            self.tempDevice.set_temp_grid()
            dltsc.log_to_textbox("2. Temperature grid set.")

            rootFolder = self.outputParams['Data Root Folder']
            outputType = str(self.outputParams['Data File Format']).strip().lower()
            if outputType == 'json':
                ext = '.json'
            elif outputType == 'hdf5':
                ext = '.h5'
            elif outputType == 'txt':
                ext = '.txt'
            else:
                ext = '.json'

            timeAndDate = datetime.now()
            temp = '{:02d}'.format(timeAndDate.month) + '{:02d}'.format(timeAndDate.day) + \
                   '{:02d}'.format(timeAndDate.year)[-2:] + '\\'
            topFolder = rootFolder + '\\' + temp
            if not os.path.exists(topFolder):
                os.makedirs(topFolder)

            timeAndDate = datetime.now()
            temp = '{:02d}'.format(timeAndDate.hour) + '{:02d}'.format(timeAndDate.minute) + \
                   '{:02d}'.format(timeAndDate.second) + '\\'
            subFolder = topFolder + '\\' + temp
            if not os.path.exists(subFolder):
                os.makedirs(subFolder)

            self.runOutputFileType = outputType
            self.dataFolder = subFolder

            fName = []
            for i in range(len(dltsc.tempDev.tempGrid)):
                if '-' in str(dltsc.tempDev.tempGrid[i]):
                   prefix = 'n'
                else:
                   prefix = 'p'
                fName.append(self.dataFolder + prefix +
                            str(np.abs(dltsc.tempDev.tempGrid[i])).replace('.','p') + ext)
            self.dataFileNames = fName
            self.paramsFileName = self.dataFolder + 'runParams.txt'

            # Publish this run's file manifest so liveDataTab.py can watch for
            # each temperature's file without reaching into this instance.
            dltsc.run_dataFolder = self.dataFolder
            dltsc.run_dataFileNames = list(self.dataFileNames)
            dltsc.run_outputFileType = self.runOutputFileType

            dltsc.log_to_textbox("3. Output file names set.")
            return 0

    def _run_single_step(self, i, deleteFirst=False):
        """Acquire and write the data for tempGrid index i. Shared by the main
        sequential run and by redo/retake, which call this for arbitrary,
        possibly out-of-order indices.
        """
        tempDev = self.tempDevice
        impdDev = self.impDevice

        if deleteFirst and self.dataFileNames is not None:
            fPath = self.dataFileNames[i]
            try:
                if os.path.exists(fPath):
                    os.remove(fPath)
                    dltsc.log_to_textbox(f"Removed existing data file for T = {tempDev.tempGrid[i]} C.")
            except Exception as exc:
                dltsc.log_to_textbox(f"Warning: could not remove existing data file for T = {tempDev.tempGrid[i]} C: {exc}")

        self.stepStatus[i] = 'running'
        ramp = tempDev.tRamp
        delay = tempDev.tStableDelay
        tempDev.go_to_temp(tempDev.tempGrid[i], ramp, delay)
        if dltsc.run_abortRequested:
            # GUI closing: the stage is now ramping to room temperature, so
            # don't acquire at a temperature that's no longer being held.
            self.stepStatus[i] = 'aborted'
            return 'aborted'
        time.sleep(1)
        # factory_reset() is skipped only for the very first pull this device
        # connection has ever done (right after setup); any later pull --
        # whether the next step in sequence, a resume, or an out-of-order
        # redo/retake of an EARLIER step -- resets first for a clean read.
        if self._everPulled:
            impdDev.device.factory_reset()
        impdDev.reload_params()

        numPoints = 2 ** dltsc.recast_param_type('output', 'Number of Points (power of 2)')
        numReps = dltsc.recast_param_type('output', 'Number of Reps')
        outType = str(self.runOutputFileType).strip().lower()
        if outType in ('txt', 'json', 'hdf5'):
            fName = self.dataFileNames[i]
            data = impdDev.pull_data(plot=False, trigger=True,
                                   numPoints=numPoints, numReps=numReps)
            if dltsc.run_abortRequested:
                # The GUI was closed during this acquisition and the stage
                # started ramping to room temperature part-way through it, so
                # this data wasn't taken at a stable temperature: discard it
                # rather than write a file that looks valid.
                self.stepStatus[i] = 'aborted'
                dltsc.log_to_textbox(f"Discarded T = {tempDev.tempGrid[i]} C data: GUI closed during acquisition.")
                return 'aborted'
            if outType == 'hdf5':
                # HDF5's start/finish flags assume one uninterrupted forward
                # pass over the whole grid; an out-of-order redo/retake of a
                # single index doesn't fit that shape cleanly, so this is
                # best-effort for HDF5 specifically (matching the existing,
                # documented gap that live HDF5 plotting isn't supported yet).
                impdDev.writeDataH5(data, fName, i, shape=[1, 8, 1],
                                    start=(not self._everPulled), finish=(i == len(tempDev.tempGrid) - 1))
            else:
                impdDev.writeDataJson(data, fName)

        self._everPulled = True
        self.stepStatus[i] = 'done'
        return 0

    def run_experiment(self, indices=None, deleteFirst=False):
        """Run the experiment.

        indices=None (the default) runs the full temperature grid in order,
        starting from self.currentStepIndex -- 0 on a fresh run, or wherever
        a previous pause left off, so calling this again after a pause simply
        resumes rather than needing a separate "restart" code path. Between
        each step it checks dltsc.run_pauseRequested; if set, it records the
        NEXT index to resume from in self.currentStepIndex and returns
        'paused' without advancing further, leaving devices connected and
        the temperature grid untouched (unlike stopping the run) so a resume
        picks up exactly where it left off.

        indices=[...] (redo / remove & retake) instead runs ONLY those
        tempGrid indices, in ascending temperature order (fewer thermal
        cycles back and forth than the selection's original order), without
        touching self.currentStepIndex -- it doesn't affect where the main
        sequence would resume from. deleteFirst=True additionally deletes
        each index's existing data file before reacquiring it ("remove &
        retake"); deleteFirst=False just overwrites it in place ("redo").

        Returns 'completed', 'paused', 'error', or 'aborted' (the GUI is
        closing -- dltsc.run_abortRequested -- see DLTSGUI_MainWindow.on_closing).
        """
        tempDev = self.tempDevice
        runIndices = sorted(indices) if indices is not None else range(self.currentStepIndex, len(tempDev.tempGrid))
        isMainSequence = indices is None

        try:
            for i in runIndices:
                if dltsc.run_abortRequested:
                    return 'aborted'
                if isMainSequence and dltsc.run_pauseRequested:
                    self.currentStepIndex = i
                    self.stepStatus[i] = 'paused'
                    dltsc.log_to_textbox(f"Run paused before T = {tempDev.tempGrid[i]} C (step {i + 1}/{len(tempDev.tempGrid)}).")
                    return 'paused'

                if self._run_single_step(i, deleteFirst=deleteFirst) == 'aborted':
                    return 'aborted'

                if isMainSequence:
                    self.currentStepIndex = i + 1
        except Exception as exc:
            if 0 <= i < len(tempDev.tempGrid):
                self.stepStatus[i] = 'failed'
            dltsc.log_to_textbox(f"Error during step T = {tempDev.tempGrid[i]} C: {exc}")
            return 'error'

        return 'completed'

    def finish_experiment(self):
        tempDev = self.tempDevice
        impdDev = self.impDevice

        if self.impDeviceParams is not None and self.tempDeviceParams is not None and self.outputParams is not None:
            runParams = {**self.impDeviceParams, **self.tempDeviceParams, **self.outputParams}
        else:
            runParams = {}
        fName = self.paramsFileName
        if impdDev is not None and hasattr(impdDev, 'writeDataJson') and fName is not None:
            impdDev.writeDataJson(runParams, fName)

        # The return to room temperature is no longer done here: this runs on
        # the Tk main thread, and waiting out the ramp froze the GUI for
        # minutes. liveDataTab._return_to_room_temp_async() calls
        # return_to_room_temp() on a background thread instead.
        dltsc.log_to_textbox("Run complete: devices remain connected for the next run until the GUI is closed.")
        return 0

    def return_to_room_temp(self):
        """Ramp the stage back to the Room Temperature (C) / Room Ramp (C/min)
        set on the Input Parameters tab and wait until it gets there. Blocking
        (polls the controller), so call it from a background thread. Returns
        the controller's status: 0 reached, 1 gave up waiting, -1 failed/not connected.
        """
        tempDev = self.tempDevice
        if tempDev is None:
            return -1
        Tr, ramp = tempDev.Troom, tempDev.roomRamp
        dltsc.log_to_textbox(f"Returning stage to room temperature: {Tr} C at {ramp} C/min...")
        try:
            status = tempDev.go_to_room_temp(Tr=Tr, ramp=ramp)
        except Exception as exc:
            dltsc.log_to_textbox(f"Warning: could not return stage to room temperature: {exc}")
            return -1
        if status == 0:
            dltsc.log_to_textbox(f"Stage is at room temperature ({Tr} C).")
        elif status == 1:
            dltsc.log_to_textbox(f"Warning: stage did not settle at {Tr} C in the expected time; "
                                 f"it is still ramping/holding toward {Tr} C.")
        else:
            dltsc.log_to_textbox("Warning: temperature controller not connected; stage was not returned to room temperature.")
        return status
        
        
        
        
        
        
        
