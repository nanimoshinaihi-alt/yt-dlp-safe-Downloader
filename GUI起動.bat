@echo off
cd /d "%~dp0"

echo [チェック中] 必要なライブラリ (yt-dlp / customtkinter) の確認を行っています...
python -c "import yt_dlp, customtkinter" 2>nul
if errorlevel 1 (
    echo [セットアップ] 必要なパッケージ (yt-dlp, customtkinter) を自動インストールしています...
    python -m pip install yt-dlp customtkinter
    if errorlevel 1 (
        echo.
        echo [エラー] Pythonが見つからないか、インストールに失敗しました。
        echo 他のPCで実行する場合は Python (3.10以上) を事前にインストールしてください。
        pause
        exit /b 1
    )
)

echo [起動中] yt-dlp Safe Downloader を起動しています...
python gui_app.py
if errorlevel 1 (
    echo.
    echo エラーが発生しました。上記のエラーメッセージをご確認ください。
    pause
)
