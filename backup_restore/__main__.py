# main.py
import sys
import os

from backup_restore.adapters.api import create_api


def main():

    if "--standalone" in sys.argv:
        print("Running in standalone API server mode")
        import uvicorn

        uvicorn.run(
            app="backup_restore.__main__:create_api",
            factory=True,
            host="0.0.0.0",
            port=os.environ.get("BACKUP_RESTORE_SERVER_PORT", 8080),
            reload=True,
        )


if __name__ == "__main__":
    main()
