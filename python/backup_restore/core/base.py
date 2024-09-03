import json
import os
import warnings
from typing import Any, Dict, Optional

import yaml
from backup_restore import services


class ConfigManager:
    def __init__(self, config_dir: str):
        self.config_dir = config_dir
        self.config = self.load_config()
        print(f"Loaded config: {self.config}")

    def get_config_by_service_name(self, service_name: str) -> Dict[str, Any]:
        print(f"Getting config for {service_name}")
        return self.config.get(service_name, {})

    def load_config(self) -> Dict[str, Any]:
        config = {}

        yaml_config_path = os.path.join(self.config_dir, "services.yaml")
        if os.path.exists(yaml_config_path):
            warnings.warn(
                "Found 'services.yaml'. This file will take precedence over individual JSON files. "
                "Avoid storing secrets in this file."
            )
            try:
                with open(yaml_config_path, "r") as yaml_file:
                    return yaml.safe_load(yaml_file) or {}
            except yaml.YAMLError as e:
                warnings.warn(f"Error loading YAML file: {e}")
                return {}

        for file_name in os.listdir(self.config_dir):
            if file_name.endswith(".json"):
                config_path = os.path.join(self.config_dir, file_name)
                try:
                    with open(config_path, "r") as config_file:
                        service_config = json.load(config_file) or {}
                        service_name = os.path.splitext(file_name)[0]
                        config[service_name] = service_config
                except json.JSONDecodeError as e:
                    warnings.warn(f"Error loading JSON file {config_path}: {e}")

        return config


class Manager:
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.services = self._load_services()

    def _load_services(self) -> Dict[str, Any]:
        services_dict = {}

        for service_name in services.__all__:
            service_class = getattr(services, service_name)
            if callable(service_class):
                service_config = self.config_manager.get_config_by_service_name(
                    service_class.name
                )
                print(f"Service config for {service_class.name}: {service_config}")
                try:
                    service_instance = service_class(config=service_config)
                    if hasattr(service_instance, "name"):
                        services_dict[service_instance.name] = service_instance
                except ValueError as e:
                    print(f"Error initializing service {service_name}: {e}")

        return services_dict
