import os
from pathlib import Path

import uvicorn


def run():
    # Tell atlas where the project root lives regardless of where the
    # package ends up installed (e.g. Nix store).
    os.environ.setdefault("ATLAS_BASE", str(Path(__file__).parent))
    uvicorn.run("atlas.main:app", host="0.0.0.0", port=3040, reload=True)


if __name__ == "__main__":
    run()
