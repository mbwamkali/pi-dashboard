@echo off
rem One-time Google sign-in for the dashboard, on Windows.
rem Double-click this file (or run it in a Command Prompt) from the pi-dashboard folder.
rem Needs client_secret.json in the same folder. Installs Python for this user if it's
rem missing, sets up the Google libraries in .venv-win, then runs authorize.py, which
rem opens the browser to sign in and saves token.json here.
setlocal
cd /d "%~dp0"

if not exist "client_secret.json" (
  echo client_secret.json is missing. Put it in this folder first:
  echo   %CD%
  goto :end
)

rem --- Find Python 3 (the "py" launcher, then python on PATH, then the usual install folders)
set "PY="
where py >nul 2>&1 && py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
  python -c "import sys; sys.exit(sys.version_info[0] != 3)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do if exist "%%D\python.exe" set "PY="%%D\python.exe""
)
if not defined PY (
  echo Python isn't installed. Installing it for this Windows user with winget...
  winget install -e --id Python.Python.3.13 --scope user --accept-package-agreements --accept-source-agreements
  for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do if exist "%%D\python.exe" set "PY="%%D\python.exe""
)
if not defined PY (
  echo Couldn't find or install Python. Install it from https://www.python.org/downloads/
  echo ^(tick "Add python.exe to PATH"^), then run this again.
  goto :end
)
echo Using Python: %PY%

rem --- Google libraries in a private folder (.venv-win), only the first time
if not exist ".venv-win\Scripts\python.exe" (
  echo Setting up the Google libraries ^(first time only^)...
  %PY% -m venv .venv-win || goto :fail
  ".venv-win\Scripts\python.exe" -m pip install --quiet --upgrade pip
  ".venv-win\Scripts\python.exe" -m pip install --quiet -r requirements.txt || goto :fail
)

rem --- Sign in (opens the browser) and list calendars / task lists
set PYTHONUTF8=1
".venv-win\Scripts\python.exe" authorize.py %* || goto :fail

echo.
echo Done. token.json is saved in:
echo   %CD%
echo Copy token.json and client_secret.json to the Pi's pi-dashboard folder, e.g.:
echo   scp token.json client_secret.json USER@HOSTNAME.local:pi-dashboard/
echo then on the Pi:  sudo systemctl restart pi-dashboard
goto :end

:fail
echo.
echo Something went wrong (see the messages above).

:end
echo.
pause
