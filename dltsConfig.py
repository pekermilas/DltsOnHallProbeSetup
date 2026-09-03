##---------------------GUI-------------------------
# Main GUI constants
root = None
tabControl = None
textbox = None
textboxes = None
textlinecount = None
maxTextLineCount = None

# Main TAB constants
runParamsTab = None
livePlotTab = None
postprocessingTab = None

##---------------------RUNTIME-------------------------
# Devices
tempDev = None
impDev = None

##---------------------TEST-------------------------
sourcePrefixSelection = None
z_params_vars = dict()
z_params_for_push = dict()
z_param_inputField = None
t_params_vars = dict()
t_params_for_push = dict()
t_param_inputField = None
d_params_vars = dict()
d_params_for_push = dict()
d_param_inputField = None
root_data_folder = None
param_history = None
param_history_labels = None
param_history_selection = None
param_history_inputField = None

run_button = None


def init():
    ##---------------------GUI-------------------------
    # Main GUI constants
    global root
    global tabControl
    global textbox
    global textboxes
    global textlinecount
    global maxTextLineCount

    # Main TAB constants
    global runParamsTab
    global livePlotTab
    global postprocessingTab

    ##---------------------RUNTIME-------------------------
    # Devices
    global tempDev
    global impDev

    ##---------------------TEST-------------------------
    global sourcePrefixSelection
    global z_params_vars
    global z_param_inputField
    global t_params_vars
    global t_param_inputField
    global d_params_vars
    global d_param_inputField
    global root_data_folder
    global param_history
    global param_history_labels
    global param_history_selection
    global param_history_inputField

    global run_button

#-----------------------Global Functions--------------------------------#
def log_to_textbox(message):
    """Appends text to all shared GUI textboxes and manages line limits."""
    global textlinecount
    try:
        _textboxes = list(textboxes) if textboxes else []
    except NameError:
        _textboxes = []
    if not _textboxes:
        try:
            if textbox:
                _textboxes = [textbox]
        except NameError:
            pass
    for tb in _textboxes:
        if tb:
            tb.insert("end", f"{message}\n")
    if _textboxes:
        textlinecount += 1
        if textlinecount > maxTextLineCount:
            for tb in _textboxes:
                if tb:
                    tb.delete("1.0", "2.0")
            textlinecount -= 1

def recast_param_type(device, pname):
    if device == 'impDev':
        if pname in z_params_vars:
            oldValue = z_params_vars[pname].get()
            if pname == 'Oscillation Amplitude':
                newValue = float(oldValue)
            if pname == 'Oscillation Frequency':
                newValue = float(oldValue)
            if pname == 'Oscillation ON/OFF':
                if oldValue == '1 - On':
                    newValue = 1
                if oldValue == '0 - Off':
                    newValue = 0
            if pname == 'Max bandwidth':
                newValue = float(oldValue)
            if pname == 'Input Control':
                if oldValue == '0 - Manual':
                    newValue = 0
                if oldValue == '1 - Auto':
                    newValue = 1
                if oldValue == '2 - Current Zone':
                    newValue = 2
            if pname == 'Current Range':
                newValue = float(oldValue)
            if pname == 'Voltage Range':
                newValue = float(oldValue)
            if pname == 'Omega Suppression':
                newValue = float(oldValue)
            if pname == 'Filter Harmonic':
                newValue = int(oldValue)
            if pname == 'Filter Bandwidth':
                newValue = int(oldValue)
            if pname == 'Data Transfer Rate':
                newValue = int(oldValue)
            if pname == 'Equivalent Circuit Mode':
                if oldValue == '0 - 4-Terminal':
                    newValue = 0
                if oldValue == '1 - 2-Terminal':
                    newValue = 1
            if pname == 'Threshold Input Signal':
                if oldValue == '59 - TU Output Value':
                    newValue = 59
                if oldValue == '58 - Aux Output Overload':
                    newValue = 58
                if oldValue == '56 - Aux Input Overload':
                    newValue = 56
                if oldValue == '55 - Output Overload':
                    newValue = 55
                if oldValue == '54 - Input(I) Overload':
                    newValue = 54
                if oldValue == '53 - Input(V) Overload':
                    newValue = 53
                if oldValue == '52 - Trigger Out':
                    newValue = 52
                if oldValue == '51 - Trigger In':
                    newValue = 51
                if oldValue == '50 - DIO':
                    newValue = 50
                if oldValue == '3 - Demod Theta':
                    newValue = 3
                if oldValue == '2 - Demod R':
                    newValue = 2
                if oldValue == '1 - Demod Y':
                    newValue = 1
                if oldValue == '0 - Demod X':
                    newValue = 0
            if pname == 'State Enable Time':
                newValue = float(oldValue)
            if pname == 'State Disable Time':
                newValue = float(oldValue)
            if pname == 'Logic Unit Not':
                if oldValue == '0 - Off':
                    newValue = 0
                if oldValue == '1 - On':
                    newValue = 1
            if pname == 'Aux Output Signal':
                if oldValue == '0 - Demod X':
                    newValue = 0
                if oldValue == '1 - Demod Y':
                    newValue = 1
                if oldValue == '2 - Demod R':
                    newValue = 2
                if oldValue == '3 - Demod Theta':
                    newValue = 3
                if oldValue == '11 - TU Filtered Value':
                    newValue = 11
                if oldValue == '12 - Manual':
                    newValue = 12
                if oldValue == '13 - TU Output Value':
                    newValue = 13
            if pname == 'Aux Output Scale':
                newValue = float(oldValue)
            if pname == 'Aux Output Offset':
                newValue = float(oldValue)
            if pname == 'Aux Output Lower Limit':
                newValue = float(oldValue)
            if pname == 'Aux Output Upper Limit':
                newValue = float(oldValue)
            if pname == 'Signal Output Add':
                if oldValue == '1 - True':
                    newValue = 1
                if oldValue == '0 - False':
                    newValue = 0
            if pname == 'Trigger Source Signal':
                if oldValue == '0 - Off':
                    newValue = 0
                if oldValue == '1 - Osc Phi Demod 2':
                    newValue = 1
                if oldValue == '36 - Threshold 1':
                    newValue = 36
                if oldValue == '37 - Threshold 2':
                    newValue = 37
                if oldValue == '38 - Threshold 3':
                    newValue = 38
                if oldValue == '39 - Threshold 4':
                    newValue = 39
                if oldValue == '52 - MDS Sync Out':
                    newValue = 52
        if device == 'tempDev':
            if pname in t_params_vars:
                oldValue = t_params_vars[pname].get()
                if pname == 'Initial Temperature (C)':
                    newValue = float(oldValue)
                if pname == 'Final Temperature (C)':
                    newValue = float(oldValue)
                if pname == 'Number of Temperatures':
                    newValue = int(oldValue)
                if pname == 'Temperature Ramp (C/min)':
                    newValue = float(oldValue)
                if pname == 'Stability Delay (s)':
                    newValue = int(oldValue)
        if device == 'output':
            if pname in d_params_vars:
                oldValue = d_params_vars[pname].get()
                if pname == 'Number of Points (power of 2)':
                    newValue = int(oldValue)
                if pname == 'Number of Reps':
                    newValue = int(oldValue)

    return newValue

