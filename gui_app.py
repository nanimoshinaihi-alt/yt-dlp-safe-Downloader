"""
yt-dlp Safe Downloader GUI Application
CustomTkinter を使用した見栄えの良いデスクトップ GUI フロントエンド。
"""

import os
import re
import sys
import json
import threading
import subprocess
import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog, messagebox

# バックエンドモジュールの読み込み
from yt_downloader import PathSafeDownloader, update_yt_dlp, APP_BASE_DIR

# CustomTkinter テーマ設定
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

CONFIG_FILE_PATH = os.path.join(APP_BASE_DIR, "config.json")

# ANSI エスケープコード除去パターン（進捗文字列のクリーニング用）
_ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*m')

# 選択可能なフォントのリスト
AVAILABLE_FONTS = [
    "Yu Gothic UI",
    "Meiryo",
    "BIZ UDPGothic",
    "Segoe UI",
    "MS Gothic",
]


def _strip_ansi(text: str) -> str:
    """ANSI カラーコードを除去して純粋なテキストを返す"""
    return _ANSI_ESCAPE.sub("", text).strip()


class SafeDownloaderGUI(ctk.CTk):
    PLACEHOLDER_TEXT = "URLを改行区切りで複数並べて入力可能です (例: https://x.com/... / tiktok.com/...)"

    def __init__(self):
        super().__init__()

        self.title("yt-dlp Safe Downloader")
        self.geometry("780x680")
        self.resizable(True, True)

        self.is_placeholder_active = False

        # 設定ファイルの読み込み
        self.config = self._load_config()
        self.output_dir          = self.config.get("output_dir", os.path.abspath("./downloads"))
        self.current_font_family = self.config.get("font_family", "Yu Gothic UI")

        self._create_widgets()
        self._apply_font_family(self.current_font_family)

        # ウインドウ閉じるイベントのフック
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        # 起動時にバックグラウンドで yt-dlp の自動更新チェックを実行
        threading.Thread(target=self._auto_update_worker, daemon=True).start()

    # ------------------------------------------------------------------ #
    #  設定管理                                                            #
    # ------------------------------------------------------------------ #

    def _load_config(self) -> dict:
        """設定ファイル (config.json) から前回の保存先ディレクトリ等を読み込み"""
        if os.path.exists(CONFIG_FILE_PATH):
            try:
                with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                # 古い硬いフォーマット指定が残っている場合は最新の柔軟な指定に更新
                old_fmt = cfg.get("format_spec", "")
                if "bestvideo[ext=mp4]" in old_fmt or not old_fmt:
                    cfg["format_spec"] = PathSafeDownloader.DEFAULT_FORMAT_SPEC
                if "download_playlist" not in cfg:
                    cfg["download_playlist"] = False
                return cfg
            except Exception as e:
                print(f"設定ファイルの読み込み失敗: {e}")
        return {"output_dir": os.path.abspath("./downloads"), "font_family": "Yu Gothic UI"}

    def _save_config(self):
        """現在の設定 (保存先ディレクトリ、オプション、フォント等) を config.json へ保存"""
        config_data = {
            "output_dir":          self.dir_entry.get().strip(),
            "max_path_bytes":      self.max_bytes_entry.get().strip(),
            "format_spec":         self.format_entry.get().strip(),
            "use_firefox_cookies": self.firefox_cookie_var.get(),
            "embed_thumbnail":     self.embed_thumb_var.get(),
            "download_playlist":   self.playlist_var.get(),
            "font_family":         self.font_option_menu.get(),
        }
        try:
            with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"設定ファイルの保存失敗: {e}")

    def _on_closing(self):
        """アプリ終了時の設定保存処理"""
        self._save_config()
        self.destroy()

    # ------------------------------------------------------------------ #
    #  UI 構築                                                             #
    # ------------------------------------------------------------------ #

    def _create_widgets(self):
        # メインフレーム
        self.main_frame = ctk.CTkFrame(self, corner_radius=10)
        self.main_frame.pack(padx=20, pady=20, fill="both", expand=True)

        # タイトル
        self.title_label = ctk.CTkLabel(
            self.main_frame,
            text="yt-dlp Safe Downloader",
            font=ctk.CTkFont(family=self.current_font_family, size=20, weight="bold"),
        )
        self.title_label.pack(pady=(15, 10))

        # 1. 複数URL入力エリア
        url_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        url_frame.pack(padx=20, pady=5, fill="x")

        self.url_label = ctk.CTkLabel(
            url_frame,
            text="動画 URL (改行で複数並べて入力できます):",
            font=ctk.CTkFont(family=self.current_font_family, weight="bold"),
        )
        self.url_label.pack(anchor="w")

        self.url_textbox = ctk.CTkTextbox(
            url_frame, height=90,
            font=ctk.CTkFont(family=self.current_font_family, size=12),
        )
        self.url_textbox.pack(pady=5, fill="x")

        self._show_placeholder()
        self.url_textbox.bind("<FocusIn>",  self._on_focus_in)
        self.url_textbox.bind("<FocusOut>", self._on_focus_out)
        self.url_textbox._textbox.bind("<<Paste>>", self._on_paste)
        self.url_textbox._textbox.bind("<Control-v>", self._on_paste)
        self._add_context_menu(self.url_textbox)

        # 2. 保存先フォルダ設定エリア
        dir_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        dir_frame.pack(padx=20, pady=5, fill="x")

        self.dir_label = ctk.CTkLabel(
            dir_frame, text="保存先フォルダ:",
            font=ctk.CTkFont(family=self.current_font_family, weight="bold"),
        )
        self.dir_label.pack(anchor="w")

        dir_input_frame = ctk.CTkFrame(dir_frame, fg_color="transparent")
        dir_input_frame.pack(fill="x", pady=2)

        self.dir_entry = ctk.CTkEntry(
            dir_input_frame,
            font=ctk.CTkFont(family=self.current_font_family, size=12),
        )
        self.dir_entry.insert(0, self.output_dir)
        self.dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self._add_context_menu(self.dir_entry)

        self.dir_browse_btn = ctk.CTkButton(
            dir_input_frame, text="参照...", width=80,
            font=ctk.CTkFont(family=self.current_font_family, size=12),
            command=self._browse_dir,
        )
        self.dir_browse_btn.pack(side="right")

        # 3. オプション設定エリア
        opts_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        opts_frame.pack(padx=20, pady=5, fill="x")

        playlist_frame = ctk.CTkFrame(opts_frame, fg_color="transparent")
        playlist_frame.pack(fill="x", pady=2)

        self.playlist_var = ctk.BooleanVar(value=self.config.get("download_playlist", False))
        self.playlist_cb = ctk.CTkCheckBox(
            playlist_frame,
            text="プレイリストの全動画をDLする（OFFは単体DL）",
            variable=self.playlist_var,
            font=ctk.CTkFont(family=self.current_font_family, size=12),
        )
        self.playlist_cb.pack(side="left")

        cb_frame = ctk.CTkFrame(opts_frame, fg_color="transparent")
        cb_frame.pack(fill="x", pady=2)

        self.firefox_cookie_var = ctk.BooleanVar(value=self.config.get("use_firefox_cookies", True))
        self.firefox_cookie_cb = ctk.CTkCheckBox(
            cb_frame,
            text="Firefox クッキーを使用 (--cookies-from-browser firefox)",
            font=ctk.CTkFont(family=self.current_font_family, size=12),
            variable=self.firefox_cookie_var,
        )
        self.firefox_cookie_cb.pack(side="left", padx=(0, 15))

        self.embed_thumb_var = ctk.BooleanVar(value=self.config.get("embed_thumbnail", True))
        self.embed_thumb_cb = ctk.CTkCheckBox(
            cb_frame,
            text="サムネイルを埋め込む (--embed-thumbnail)",
            font=ctk.CTkFont(family=self.current_font_family, size=12),
            variable=self.embed_thumb_var,
        )
        self.embed_thumb_cb.pack(side="left")

        # フォーマット指定・最大バイト数・フォント切替
        fmt_frame = ctk.CTkFrame(opts_frame, fg_color="transparent")
        fmt_frame.pack(fill="x", pady=3)

        self.fmt_label = ctk.CTkLabel(
            fmt_frame, text="画質・フォーマット:",
            font=ctk.CTkFont(family=self.current_font_family, size=12),
        )
        self.fmt_label.pack(side="left", padx=(0, 5))

        saved_fmt = self.config.get("format_spec", PathSafeDownloader.DEFAULT_FORMAT_SPEC)
        if "bestvideo[ext=mp4]" in saved_fmt or not saved_fmt:
            saved_fmt = PathSafeDownloader.DEFAULT_FORMAT_SPEC

        self.format_entry = ctk.CTkEntry(
            fmt_frame, font=ctk.CTkFont(family=self.current_font_family, size=12),
        )
        self.format_entry.insert(0, saved_fmt)
        self.format_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self._add_context_menu(self.format_entry)

        self.max_bytes_label = ctk.CTkLabel(
            fmt_frame, text="最大パスバイト:",
            font=ctk.CTkFont(family=self.current_font_family, size=12),
        )
        self.max_bytes_label.pack(side="left", padx=(0, 5))

        saved_max_bytes = str(self.config.get("max_path_bytes", "240"))
        self.max_bytes_entry = ctk.CTkEntry(
            fmt_frame, width=50,
            font=ctk.CTkFont(family=self.current_font_family, size=12),
        )
        self.max_bytes_entry.insert(0, saved_max_bytes)
        self.max_bytes_entry.pack(side="left", padx=(0, 10))
        self._add_context_menu(self.max_bytes_entry)

        self.font_label = ctk.CTkLabel(
            fmt_frame, text="フォント:",
            font=ctk.CTkFont(family=self.current_font_family, size=12),
        )
        self.font_label.pack(side="left", padx=(0, 5))

        self.font_option_menu = ctk.CTkOptionMenu(
            fmt_frame,
            values=AVAILABLE_FONTS,
            width=130,
            font=ctk.CTkFont(family=self.current_font_family, size=12),
            command=self._on_font_selected,
        )
        self.font_option_menu.set(self.current_font_family)
        self.font_option_menu.pack(side="left")

        # 4. ボタンエリア
        btn_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        btn_frame.pack(padx=20, pady=10, fill="x")

        self.preview_btn = ctk.CTkButton(
            btn_frame, text="事前プレビュー (確認)",
            fg_color="#3B82F6", hover_color="#2563EB",
            font=ctk.CTkFont(family=self.current_font_family, size=13, weight="bold"),
            command=self.start_preview,
        )
        self.preview_btn.pack(side="left", padx=5, expand=True, fill="x")

        self.download_btn = ctk.CTkButton(
            btn_frame, text="一括ダウンロード開始",
            fg_color="#10B981", hover_color="#059669",
            font=ctk.CTkFont(family=self.current_font_family, size=13, weight="bold"),
            command=self.start_download,
        )
        self.download_btn.pack(side="right", padx=5, expand=True, fill="x")

        # 5. 情報プレビュー表示エリア
        self.info_box = ctk.CTkTextbox(
            self.main_frame, height=130,
            font=ctk.CTkFont(family=self.current_font_family, size=12),
        )
        self.info_box.pack(padx=20, pady=5, fill="both", expand=True)
        self.info_box.insert(
            "1.0",
            "【機能概要】\n"
            "・起動時に yt-dlp の最新版への自動アップデートチェックを実施\n"
            "・改行区切りで複数URLをまとめて一括順次ダウンロード可能\n"
            "・フォント切替や前回の保存先・設定を自動記憶",
        )
        self.info_box.configure(state="disabled")

        # 6. 進捗表示
        progress_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        progress_frame.pack(padx=20, pady=(5, 15), fill="x")

        self.status_label = ctk.CTkLabel(
            progress_frame, text="yt-dlp の更新チェック中...",
            font=ctk.CTkFont(family=self.current_font_family, size=12),
            anchor="w",
        )
        self.status_label.pack(fill="x", pady=2)

        self.progress_bar = ctk.CTkProgressBar(progress_frame)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", pady=2)

    # ------------------------------------------------------------------ #
    #  右クリックコンテキストメニュー                                      #
    # ------------------------------------------------------------------ #

    def _add_context_menu(self, widget):
        """右クリックメニュー (切り取り/コピー/貼り付け/すべて選択) を追加"""
        menu = tk.Menu(widget, tearoff=0, font=("Yu Gothic UI", 10))

        # CustomTkinter は内部に標準 Tkinter ウィジェットを持つためそちらに直接バインド
        if hasattr(widget, "_textbox"):
            inner = widget._textbox
        elif hasattr(widget, "_entry"):
            inner = widget._entry
        else:
            inner = widget

        menu.add_command(label="切り取り",    command=lambda: inner.event_generate("<<Cut>>"))
        menu.add_command(label="コピー",      command=lambda: inner.event_generate("<<Copy>>"))
        menu.add_command(label="貼り付け",    command=lambda: inner.event_generate("<<Paste>>"))
        menu.add_separator()
        menu.add_command(label="すべて選択",  command=lambda: inner.event_generate("<<SelectAll>>"))

        def show_menu(event):
            try:
                if widget.cget("state") != "disabled":
                    menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        widget.bind("<Button-3>", show_menu)
        inner.bind("<Button-3>",  show_menu)

    # ------------------------------------------------------------------ #
    #  フォント一括適用                                                    #
    # ------------------------------------------------------------------ #

    def _on_font_selected(self, selected_font: str):
        """フォント選択ドロップダウン変更時のイベント"""
        self.current_font_family = selected_font
        self._apply_font_family(selected_font)
        self._save_config()

    def _apply_font_family(self, font_family: str):
        """指定されたフォントファミリを全ウィジェットへ即時適用"""
        try:
            bold   = ctk.CTkFont(family=font_family, weight="bold")
            normal = ctk.CTkFont(family=font_family, size=12)
            large  = ctk.CTkFont(family=font_family, size=20, weight="bold")
            btn    = ctk.CTkFont(family=font_family, size=13, weight="bold")

            widget_fonts = [
                (self.title_label,        large),
                (self.url_label,          bold),
                (self.url_textbox,        normal),
                (self.dir_label,          bold),
                (self.dir_entry,          normal),
                (self.dir_browse_btn,     normal),
                (self.firefox_cookie_cb,  normal),
                (self.embed_thumb_cb,     normal),
                (self.fmt_label,          normal),
                (self.format_entry,       normal),
                (self.max_bytes_label,    normal),
                (self.max_bytes_entry,    normal),
                (self.font_label,         normal),
                (self.font_option_menu,   normal),
                (self.preview_btn,        btn),
                (self.download_btn,       btn),
                (self.info_box,           normal),
                (self.status_label,       normal),
            ]
            for widget, font in widget_fonts:
                widget.configure(font=font)
        except Exception as e:
            print(f"フォント適用中の例外: {e}")

    # ------------------------------------------------------------------ #
    #  プレースホルダー制御                                                #
    # ------------------------------------------------------------------ #

    def _show_placeholder(self):
        """グレーの案内テキストを表示"""
        self.url_textbox.configure(text_color="gray")
        self.url_textbox.delete("1.0", "end")
        self.url_textbox.insert("1.0", self.PLACEHOLDER_TEXT)
        self.is_placeholder_active = True

    def _hide_placeholder(self):
        """プレースホルダーを消去して通常入力モードに切り替え"""
        if self.is_placeholder_active:
            self.url_textbox.delete("1.0", "end")
            self.url_textbox.configure(text_color=("black", "white"))
            self.is_placeholder_active = False

    def _on_focus_in(self, event=None):
        if self.is_placeholder_active:
            self._hide_placeholder()

    def _on_focus_out(self, event=None):
        if not self.url_textbox.get("1.0", "end").strip():
            self._show_placeholder()

    def _on_paste(self, event=None):
        """URL入力欄へのペースト時、自動で改行を挿入する"""
        try:
            clipboard = self.url_textbox.clipboard_get()
            if clipboard:
                if self.is_placeholder_active:
                    self._hide_placeholder()
                
                text_to_insert = clipboard.strip()
                if text_to_insert:
                    self.url_textbox.insert("insert", text_to_insert + "\n")
                    self.url_textbox.see("insert")
                
                return "break"  # デフォルトのペースト処理をキャンセル
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    #  入力・UI ユーティリティ                                             #
    # ------------------------------------------------------------------ #

    def _get_input_urls(self) -> list:
        """入力された有効な URL リストを抽出（http/https 始まりのみ受け付ける）"""
        if self.is_placeholder_active:
            return []
        raw_text = self.url_textbox.get("1.0", "end")
        urls = []
        for line in raw_text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and (line.startswith("http://") or line.startswith("https://")):
                urls.append(line)
        return urls

    def _browse_dir(self):
        selected = filedialog.askdirectory(initialdir=self.dir_entry.get())
        if selected:
            self.dir_entry.delete(0, "end")
            self.dir_entry.insert(0, selected)
            self._save_config()

    def _log_info(self, text: str, clear: bool = False):
        self.info_box.configure(state="normal")
        if clear:
            self.info_box.delete("1.0", "end")
        self.info_box.insert("end", text + "\n")
        self.info_box.see("end")
        self.info_box.configure(state="disabled")

    def _clear_url_textbox(self):
        """URL入力エリアのクリアとプレースホルダー再表示"""
        self.url_textbox.configure(state="normal")
        self._show_placeholder()

    def _on_cancel_clicked(self):
        """キャンセルボタンが押された時の処理"""
        if hasattr(self, 'downloader') and self.downloader:
            self.downloader.cancel_download()
            self.download_btn.configure(text="キャンセル処理中...", state="disabled")
            self._log_info("\n[キャンセル] ユーザーにより停止信号が送信されました。処理が中断されるまで数秒お待ちください...\n")

    def _set_ui_state(self, state: str):
        """処理中の UI 要素の有効化 / 無効化制御"""
        for widget in (
            self.url_textbox, self.dir_entry, self.dir_browse_btn,
            self.firefox_cookie_cb, self.embed_thumb_cb, self.playlist_cb,
            self.format_entry, self.max_bytes_entry,
            self.font_option_menu, self.preview_btn,
        ):
            widget.configure(state=state)

        if state == "disabled":
            # ダウンロード中: 開始ボタンを停止ボタンに変更
            self.download_btn.configure(
                text="■停止",
                fg_color="#c0392b",
                hover_color="#e74c3c",
                command=self._on_cancel_clicked,
                state="normal"  # ボタン自体は押せる状態を維持
            )
        else:
            # 完了後: 元のボタンに戻す
            # ThemeManager のデフォルトまたは適当な青系色に戻す
            self.download_btn.configure(
                text="一括ダウンロード開始",
                fg_color="#10B981",
                hover_color="#059669",
                command=self.start_download,
                state="normal"
            )

    def _get_downloader(self) -> PathSafeDownloader:
        """現在の UI 設定から PathSafeDownloader インスタンスを生成"""
        out_dir = self.dir_entry.get().strip() or "./downloads"
        try:
            max_b = int(self.max_bytes_entry.get().strip())
        except ValueError:
            max_b = 240
        fmt = self.format_entry.get().strip() or PathSafeDownloader.DEFAULT_FORMAT_SPEC

        return PathSafeDownloader(
            output_dir=out_dir,
            max_path_bytes=max_b,
            title_ratio=0.7,
            use_firefox_cookies=self.firefox_cookie_var.get(),
            format_spec=fmt,
            embed_thumbnail=self.embed_thumb_var.get(),
            download_playlist=self.playlist_var.get(),
        )

    # ------------------------------------------------------------------ #
    #  起動時自動更新                                                      #
    # ------------------------------------------------------------------ #

    def _auto_update_worker(self):
        """起動時の yt-dlp 自動アップデートチェック"""
        def update_status(msg: str):
            self.after(0, lambda: self.status_label.configure(text=msg))
        update_yt_dlp(status_callback=update_status)

    # ------------------------------------------------------------------ #
    #  プレビュー                                                          #
    # ------------------------------------------------------------------ #

    def start_preview(self):
        urls = self._get_input_urls()
        if not urls:
            messagebox.showwarning("警告", "有効な動画URL (http/https) が入力されていません。")
            return

        self._save_config()
        self._set_ui_state("disabled")
        self.status_label.configure(text="事前プレビュー取得中...")
        self.progress_bar.set(0)
        threading.Thread(target=self._preview_worker, args=(urls,), daemon=True).start()

    def _preview_worker(self, urls: list):
        try:
            downloader = self._get_downloader()
            self.after(0, lambda: self._log_info("--- 事前確認プレビュー ---", clear=True))
            total = len(urls)

            for idx, url in enumerate(urls, 1):
                self.after(0, lambda i=idx, t=total: self.status_label.configure(
                    text=f"[{i}/{t}件目] メタデータ取得中..."
                ))
                try:
                    info        = downloader.fetch_info(url)
                    upload_date = info.get("upload_date") or ""
                    video_id    = info.get("id") or ""
                    site_name   = downloader.detect_site_name(info, url)
                    uploader    = downloader.extract_clean_uploader(info, url)
                    title       = downloader.extract_clean_title(info, url)

                    safe_name, safe_path = downloader.generate_safe_filename(
                        title=title, uploader=uploader, upload_date=upload_date,
                        site_name=site_name, video_id=video_id, ext="mp4",
                    )
                    path_bytes = len(safe_path.encode("utf-8"))

                    msg = (
                        f"[{idx}/{total}] サイト: {site_name or '(なし)'} | 日付: {upload_date or '本日'}\n"
                        f"  アカウント: {uploader}\n"
                        f"  タイトル  : {title}\n"
                        f"  出力ファイル名: {safe_name} ({path_bytes}B)\n"
                    )
                    self.after(0, lambda m=msg: self._log_info(m))
                except Exception as e:
                    self.after(0, lambda i=idx, u=url, err=e: self._log_info(
                        f"[{i}/{total}] 取得失敗: {u}\n  エラー: {err}\n"
                    ))

            self.after(0, lambda: self.status_label.configure(text="プレビュー完了"))
        except Exception as e:
            self.after(0, lambda: self._log_info(f"プレビュー中に致命的エラー: {e}"))
            self.after(0, lambda: self.status_label.configure(text="プレビュー失敗"))
        finally:
            self.after(0, lambda: self._set_ui_state("normal"))

    # ------------------------------------------------------------------ #
    #  ダウンロード                                                        #
    # ------------------------------------------------------------------ #

    def start_download(self):
        urls = self._get_input_urls()
        if not urls:
            messagebox.showwarning("警告", "有効な動画URL (http/https) が入力されていません。")
            return

        self._save_config()
        self._set_ui_state("disabled")
        self.status_label.configure(text="一括ダウンロード準備中...")
        self.progress_bar.set(0)
        threading.Thread(target=self._download_worker, args=(urls,), daemon=True).start()

    def _make_progress_hook(self, current_idx: int, total_count: int):
        def progress_hook(d):
            if d["status"] == "downloading":
                downloaded = d.get("downloaded_bytes", 0)
                total      = d.get("total_bytes") or d.get("total_bytes_estimate", 1)
                single_ratio  = min(1.0, max(0.0, downloaded / total))
                overall_ratio = ((current_idx - 1) + single_ratio) / total_count

                percent_str = _strip_ansi(d.get("_percent_str", ""))
                speed_str   = _strip_ansi(d.get("_speed_str", ""))
                eta_str     = _strip_ansi(d.get("_eta_str", ""))

                status_text = f"[{current_idx}/{total_count}件目] {percent_str} | 速度: {speed_str} | 残り: {eta_str}"
                self.after(0, lambda: self.progress_bar.set(overall_ratio))
                self.after(0, lambda: self.status_label.configure(text=status_text))

            elif d["status"] == "finished":
                self.after(0, lambda: self.status_label.configure(
                    text=f"[{current_idx}/{total_count}件目] MP4結合・処理中..."
                ))

        return progress_hook

    def _download_worker(self, urls: list):
        success_count = 0
        fail_count    = 0
        total_count   = len(urls)

        self.after(0, lambda: self._log_info(f"=== 一括ダウンロード開始 (全{total_count}件) ===", clear=True))
        self.downloader = self._get_downloader()

        for idx, url in enumerate(urls, 1):
            self.after(0, lambda i=idx, t=total_count: self.status_label.configure(
                text=f"[{i}/{t}件目] 処理準備中..."
            ))
            try:
                hook       = self._make_progress_hook(idx, total_count)
                saved_results = self.downloader.download(url, progress_hook=hook)
                for saved_path, _ in saved_results:
                    success_count += 1
                    msg = f"[{idx}/{total_count}] 成功: {os.path.basename(saved_path)}\n"
                    self.after(0, lambda m=msg: self._log_info(m))
            except Exception as e:
                fail_count += 1
                msg = f"[{idx}/{total_count}] 失敗: {url}\n  エラー内容: {e}\n"
                self.after(0, lambda m=msg: self._log_info(m))

        # UI 復帰
        self.after(0, lambda: self._set_ui_state("normal"))

        # 成功件数があれば URL 欄をクリア
        if success_count > 0:
            self.after(0, self._clear_url_textbox)

        summary_msg = (
            f"\n=== 一括ダウンロード完了 ===\n"
            f"成功: {success_count} 件 / 失敗: {fail_count} 件 / 合計: {total_count} 件"
        )
        self.after(0, lambda: self._log_info(summary_msg))
        self.after(0, lambda: self.progress_bar.set(1.0))
        self.after(0, lambda: self.status_label.configure(
            text=f"全処理完了 (成功: {success_count} / 失敗: {fail_count})"
        ))
        self.after(0, lambda: messagebox.showinfo(
            "一括完了",
            f"ダウンロード処理が完了しました！\n\n成功: {success_count} 件\n失敗: {fail_count} 件",
        ))


if __name__ == "__main__":
    app = SafeDownloaderGUI()
    app.mainloop()
