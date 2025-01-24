# Copyright (c) 2024 CRS4
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

import rocrate_validator.log as logging
from rocrate_validator.models import ValidationContext
from rocrate_validator.requirements.python import (PyFunctionCheck, check,
                                                   requirement)

# set up logging
logger = logging.getLogger(__name__)


@requirement(name="Data Entity: REQUIRED resource availability")
class DataEntityRequiredChecker(PyFunctionCheck):
    """
    Data Entity instances MUST be present within the RO-Crate
    """

    @check(name="Data Entity: REQUIRED resource availability")
    def check_availability(self, context: ValidationContext) -> bool:
        """
        Check if the presence of the Data Entity within the RO-Crate
        """
        result = True
        for entity in context.ro_crate.metadata.get_data_entities(exclude_web_data_entities=True):
            assert entity.id is not None, "Entity has no @id"
            logger.debug("Ensure the presence of the Data Entity '%s' within the RO-Crate", entity.id)
            try:
                logger.debug("Ensure the presence of the Data Entity '%s' within the RO-Crate", entity.id)
                if not entity.is_available():
                    context.result.add_issue(
                        f"The RO-Crate does not include the Data Entity '{entity.id}' as part of its payload", self)
                    result = False
            except Exception as e:
                context.result.add_issue(
                    f"Unable to check the the presence of the Data Entity '{entity.id}' within the RO-Crate", self)
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(e, exc_info=True)
                result = False
            if not result and context.fail_fast:
                return result
        return result
