"""
yt-dlp Path-Safe Downloader Module
OS や NAS のパス長制限 (MAX_PATH / UTF-8 バイト数制限) を回避し、
yt-dlp の自動更新機能や各種フォーマット設定に対応したダウンロードモジュール。
"""

import os
import re
import sys
import json
import time
import logging
import subprocess
from datetime import datetime
from typing import Dict, Any, Optional, Callable, Tuple
import yt_dlp

# ロギング設定
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger("PathSafeDownloader")

# アプリ本体のルートディレクトリ
APP_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def update_yt_dlp(status_callback: Optional[Callable[[str], None]] = None) -> bool:
    """
    yt-dlp を最新バージョンに自動更新します。
    TikTok や YouTube 等の各 SNS サイトの仕様変更によるダウンロードエラーを未然に防ぎます。
    """
    try:
        if status_callback:
            status_callback("yt-dlp の更新チェック中...")
        logger.info("yt-dlp の自動更新チェックを開始します...")

        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if "Successfully installed" in result.stdout:
            msg = "yt-dlp を最新バージョンに更新しました！"
            logger.info(msg)
            if status_callback:
                status_callback(msg)
            return True
        else:
            msg = "yt-dlp は最新バージョンです。"
            logger.info(msg)
            if status_callback:
                status_callback(msg)
            return False
    except Exception as e:
        msg = f"yt-dlp の更新チェックをスキップしました: {e}"
        logger.warning(msg)
        if status_callback:
            status_callback("yt-dlp 更新チェック完了 (既存バージョン使用)")
        return False


class PathSafeDownloader:
    """
    パス長制限 (MAX_PATH / UTF-8 バイト数制限) 回避対応 yt-dlp ダウンローダー
    """

    INVALID_CHAR_MAP = {
        '\\': '＿',
        '/': '＿',
        ':': '：',
        '*': '＊',
        '?': '？',
        '"': '”',
        '<': '＜',
        '>': '＞',
        '|': '｜',
    }

    TARGET_SITES = {
        "x.com": ["twitter", "x.com", "x_com"],
        "tiktok": ["tiktok"],
        "instagram": ["instagram"]
    }

    # 標準フォーマット指定 (最高の映像と音声を自動取得しMP4へ無劣化結合)
    DEFAULT_FORMAT_SPEC = "bestvideo+bestaudio/best"

    def __init__(
        self,
        output_dir: str = "./downloads",
        max_path_bytes: int = 240,
        title_ratio: float = 0.7,
        ellipsis: str = "…",
        use_firefox_cookies: bool = True,
        format_spec: Optional[str] = None,
        embed_thumbnail: bool = True,
        history_file_path: Optional[str] = None
    ):
        self.output_dir = os.path.abspath(output_dir)
        self.max_path_bytes = max_path_bytes
        self.title_ratio = max(0.0, min(1.0, title_ratio))
        self.ellipsis = ellipsis
        self.use_firefox_cookies = use_firefox_cookies
        self.format_spec = format_spec or self.DEFAULT_FORMAT_SPEC
        self.embed_thumbnail = embed_thumbnail

        # 保存先ディレクトリの自動準備
        os.makedirs(self.output_dir, exist_ok=True)

        # 履歴ファイルはアプリ本体のフォルダ直下に集約
        if history_file_path:
            self.history_file = os.path.abspath(history_file_path)
        else:
            self.history_file = os.path.join(APP_BASE_DIR, "download_history.json")

        self.history = self._load_history()

    def _load_history(self) -> Dict[str, str]:
        """ダウンロード履歴 (filepath -> video_id) を読み込みます"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"履歴ファイルの読み込みに失敗しました: {e}")
        return {}

    def _save_history(self):
        """ダウンロード履歴を保存します"""
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"履歴ファイルの保存に失敗しました: {e}")

    @classmethod
    def sanitize_filename(cls, text: str) -> str:
        """OS/ファイルシステムで使用不可な文字を除去・置換"""
        if not text:
            return ""

        text = re.sub(r'[\x00-\x1f\x7f]', '', text)

        for bad_char, safe_char in cls.INVALID_CHAR_MAP.items():
            text = text.replace(bad_char, safe_char)

        text = text.strip(" .")

        return text

    def safe_truncate_bytes(self, text: str, max_bytes: int) -> str:
        """UTF-8 バイト数制限以内への安全な切り詰め"""
        text_bytes = text.encode("utf-8")
        if len(text_bytes) <= max_bytes:
            return text

        ellipsis_bytes = self.ellipsis.encode("utf-8")
        limit_bytes = max_bytes - len(ellipsis_bytes)

        if limit_bytes <= 0:
            return self.ellipsis[:max_bytes.decode('utf-8', errors='ignore')] if max_bytes > 0 else ""

        truncated_chars = []
        current_bytes = 0

        for char in text:
            char_bytes = len(char.encode("utf-8"))
            if current_bytes + char_bytes > limit_bytes:
                break
            truncated_chars.append(char)
            current_bytes += char_bytes

        res = "".join(truncated_chars)
        res = res.rstrip(" ._-\t\r\n,;:!?/\\（(【[『「")
        return res + self.ellipsis

    def detect_site_name(self, info: Dict[str, Any], url: str = "") -> str:
        """対象サイト判定 (x.com, tiktok, instagram のみ記載)"""
        extractor = (info.get("extractor") or info.get("extractor_key") or "").lower()
        webpage_url = (info.get("webpage_url") or url).lower()

        for site_label, keywords in self.TARGET_SITES.items():
            for kw in keywords:
                if kw in extractor or kw in webpage_url:
                    return site_label
        return ""

    def extract_clean_uploader(self, info: Dict[str, Any], url: str = "") -> str:
        """
        SNS (X, TikTok, Instagram) および動画サイトからのアカウント名抽出。
        """
        site_name = self.detect_site_name(info, url)
        uploader_id = (info.get("uploader_id") or "").strip()
        uploader = (info.get("uploader") or info.get("channel") or info.get("creator") or "").strip()

        if site_name == "x.com":
            name = uploader or uploader_id or "Unknown"
            name = name.strip().lstrip("@")
            return name or "Unknown"

        elif site_name == "instagram":
            handle = uploader
            if not handle or handle.isdigit():
                handle = info.get("channel") or uploader_id or "Unknown"
            return handle.strip().lstrip("@") or "Unknown"

        elif site_name == "tiktok":
            handle = uploader_id or uploader or "Unknown"
            return handle.strip().lstrip("@") or "Unknown"

        else:
            return uploader or uploader_id or "不明"

    def extract_clean_title(self, info: Dict[str, Any], url: str = "") -> str:
        """
        タイトルの先頭に含まれる重複アカウント名の自動除去、および Instagram の "Video by ○○" 回避。
        """
        site_name = self.detect_site_name(info, url)
        title = (info.get("title") or "").strip()
        description = (info.get("description") or info.get("caption") or "").strip()
        uploader_id = (info.get("uploader_id") or "").strip().lstrip("@")
        uploader = (info.get("uploader") or info.get("channel") or "").strip().lstrip("@")

        if site_name == "instagram" and description:
            text = description
        else:
            if title.lower().startswith(("video by", "reel by")) and description:
                text = description
            else:
                text = title or description or "無題"

        text = re.sub(r'[\r\n]+', ' ', text).strip()

        candidates = [uploader, uploader_id]
        for candidate in candidates:
            if not candidate or len(candidate) < 2:
                continue
            escaped_cand = re.escape(candidate)
            regex = r'^(?:@?' + escaped_cand + r'|.*?\(@?' + escaped_cand + r'\))\s*[:：\-＿]\s*'
            text = re.sub(regex, '', text, flags=re.IGNORECASE).strip()

        if text.lower().startswith(("video by", "reel by", "photo by")):
            text = description or "無題"
            text = re.sub(r'[\r\n]+', ' ', text).strip()

        return text or "無題"

    def generate_safe_filename(
        self,
        title: str,
        uploader: str,
        upload_date: str,
        site_name: str = "",
        video_id: str = "",
        ext: str = "mp4"
    ) -> Tuple[str, str]:
        """TVerRec準拠フォーマットで安全なファイル名・パスを生成"""
        clean_title = self.sanitize_filename(title) or "無題"
        clean_uploader = self.sanitize_filename(uploader) or "不明"
        clean_ext = self.sanitize_filename(ext).lstrip(".") or "mp4"
        clean_site = self.sanitize_filename(site_name)

        clean_date = re.sub(r'\D', '', upload_date) if upload_date else ""
        if len(clean_date) != 8:
            clean_date = datetime.now().strftime("%Y%m%d")

        counter = 0
        while True:
            suffix = f" ({counter})" if counter > 0 else ""

            if clean_site:
                prefix = f"{clean_site} - {clean_date} - "
            else:
                prefix = f"{clean_date} - "

            output_dir_bytes = len(self.output_dir.encode("utf-8"))
            separator_bytes = len(os.sep.encode("utf-8"))

            fixed_parts_str = f"{prefix} - {suffix}.{clean_ext}"
            fixed_bytes = output_dir_bytes + separator_bytes + len(fixed_parts_str.encode("utf-8"))

            available_bytes = self.max_path_bytes - fixed_bytes
            if available_bytes < 10:
                available_bytes = max(10, available_bytes)

            uploader_req_bytes = len(clean_uploader.encode("utf-8"))
            title_req_bytes = len(clean_title.encode("utf-8"))

            raw_title_limit = int(available_bytes * self.title_ratio)
            raw_uploader_limit = available_bytes - raw_title_limit

            if uploader_req_bytes < raw_uploader_limit:
                surplus = raw_uploader_limit - uploader_req_bytes
                final_uploader_limit = uploader_req_bytes
                final_title_limit = raw_title_limit + surplus
            elif title_req_bytes < raw_title_limit:
                surplus = raw_title_limit - title_req_bytes
                final_title_limit = title_req_bytes
                final_uploader_limit = raw_uploader_limit + surplus
            else:
                final_title_limit = raw_title_limit
                final_uploader_limit = raw_uploader_limit

            safe_uploader = self.safe_truncate_bytes(clean_uploader, final_uploader_limit)
            safe_title = self.safe_truncate_bytes(clean_title, final_title_limit)

            safe_filename = f"{prefix}{safe_uploader} - {safe_title}{suffix}.{clean_ext}"
            safe_full_path = os.path.join(self.output_dir, safe_filename)

            if os.path.exists(safe_full_path):
                existing_video_id = self.history.get(safe_full_path)
                if video_id and existing_video_id == video_id:
                    logger.info(f"同一動画の再ダウンロードとして検出されました。上書き保存します: {safe_filename}")
                    break
                else:
                    counter += 1
                    continue
            else:
                break

        return safe_filename, safe_full_path

    def register_download_history(self, full_path: str, video_id: str):
        """ダウンロード履歴記録"""
        if full_path and video_id:
            self.history[full_path] = video_id
            self._save_history()

    def _build_base_ydl_opts(self) -> Dict[str, Any]:
        """基本オプション構築"""
        opts = {
            "format": self.format_spec,
            "merge_output_format": "mp4",
            "nocheckcertificate": True,
            "remote_components": ["ejs:github"],
            "retries": 15,
            "fragment_retries": 15,
            "file_access_retries": 15,
            "http_chunk_size": 10485760, # 10MB単位で取得し、Bilibili等の切断エラーを防止
        }

        if self.use_firefox_cookies:
            opts["cookiesfrombrowser"] = ("firefox",)

        if self.embed_thumbnail:
            opts["writethumbnails"] = True
            opts["postprocessors"] = [
                {
                    "key": "EmbedThumbnail",
                    "already_have_thumbnail": False,
                }
            ]

        return opts

    def fetch_info(self, url: str, extra_ydl_opts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        動画メタデータの事前取得。
        process=False を指定することで Format 選定エラーを完全に回避。
        """
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": False,
            "nocheckcertificate": True,
            "remote_components": ["ejs:github"],
        }

        if self.use_firefox_cookies:
            ydl_opts["cookiesfrombrowser"] = ("firefox",)

        if extra_ydl_opts:
            ydl_opts.update(extra_ydl_opts)

        logger.info(f"メタデータを取得中: {url}")

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False, process=False)
        except Exception as e:
            if self.use_firefox_cookies and "cookies" in str(e).lower():
                logger.warning("Firefoxのクッキー取得に失敗しました。クッキーなしで再試行します...")
                ydl_opts.pop("cookiesfrombrowser", None)
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False, process=False)
            else:
                raise e

        if info is None:
            raise ValueError("動画情報の取得に失敗しました。")

        if "entries" in info and len(info["entries"]) > 0:
            info = info["entries"][0]

        return info

    def download(
        self,
        url: str,
        extra_ydl_opts: Optional[Dict[str, Any]] = None,
        progress_hook: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        事前メタデータ取得 -> 安全なパス計算 -> 指定オプションでの本番ダウンロード
        """
        # 1. 事前メタデータ取得
        info = self.fetch_info(url, extra_ydl_opts)

        upload_date = info.get("upload_date") or ""
        video_id = info.get("id") or ""

        site_name = self.detect_site_name(info, url)
        uploader = self.extract_clean_uploader(info, url)
        title = self.extract_clean_title(info, url)

        # 2. 安全なファイル名の動的計算
        safe_filename, safe_full_path = self.generate_safe_filename(
            title=title,
            uploader=uploader,
            upload_date=upload_date,
            site_name=site_name,
            video_id=video_id,
            ext="mp4"
        )

        logger.info("=== ダウンロード準備完了 ===")
        logger.info(f"  サイト判定   : {site_name or '(記載なし)'}")
        logger.info(f"  投稿日       : {upload_date}")
        logger.info(f"  抽出タイトル : {title}")
        logger.info(f"  抽出アカウント : {uploader}")
        logger.info(f"  生成ファイル : {safe_filename}")
        logger.info(f"  パスバイト長 : {len(safe_full_path.encode('utf-8'))} bytes (上限: {self.max_path_bytes} bytes)")
        logger.info(f"  履歴ファイル : {self.history_file}")

        # 3. yt-dlp オプションの設定とダウンロード実行
        filename_without_ext, _ = os.path.splitext(safe_filename)
        outtmpl_path = os.path.join(self.output_dir, f"{filename_without_ext}.%(ext)s")

        ydl_opts = self._build_base_ydl_opts()
        ydl_opts.update({
            "outtmpl": outtmpl_path,
            "quiet": False,
            "no_warnings": False,
        })

        if progress_hook:
            ydl_opts["progress_hooks"] = [progress_hook]

        if extra_ydl_opts:
            ydl_opts.update(extra_ydl_opts)

        logger.info("本番ダウンロードを開始します...")
        
        max_resume_retries = 5
        resume_count = 0
        
        while True:
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                break  # 成功したらループを抜ける
            except Exception as e:
                err_str = str(e)
                
                # 1. ネットワーク切断による中断エラーの検知 (Bilibili等で発生)
                if ("bytes read" in err_str and "more expected" in err_str) or "IncompleteRead" in err_str or "Connection reset" in err_str or "10054" in err_str or "タイムアウト" in err_str:
                    if resume_count < max_resume_retries:
                        resume_count += 1
                        logger.warning(f"ネットワーク切断を検知しました。自動レジューム(再開)を試みます... ({resume_count}/{max_resume_retries})")
                        time.sleep(3)
                        continue
                    else:
                        raise ValueError(f"ネットワーク切断が多発したためダウンロードを中断しました。({max_resume_retries}回再試行失敗)")
                
                # 2. クッキーによる YouTube ブロック検知時の自動フォールバック
                if self.use_firefox_cookies and "cookiesfrombrowser" in ydl_opts and ("format is not available" in err_str or "cookies" in err_str.lower() or "images are available" in err_str.lower()):
                    logger.warning("クッキーによるブロックまたはフォーマットエラーを検出しました。クッキーなしで再試行します...")
                    ydl_opts.pop("cookiesfrombrowser", None)
                    ydl_opts["format"] = "bestvideo+bestaudio/best"
                    continue  # クッキーなしの ydl_opts でリトライ
                
                # 3. フォールバック(クッキーなし)で LOGIN_REQUIRED になった場合の親切なエラーメッセージ
                if "video is not available" in err_str or "LOGIN_REQUIRED" in err_str or "Sign in" in err_str:
                    if self.use_firefox_cookies and "cookiesfrombrowser" not in ydl_opts:
                        logger.error("【エラー】この動画は年齢制限やメンバーシップ等のためログイン(クッキー)が必須ですが、YouTubeのbot対策によりクッキーを使用できませんでした。Node.jsまたはDenoをPCにインストールすると解決する可能性があります。")
                        raise ValueError("動画のダウンロードにログインが必須ですが、bot対策によりブロックされました。Node.jsまたはDenoをインストールして再度お試しください。")
                
                raise e

        # 4. 履歴登録
        self.register_download_history(safe_full_path, video_id)

        logger.info(f"ダウンロード完了: {safe_full_path}")
        return safe_full_path, info
