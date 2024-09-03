from .base import Manager


class RestoreManager(Manager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def restore_all(self) -> None:
        for service in self.services:
            service._import()

    def restore(self): ...
