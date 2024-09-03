import os
import shutil
from typing import Annotated, Optional, Union

import boto3
from pydantic import BaseModel, DirectoryPath, RootModel, constr


class S3ClientConfig(BaseModel):
    aws_access_key_id: Annotated[str, constr(min_length=1)] = ""
    aws_secret_access_key: Annotated[str, constr(min_length=1)] = ""
    region: Annotated[str, constr(min_length=1)] = "us-east-1"


class LocalClientConfig(BaseModel):
    base_dir: DirectoryPath = "/tmp"


class ArchiveManagerConfig(BaseModel):
    type: Annotated[str, constr(min_length=1)] = "local"
    s3: Optional[S3ClientConfig] = S3ClientConfig()
    local: Optional[LocalClientConfig] = LocalClientConfig()

    def get_client_config(self):
        if self.type == "s3" and self.s3:
            return self.s3
        elif self.type == "local" and self.local:
            return self.local
        else:
            raise ValueError(f"Invalid configuration for type: {self.type}")


class ArchiveManager:
    def __init__(self, config: dict = {}):
        # Validate the config using the ArchiveManagerConfig schema
        validated_config = ArchiveManagerConfig(**config)
        self.config = validated_config.get_client_config()
        self.client = self._initialize_client()

    def _initialize_client(self):
        if isinstance(self.config, S3ClientConfig):
            return S3Client(self.config.model_dump())
        elif isinstance(self.config, LocalClientConfig):
            return LocalClient(self.config.model_dump())
        else:
            raise ValueError(f"Unsupported storage type: {self.config.type}")

    def list(self, bucket_name: str):
        return self.client.list(bucket_name)

    def upload(
        self, bucket_name: str, dir: str, tar: bool = False, file_name: str = None
    ):
        return self.client.upload(bucket_name, dir, tar, file_name)

    def download(self, bucket_name: str, dir: str):
        return self.client.download(bucket_name, dir)


class S3Client:
    def __init__(self, config):
        self.s3 = boto3.client(
            "s3",
            aws_access_key_id=config["aws_access_key_id"],
            aws_secret_access_key=config["aws_secret_access_key"],
            region_name=config["region"],
        )

    def list(self, bucket_name: str):
        response = self.s3.list_objects_v2(Bucket=bucket_name)
        return [obj["Key"] for obj in response.get("Contents", [])]

    def upload(
        self, bucket_name: str, dir: str, tar: bool = False, file_name: str = None
    ):
        if tar:
            with open(file_name, "rb") as data:
                self.s3.upload_fileobj(data, bucket_name, os.path.basename(file_name))
        else:
            for root, dirs, files in os.walk(dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    self.s3.upload_file(file_path, bucket_name, file)

    def download(self, bucket_name: str, dir: str):
        objects = self.list(bucket_name)
        for obj in objects:
            file_path = os.path.join(dir, obj)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            self.s3.download_file(bucket_name, obj, file_path)


class LocalClient:
    def __init__(self, config):
        self.base_dir = config["base_dir"]

    def list(self, bucket_name: str):
        bucket_path = os.path.join(self.base_dir, bucket_name)
        return [
            os.path.relpath(os.path.join(root, file), bucket_path)
            for root, _, files in os.walk(bucket_path)
            for file in files
        ]

    def upload(
        self, bucket_name: str, dir: str, tar: bool = False, file_name: str = None
    ):
        bucket_path = os.path.join(self.base_dir, bucket_name)
        os.makedirs(bucket_path, exist_ok=True)

        if tar and file_name:
            shutil.copy(file_name, bucket_path)
        else:
            shutil.copytree(dir, bucket_path, dirs_exist_ok=True)

    def download(self, bucket_name: str, dir: str):
        bucket_path = os.path.join(self.base_dir, bucket_name)
        shutil.copytree(bucket_path, dir, dirs_exist_ok=True)
