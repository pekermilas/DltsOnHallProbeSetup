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

Dim oShell, oFSO
Set oShell = CreateObject("Wscript.Shell")
Set oFSO = CreateObject("Scripting.FileSystemObject")

Dim strRepo
strRepo = FindRepo()
If strRepo = "" Then
    MsgBox "Could not find the " & REPO_NAME & " folder containing " & MAIN_PY & ".", _
           vbExclamation, "DLTS GUI"
    WScript.Quit 1
End If

UpdateShortcut strRepo

oShell.CurrentDirectory = strRepo
oShell.Run "cmd /c """"" & strRepo & "\" & BAT_NAME & """ """ & strRepo & """""", 0, False


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
