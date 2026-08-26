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