# adapters/api.py
import inspect
import os
from functools import partial, wraps

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backup_restore.adapters.base import AdaptersBaseFactory
from backup_restore.core.backup import BackupManager
from backup_restore.core.base import ConfigManager, Manager
from backup_restore.core.restore import RestoreManager


class ServiceAPIFactory(AdaptersBaseFactory):
    def __init__(self, manager: Manager, operation: str):
        super().__init__(manager, operation)

    def _create_service_router(self, service_name: str, service) -> APIRouter:
        router = APIRouter(
            prefix=f"/{service_name}",
        )

        def register_route(method: str, method_type: str):
            route_name = method[len(f"{method_type}_") :]
            func = self._get_function(service, method, method_type)

            # Determine the HTTP method based on the method type
            http_method = "GET" if method_type == "export" else "POST"

            # Define a dependency to modify the response status
            async def set_status(response: Response, result: dict = Depends(func)):
                response_status = result.get("status", 200)
                response.status_code = response_status
                return result

            # Register the route with FastAPI
            router.add_api_route(
                f"/{route_name}",
                set_status,
                methods=[http_method],
                tags=[service_name],
                response_class=JSONResponse,
                description=inspect.getdoc(func),
                summary=route_name,
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

        def background_task_wrapper(func):
            @wraps(func)
            def wrapper(
                *args, background_tasks: BackgroundTasks = BackgroundTasks(), **kwargs
            ):
                # Pass along all original arguments and inject BackgroundTasks
                background_tasks.add_task(func, *args, **kwargs)
                return {"status": 202}

            return wrapper

        # Register root route from the manager
        main_router.add_api_route(
            "/",
            # background_task_wrapper(getattr(self.manager, self.operation)),
            getattr(self.manager, self.operation),
            methods=["POST"],
            tags=[self.operation],
        )

        for manager_method in self._get_methods(self.manager, method_type="root"):
            if manager_method.startswith(self.operation):
                continue
            main_router.add_api_route(
                f"/{manager_method}",
                getattr(self.manager, manager_method),
                methods=["GET"],
                tags=[self.operation],
            )

        for service_name, service in self.services.items():
            service_router = self._create_service_router(service_name, service)
            main_router.include_router(service_router)

        return main_router


def create_api() -> FastAPI:
    app = FastAPI()

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        errors = exc.errors()
        # Customize the response as needed
        custom_errors = []
        for error in errors:
            if error["type"] == "missing":
                custom_errors.append(
                    {
                        "loc": error["loc"],
                        "msg": f"The field {error['loc']} is required but missing.",
                    }
                )
        return JSONResponse(
            status_code=400,
            content={"detail": custom_errors},
        )

    config_manager = ConfigManager(config_dir=os.environ.get("CONFIG_DIR", "config"))

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
