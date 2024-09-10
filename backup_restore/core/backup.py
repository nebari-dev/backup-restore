import datetime
import json
import uuid
from typing import Dict, Optional

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
        """Generate a unique snapshot ID."""
        return str(uuid.uuid4())

    def _generate_service_snapshot_metadata(self, service: Service) -> dict:
        """Generate metadata for a specific service snapshot."""
        return ServiceSnapshotMetadata(
            name=service.name,
            type=service.type,
            version=service.version,
            priority=service.priority,
            data=service.state.id,
        ).model_dump()

    def _generate_snapshot_metadata(
        self,
        version: str,
        description: Optional[str] = None,
        created_at: Optional[str] = None,
        services: Optional[Dict[str, Service]] = None,
    ) -> dict:
        """Generate metadata for a full backup snapshot."""
        return SnapshotMetadata(
            backup_and_restore_version=version,
            snapshot_id=self.generate_snapshot_id(),
            description=description or "Backup of all services",
            created_at=created_at or datetime.datetime.now().isoformat(),
            services={
                service_name: self._generate_service_snapshot_metadata(service)
                for service_name, service in services.items()
            },
        ).model_dump()

    def list(self, service_name: Optional[str] = None):
        """List available backups."""
        pass

    def info(self, snapshot_id: Optional[str] = None):
        """Retrieve information about a specific backup."""
        pass

    def get(self, snapshot_id: Optional[str] = None):
        """Retrieve a specific backup."""
        pass

    def _update_service_data(
        self, metadata: dict, service_name: str, data: str
    ) -> dict:
        """Update service data in the metadata."""
        service_data = metadata["services"].get(service_name, {}).get("data", [])
        service_data.append(data)
        metadata["services"][service_name]["data"] = service_data
        return metadata

    def backup(
        self,
        service_name: Optional[str] = None,
        snapshot: bool = True,
        description: Optional[str] = None,
        compressing: bool = False,
        archive_only: bool = True,
    ):
        """Perform a backup of the specified service(s)."""
        storage_client = self.storage_client
        services_to_backup = self.services

        if service_name:
            if service_name not in services_to_backup:
                raise ValueError(f"Service '{service_name}' not found.")
            services_to_backup = {service_name: services_to_backup[service_name]}

        if snapshot:
            metadata = self._generate_snapshot_metadata(
                version="1.0.0", services=services_to_backup, description=description
            )
        else:
            metadata = {}

        for svc_name, service in services_to_backup.items():
            backup_data = service.backup(
                storage_client=storage_client,
                archive_only=archive_only,
                bucket_name=(
                    service.name
                    if not snapshot
                    else f"{service.state.id}/{service.name}"
                ),
                tar=compressing,
            )
            if not archive_only:
                if snapshot:
                    metadata["services"][svc_name]["data"] = backup_data
                else:
                    metadata.setdefault(svc_name, []).append(backup_data)

        if snapshot and archive_only:
            metadata_file = f"{metadata['snapshot_id']}_metadata.json"
            storage_client.upload(
                bucket_name="", data=json.dumps(metadata), file_name=metadata_file
            )
            return {
                "message": "Backup completed successfully.",
                "result": {
                    "snapshot_id": metadata["snapshot_id"],
                    "metadata_file": metadata_file,
                },
                "error": None,
            }
        elif not archive_only:
            return metadata
