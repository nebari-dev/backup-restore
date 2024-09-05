# core/restore.py
from backup_restore.core.base import Manager


class RestoreManager(Manager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def restore_all(self) -> None:
        for service in self.services.values():
            service._import()

    def restore(
        self,
        service_name: str = None,
        snapshot: bool = False,
        tar: bool = False,
    ) -> None:
        "Not implemented"
        raise NotImplementedError
