"""Restore a backup (stop the app first):  python -m app.restore data/backups/backup-XXXX.zip
Users, chats, audit log and documents are restored; the search index rebuilds on next start."""
import getpass, io, os, shutil, sys, zipfile
from pathlib import Path

from app import crypto

BASE = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv("DATA_DIR", BASE / "data"))
DOCS = Path(os.getenv("DOCS_DIR", BASE / "docs"))


def restore(path: str):
    data = Path(path).read_bytes()
    if data.startswith(crypto.MAGIC):
        data = crypto.decrypt(data, os.getenv("BACKUP_PASSPHRASE") or getpass.getpass("Backup passphrase: "))
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        assert "users.db" in names, "Not a backup from this app."
        assert all(not n.startswith("/") and ".." not in n for n in names), "Unsafe paths in archive."
        shutil.rmtree(DOCS, ignore_errors=True)
        DATA.mkdir(parents=True, exist_ok=True)
        for n in names:
            if n.endswith("/"):
                continue
            dest = (DATA / "users.db" if n == "users.db" else DOCS / n[5:] if n.startswith("docs/")
                    else DATA / n if n.startswith("avatars/") else None)
            if dest:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(z.read(n))
    for ext in ("-wal", "-shm"):
        (DATA / f"users.db{ext}").unlink(missing_ok=True)
    shutil.rmtree(DATA / "chroma", ignore_errors=True)
    print("Restored. Start the app; the index rebuilds from the documents.")


if __name__ == "__main__":
    restore(sys.argv[1])
