# main.py
import sys
from backup_restore.adapters.api import create_api
from backup_restore.adapters.cli import create_cli


def main():

    if "--standalone" in sys.argv:
        print("Running in standalone API server mode")
        import uvicorn

        uvicorn.run(
            app="backup_restore.__main__:create_api",
            factory=True,
            host="0.0.0.0",
            port=8000,
            reload=True,
        )
    else:
        print("Running in CLI mode")
        create_cli()


if __name__ == "__main__":
    main()
