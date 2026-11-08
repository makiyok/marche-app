import uuid
from pathlib import Path

from flask import current_app

# media_type → 保存するときの拡張子
EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def detect_media_type(data: bytes) -> str | None:
    """ファイルの先頭のバイト（マジックナンバー）で JPEG / PNG / WebP を判定する。どれでもなければ None"""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def save_image(data: bytes, media_type: str) -> str:
    """UUID のファイル名で保存し、そのファイル名を返す（元のファイル名は使わない）"""
    folder = Path(current_app.config["UPLOAD_FOLDER"])
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{EXTENSIONS[media_type]}"
    (folder / filename).write_bytes(data)
    return filename


def delete_image(filename: str | None) -> None:
    """写真を消す。無くてもエラーにしない"""
    if not filename:
        return
    # 保存先の外を消さないように、ファイル名の部分だけを使う
    path = Path(current_app.config["UPLOAD_FOLDER"]) / Path(filename).name
    path.unlink(missing_ok=True)
