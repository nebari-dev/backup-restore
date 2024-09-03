from setuptools import setup, find_packages

setup(
    name="backup_restore",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "fastapi",
        "uvicorn",
        "typer",
    ],
    entry_points={
        "console_scripts": [
            "backup-restore=backup_restore.__main__:main",
        ],
    },
)
