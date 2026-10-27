@echo off
setlocal
cd /d "%~dp0"
rem Probe the Python launcher, then every matching interpreter on PATH.
for /f "delims=" %%P in ('where py 2^>nul') do (
    for %%V in (-3 -3.15 -3.14 -3.13 -3.12 -3.11) do (
        "%%P" %%V -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>nul
        if not errorlevel 1 (
            "%%P" %%V scripts\local.py %*
            exit /b
        )
    )
)
for /f "delims=" %%P in ('where python3 python3.15 python3.14 python3.13 python3.12 python3.11 python 2^>nul') do (
    "%%P" -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>nul
    if not errorlevel 1 (
        "%%P" scripts\local.py %*
        exit /b
    )
)
echo Install Python 3.11+ and Docker Desktop, then run this launcher again.
exit /b 1
