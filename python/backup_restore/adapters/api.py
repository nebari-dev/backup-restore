import os

from backup_restore.adapters.base import AdaptersBaseFactory, ConfigManager
from backup_restore.core.backup import BackupManager
from backup_restore.core.restore import RestoreManager
from fastapi import APIRouter, FastAPI, HTTPException


from fastapi import APIRouter, HTTPException
import inspect
from functools import wraps


class ServiceAPIFactory(AdaptersBaseFactory):
    def _create_service_router(self, service_name: str, service) -> APIRouter:
        router = APIRouter(prefix=f"/{service_name}")

        def register_route(method: str, method_type: str):
            route_name = method[len(f"_{method_type}_") :]
            func = self._get_function(service, method, method_type)

            # Determine the HTTP method based on the method type
            http_method = "GET" if method_type == "export" else "POST"

            # Define the FastAPI route with the correct parameters
            router.add_api_route(
                f"/{route_name}",
                func,
                methods=[http_method],
                tags=[service_name],
            )

        if self.operation == "backup":
            export_methods = self._get_methods(service, "export")
            for method in export_methods:
                register_route(method, "export")

        if self.operation == "restore":
            import_methods = self._get_methods(service, "import")
            for method in import_methods:
                register_route(method, "import")

        return router

    def create_main_router(self) -> APIRouter:
        main_router = APIRouter()

        for service_name, service in self.services.items():
            service_router = self._create_service_router(service_name, service)
            main_router.include_router(service_router)

        return main_router


def create_api():
    app = FastAPI()
    config_manager = ConfigManager(config_dir=os.environ.get("CONFIG_DIR", "config"))
    from functools import partial

    # Add routers for backup and restore
    for manager, prefix in [
        (partial(BackupManager, config_manager=config_manager), "/backup"),
        (partial(RestoreManager, config_manager=config_manager), "/restore"),
    ]:
        router = ServiceAPIFactory(
            manager, operation=prefix.strip("/")
        ).create_main_router()
        app.include_router(router, prefix=prefix)

    return app
