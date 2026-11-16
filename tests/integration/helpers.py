import os, socket, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait(url: str, secs: int = 90):
    for _ in range(secs * 4):
        try:
            urllib.request.urlopen(url)
            return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("did not start: " + url)


def wait_port(port: int, secs: int = 30):
    for _ in range(secs * 4):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.25)
    raise RuntimeError(f"port {port} did not open")


class Proc:
    def __init__(self, args, env=None):
        self.p = subprocess.Popen(args, cwd=ROOT, env={**os.environ, **(env or {})}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def stop(self):
        self.p.terminate()


def start_app(**env):
    """Start the real app in a subprocess with a fresh data dir. Returns (process, base_url)."""
    tmp, port = tempfile.mkdtemp(), free_port()
    base = {"DATA_DIR": f"{tmp}/data", "DOCS_DIR": f"{tmp}/docs", "ADMIN_PASSWORD": "adminpass1", "SEED_DEMO": "1",
            "JWT_SECRET": "it-secret", "BACKUP_HOURS": "0", "GEMINI_API_KEY": "", "APP_ENV": "development",
            "BASE_URL": f"http://localhost:{port}"}
    proc = Proc([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)], {**base, **env})
    wait(f"http://127.0.0.1:{port}/api/health")
    return proc, f"http://localhost:{port}"


def login(url: str, user: str, pw: str) -> dict:
    import httpx
    return {"Authorization": "Bearer " + httpx.post(url + "/api/login", json={"username": user, "password": pw}).json()["token"]}
