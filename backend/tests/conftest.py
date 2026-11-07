import os
from pathlib import Path

# Point the app at the test database before anything imports app.database.
_env = (
    dict(
        line.split("=", 1)
        for line in (Path(__file__).parents[1] / ".env").read_text().splitlines()
        if "=" in line and not line.startswith("#")
    )
    if (Path(__file__).parents[1] / ".env").exists()
    else {}
)
for key in ("DATABASE_URL", "DATABASE_URL_OWNER"):
    url = os.environ.get(f"TEST_{key}") or _env.get(key, "")
    if url.endswith("/anylo"):
        url += "_test"
    if url:
        os.environ[key] = url
