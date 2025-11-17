import logging
from typing import Any

from griptape_cloud.base.base_griptape_cloud_node import BaseGriptapeCloudNode
from griptape_cloud.buckets.bucket_options import BucketOptions
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import DataNode

logger = logging.getLogger("griptape_nodes")
logger.setLevel(logging.INFO)


class GetBucket(BaseGriptapeCloudNode, DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.buckets = self._list_buckets().buckets
        self.choices = list(map(BucketOptions._bucket_to_name_and_id, self.buckets))

        self.add_parameter(
            Parameter(
                name="bucket_id",
                input_types=["str"],
                output_type="str",
                type="str",
                default_value=self.buckets[0].bucket_id if self.buckets else None,
                traits={
                    BucketOptions(
                        choices=self.choices,
                        choices_value_lookup={BucketOptions._bucket_to_name_and_id(b): b for b in self.buckets},
                    )
                },
                tooltip="The ID of the bucket",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="name",
                input_types=["str"],
                type="str",
                output_type="str",
                default_value=None,
                tooltip="The name of the bucket",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="bucket",
                input_types=["BucketDetail"],
                type="BucketDetail",
                output_type="BucketDetail",
                default_value=None,
                tooltip="The bucket",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def validate_before_workflow_run(self) -> list[Exception] | None:
        exceptions = super().validate_before_workflow_run() or []

        try:
            if not self.get_parameter_value("bucket_id"):
                msg = "Bucket ID is not set. Configure the Node with a valid Griptape Cloud Bucket ID before running."
                exceptions.append(ValueError(msg))

        except Exception as e:
            exceptions.append(e)

        return exceptions if exceptions else None

    def after_value_set(
        self, parameter: Parameter, value: Any, modified_parameters_set: set[str] | None = None
    ) -> None:
        if parameter.name == "bucket_id" and value is not None:
            bucket = next((b for b in self.buckets if b.bucket_id == value), None)
            if bucket is None:
                msg = f"Bucket with ID '{value}' not found."
                logger.error(msg)
                raise ValueError(msg)
            self.set_parameter_value("bucket", bucket)
            self.set_parameter_value("name", bucket.name)
            if modified_parameters_set is not None:
                modified_parameters_set.add("bucket")
                modified_parameters_set.add("name")

    def process(self) -> None:
        pass
