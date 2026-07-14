import shutil
import subprocess
import sys
from pathlib import Path


def test_installed_application_serves_built_frontend(tmp_path: Path) -> None:
    release_dir = tmp_path / "release"
    site_packages = release_dir / "venv" / "lib" / "python3.12" / "site-packages"
    shutil.copytree(Path("backend/lightops"), site_packages / "lightops")
    frontend_dist = release_dir / "frontend" / "dist"
    frontend_dist.mkdir(parents=True)
    (frontend_dist / "index.html").write_text("<h1>LightOps frontend</h1>", encoding="utf-8")
    script = f"""
import sys
sys.prefix = {str(release_dir / 'venv')!r}
sys.path.insert(0, {str(site_packages)!r})
from fastapi.testclient import TestClient
from lightops.api import app
response = TestClient(app).get('/')
assert response.status_code == 200, response.text
assert 'LightOps frontend' in response.text
"""

    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=False)

    assert completed.returncode == 0, completed.stderr
