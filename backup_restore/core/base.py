# core/base.py
import json
import os
import warnings
from typing import Any, Dict, List

import yaml
from pydantic import BaseModel

from backup_restore import services
from backup_restore.services.base import Service

ALL_SERVICES = services.__all__


class ServiceSnapshotMetadata(BaseModel):
    name: str
    type: str
    version: str
    priority: int
    data: str


class SnapshotMetadata(BaseModel):
    backup_and_restore_version: str
    snapshot_id: str
    description: str
    created_at: str
    services: List[ServiceSnapshotMetadata]


class ConfigManager:
    def __init__(self, config_dir: str):
        self.config_dir = config_dir
        self.config = self.load_config()
        # print(f"Loaded config: {self.config}")

    def get_config_by_service_name(self, service_name: str) -> Dict[str, Any]:
        # print(f"Getting config for {service_name}")
        return self.config.get(service_name, {})

    def load_config(self) -> Dict[str, Any]:
        config = {}

        # Check if config directory exists
        if not os.path.exists(self.config_dir):
            raise FileNotFoundError(f"Config directory {self.config_dir} not found.")

        yaml_config_path = os.path.join(self.config_dir, "services.yaml")
        if os.path.isfile(yaml_config_path):
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

    def _get_service_by_name(self, service_name: str) -> Service:
        return getattr(services, service_name)

    def _load_services(self) -> Dict[str, Service]:
        services_dict = {}

        for service_name in ALL_SERVICES:
            service_class = self._get_service_by_name(service_name)

            if callable(service_class):
                service_config = self.config_manager.get_config_by_service_name(
                    service_class.name
                )
                try:
                    service_instance = service_class(config=service_config)

                    if hasattr(service_instance, "name"):
                        services_dict[service_instance.name] = service_instance

                except ValueError as e:
                    print(f"Error initializing service {service_name}: {e}")

        return services_dict
