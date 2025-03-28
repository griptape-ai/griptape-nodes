import os
import time

import requests
from griptape.drivers import GriptapeCloudFileManagerDriver

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, ParameterUIOptions
from griptape_nodes.exe_types.node_types import ControlNode


class ComfyUIImageGenerationNode(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Need to define the category
        self.category = "Comfy"
        self.description = "Run the ComfyUI Image Generation Flow"

        prompt_parameter = Parameter(
            name="prompt",
            input_types=["str"],
            output_type="str",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value="Capybara on the beach",
            ui_options=ParameterUIOptions(
                string_type_options=ParameterUIOptions.StringType(
                    multiline=True, placeholder_text="Enter your prompt here"
                )
            ),
            tooltip="The prompt for the image you want to generate.",
        )
        output_parameter = Parameter(
            name="output",
            input_types=["dict"],
            output_type="dict",
            allowed_modes={ParameterMode.OUTPUT},
            ui_options=ParameterUIOptions(
                string_type_options=ParameterUIOptions.StringType(
                    multiline=True, placeholder_text="Path to the generated file"
                )
            ),
            tooltip="The path to the image you want to generate.",
        )
        self.add_parameter(prompt_parameter)
        self.add_parameter(output_parameter)

    def process(self) -> None:
        time.sleep(10)
        self.parameter_output_values["output"] = {
            "asset_url": "https://cloud.griptape.ai/api/buckets/0919f587-226c-4552-b06a-01076b59b863/assets/output_2025-03-13_14-58-24.png",
            "asset_name": "output_2025-03-13_14-58-24.png",
            "asset_path": "/api/buckets/0919f587-226c-4552-b06a-01076b59b863/assets/output_2025-03-13_14-58-24.png",
        }


class ComfyUIFluxWorkflowNode(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Need to define the category
        self.category = "Comfy"
        self.description = "Run the ComfyUI Flux Workflow"

        prompt_parameter = Parameter(
            name="prompt",
            allowed_types=["str"],
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value="Capybara on the beach",
            ui_options=ParameterUIOptions(
                string_type_options=ParameterUIOptions.StringType(
                    multiline=True, placeholder_text="Enter your prompt here"
                )
            ),
            tooltip="The prompt for the image you want to generate.",
        )
        output_parameter = Parameter(
            name="output",
            allowed_types=["dict"],
            allowed_modes={ParameterMode.OUTPUT},
            ui_options=ParameterUIOptions(
                string_type_options=ParameterUIOptions.StringType(
                    multiline=True, placeholder_text="Path to the generated file"
                )
            ),
            tooltip="The path to the image you want to generate.",
        )
        self.add_parameter(prompt_parameter)
        self.add_parameter(output_parameter)

    def process(self) -> None:
        prompt = self.parameter_values.get("prompt", None)
        api_key = os.getenv("GT_CLOUD_API_KEY")

        final_output = None
        if prompt and api_key:
            structure_id = "c71410d1-f773-4a62-b573-420593489618"
            run_url = f"https://cloud.griptape.ai/api/structures/{structure_id}/runs"
            headers = {"Authorization": f"Bearer {api_key}"}
            args = {"args": [prompt]}
            response = requests.post(url=run_url, headers=headers, json=args, timeout=30)
            response.raise_for_status()
            data = response.json()
            if response.status_code == requests.codes.created:
                structure_run_id = data["structure_run_id"]
                # now get events until a finishedstructurerunevent
                event_url = f"https://cloud.griptape.ai/api/structure-runs/{structure_run_id}/events"
                offset = 0
                limit = 100
                finished = False
                while not finished:
                    time.sleep(10)
                    params = {"offset": offset, "limit": limit}
                    response = requests.get(url=event_url, headers=headers, params=params, timeout=30)
                    response.raise_for_status()
                    data = response.json()
                    events = data["events"]
                    for event in events:
                        if event["type"] == "FinishStructureRunEvent":
                            finished = True
                            final_output = event["payload"]["output_task_output"]["value"]
                            break
                        if event["type"] == "StructureRunCompleted":
                            if event["payload"]["status"] == "FAILED":
                                final_output = f"Structure Run Failed. Error: {event['payload']}"
                                finished = True
                                self.stop_flow = True
                                break
                            if event["payload"]["status"] == "CANCELLED":
                                final_output = f"Structure Run Cancelled. Error: {event['payload']}"
                                finished = True
                                self.stop_flow = True
                                break
                            if event["payload"]["status"] == "SUCCEEDED":
                                # get to the finished structure run event please
                                continue
                            final_output = "Unknown error occurred"
                            finished = True
                            self.stop_flow = True
                            break

                    offset = data["next_offset"]
                self.parameter_output_values["output"] = final_output
                print(final_output)
                return
            self.parameter_output_values["output"] = {"ERROR!": "Something failed. Exception."}


class ComfyUIPhotographerComparison(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Need to define the category
        self.category = "Comfy"
        self.description = "Run the ComfyUI Photographer Comparison Workflow"

        prompt_parameter = Parameter(
            name="prompt",
            allowed_types=["str"],
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            default_value="Dinosaur in the Jungle",
            ui_options=ParameterUIOptions(
                string_type_options=ParameterUIOptions.StringType(
                    multiline=True, placeholder_text="Enter your prompt here"
                )
            ),
            tooltip="The prompt for the image you want to generate.",
        )
        output_parameter = Parameter(
            name="output",
            allowed_types=["dict"],
            allowed_modes={ParameterMode.OUTPUT},
            ui_options=ParameterUIOptions(
                string_type_options=ParameterUIOptions.StringType(
                    multiline=True, placeholder_text="Path to the generated file"
                )
            ),
            tooltip="The path to the image you want to generate.",
        )
        self.add_parameter(prompt_parameter)
        self.add_parameter(output_parameter)

    def process(self) -> None:
        # Get input values
        prompt = self.parameter_values.get("prompt", None)
        api_key = os.getenv("GT_CLOUD_API_KEY")
        final_output = None
        if prompt and api_key:
            structure_id = "71998a96-30c0-42ce-930f-13b0ea0e3e00"
            run_url = f"https://cloud.griptape.ai/api/structures/{structure_id}/runs"
            headers = {"Authorization": f"Bearer {api_key}"}
            args = {"args": [prompt]}
            response = requests.post(url=run_url, headers=headers, json=args, timeout=30)
            response.raise_for_status()
            data = response.json()
            if response.status_code == requests.codes.created:
                structure_run_id = data["structure_run_id"]
                # now get events until a finishedstructurerunevent
                event_url = f"https://cloud.griptape.ai/api/structure-runs/{structure_run_id}/events"
                offset = 0
                limit = 100
                finished = False
                while not finished:
                    time.sleep(10)
                    params = {"offset": offset, "limit": limit}
                    response = requests.get(url=event_url, headers=headers, params=params, timeout=30)
                    response.raise_for_status()
                    data = response.json()
                    events = data["events"]
                    for event in events:
                        if event["type"] == "FinishStructureRunEvent":
                            finished = True
                            final_output = event["payload"]["output_task_output"]["value"]
                            break
                        if event["type"] == "StructureRunCompleted":
                            if event["payload"]["status"] == "FAILED":
                                final_output = f"Structure Run Failed. Error: {event['payload']}"
                                finished = True
                                self.stop_flow = True
                                break
                            if event["payload"]["status"] == "CANCELLED":
                                final_output = f"Structure Run Cancelled. Error: {event['payload']}"
                                finished = True
                                self.stop_flow = True
                                break
                            if event["payload"]["status"] == "SUCCEEDED":
                                # get to the finished structure run event please
                                continue
                            final_output = "Unknown error occurred"
                            finished = True
                            self.stop_flow = True
                            break

                    offset = data["next_offset"]
                self.parameter_output_values["output"] = final_output
                return
        self.parameter_output_values["output"] = {"ERROR!": "Something failed. Exception."}
        self.stop_flow = True


class LoadFileFromDataLakeNode(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Need to define the category
        self.category = "Comfy"
        self.description = "Load an asset from a data lake"
        asset_paths = Parameter(
            name="asset_path",
            allowed_types=["str", "dict"],
            ui_options=ParameterUIOptions(
                string_type_options=ParameterUIOptions.StringType(
                    multiline=True, placeholder_text="Enter your prompt here"
                )
            ),
            tooltip="The asset path to the bucket you want",
            allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
        )
        file_parameter = Parameter(
            name="output",
            allowed_types=["ImageArtifact", "BlobArtifact"],
            allowed_modes={ParameterMode.OUTPUT},
            ui_options=ParameterUIOptions(
                string_type_options=ParameterUIOptions.StringType(multiline=True, placeholder_text="Image created")
            ),
            tooltip="The image that has been generated.",
        )
        self.add_parameter(asset_paths)
        self.add_parameter(file_parameter)
        # Add input parameter for model selection

    def get_bucket_and_file(self, path: str) -> tuple:
        try:
            # Split the path by "/"
            parts = path.split("/")

            # Find the index of "buckets" in the parts
            buckets_index = parts.index("buckets")

            # The bucket ID is the next element after "buckets"
            bucket_id = parts[buckets_index + 1]

            # Find the index of "assets" in the parts
            assets_index = parts.index("assets")

            # The file path is everything after "assets", joined with "/"
            file_path = "/" + "/".join(parts[assets_index + 1 :])

        except (ValueError, IndexError) as e:
            msg = "Invalid path format. Expected 'i/buckets/{bucket_id}/assets/{filename}'"
            raise ValueError(msg) from e
        else:
            return bucket_id, file_path

    def process(self) -> None:
        # Get input values
        api_key = os.getenv("GT_CLOUD_API_KEY")
        asset_path = self.parameter_values.get("asset_path")
        file_path = None
        if api_key and asset_path:
            if isinstance(asset_path, dict):
                if "asset_path" in asset_path:
                    file_path = str(asset_path["asset_path"])
                else:
                    msg = "Invalid asset path format. Expected 'asset_path' key in the dictionary."
                    raise ValueError(msg)
            else:
                file_path = asset_path
            if file_path:
                try:
                    bucket, file = self.get_bucket_and_file(file_path)
                    driver = GriptapeCloudFileManagerDriver(api_key=api_key, bucket_id=bucket)
                    results = driver.load_file(file)
                    self.parameter_output_values["output"] = results
                except Exception as e:
                    print(f"There was an exception. {e}")
