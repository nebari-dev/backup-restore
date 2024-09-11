from typing import Optional

from backup_restore.core.base import ConfigManager, Manager, SnapshotMetadata
from backup_restore.core.storage import StorageManager
from backup_restore.services.base import Service


class RestoreManager(Manager):
    def __init__(self, config_manager: ConfigManager):
        super().__init__(config_manager)
        self.storage_client = StorageManager(
            config=config_manager.get_config_by_service_name("storage")
        )

    def _get_service_snapshot_metadata(self, snapshot: dict, service_name: str) -> dict:
        """Retrieve metadata for a specific service from the snapshot."""
        return snapshot["services"].get(service_name, {})

    def restore(
        self,
        service_name: Optional[str] = None,
        snapshot: Optional[SnapshotMetadata] = None,
        snapshot_id: Optional[str] = None,
        plan: bool = True,
    ) -> dict:
        """
        Restore the specified service(s) from a snapshot.

        If `service_name` is passed, only that service will be restored.
        The data will come from the `snapshot` parameter if passed,
        or from the snapshot associated with the given `snapshot_id`.
        """
        if snapshot is None and snapshot_id is None:
            raise ValueError("Either snapshot or snapshot_id must be provided.")

        # Load the snapshot metadata if snapshot_id is provided
        if snapshot_id:
            snapshot_data = self.storage_client.get(snapshot_id=snapshot_id)
            snapshot = SnapshotMetadata(**snapshot_data)

        services_to_restore = self.services

        if service_name:
            if service_name not in services_to_restore:
                raise ValueError(f"Service '{service_name}' not found.")
            services_to_restore = {service_name: services_to_restore[service_name]}

        restore_plan = {}

        for svc_name, service in services_to_restore.items():
            service_metadata = self._get_service_snapshot_metadata(
                snapshot.model_dump(), svc_name
            )
            if not service_metadata:
                raise ValueError(
                    f"No metadata found for service '{svc_name}' in snapshot."
                )

            # Perform the restore operation for each service or generate the plan
            result = service.restore(
                storage_client=self.storage_client,
                data=service_metadata.get("data"),
                dry_run=plan,
                bucket_name=(
                    service.name
                    if snapshot_id is None
                    else f"{snapshot.snapshot_id}/{service.name}"
                ),
            )

            if plan:
                restore_plan[svc_name] = result

        if plan:
            return {
                "message": "Restore plan generated successfully.",
                "plan": restore_plan,
                "error": None,
            }

        return {"message": "Restore completed successfully.", "error": None}
