import uuid
import datetime
from .base import Manager, ConfigManager
from backup_restore.services.base import Service
from .archive import ArchiveManager


class BackupManager(Manager):
    def __init__(self, config_manager: ConfigManager):
        super().__init__(config_manager)
        self.storage_client = ArchiveManager(
            config=config_manager.get_config_by_service_name("archive")
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
        self, version: str, description: str = None, created_at: str = None
    ) -> dict:

        return {
            "backup_and_restore_version": version,
            "snapshot_id": self.generate_snapshot_id(),
            "description": description or "Backup of all services",
            "created_at": created_at or datetime.datetime.now().isoformat(),
            "services": [
                self._generate_service_snapshot_metadata(service)
                for service in self.services.values()
            ],
        }

    def backup(self, snapshot=False, tar=False) -> None:
        storage_client = self.storage_client
        if snapshot:
            metadata = self._generate_snapshot_metadata(version="1.0.0")

            for service in self.services.values():
                service.backup(storage_client, tar=tar)

            metadata_file = f"{metadata['snapshot_id']}_metadata.json"
            storage_client.upload(
                bucket_name="metadata", data=metadata, file_name=metadata_file
            )
