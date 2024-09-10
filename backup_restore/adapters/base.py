from backup_restore.core.base import Manager


class AdaptersBaseFactory:
    def __init__(self, manager: Manager, operation: str):
        self.manager = manager()
        self.services = self.manager.services
        self.operation = operation

    def _get_methods(self, service, method_type: str, prefix: str = ""):
        if method_type == "export":
            start_with = f"{prefix}{method_type}"
            return [
                method
                for method in dir(service.exporter)
                if method.startswith(start_with)
            ]
        elif method_type == "import":
            start_with = f"{prefix}{method_type}"
            return [
                method
                for method in dir(service.importer)
                if method.startswith(start_with)
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
