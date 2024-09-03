import typer
from typer import Typer
import os
from backup_restore.adapters.base import AdaptersBaseFactory, ConfigManager
from backup_restore.core.backup import BackupManager
from backup_restore.core.restore import RestoreManager


class ServiceAppFactory(AdaptersBaseFactory):
    def _create_service_app(self, service_name: str, service) -> typer.Typer:
        app = typer.Typer()

        def register_command(method: str, method_type: str):
            command_name = method[len(f"_{method_type}_") :]
            _func = self._get_function(service, method, method_type)
            app.command(name=command_name)(_func)

        if self.operation == "backup":
            export_methods = self._get_methods(service, "export")
            for method in export_methods:
                register_command(method, "export")

        if self.operation == "restore":
            import_methods = self._get_methods(service, "import")
            for method in import_methods:
                register_command(method, "import")

        return app

    def _create_main_app(self) -> typer.Typer:
        app = typer.Typer()

        for service_name, service in self.services.items():
            service_app = self._create_service_app(service_name, service)
            app.add_typer(service_app, name=service_name)

        return app

    def app(self):
        return self._create_main_app()


def create_cli():
    app = Typer()
    config_manager = ConfigManager(config_dir=os.environ.get("CONFIG_DIR", "config"))
    from functools import partial

    # Add routers for backup and restore
    for manager, name in [
        (partial(BackupManager, config_manager=config_manager), "backup"),
        (partial(RestoreManager, config_manager=config_manager), "restore"),
    ]:
        service_app = ServiceAppFactory(manager, operation=name).app()
        app.add_typer(service_app, name=name)

    return app()
