from griptape.drivers.structure_run.base_structure_run_driver import BaseStructureRunDriver
from griptape.drivers.structure_run.griptape_cloud_structure_run_driver import GriptapeCloudStructureRunDriver
from griptape.drivers.structure_run.local_structure_run_driver import LocalStructureRunDriver
from griptape.mixins.serializable_mixin import SerializableMixin

# This file grants griptape classes the SerializableMixin
# to allow them to be serialized and deserialized.


class GtBaseStructureRunDriver(BaseStructureRunDriver, SerializableMixin):
    pass


class GtLocalStructureRunDriver(LocalStructureRunDriver, GtBaseStructureRunDriver):
    pass


class GtGriptapeCloudStructureRunDriver(GriptapeCloudStructureRunDriver, GtBaseStructureRunDriver):
    pass
