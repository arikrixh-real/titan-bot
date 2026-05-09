@echo off
cd /d "%~dp0"

echo TITAN folder:
cd

echo.
echo Starting TITAN Backend API...
start "TITAN API" cmd /k "cd /d "%~dp0" && python titan_api.py"

timeout /t 4

echo.
echo Starting TITAN Assistant UI...
start "TITAN UI" cmd /k "cd /d "%~dp0" && streamlit run titan_assistant_app.py"

timeout /t 6

echo.
echo Opening browser...
start http://localhost:8501

echo.
echo If browser did not open, manually open:
echo http://localhost:8501

pause