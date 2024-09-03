import json
import os
from typing import Any, Dict, Optional

from backup_restore import services


class ConfigManager:
    def __init__(self, config_dir: str):
        """
        Initialize the ConfigManager with a directory where the service configuration files reside.
        :param config_dir: Path to the directory containing <service>-config.json files.
        """
        self.config_dir = config_dir

    def load_config(self, service_name: str) -> Optional[Dict[str, Any]]:
        """
        Load the configuration for a given service.
        :param service_name: Name of the service (e.g., 'keycloak').
        :return: Dictionary containing the service's configuration, or None if the file does not exist.
        """
        config_path = os.path.join(self.config_dir, f"{service_name}.json")
        print(f"Loading configuration for {service_name} from {config_path}")

        if not os.path.exists(config_path):
            print(f"Configuration file for {service_name} not found.")
            return {}

        with open(config_path, "r") as config_file:
            config = json.load(config_file)

        return config


class Handler:
    """Does the service registration and loading by interacting with the services module"""

    def __init__(self):
        self.config_manager = ConfigManager(
            config_dir=os.environ.get("CONFIG_DIR", "config")
        )
        self.services = self._load_services()

    def _load_services(self):
        services_list = []

        for service in services.__all__:
            service_class = getattr(services, service)
            if callable(service_class):
                # Load the config for this service
                service_config = self.config_manager.load_config(service)

                try:
                    # Initialize the service (which will validate its own config)
                    service_instance = service_class(config=service_config)
                    services_list.append(service_instance)
                except ValueError as e:
                    print(f"Error initializing service {service}: {e}")

        return services_list
