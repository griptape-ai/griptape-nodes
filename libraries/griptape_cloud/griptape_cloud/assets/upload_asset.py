import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast

import requests
from griptape_cloud_client.models.assert_url_operation import AssertUrlOperation

from griptape_cloud.base.base_griptape_cloud_node import BaseGriptapeCloudNode
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode

if TYPE_CHECKING:
    from griptape_cloud_client.models.bucket_detail import BucketDetail

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class UploadAsset(BaseGriptapeCloudNode, ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="bucket",
                input_types=["BucketDetail"],
                type="BucketDetail",
                output_type="BucketDetail",
                default_value=None,
                tooltip="The bucket to upload to",
                allowed_modes={ParameterMode.INPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="file_path",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value=None,
                ui_options={
                    "clickable_file_browser": True,
                    "expander": True,
                    "display_name": "Path to File",
                },
                tooltip="The file path of the asset to upload",
            )
        )

        self.add_parameter(
            Parameter(
                name="content_type",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value="application/octet-stream",
                ui_options={
                    "display_name": "Content Type",
                },
                tooltip="The content type of the asset to upload",
            )
        )

        self.add_parameter(
            Parameter(
                name="asset_name",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value=None,
                tooltip="The name of the asset",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            )
        )

    def validate_before_node_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_node_run() or []

        try:
            if not self.get_parameter_value("bucket"):
                msg = "Bucket is not set. Configure the Node with a valid Griptape Cloud Bucket before running."
                exceptions.append(ValueError(msg))

            if not self.get_parameter_value("asset_name"):
                msg = "Asset name is not set. Configure the Node with a valid asset name before running."
                exceptions.append(ValueError(msg))

            file_path = self.get_parameter_value("file_path")
            if not file_path:
                msg = "File path is not set. Configure the Node with a valid file path before running."
                exceptions.append(ValueError(msg))
            elif not Path(file_path).exists():
                msg = f"File does not exist at path: {file_path}"
                exceptions.append(FileNotFoundError(msg))

            cast("BucketDetail", self.get_parameter_value("bucket"))

        except Exception as e:
            exceptions.append(e)

        return exceptions if exceptions else None

    def _process(self) -> None:
        bucket = cast("BucketDetail", self.get_parameter_value("bucket"))
        asset_name = self.get_parameter_value("asset_name")
        file_path = self.get_parameter_value("file_path")
        content_type = self.get_parameter_value("content_type")

        if bucket and asset_name and file_path:
            try:
                self._create_asset(
                    asset_name=asset_name,
                    bucket_id=bucket.bucket_id,
                )
                upload_url_response = self._create_asset_url(asset_name, bucket.bucket_id, AssertUrlOperation.PUT)

                with Path(file_path).open("rb") as file:
                    headers = upload_url_response.headers.to_dict() or {}
                    headers["Content-Type"] = content_type
                    upload_response = requests.put(upload_url_response.url, data=file, headers=headers, timeout=300)
                    upload_response.raise_for_status()

                self.parameter_output_values["asset_name"] = asset_name

                logger.info("Successfully uploaded asset %s to bucket %s", asset_name, bucket.bucket_id)

            except Exception as e:
                logger.error("Error uploading asset: %s", e)
                raise

    def process(self) -> AsyncResult[None]:
        yield lambda: self._process()
