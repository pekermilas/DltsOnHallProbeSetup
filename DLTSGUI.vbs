' Launches DLTSGUI_MainWindow.py (via DLTSGUI.bat) without a console window.
' Searches for the DltsOnHallProbeSetup folder so it works on any PC, and keeps
' DLTSGUI.lnk pointing at the folder that was found.
Option Explicit

Const REPO_NAME = "DltsOnHallProbeSetup"
Const MAIN_PY = "DLTSGUI_MainWindow.py"
Const BAT_NAME = "DLTSGUI.bat"
Const VBS_NAME = "DLTSGUI.vbs"
Const LNK_NAME = "DLTSGUI.lnk"
Const ICON_NAME = "Simpleicons-Team-Simple-Crystal.ico"
Const DEFAULT_REPO = "%USERPROFILE%\Documents\GitHub\DltsOnHallProbeSetup"
Const MAX_SCAN_DEPTH = 4

Dim oShell, oFSO, strLock, bHaveLock
Set oShell = CreateObject("Wscript.Shell")
Set oFSO = CreateObject("Scripting.FileSystemObject")

' Held by a launcher from its start until DLTSGUI.bat is running, so that of
' two launchers started together only the later one asks (only one can create
' the file). Left behind by a launcher that died, it is taken over.
strLock = oShell.ExpandEnvironmentStrings("%TEMP%") & "\DLTSGUI.launch.lock"
bHaveLock = TryLock()
If Not bHaveLock And CountLaunchers() <= 1 Then
    On Error Resume Next
    oFSO.DeleteFile strLock, True
    On Error GoTo 0
    bHaveLock = TryLock()
End If

' A GUI that is still starting (conda activation, imports) shows no window for
' a while, so a second click is easy. Ask before starting another one.
If Not bHaveLock Or IsGuiRunning() Then
    If MsgBox("A DLTS GUI is already running or still starting up." & vbCrLf & vbCrLf & _
              "Do you want to start another instance?", _
              vbYesNo + vbQuestion + vbDefaultButton2 + vbSystemModal, "DLTS GUI") <> vbYes Then
        ReleaseLock
        WScript.Quit 0
    End If
End If

Dim strRepo
strRepo = FindRepo()
If strRepo = "" Then
    ReleaseLock
    MsgBox "Could not find the " & REPO_NAME & " folder containing " & MAIN_PY & ".", _
           vbExclamation, "DLTS GUI"
    WScript.Quit 1
End If

UpdateShortcut strRepo

oShell.CurrentDirectory = strRepo
oShell.Run "cmd /c """"" & strRepo & "\" & BAT_NAME & """ """ & strRepo & """""", 0, False
' From here on IsGuiRunning sees the cmd/python process instead of the lock.
ReleaseLock


Function TryLock()
    ' CreateTextFile without overwrite fails if the file exists, so only one
    ' launcher gets it.
    On Error Resume Next
    oFSO.CreateTextFile(strLock, False).Close
    TryLock = (Err.Number = 0)
    Err.Clear
    On Error GoTo 0
End Function

Sub ReleaseLock()
    If Not bHaveLock Then Exit Sub
    On Error Resume Next
    oFSO.DeleteFile strLock, True
    On Error GoTo 0
    bHaveLock = False
End Sub

Function CountLaunchers()
    ' Running copies of this .vbs, this one included.
    Dim oWMI, oProc
    CountLaunchers = 0
    On Error Resume Next
    Set oWMI = GetObject("winmgmts:{impersonationLevel=impersonate}!\\.\root\cimv2")
    If Err.Number <> 0 Then Err.Clear : Exit Function
    For Each oProc In oWMI.ExecQuery("SELECT CommandLine FROM Win32_Process WHERE " & _
            "Name='wscript.exe' OR Name='cscript.exe'")
        If InStr(LCase(oProc.CommandLine & ""), LCase(VBS_NAME)) > 0 Then CountLaunchers = CountLaunchers + 1
    Next
    On Error GoTo 0
End Function

Function IsGuiRunning()
    ' True if a python process runs MAIN_PY, or a cmd process runs BAT_NAME
    ' (the GUI between launch and python start).
    Dim oWMI, oProc, cmdLine
    IsGuiRunning = False
    On Error Resume Next
    Set oWMI = GetObject("winmgmts:{impersonationLevel=impersonate}!\\.\root\cimv2")
    If Err.Number <> 0 Then Err.Clear : Exit Function
    For Each oProc In oWMI.ExecQuery("SELECT Name, CommandLine FROM Win32_Process WHERE " & _
            "Name='python.exe' OR Name='pythonw.exe' OR Name='cmd.exe'")
        cmdLine = LCase(oProc.CommandLine & "")
        Select Case LCase(oProc.Name)
            Case "python.exe", "pythonw.exe"
                If InStr(cmdLine, LCase(MAIN_PY)) > 0 Then IsGuiRunning = True
            Case "cmd.exe"
                If InStr(cmdLine, LCase(BAT_NAME)) > 0 Then IsGuiRunning = True
        End Select
    Next
    On Error GoTo 0
End Function

Function IsRepo(p)
    IsRepo = False
    If p = "" Then Exit Function
    If oFSO.FileExists(p & "\" & MAIN_PY) And oFSO.FileExists(p & "\" & BAT_NAME) Then IsRepo = True
End Function

Function FindRepo()
    Dim candidates, c, p, drv, docs, user
    FindRepo = ""

    ' 1) Folder this script lives in
    p = oFSO.GetParentFolderName(WScript.ScriptFullName)
    If IsRepo(p) Then FindRepo = p : Exit Function

    ' 2) Common GitHub locations (Documents may be redirected to OneDrive)
    docs = oShell.SpecialFolders("MyDocuments")
    user = oShell.ExpandEnvironmentStrings("%USERPROFILE%")
    candidates = Array( _
        docs & "\GitHub", _
        user & "\Documents\GitHub", _
        oShell.ExpandEnvironmentStrings("%OneDrive%") & "\Documents\GitHub", _
        oShell.ExpandEnvironmentStrings("%OneDriveCommercial%") & "\Documents\GitHub", _
        user & "\OneDrive\Documents\GitHub", _
        user & "\GitHub", _
        user & "\source\repos", _
        user & "\Desktop\GitHub", _
        user)
    For Each c In candidates
        If IsRepo(c & "\" & REPO_NAME) Then FindRepo = c & "\" & REPO_NAME : Exit Function
    Next

    ' 3) Typical spots on every fixed drive
    For Each drv In oFSO.Drives
        If drv.DriveType = 2 And drv.IsReady Then
            candidates = Array(drv.Path & "\GitHub", drv.Path & "\Documents\GitHub", drv.Path)
            For Each c In candidates
                If IsRepo(c & "\" & REPO_NAME) Then FindRepo = c & "\" & REPO_NAME : Exit Function
            Next
        End If
    Next

    ' 4) Limited-depth scan: user profile first, then each fixed drive
    p = ScanFolder(user, 0)
    If p <> "" Then FindRepo = p : Exit Function
    For Each drv In oFSO.Drives
        If drv.DriveType = 2 And drv.IsReady Then
            p = ScanFolder(drv.Path & "\", 0)
            If p <> "" Then FindRepo = p : Exit Function
        End If
    Next
End Function

Function ScanFolder(p, depth)
    Dim oFolder, oSub, found
    ScanFolder = ""
    If depth > MAX_SCAN_DEPTH Then Exit Function
    On Error Resume Next
    Set oFolder = oFSO.GetFolder(p)
    If Err.Number <> 0 Then Err.Clear : Exit Function
    For Each oSub In oFolder.SubFolders
        If Err.Number <> 0 Then Err.Clear : Exit For
        If LCase(oSub.Name) = LCase(REPO_NAME) And IsRepo(oSub.Path) Then
            ScanFolder = oSub.Path : Exit Function
        End If
        If Not IsSkipped(oSub) Then
            found = ScanFolder(oSub.Path, depth + 1)
            If found <> "" Then ScanFolder = found : Exit Function
        End If
    Next
    On Error GoTo 0
End Function

Function IsSkipped(oSub)
    Dim n
    n = LCase(oSub.Name)
    IsSkipped = (oSub.Attributes And 1030) <> 0 _
        Or n = "windows" Or n = "program files" Or n = "program files (x86)" _
        Or n = "programdata" Or n = "appdata" Or n = "$recycle.bin" _
        Or n = "system volume information" Or n = "node_modules" Or n = ".git" _
        Or Left(n, 8) = "anaconda" Or Left(n, 9) = "miniconda"
End Function

Sub UpdateShortcut(repo)
    ' Use the portable %USERPROFILE% form when the repo is in the default place,
    ' otherwise the absolute folder that was found. Rewrite only if it changed.
    Dim base, args, oLnk
    base = repo
    If LCase(repo) = LCase(oShell.ExpandEnvironmentStrings(DEFAULT_REPO)) Then base = DEFAULT_REPO
    args = """" & base & "\" & VBS_NAME & """"

    On Error Resume Next
    Set oLnk = oShell.CreateShortcut(repo & "\" & LNK_NAME)
    If oFSO.FileExists(repo & "\" & LNK_NAME) And oLnk.Arguments = args Then Exit Sub
    oLnk.TargetPath = "%SystemRoot%\System32\wscript.exe"
    oLnk.Arguments = args
    oLnk.WorkingDirectory = base
    oLnk.IconLocation = base & "\" & ICON_NAME & ",0"
    oLnk.Description = "DLTS GUI"
    oLnk.WindowStyle = 1
    oLnk.Save
    On Error GoTo 0
End Sub
