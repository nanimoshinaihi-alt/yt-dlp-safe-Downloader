@echo off
cd /d "%~dp0"

echo ==================================================
echo  yt-dlp Safe Downloader 起動スクリプト
echo ==================================================
echo.

python -c "import yt_dlp, customtkinter" >nul 2>&1
if errorlevel 1 goto INSTALL_LIB
goto START_APP

:INSTALL_LIB
echo [セットアップ] 必要なライブラリ (yt-dlp, customtkinter) をインストールしています...
python -m pip install yt-dlp customtkinter
if errorlevel 1 goto ERROR_PYTHON
goto START_APP

:START_APP
echo [起動中] アプリケーションを起動しています...
python gui_app.py
if errorlevel 1 goto ERROR_APP
exit /b 0

:ERROR_PYTHON
echo.
echo [エラー] Pythonが見つからないか、ライブラリの自動インストールに失敗しました。
echo Python (3.10以上) がインストールされているかをご確認ください。
echo.
pause
exit /b 1

:ERROR_APP
echo.
echo [エラー] アプリケーションの実行中にエラーが発生しました。
echo 上記のエラーメッセージをご確認ください。
echo.
pause
exit /b 1
