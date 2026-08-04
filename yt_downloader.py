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
from typing import Any, Callable, Dict, Optional, Tuple

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
    def _notify(msg: str) -> None:
        logger.info(msg)
        if status_callback:
            status_callback(msg)

    try:
        _notify("yt-dlp の更新チェック中...")
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if "Successfully installed" in result.stdout:
            _notify("yt-dlp を最新バージョンに更新しました！")
            return True
        else:
            _notify("yt-dlp は最新バージョンです。")
            return False

    except Exception as e:
        logger.warning(f"yt-dlp の更新チェックをスキップしました: {e}")
        if status_callback:
            status_callback("yt-dlp 更新チェック完了 (既存バージョン使用)")
        return False


class PathSafeDownloader:
    """
    パス長制限 (MAX_PATH / UTF-8 バイト数制限) 回避対応 yt-dlp ダウンローダー
    """

    # OS/ファイルシステムで使用不可な文字の置換マップ
    INVALID_CHAR_MAP: Dict[str, str] = {
        '\\': '＿', '/': '＿', ':': '：', '*': '＊',
        '?': '？', '"': '\u201d', '<': '＜', '>': '＞', '|': '｜',
    }

    # サイト別判定キーワード
    TARGET_SITES: Dict[str, list] = {
        "x.com":     ["twitter", "x.com", "x_com"],
        "tiktok":    ["tiktok"],
        "instagram": ["instagram"],
    }

    # ネットワーク切断エラーの検知文字列
    _NETWORK_DROP_PATTERNS = (
        "bytes read",
        "IncompleteRead",
        "Connection reset",
        "10054",
        "タイムアウト",
        "timed out",
        "ReadTimeoutError",
    )

    # クッキー関連ブロックエラーの検知文字列
    _COOKIE_BLOCK_PATTERNS = (
        "format is not available",
        "images are available",
    )

    # ログイン必須エラーの検知文字列
    _LOGIN_REQUIRED_PATTERNS = (
        "video is not available",
        "LOGIN_REQUIRED",
        "Sign in",
    )

    # 標準フォーマット指定 (最高の映像と音声を自動取得しMP4へ無劣化結合)
    DEFAULT_FORMAT_SPEC = "bestvideo+bestaudio/best"

    # フォーマット選択の優先ルール
    # hasvid: 映像ありを優先 / lang: オリジナル言語優先（吹き替え回避）
    # quality: 主観品質スコア / res: 解像度 / fps: フレームレート
    # size: 物理サイズ優先（ダミービットレートに騙されない）/ br/tbr: 最終手段
    DEFAULT_FORMAT_SORT = ["hasvid", "lang", "quality", "res", "fps", "size", "br", "tbr"]

    def __init__(
        self,
        output_dir: str = "./downloads",
        max_path_bytes: int = 240,
        title_ratio: float = 0.7,
        ellipsis: str = "…",
        use_firefox_cookies: bool = True,
        format_spec: Optional[str] = None,
        embed_thumbnail: bool = True,
        history_file_path: Optional[str] = None,
    ):
        self.output_dir          = os.path.abspath(output_dir)
        self.max_path_bytes      = max_path_bytes
        self.title_ratio         = max(0.0, min(1.0, title_ratio))
        self.ellipsis            = ellipsis
        self.use_firefox_cookies = use_firefox_cookies
        self.format_spec         = format_spec or self.DEFAULT_FORMAT_SPEC
        self.embed_thumbnail     = embed_thumbnail

        os.makedirs(self.output_dir, exist_ok=True)

        self.history_file = (
            os.path.abspath(history_file_path)
            if history_file_path
            else os.path.join(APP_BASE_DIR, "download_history.json")
        )
        self.history = self._load_history()

    # ------------------------------------------------------------------ #
    #  履歴管理                                                            #
    # ------------------------------------------------------------------ #

    def _load_history(self) -> Dict[str, str]:
        """ダウンロード履歴 (filepath -> video_id) を読み込みます"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"履歴ファイルの読み込みに失敗しました: {e}")
        return {}

    def _save_history(self) -> None:
        """ダウンロード履歴を保存します"""
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"履歴ファイルの保存に失敗しました: {e}")

    def register_download_history(self, full_path: str, video_id: str) -> None:
        """ダウンロード履歴記録"""
        if full_path and video_id:
            self.history[full_path] = video_id
            self._save_history()

    # ------------------------------------------------------------------ #
    #  ファイル名サニタイズ・安全パス計算                                  #
    # ------------------------------------------------------------------ #

    @classmethod
    def sanitize_filename(cls, text: str) -> str:
        """OS/ファイルシステムで使用不可な文字を除去・置換"""
        if not text:
            return ""
        text = re.sub(r'[\x00-\x1f\x7f]', '', text)
        for bad_char, safe_char in cls.INVALID_CHAR_MAP.items():
            text = text.replace(bad_char, safe_char)
        return text.strip(" .")

    def safe_truncate_bytes(self, text: str, max_bytes: int) -> str:
        """UTF-8 バイト数制限以内への安全な切り詰め"""
        if len(text.encode("utf-8")) <= max_bytes:
            return text

        ellipsis_bytes = len(self.ellipsis.encode("utf-8"))
        limit_bytes = max_bytes - ellipsis_bytes

        if limit_bytes <= 0:
            return self.ellipsis if max_bytes > 0 else ""

        truncated_chars: list = []
        current_bytes = 0
        for char in text:
            char_bytes = len(char.encode("utf-8"))
            if current_bytes + char_bytes > limit_bytes:
                break
            truncated_chars.append(char)
            current_bytes += char_bytes

        result = "".join(truncated_chars).rstrip(" ._-\t\r\n,;:!?/\\")
        return result + self.ellipsis

    def generate_safe_filename(
        self,
        title: str,
        uploader: str,
        upload_date: str,
        site_name: str = "",
        video_id: str = "",
        ext: str = "mp4",
    ) -> Tuple[str, str]:
        """TVerRec準拠フォーマットで安全なファイル名・パスを生成"""
        clean_title    = self.sanitize_filename(title)    or "無題"
        clean_uploader = self.sanitize_filename(uploader) or "不明"
        clean_ext      = self.sanitize_filename(ext).lstrip(".") or "mp4"
        clean_site     = self.sanitize_filename(site_name)

        clean_date = re.sub(r'\D', '', upload_date) if upload_date else ""
        if len(clean_date) != 8:
            clean_date = datetime.now().strftime("%Y%m%d")

        counter = 0
        while True:
            suffix = f" ({counter})" if counter > 0 else ""
            prefix = f"{clean_site} - {clean_date} - " if clean_site else f"{clean_date} - "

            # 固定部 (ディレクトリ + prefix + " - " + suffix + ".ext") のバイト数を正確に計算
            dir_bytes   = len(self.output_dir.encode("utf-8"))
            sep_bytes   = len(os.sep.encode("utf-8"))
            fixed_bytes = (
                dir_bytes + sep_bytes
                + len(prefix.encode("utf-8"))
                + len(" - ".encode("utf-8"))
                + len(suffix.encode("utf-8"))
                + len(f".{clean_ext}".encode("utf-8"))
            )

            available_bytes = max(10, self.max_path_bytes - fixed_bytes)

            uploader_req = len(clean_uploader.encode("utf-8"))
            title_req    = len(clean_title.encode("utf-8"))

            raw_title_limit    = int(available_bytes * self.title_ratio)
            raw_uploader_limit = available_bytes - raw_title_limit

            if uploader_req < raw_uploader_limit:
                final_uploader_limit = uploader_req
                final_title_limit    = available_bytes - uploader_req
            elif title_req < raw_title_limit:
                final_title_limit    = title_req
                final_uploader_limit = available_bytes - title_req
            else:
                final_title_limit    = raw_title_limit
                final_uploader_limit = raw_uploader_limit

            safe_uploader  = self.safe_truncate_bytes(clean_uploader, final_uploader_limit)
            safe_title     = self.safe_truncate_bytes(clean_title,    final_title_limit)
            safe_filename  = f"{prefix}{safe_uploader} - {safe_title}{suffix}.{clean_ext}"
            safe_full_path = os.path.join(self.output_dir, safe_filename)

            if os.path.exists(safe_full_path):
                if video_id and self.history.get(safe_full_path) == video_id:
                    logger.info(f"同一動画の再ダウンロード。上書き保存します: {safe_filename}")
                    break
                counter += 1
                continue
            break

        return safe_filename, safe_full_path

    # ------------------------------------------------------------------ #
    #  サイト判定・メタデータ抽出                                          #
    # ------------------------------------------------------------------ #

    def detect_site_name(self, info: Dict[str, Any], url: str = "") -> str:
        """対象サイト判定 (x.com, tiktok, instagram のみ記載)"""
        extractor   = (info.get("extractor") or info.get("extractor_key") or "").lower()
        webpage_url = (info.get("webpage_url") or url).lower()
        for site_label, keywords in self.TARGET_SITES.items():
            if any(kw in extractor or kw in webpage_url for kw in keywords):
                return site_label
        return ""

    def extract_clean_uploader(self, info: Dict[str, Any], url: str = "") -> str:
        """SNS (X, TikTok, Instagram) および動画サイトからのアカウント名抽出"""
        site_name   = self.detect_site_name(info, url)
        uploader_id = (info.get("uploader_id") or "").strip()
        uploader    = (info.get("uploader") or info.get("channel") or info.get("creator") or "").strip()

        if site_name == "x.com":
            return (uploader or uploader_id or "Unknown").strip().lstrip("@") or "Unknown"
        if site_name == "instagram":
            handle = uploader
            if not handle or handle.isdigit():
                handle = info.get("channel") or uploader_id or "Unknown"
            return handle.strip().lstrip("@") or "Unknown"
        if site_name == "tiktok":
            return (uploader_id or uploader or "Unknown").strip().lstrip("@") or "Unknown"
        return uploader or uploader_id or "不明"

    def extract_clean_title(self, info: Dict[str, Any], url: str = "") -> str:
        """
        タイトルの先頭に含まれる重複アカウント名の自動除去、
        および Instagram の "Video by" 形式タイトルの回避。
        """
        site_name   = self.detect_site_name(info, url)
        title       = (info.get("title") or "").strip()
        description = (info.get("description") or info.get("caption") or "").strip()
        uploader_id = (info.get("uploader_id") or "").strip().lstrip("@")
        uploader    = (info.get("uploader") or info.get("channel") or "").strip().lstrip("@")

        if site_name == "instagram" and description:
            text = description
        elif title.lower().startswith(("video by", "reel by")) and description:
            text = description
        else:
            text = title or description or "無題"

        text = re.sub(r'[\r\n]+', ' ', text).strip()

        for candidate in (uploader, uploader_id):
            if not candidate or len(candidate) < 2:
                continue
            escaped = re.escape(candidate)
            pattern = r'^(?:@?' + escaped + r'|.*?\(@?' + escaped + r'\))\s*[:：\-＿]\s*'
            text = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()

        if text.lower().startswith(("video by", "reel by", "photo by")):
            text = re.sub(r'[\r\n]+', ' ', description).strip() if description else "無題"

        return text or "無題"

    # ------------------------------------------------------------------ #
    #  yt-dlp オプションビルダー                                           #
    # ------------------------------------------------------------------ #

    def _build_base_ydl_opts(self) -> Dict[str, Any]:
        """ダウンロード用の基本オプション構築"""
        opts: Dict[str, Any] = {
            "format":              self.format_spec,
            "format_sort":         self.DEFAULT_FORMAT_SORT,
            "merge_output_format": "mp4",
            "nocheckcertificate":  True,
            "remote_components":   ["ejs:github"],
            "retries":             15,
            "fragment_retries":    15,
            "file_access_retries": 15,
            "http_chunk_size":     10 * 1024 * 1024,
        }
        if self.use_firefox_cookies:
            opts["cookiesfrombrowser"] = ("firefox",)
        if self.embed_thumbnail:
            opts["writethumbnails"] = True
            opts["postprocessors"] = [
                {"key": "EmbedThumbnail", "already_have_thumbnail": False}
            ]
        return opts

    def _build_fetch_ydl_opts(self) -> Dict[str, Any]:
        """メタデータ取得専用の軽量オプション構築 (ダウンロードは行わない)"""
        opts: Dict[str, Any] = {
            "quiet":              True,
            "no_warnings":        True,
            "skip_download":      True,
            "extract_flat":       False,
            "nocheckcertificate": True,
            "remote_components":  ["ejs:github"],
        }
        if self.use_firefox_cookies:
            opts["cookiesfrombrowser"] = ("firefox",)
        return opts

    # ------------------------------------------------------------------ #
    #  エラー判定ヘルパー                                                  #
    # ------------------------------------------------------------------ #

    @classmethod
    def _is_network_drop(cls, err_str: str) -> bool:
        """ネットワーク切断系エラーかどうかを判定"""
        lower = err_str.lower()
        if "bytes read" in lower and "more expected" in lower:
            return True
        return any(p.lower() in lower for p in cls._NETWORK_DROP_PATTERNS)

    @classmethod
    def _is_cookie_block(cls, err_str: str) -> bool:
        """クッキーによるブロック・フォーマットエラーかどうかを判定"""
        lower = err_str.lower()
        return "cookies" in lower or any(p.lower() in lower for p in cls._COOKIE_BLOCK_PATTERNS)

    @classmethod
    def _is_login_required(cls, err_str: str) -> bool:
        """ログイン必須エラーかどうかを判定"""
        lower = err_str.lower()
        return any(p.lower() in lower for p in cls._LOGIN_REQUIRED_PATTERNS)

    # ------------------------------------------------------------------ #
    #  公開API                                                             #
    # ------------------------------------------------------------------ #

    def fetch_info(self, url: str, extra_ydl_opts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        動画メタデータの事前取得。
        process=False を指定することでフォーマット選定エラーを完全に回避。
        """
        logger.info(f"メタデータを取得中: {url}")
        ydl_opts = self._build_fetch_ydl_opts()
        if extra_ydl_opts:
            ydl_opts.update(extra_ydl_opts)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False, process=False)
        except Exception as e:
            if self.use_firefox_cookies and "cookies" in str(e).lower():
                logger.warning("Firefoxのクッキー取得に失敗。クッキーなしで再試行します...")
                ydl_opts.pop("cookiesfrombrowser", None)
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False, process=False)
            else:
                raise

        if info is None:
            raise ValueError("動画情報の取得に失敗しました。")
        if "entries" in info and info["entries"]:
            info = info["entries"][0]

        return info

    def download(
        self,
        url: str,
        extra_ydl_opts: Optional[Dict[str, Any]] = None,
        progress_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        事前メタデータ取得 → 安全なパス計算 → 本番ダウンロード。
        ネットワーク切断時は自動レジューム、クッキーブロック時は自動フォールバック。
        """
        # 1. メタデータ取得
        info = self.fetch_info(url, extra_ydl_opts)

        upload_date = info.get("upload_date") or ""
        video_id    = info.get("id") or ""
        site_name   = self.detect_site_name(info, url)
        uploader    = self.extract_clean_uploader(info, url)
        title       = self.extract_clean_title(info, url)

        # 2. 安全なファイル名計算
        safe_filename, safe_full_path = self.generate_safe_filename(
            title=title, uploader=uploader, upload_date=upload_date,
            site_name=site_name, video_id=video_id, ext="mp4",
        )

        logger.info("=== ダウンロード準備完了 ===")
        logger.info(f"  サイト判定     : {site_name or '(記載なし)'}")
        logger.info(f"  投稿日         : {upload_date}")
        logger.info(f"  抽出タイトル   : {title}")
        logger.info(f"  抽出アカウント : {uploader}")
        logger.info(f"  生成ファイル   : {safe_filename}")
        logger.info(f"  パスバイト長   : {len(safe_full_path.encode('utf-8'))} bytes (上限: {self.max_path_bytes} bytes)")
        logger.info(f"  履歴ファイル   : {self.history_file}")

        # 3. yt-dlp オプション組み立て
        filename_without_ext = os.path.splitext(safe_filename)[0]
        outtmpl_path = os.path.join(self.output_dir, f"{filename_without_ext}.%(ext)s")

        ydl_opts = self._build_base_ydl_opts()
        ydl_opts.update({"outtmpl": outtmpl_path, "quiet": False, "no_warnings": False})
        if progress_hook:
            ydl_opts["progress_hooks"] = [progress_hook]
        if extra_ydl_opts:
            ydl_opts.update(extra_ydl_opts)

        # 4. 本番ダウンロード（自動レジューム・クッキーフォールバックループ）
        logger.info("本番ダウンロードを開始します...")

        MAX_RESUME = 5
        resume_count = 0
        cookie_fallback_done = False

        while True:
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                break

            except Exception as e:
                err_str = str(e)

                # ケース1: ネットワーク切断 → 自動レジューム
                if self._is_network_drop(err_str):
                    if resume_count < MAX_RESUME:
                        resume_count += 1
                        logger.warning(
                            f"ネットワーク切断を検知。自動レジュームを試みます... ({resume_count}/{MAX_RESUME})"
                        )
                        time.sleep(3)
                        continue
                    raise ValueError(
                        f"ネットワーク切断が多発しダウンロードを中断しました。({MAX_RESUME}回再試行失敗)"
                    )

                # ケース2: クッキーブロック → クッキーなしでリトライ（1回限り）
                if (
                    not cookie_fallback_done
                    and self.use_firefox_cookies
                    and "cookiesfrombrowser" in ydl_opts
                    and self._is_cookie_block(err_str)
                ):
                    logger.warning("クッキーブロックを検知。クッキーなしで再試行します...")
                    ydl_opts.pop("cookiesfrombrowser", None)
                    ydl_opts["format"] = "bestvideo+bestaudio/best"
                    cookie_fallback_done = True
                    continue

                # ケース3: フォールバック後のログイン必須エラー → 丁寧なメッセージで終了
                if self._is_login_required(err_str) and cookie_fallback_done:
                    logger.error(
                        "【エラー】この動画はログイン必須ですが、bot対策によりクッキーを使用できませんでした。"
                        " Node.js または Deno をインストールすると解決する可能性があります。"
                    )
                    raise ValueError(
                        "動画のダウンロードにログインが必須ですが、bot対策によりブロックされました。"
                        " Node.js または Deno をインストールして再度お試しください。"
                    )

                raise

        # 5. 履歴登録
        self.register_download_history(safe_full_path, video_id)
        logger.info(f"ダウンロード完了: {safe_full_path}")
        return safe_full_path, info
