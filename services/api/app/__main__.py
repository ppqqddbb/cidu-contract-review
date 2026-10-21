import os
from pathlib import Path

import uvicorn

if __name__ == "__main__":
    reload_enabled = os.getenv("API_RELOAD", "true").strip().lower() in {"1", "true", "yes", "on"}
    uvicorn.run(
        "app.main:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=reload_enabled,
        reload_dirs=[str(Path(__file__).resolve().parents[1])] if reload_enabled else None,
        # The packaged backend has no console, so sys.stderr is None and
        # Uvicorn's default color formatter crashes while calling isatty().
        log_config=None,
        access_log=False,
    )
