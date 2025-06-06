# Copyright (c) 2024-2025 CRS4
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from pathlib import Path
from typing import Optional

from rdflib import RDF

import rocrate_validator.log as logging
from rocrate_validator.constants import VALIDATOR_NS
from rocrate_validator.models import (Profile, Requirement, RequirementCheck,
                                      RequirementLevel, RequirementLoader)
from rocrate_validator.requirements.shacl.checks import SHACLCheck
from rocrate_validator.requirements.shacl.models import Shape, ShapesRegistry

# set up logging
logger = logging.getLogger(__name__)


class SHACLRequirement(Requirement):

    def __init__(self,
                 shape: Shape,
                 profile: Profile,
                 path: Path):
        self._shape = shape
        super().__init__(profile,
                         shape.name if shape.name else "",
                         shape.description if shape.description else "",
                         path)
        # init checks
        self._checks = self.__init_checks__()
        # assign check IDs
        self.__reorder_checks__()

    def __reorder_checks__(self) -> None:
        i = 0
        for check in self._checks:
            check.order_number = i
            i += 1

    def __init_checks__(self) -> list[RequirementCheck]:
        # check if the shape is not None before creating checks
        assert self.shape is not None, "The shape cannot be None"
        assert self.shape.node is not None, "The shape node cannot be None"
        # assign a check to each property of the shape
        checks = []
        # check if the shape has nested properties
        has_properties = hasattr(self.shape, "properties") and len(self.shape.properties) > 0
        # create a check for the shape itself, hidden if the shape has nested properties
        checks.append(SHACLCheck(self, self.shape, name=f"Check {self.shape.name}" if has_properties else None,
                                 hidden=has_properties, root=True))
        # create a check for each property if the shape has nested properties
        if has_properties:
            for prop in self.shape.properties:
                logger.debug("Creating check for property %s %s", prop.name, prop.description)
                property_check = SHACLCheck(self, prop)
                logger.debug("Property check %s: %s", property_check.name, property_check.description)
                checks.append(property_check)

        return checks

    @property
    def shape(self) -> Shape:
        return self._shape

    @property
    def hidden(self) -> bool:
        if self.shape.node is not None:
            if (self.shape.node, RDF.type, VALIDATOR_NS.HiddenShape) in self.shape.graph:
                return True
        return False


class SHACLRequirementLoader(RequirementLoader):

    def __init__(self, profile: Profile):
        super().__init__(profile)
        self._shape_registry = ShapesRegistry.get_instance(profile)
        # reset the shapes registry
        self._shape_registry.clear()  # should be removed

    @property
    def shapes_registry(self) -> ShapesRegistry:
        return self._shape_registry

    def load(self, profile: Profile,
             requirement_level: RequirementLevel,
             file_path: Path, publicID: Optional[str] = None) -> list[Requirement]:
        assert file_path is not None, "The file path cannot be None"
        shapes: list[Shape] = self.shapes_registry.load_shapes(file_path, publicID)
        logger.debug("Loaded %s shapes: %s", len(shapes), shapes)
        requirements = []
        for shape in shapes:
            if shape is not None and shape.level >= requirement_level:
                requirements.append(SHACLRequirement(shape, profile, file_path))
        return requirements
