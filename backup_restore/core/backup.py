# core/backups.py
import datetime
import uuid
from typing import Optional

from backup_restore.core.base import (
    ConfigManager,
    Manager,
    ServiceSnapshotMetadata,
    SnapshotMetadata,
)
from backup_restore.services.base import Service


class BackupManager(Manager):
    def __init__(self, config_manager: ConfigManager):
        super().__init__(config_manager)

    def generate_snapshot_id(self) -> str:
        return str(uuid.uuid4())

    def backup(
        self,
        service_name: str = None,
        snapshot: bool = False,
        tar: bool = False,
    ) -> None:
        "Not implemented"
        raise NotImplementedError
