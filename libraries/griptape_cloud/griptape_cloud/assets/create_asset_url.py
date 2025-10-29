import logging
from typing import TYPE_CHECKING, cast

from griptape_cloud_client.models.assert_url_operation import AssertUrlOperation

from griptape_cloud.base.base_griptape_cloud_node import BaseGriptapeCloudNode
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import ControlNode
from griptape_nodes.traits.options import Options

if TYPE_CHECKING:
    from griptape_cloud_client.models.bucket_detail import BucketDetail

logger = logging.getLogger("griptape_nodes")
logger.setLevel(logging.INFO)


class CreateAssetUrl(BaseGriptapeCloudNode, ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="bucket",
                input_types=["BucketDetail"],
                type="BucketDetail",
                output_type="BucketDetail",
                default_value=None,
                tooltip="The bucket to create asset URL for",
                allowed_modes={ParameterMode.INPUT},
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

        self.add_parameter(
            Parameter(
                name="operation",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value=AssertUrlOperation.GET.value,
                tooltip="The URL operation to perform",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={
                    Options(
                        choices=[op.value for op in AssertUrlOperation],
                    )
                },
            )
        )

        self.add_parameter(
            Parameter(
                name="asset_url",
                type="str",
                output_type="str",
                default_value=None,
                tooltip="The URL of the asset",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def validate_before_workflow_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_workflow_run() or []

        try:
            if not self.get_parameter_value("bucket"):
                msg = "Bucket is not set. Configure the Node with a valid Griptape Cloud Bucket before running."
                exceptions.append(ValueError(msg))

            if not self.get_parameter_value("asset_name"):
                msg = "Asset name is not set. Configure the Node with a valid asset name before running."
                exceptions.append(ValueError(msg))

            cast("BucketDetail", self.get_parameter_value("bucket"))

        except Exception as e:
            exceptions.append(e)

        # if there are exceptions, they will display when the user tries to run the flow with the node.
        return exceptions if exceptions else None

    def process(self) -> None:
        bucket = cast("BucketDetail", self.get_parameter_value("bucket"))
        asset_name = self.get_parameter_value("asset_name")
        operation = self.get_parameter_value("operation")

        if bucket and asset_name:
            response = self._create_asset_url(asset_name, bucket.bucket_id, AssertUrlOperation(operation))
            self.set_parameter_value("asset_url", response.url)
            self.parameter_output_values["asset_url"] = response.url
