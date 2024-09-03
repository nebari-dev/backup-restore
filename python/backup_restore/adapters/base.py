import json
import os
from typing import Any, Callable, Dict, Optional, Type

from backup_restore.core.base import ConfigManager, Manager


class AdaptersBaseFactory:
    def __init__(self, manager: Manager, operation: str):
        self.manager = manager()
        self.services = self.manager.services
        self.operation = operation

    def _get_methods(self, service, method_type: str):
        if method_type == "export":
            return [
                method
                for method in dir(service.exporter)
                if method.startswith("_export_")
            ]
        elif method_type == "import":
            return [
                method
                for method in dir(service.importer)
                if method.startswith("_import_")
            ]
        else:
            raise ValueError("Invalid method type")

    def _get_function(self, service, method: str, method_type: str):
        if method_type == "export":
            return getattr(service.exporter, method)
        elif method_type == "import":
            return getattr(service.importer, method)
        elif method_type == "root":
            return getattr(service, method)
        else:
            raise ValueError("Invalid method type")
