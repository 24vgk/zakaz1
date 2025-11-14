
from pathlib import Path
from config import STORAGE_ROOT
def ensure_dirs():
    Path(STORAGE_ROOT).mkdir(parents=True, exist_ok=True)
    for sub in ("reports", "problems", "users"):
        Path(STORAGE_ROOT, sub).mkdir(parents=True, exist_ok=True)

def build_paths(problem_id: int, user_id: int, report_id: int, filename: str):
    p1 = Path(STORAGE_ROOT, "reports", str(report_id))
    p2 = Path(STORAGE_ROOT, "problems", str(problem_id))
    p3 = Path(STORAGE_ROOT, "users", str(user_id), "problems", str(problem_id))
    for p in (p1, p2, p3): p.mkdir(parents=True, exist_ok=True)
    return p1 / filename, p2 / filename, p3 / filename

def save_bytes_to_all(destinations, data: bytes):
    for d in destinations:
        with open(d, "wb") as f: f.write(data)
