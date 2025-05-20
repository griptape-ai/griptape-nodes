import logging

from diffusers_nodes_library.pipelines.flux.diptych_flux_fill_pipeline_parameters import (
    DiptychFluxFillPipelineParameters,  # type: ignore[reportMissingImports]
)
from diffusers_nodes_library.pipelines.flux.flux_fill_pipeline import FluxFillPipeline
from diffusers_nodes_library.pipelines.flux.flux_fill_pipeline_parameters import (
    FluxFillPipelineParameters,
)

logger = logging.getLogger("diffusers_nodes_library")


class DiptychFluxFillPipeline(FluxFillPipeline):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    def get_pipe_params(self) -> FluxFillPipelineParameters | DiptychFluxFillPipelineParameters:
        return DiptychFluxFillPipelineParameters(self)
