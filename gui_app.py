"""
yt-dlp Safe Downloader GUI Application
CustomTkinter を使用した見栄えの良いデスクトップ GUI フロントエンド。
起動時 yt-dlp 自動更新チェック機能付き。
"""

import os
import sys
import json
import threading
import subprocess
import customtkinter as ctk
from tkinter import filedialog, messagebox

# バックエンドモジュールの読み込み
from yt_downloader import PathSafeDownloader, update_yt_dlp, APP_BASE_DIR

# CustomTkinter テーマ設定
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

CONFIG_FILE_PATH = os.path.join(APP_BASE_DIR, "config.json")


class SafeDownloaderGUI(ctk.CTk):
    PLACEHOLDER_TEXT = "URLを改行区切りで複数並べて入力可能です (例: https://x.com/... / tiktok.com/...)"

    def __init__(self):
        super().__init__()

        self.title("yt-dlp Safe Downloader")
        self.geometry("760x660")
        self.resizable(True, True)

        self.is_placeholder_active = False

        # 設定ファイルの読み込み
        self.config = self._load_config()
        self.output_dir = self.config.get("output_dir", os.path.abspath("./downloads"))

        self.downloader = PathSafeDownloader(output_dir=self.output_dir)

        self._create_widgets()

        # ウインドウ閉じるイベントの保存フック
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        # 起動時にバックグラウンドで yt-dlp の自動更新チェックを実行
        threading.Thread(target=self._auto_update_worker, daemon=True).start()

    def _auto_update_worker(self):
        """起動時の yt-dlp 自動アップデートチェック"""
        def update_status(msg: str):
            self.after(0, lambda: self.status_label.configure(text=msg))

        update_yt_dlp(status_callback=update_status)

    def _load_config(self) -> dict:
        """設定ファイル (config.json) から前回の保存先ディレクトリ等を読み込み"""
        if os.path.exists(CONFIG_FILE_PATH):
            try:
                with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"設定ファイルの読み込み失敗: {e}")
        return {"output_dir": os.path.abspath("./downloads")}

    def _save_config(self):
        """現在の設定 (保存先ディレクトリ、オプション等) を config.json へ保存"""
        out_dir = self.dir_entry.get().strip() if hasattr(self, 'dir_entry') else self.output_dir
        max_bytes = self.max_bytes_entry.get().strip() if hasattr(self, 'max_bytes_entry') else "240"
        fmt = self.format_entry.get().strip() if hasattr(self, 'format_entry') else PathSafeDownloader.DEFAULT_FORMAT_SPEC
        ff_cookie = self.firefox_cookie_var.get() if hasattr(self, 'firefox_cookie_var') else True
        thumb = self.embed_thumb_var.get() if hasattr(self, 'embed_thumb_var') else True

        config_data = {
            "output_dir": out_dir,
            "max_path_bytes": max_bytes,
            "format_spec": fmt,
            "use_firefox_cookies": ff_cookie,
            "embed_thumbnail": thumb,
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

    def _create_widgets(self):
        # メインフレーム
        self.main_frame = ctk.CTkFrame(self, corner_radius=10)
        self.main_frame.pack(padx=20, pady=20, fill="both", expand=True)

        # タイトル
        self.title_label = ctk.CTkLabel(
            self.main_frame,
            text="yt-dlp Safe Downloader",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        self.title_label.pack(pady=(15, 10))

        # 1. 複数URL入力エリア
        url_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        url_frame.pack(padx=20, pady=5, fill="x")

        ctk.CTkLabel(
            url_frame,
            text="動画 URL (改行で複数並べて入力できます):",
            font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w")

        self.url_textbox = ctk.CTkTextbox(url_frame, height=90, font=ctk.CTkFont(size=12))
        self.url_textbox.pack(pady=5, fill="x")

        # プレースホルダーのバインド設定
        self._show_placeholder()
        self.url_textbox.bind("<FocusIn>", self._on_focus_in)
        self.url_textbox.bind("<FocusOut>", self._on_focus_out)

        # 2. 保存先フォルダ設定エリア
        dir_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        dir_frame.pack(padx=20, pady=5, fill="x")

        ctk.CTkLabel(dir_frame, text="保存先フォルダ:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")

        dir_input_frame = ctk.CTkFrame(dir_frame, fg_color="transparent")
        dir_input_frame.pack(fill="x", pady=2)

        self.dir_entry = ctk.CTkEntry(dir_input_frame)
        self.dir_entry.insert(0, self.output_dir)
        self.dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.dir_browse_btn = ctk.CTkButton(dir_input_frame, text="参照...", width=80, command=self._browse_dir)
        self.dir_browse_btn.pack(side="right")

        # 3. オプション設定エリア
        opts_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        opts_frame.pack(padx=20, pady=5, fill="x")

        cb_frame = ctk.CTkFrame(opts_frame, fg_color="transparent")
        cb_frame.pack(fill="x", pady=2)

        saved_ff_cookie = self.config.get("use_firefox_cookies", True)
        self.firefox_cookie_var = ctk.BooleanVar(value=saved_ff_cookie)
        self.firefox_cookie_cb = ctk.CTkCheckBox(
            cb_frame, text="Firefox クッキーを使用 (--cookies-from-browser firefox)",
            variable=self.firefox_cookie_var
        )
        self.firefox_cookie_cb.pack(side="left", padx=(0, 15))

        saved_embed_thumb = self.config.get("embed_thumbnail", True)
        self.embed_thumb_var = ctk.BooleanVar(value=saved_embed_thumb)
        self.embed_thumb_cb = ctk.CTkCheckBox(
            cb_frame, text="サムネイルを埋め込む (--embed-thumbnail)",
            variable=self.embed_thumb_var
        )
        self.embed_thumb_cb.pack(side="left")

        # フォーマット指定＆最大バイト数
        fmt_frame = ctk.CTkFrame(opts_frame, fg_color="transparent")
        fmt_frame.pack(fill="x", pady=3)

        ctk.CTkLabel(fmt_frame, text="画質・フォーマット:").pack(side="left", padx=(0, 5))
        self.format_entry = ctk.CTkEntry(fmt_frame)
        saved_fmt = self.config.get("format_spec", PathSafeDownloader.DEFAULT_FORMAT_SPEC)
        self.format_entry.insert(0, saved_fmt)
        self.format_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        ctk.CTkLabel(fmt_frame, text="最大パスバイト:").pack(side="left", padx=(0, 5))
        self.max_bytes_entry = ctk.CTkEntry(fmt_frame, width=60)
        saved_max_bytes = str(self.config.get("max_path_bytes", "240"))
        self.max_bytes_entry.insert(0, saved_max_bytes)
        self.max_bytes_entry.pack(side="left")

        # 4. ボタンエリア
        btn_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        btn_frame.pack(padx=20, pady=10, fill="x")

        self.preview_btn = ctk.CTkButton(
            btn_frame, text="事前プレビュー (確認)",
            fg_color="#3B82F6", hover_color="#2563EB",
            command=self.start_preview
        )
        self.preview_btn.pack(side="left", padx=5, expand=True, fill="x")

        self.download_btn = ctk.CTkButton(
            btn_frame, text="一括ダウンロード開始",
            fg_color="#10B981", hover_color="#059669",
            command=self.start_download
        )
        self.download_btn.pack(side="right", padx=5, expand=True, fill="x")

        # 5. 情報プレビュー表示エリア
        self.info_box = ctk.CTkTextbox(self.main_frame, height=130, font=ctk.CTkFont(family="Consolas", size=12))
        self.info_box.pack(padx=20, pady=5, fill="both", expand=True)
        self.info_box.insert("1.0", "【機能概要】\n・起動時に yt-dlp の最新版への自動アップデートチェックを実施\n・改行区切りで複数URLをまとめて一括順次ダウンロード可能\n・前回使用した保存先フォルダや設定を自動記憶・復元")
        self.info_box.configure(state="disabled")

        # 6. 進捗表示
        progress_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        progress_frame.pack(padx=20, pady=(5, 15), fill="x")

        self.status_label = ctk.CTkLabel(progress_frame, text="yt-dlp の更新チェック中...", anchor="w")
        self.status_label.pack(fill="x", pady=2)

        self.progress_bar = ctk.CTkProgressBar(progress_frame)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", pady=2)

    # --- プレースホルダー制御 ---
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
        text = self.url_textbox.get("1.0", "end").strip()
        if not text:
            self._show_placeholder()

    def _get_input_urls(self) -> list[str]:
        """入力された有効なURLリストを抽出"""
        if self.is_placeholder_active:
            return []

        raw_text = self.url_textbox.get("1.0", "end")
        urls = []
        for line in raw_text.splitlines():
            line_str = line.strip()
            if line_str and not line_str.startswith("#"):
                urls.append(line_str)
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

    def _set_ui_state(self, state: str):
        """処理中の UI 要素の有効化 / 無効化制御"""
        self.url_textbox.configure(state=state)
        self.dir_entry.configure(state=state)
        self.dir_browse_btn.configure(state=state)
        self.firefox_cookie_cb.configure(state=state)
        self.embed_thumb_cb.configure(state=state)
        self.format_entry.configure(state=state)
        self.max_bytes_entry.configure(state=state)
        self.preview_btn.configure(state=state)
        self.download_btn.configure(state=state)

    def _get_downloader(self) -> PathSafeDownloader:
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
            embed_thumbnail=self.embed_thumb_var.get()
        )

    def start_preview(self):
        urls = self._get_input_urls()
        if not urls:
            messagebox.showwarning("警告", "有効な動画URLが入力されていません。")
            return

        self._save_config()
        self._set_ui_state("disabled")
        self.status_label.configure(text="事前プレビュー取得中...")
        self.progress_bar.set(0)

        threading.Thread(target=self._preview_worker, args=(urls,), daemon=True).start()

    def _preview_worker(self, urls: list[str]):
        try:
            downloader = self._get_downloader()
            self.after(0, lambda: self._log_info("--- 事前確認プレビュー ---", clear=True))

            total = len(urls)
            for idx, url in enumerate(urls, 1):
                self.after(0, lambda i=idx, t=total: self.status_label.configure(text=f"[{i}/{t}件目] メタデータ取得中..."))

                try:
                    info = downloader.fetch_info(url)
                    upload_date = info.get("upload_date") or ""
                    video_id = info.get("id") or ""

                    site_name = downloader.detect_site_name(info, url)
                    uploader = downloader.extract_clean_uploader(info, url)
                    title = downloader.extract_clean_title(info, url)

                    safe_name, safe_path = downloader.generate_safe_filename(
                        title=title, uploader=uploader, upload_date=upload_date,
                        site_name=site_name, video_id=video_id, ext="mp4"
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
                    self.after(0, lambda i=idx, u=url, err=e: self._log_info(f"[{i}/{total}] 取得失敗: {u}\n  エラー: {err}\n"))

            self.after(0, lambda: self.status_label.configure(text="プレビュー完了"))
        except Exception as e:
            self.after(0, lambda: self._log_info(f"プレビュー中に致命的エラー: {e}"))
            self.after(0, lambda: self.status_label.configure(text="プレビュー失敗"))
        finally:
            self.after(0, lambda: self._set_ui_state("normal"))

    def start_download(self):
        urls = self._get_input_urls()
        if not urls:
            messagebox.showwarning("警告", "有効な動画URLが入力されていません。")
            return

        self._save_config()
        self._set_ui_state("disabled")
        self.status_label.configure(text="一括ダウンロード準備中...")
        self.progress_bar.set(0)

        threading.Thread(target=self._download_worker, args=(urls,), daemon=True).start()

    def _make_progress_hook(self, current_idx: int, total_count: int):
        def progress_hook(d):
            if d['status'] == 'downloading':
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 1)
                single_ratio = min(1.0, max(0.0, downloaded / total))

                overall_ratio = ((current_idx - 1) + single_ratio) / total_count

                percent_str = d.get('_percent_str', '').strip()
                speed_str = d.get('_speed_str', '').strip()
                eta_str = d.get('_eta_str', '').strip()

                status_text = f"[{current_idx}/{total_count}件目] {percent_str} | 速度: {speed_str} | 残り: {eta_str}"

                self.after(0, lambda: self.progress_bar.set(overall_ratio))
                self.after(0, lambda: self.status_label.configure(text=status_text))
            elif d['status'] == 'finished':
                self.after(0, lambda: self.status_label.configure(text=f"[{current_idx}/{total_count}件目] MP4結合・処理中..."))
        return progress_hook

    def _download_worker(self, urls: list[str]):
        success_count = 0
        fail_count = 0
        total_count = len(urls)

        self.after(0, lambda: self._log_info(f"=== 一括ダウンロード開始 (全{total_count}件) ===", clear=True))

        downloader = self._get_downloader()

        for idx, url in enumerate(urls, 1):
            self.after(0, lambda i=idx, t=total_count: self.status_label.configure(text=f"[{i}/{t}件目] 処理準備中..."))

            try:
                hook = self._make_progress_hook(idx, total_count)
                saved_path, info = downloader.download(url, progress_hook=hook)
                success_count += 1

                msg = f"[{idx}/{total_count}] 成功: {os.path.basename(saved_path)}\n"
                self.after(0, lambda m=msg: self._log_info(m))
            except Exception as e:
                fail_count += 1
                msg = f"[{idx}/{total_count}] 失敗: {url}\n  エラー内容: {e}\n"
                self.after(0, lambda m=msg: self._log_info(m))

        # 1. UI状態を入力可能に戻す
        self.after(0, lambda: self._set_ui_state("normal"))

        # 2. 完了時にプレースホルダー付きで全消去
        if success_count > 0:
            self.after(0, self._clear_url_textbox)

        # 3. メッセージ表示
        summary_msg = f"\n=== 一括ダウンロード完了 ===\n成功: {success_count} 件 / 失敗: {fail_count} 件 / 合計: {total_count} 件"
        self.after(0, lambda: self._log_info(summary_msg))
        self.after(0, lambda: self.progress_bar.set(1.0))
        self.after(0, lambda: self.status_label.configure(text=f"全処理完了 (成功: {success_count} / 失敗: {fail_count})"))

        self.after(0, lambda: messagebox.showinfo(
            "一括完了",
            f"ダウンロード処理が完了しました！\n\n成功: {success_count} 件\n失敗: {fail_count} 件"
        ))


if __name__ == "__main__":
    app = SafeDownloaderGUI()
    app.mainloop()
