# core/backups.py
import datetime
import json
import uuid
from typing import Optional, Dict

from backup_restore.core.base import (
    ConfigManager,
    Manager,
    ServiceSnapshotMetadata,
    SnapshotMetadata,
)
from backup_restore.core.storage import StorageManager
from backup_restore.services.base import Service


class BackupManager(Manager):
    def __init__(self, config_manager: ConfigManager):
        super().__init__(config_manager)
        self.storage_client = StorageManager(
            config=config_manager.get_config_by_service_name("storage")
        )

    def generate_snapshot_id(self) -> str:
        return str(uuid.uuid4())

    def _generate_service_snapshot_metadata(self, service: Service) -> dict:
        return {
            "name": service.name,
            "type": service.type,
            "version": service.version,
            "priority": service.priority,
            "data": service.state.id,
        }

    def _generate_snapshot_metadata(
        self,
        version: str,
        description: str = None,
        created_at: str = None,
        services: Dict[str, Service] = None,
    ) -> dict:

        return {
            "backup_and_restore_version": version,
            "snapshot_id": self.generate_snapshot_id(),
            "description": description or "Backup of all services",
            "created_at": created_at or datetime.datetime.now().isoformat(),
            "services": [
                self._generate_service_snapshot_metadata(service)
                for service in services.values()
            ],
        }

    def list(service_name: str = None): ...

    def info(snapshot_id: str = None): ...

    def get(snapshot_id: str = None): ...

    def backup(
        self,
        service_name: str = None,
        snapshot: bool = False,
        compressing: bool = False,
        archive: bool = True,
    ):
        storage_client = self.storage_client
        __services__ = self.services

        if service_name:
            # raise an error if service_name is not in services
            if service_name not in self.services:
                raise ValueError(f"Service {service_name} not found.")
            __services__ = {service_name: self.services[service_name]}

        metadata = self._generate_snapshot_metadata(
            version="1.0.0", services=__services__
        )

        for service_name, service in __services__.items():
            service.backup(storage_client=storage_client, tar=compressing)
            print(f"Backing up {service_name}... Service backup completed.")

        metadata_file = f"{metadata['snapshot_id']}_metadata.json"
        # storage_client.upload(
        #     bucket_name="", data=json.dumps(metadata), file_name=metadata_file
        # )
