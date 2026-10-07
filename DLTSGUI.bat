@echo on
rem Launches DLTSGUI_MainWindow.py from the folder given as %1 (passed by DLTSGUI.vbs),
rem or from the folder of this .bat file when run directly.
rem Uses the first Anaconda/Miniconda install found; falls back to python on PATH.
set "APPDIR=%~1"
if "%APPDIR%"=="" set "APPDIR=%~dp0"
if "%APPDIR:~-1%"=="\" set "APPDIR=%APPDIR:~0,-1%"
set "SCRIPT=%APPDIR%\DLTSGUI_MainWindow.py"
cd /d "%APPDIR%"

for %%C in ("%USERPROFILE%\anaconda3" "%USERPROFILE%\miniconda3" "%ProgramData%\anaconda3" "%ProgramData%\miniconda3" "%LOCALAPPDATA%\anaconda3" "%LOCALAPPDATA%\miniconda3") do (
    if exist "%%~C\python.exe" (
        call "%%~C\Scripts\activate.bat"
        "%%~C\python.exe" "%SCRIPT%"
        goto :eof
    )
)

python "%SCRIPT%"
