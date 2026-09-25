"""Приём файлов: проверка расширения, размера, безопасное имя на диске."""
import mimetypes
import secrets
import time

from core import config

SNIFF = {
    b"\x89PNG\r\n\x1a\n": "png",
    b"\xff\xd8\xff": "jpg",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
    b"%PDF": "pdf",
}


def ext_of(filename: str) -> str:
    return filename.rsplit(".", 1)[1].lower() if "." in filename else ""


def ext_allowed(filename: str) -> bool:
    return ext_of(filename) in config.ALLOWED_EXT


def looks_like_declared(blob: bytes, ext: str) -> bool:
    """Грубая проверка сигнатуры: .png не должен оказаться исполняемым файлом."""
    for magic, kind in SNIFF.items():
        if blob.startswith(magic):
            if kind == "jpg":
                return ext in ("jpg", "jpeg")
            return ext == kind
    return ext not in ("png", "jpg", "jpeg", "gif", "pdf")


def save_many(file_storages, *, max_files: int | None = None) -> tuple[list[dict], list[str]]:
    saved: list[dict] = []
    errors: list[str] = []
    limit = max_files or config.MAX_FILES
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    for fs in file_storages:
        if not fs or not fs.filename:
            continue
        if len(saved) >= limit:
            errors.append(f"Максимум {limit} файлов — лишние не приняты.")
            break
        original = fs.filename[:200]
        ext = ext_of(original)
        if not ext_allowed(original):
            errors.append(f"«{original}» — недопустимый формат.")
            continue
        blob = fs.read()
        if not blob:
            continue
        if len(blob) > config.MAX_FILE_MB * 1024 * 1024:
            errors.append(f"«{original}» больше {config.MAX_FILE_MB} МБ.")
            continue
        if not looks_like_declared(blob, ext):
            errors.append(f"«{original}» — содержимое не совпадает с расширением.")
            continue

        stored = f"{int(time.time())}_{secrets.token_hex(10)}.{ext}"
        (config.UPLOAD_DIR / stored).write_bytes(blob)
        saved.append({
            "stored_name": stored,
            "original_name": original,
            "size_bytes": len(blob),
            "mime": mimetypes.guess_type(original)[0] or fs.mimetype,
        })
    return saved, errors


def save_one(file_storage) -> tuple[dict | None, list[str]]:
    saved, errors = save_many([file_storage], max_files=1)
    return (saved[0] if saved else None), errors


def remove(stored_name: str) -> None:
    if not stored_name:
        return
    path = (config.UPLOAD_DIR / stored_name).resolve()
    if path.parent == config.UPLOAD_DIR.resolve():
        path.unlink(missing_ok=True)
