@echo off
title TokenGPT Windows Builder
echo ==========================================
echo   Building Standalone TokenGPT.exe...
echo ==========================================

python -m pip install --upgrade pip
pip install -r requirements.txt

pyinstaller --noconfirm --onefile --windowed --name "TokenGPT" --collect-all customtkinter main.py

echo.
echo ==========================================
echo   DONE! Your app is inside the "dist" folder:
echo   dist\TokenGPT.exe
echo ==========================================
pause