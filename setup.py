from setuptools import setup, find_packages


def find_requirements():
    with open("requirements.txt") as f:
        return f.read().splitlines()


setup(
    name="backup_restore",
    version="0.1.0",
    packages=find_packages(),
    install_requires=find_requirements(),
    entry_points={
        "console_scripts": [
            "backup-restore=backup_restore.__main__:main",
        ],
    },
)
