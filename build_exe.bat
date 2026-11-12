@echo off
echo Membuat Vidrop.exe ...
python -m pip install -q -U -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --name Vidrop ^
  --icon assets\vidrop.ico --add-data "assets;assets" ^
  --collect-all imageio_ffmpeg --collect-all yt_dlp --collect-all yt_dlp_ejs vidrop.py
echo.
echo Selesai! File ada di folder dist\Vidrop.exe
pause
