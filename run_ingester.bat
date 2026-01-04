@echo off
setlocal ENABLEDELAYEDEXPANSION

REM ==============================
REM Configuration
REM ==============================
set "SUBMITTER="

if "%SUBMITTER%"=="" (
    echo ERROR: SUBMITTER is not set.
    echo Please edit this script (run_ingester.bat) and set the SUBMITTER=your_faf_username before running it.
    goto :wait
)


echo Checking for Python...

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3 and ensure it is added to PATH.
    goto :wait
)

echo Python found.
echo.

echo Upgrading pip...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo ERROR: Failed to upgrade pip.
    goto :wait
)

echo.
echo Installing dependencies...

python -m pip install ^
    requests ^
    tqdm ^
    download

if errorlevel 1 (
    echo ERROR: Failed to install one or more dependencies.
    goto :wait
)

echo.
echo All dependencies installed successfully.
echo.

echo Starting ingester with SUBMITTER=%SUBMITTER%
echo.

python .\ingester.py ^
    --use-latest ^
    --follow ^
    --wait-for-new-file ^
    --target-server https://fa-metrics.rancher.katzencluster.atlantishq.de ^
    --submitter %SUBMITTER%

echo.
echo Ingester process exited.

:wait
echo.
echo Press any key to close this window...
pause >nul
endlocal