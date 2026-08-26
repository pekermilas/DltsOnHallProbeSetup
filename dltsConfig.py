def init():
    ##---------------------GUI-------------------------
    # Main GUI constants
    global root
    global tabControl
    global textbox
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
    """Appends text to the shared GUI textbox and manages line limits."""
    # Use 'global' inside the function ONLY if you plan to reassign the variable (e.g., textlinecount = ...)
    global textlinecount
    # global maxTextLineCount
    # global textbox

    # You can read and call methods on objects (like textbox) without the 'global' keyword
    if textbox:
        textbox.insert("end", f"{message}\n")
        textlinecount += 1

        # Example using your shared max limit constant
        if textlinecount > maxTextLineCount:
            textbox.delete("1.0", "2.0")
            textlinecount -= 1