import os
import pathlib
import shutil
import asyncio
from typing import Annotated, Optional, Union, Dict
from abc import ABC, abstractmethod
import boto3.exceptions
import boto3.s3
from pydantic import BaseModel, DirectoryPath, constr
import boto3
import botocore
import aiofiles
from aioboto3 import Session


class StorageClient(ABC):
    def __init__(self, config: Dict[str, str]):
        self.config = config

    @abstractmethod
    def list(self, bucket_name: str):
        pass

    @abstractmethod
    def upload(
        self, bucket_name: str, dir: str, tar: bool = False, file_name: str = None
    ):
        pass

    @abstractmethod
    def download(self, bucket_name: str, dir: str):
        pass


class S3Client(StorageClient):
    def __init__(self, config):
        super().__init__(config)
        self.session = Session()

    def _get_client(self):
        # attempt to initialize client (within k8s)
        try:
            return boto3.client(
                "s3",
            )
        except botocore.exceptions.PartialCredentialsError as e:
            return boto3.client(
                "s3",
                aws_access_key_id=self.config["aws_access_key_id"],
                aws_secret_access_key=self.config["aws_secret_access_key"],
                region_name=self.config["region"],
            )

    def list(self, bucket_name: str):
        with self._get_client() as s3:
            response = s3.list_objects_v2(Bucket=bucket_name, Prefix="snapshots/")
            return [obj["Key"] for obj in response.get("Contents", [])]

    def upload(
        self, bucket_name: str, dir: str, tar: bool = False, file_name: str = None
    ):
        with self._get_client() as s3:
            if tar:
                with aiofiles.open(file_name, "rb") as data:
                    s3.upload_fileobj(data, bucket_name, os.path.basename(file_name))
            else:
                for root, dirs, files in os.walk(dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        s3.upload_file(file_path, bucket_name, file)

    def download(self, bucket_name: str, dir: str):
        with self._get_client() as s3:
            objects = self.list(bucket_name)
            for obj in objects:
                file_path = os.path.join(dir, obj)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                s3.download_file(bucket_name, obj, file_path)


class LocalClient(StorageClient):
    def __init__(self, config):
        super().__init__(config)
        self.base_dir = pathlib.Path(config["base_dir"])

    def list(self, bucket_name: str, prefix: str = "snapshots"):
        bucket_path = self.base_dir / bucket_name / prefix
        return [
            os.path.relpath(os.path.join(root, file), bucket_path)
            for root, _, files in os.walk(bucket_path)
            for file in files
        ]

    def upload(
        self,
        bucket_name: str,
        # data: str = None,
        dir: str,
        tar: bool = False,
        file_name: str = None,
    ):
        bucket_path = os.path.join(self.base_dir, bucket_name)
        os.makedirs(bucket_path, exist_ok=True)
        print(f"Uploading to {bucket_path}...")
        # print("available args: ", data, dir, tar, file_name)
        if tar and file_name:
            with open(file_name, "rb") as source_file:
                with open(
                    os.path.join(bucket_path, os.path.basename(file_name)), "wb"
                ) as dest_file:
                    dest_file.write(source_file.read())
        # if data and file_name:
        #     with open(
        #         os.path.join(bucket_path, os.path.basename(file_name)), "w"
        #     ) as dest_file:
        #         dest_file.write(data)
        else:
            shutil.copytree(dir, bucket_path, dirs_exist_ok=True)

    def download(self, bucket_name: str, dir: str):
        bucket_path = os.path.join(self.base_dir, bucket_name)
        shutil.copytree(bucket_path, dir, dirs_exist_ok=True)


class S3ClientConfig(BaseModel):
    aws_access_key_id: Annotated[str, constr(min_length=1)] = ""
    aws_secret_access_key: Annotated[str, constr(min_length=1)] = ""
    region: Annotated[str, constr(min_length=1)] = "us-east-1"


class LocalClientConfig(BaseModel):
    base_dir: DirectoryPath = "/tmp"


class StorageManagerConfig(BaseModel):
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


class StorageManager:
    def __init__(self, config: dict = {}):
        validated_config = StorageManagerConfig(**config)
        self.config = validated_config.get_client_config()
        self.client = self._initialize_client()

    def _initialize_client(self) -> StorageClient:
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
        print(f"Uploading to {bucket_name}...")
        return self.client.upload(bucket_name, dir, tar, file_name)

    def download(self, bucket_name: str, dir: str):
        return self.client.download(bucket_name, dir)
