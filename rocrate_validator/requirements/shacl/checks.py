import json
from timeit import default_timer as timer
from typing import Optional

import rocrate_validator.log as logging
from rocrate_validator.errors import ROCrateMetadataNotFoundError
from rocrate_validator.events import EventType
from rocrate_validator.models import (Requirement, RequirementCheck,
                                      RequirementCheckValidationEvent,
                                      SkipRequirementCheck, ValidationContext)
from rocrate_validator.requirements.shacl.models import Shape
from rocrate_validator.requirements.shacl.utils import make_uris_relative

from .validator import (SHACLValidationAlreadyProcessed,
                        SHACLValidationContext, SHACLValidationContextManager,
                        SHACLValidationSkip, SHACLValidator, SHACLViolation)

logger = logging.getLogger(__name__)


class SHACLCheck(RequirementCheck):
    """
    A SHACL check for a specific shape property
    """

    # Map shape to requirement check instances
    __instances__ = {}

    def __init__(self,
                 requirement: Requirement,
                 shape: Optional[Shape]) -> None:
        self._shape = shape
        # init the check
        super().__init__(requirement,
                         shape.name if shape and shape.name
                         else shape.parent.name if shape.parent
                         else None,
                         shape.description if shape and shape.description
                         else shape.parent.description if shape.parent
                         else None)
        # store the instance
        SHACLCheck.__add_instance__(shape, self)

    @property
    def shape(self) -> Shape:
        return self._shape

    def execute_check(self, context: ValidationContext):
        logger.debug("Starting check %s", self)
        try:
            logger.debug("SHACL Validation of profile %s requirement %s started", self.requirement.profile, self)
            with SHACLValidationContextManager(self, context) as ctx:
                # The check is executed only if the profile is the most specific one
                logger.debug("SHACL Validation of profile %s requirement %s started", self.requirement.profile, self)
                result = self.__do_execute_check__(ctx)
                ctx.current_validation_result = not self in result
                return ctx.current_validation_result
        except SHACLValidationAlreadyProcessed as e:
            logger.debug("SHACL Validation of profile %s already processed", self.requirement.profile)
            # The check belongs to a profile which has already been processed
            # so we can skip the validation and return the specific result for the check
            return not self in [i.check for i in context.result.get_issues()]
        except SHACLValidationSkip as e:
            logger.debug("SHACL Validation of profile %s requirement %s skipped", self.requirement.profile, self)
            # The validation is postponed to the more specific profiles
            # so the check is not considered as failed.
            # We assume that the main algorithm catches the issue
            # and the check is marked as skipped withing the context.result
            raise SkipRequirementCheck(self, str(e))
        except ROCrateMetadataNotFoundError as e:
            logger.debug("Unable to perform metadata validation due to missing metadata file: %s", e)
            return False

    def __do_execute_check__(self, shacl_context: SHACLValidationContext):
        # get the shapes registry
        shapes_registry = shacl_context.shapes_registry

        # set up the input data for the validator
        start_time = timer()
        ontology_graph = shacl_context.ontology_graph
        end_time = timer()
        logger.debug(f"Execution time for getting ontology graph: {end_time - start_time} seconds")

        data_graph = None
        try:
            start_time = timer()
            data_graph = shacl_context.data_graph
            end_time = timer()
            logger.debug(f"Execution time for getting data graph: {end_time - start_time} seconds")
        except json.decoder.JSONDecodeError as e:
            logger.debug("Unable to perform metadata validation due to an error in the JSON-LD data file: %s", e)
            return False

        # Begin the timer
        start_time = timer()
        shapes_graph = shapes_registry.shapes_graph
        end_time = timer()
        logger.debug(f"Execution time for getting shapes: {end_time - start_time} seconds")

        # # uncomment to save the graphs to the logs folder (for debugging purposes)
        # start_time = timer()
        # data_graph.serialize("logs/data_graph.ttl", format="turtle")
        # shapes_graph.serialize("logs/shapes_graph.ttl", format="turtle")
        # if ontology_graph:
        #     ontology_graph.serialize("logs/ontology_graph.ttl", format="turtle")
        # end_time = timer()
        # logger.debug(f"Execution time for saving graphs: {end_time - start_time} seconds")

        # validate the data graph
        start_time = timer()
        shacl_validator = SHACLValidator(shapes_graph=shapes_graph, ont_graph=ontology_graph)
        shacl_result = shacl_validator.validate(
            data_graph=data_graph, ontology_graph=ontology_graph, **shacl_context.settings)
        # parse the validation result
        end_time = timer()
        logger.debug("Validation '%s' conforms: %s", self.name, shacl_result.conforms)
        logger.debug(f"Execution time for validating the data graph: {end_time - start_time} seconds")

        # store the validation result in the context
        start_time = timer()
        result = shacl_result.conforms
        # if the validation fails, process the failed checks
        failed_requirements_checks = []
        failed_requirements_checks_violations: dict[str, SHACLViolation] = {}
        failed_requirement_checks_notified = []
        if not shacl_result.conforms:
            logger.debug("Parsing Validation with result: %s", result)
            # process the failed checks to extract the requirement checks involved
            for violation in shacl_result.violations:
                shape = shapes_registry.get_shape(Shape.compute_key(shapes_graph, violation.sourceShape))
                assert shape is not None, "Unable to map the violation to a shape"
                requirementCheck = SHACLCheck.get_instance(shape)
                assert requirementCheck is not None, "The requirement check cannot be None"
                failed_requirements_checks.append(requirementCheck)
                failed_requirements_checks_violations[requirementCheck.identifier] = violation
        # sort the failed checks by identifier and severity
        # to ensure a consistent order of the issues
        # and to make the fail fast mode deterministic
        for requirementCheck in sorted(failed_requirements_checks, key=lambda x: (x.identifier, x.severity)):
            # add only the issues for the current profile when the `target_profile_only` mode is disabled
            # (issues related to other profiles will be added by the corresponding profile validation)
            violation = failed_requirements_checks_violations[requirementCheck.identifier]
            if requirementCheck.requirement.profile == shacl_context.current_validation_profile or \
                    shacl_context.settings.get("target_only_validation", False):
                c = shacl_context.result.add_check_issue(message=violation.get_result_message(shacl_context.rocrate_path),
                                                         check=requirementCheck,
                                                         severity=violation.get_result_severity(),
                                                         resultPath=violation.resultPath.toPython() if violation.resultPath else None,
                                                         focusNode=make_uris_relative(
                    violation.focusNode.toPython(), shacl_context.publicID),
                    value=violation.value)
                # if the fail fast mode is enabled, stop the validation after the first issue
                if shacl_context.fail_fast:
                    break

            # If the fail fast mode is disabled, notify all the validation issues
            # related to profiles other than the current one.
            # They are issues which have not been notified yet because skipped during
            # the validation of their corresponding profile because SHACL checks are executed
            # all together and not profile by profile
            if not shacl_context.fail_fast:
                if requirementCheck.requirement.profile != shacl_context.current_validation_profile and \
                        not requirementCheck.identifier in failed_requirement_checks_notified:
                    #
                    failed_requirement_checks_notified.append(requirementCheck.identifier)

                    shacl_context.validator.notify(RequirementCheckValidationEvent(
                        EventType.REQUIREMENT_CHECK_VALIDATION_END, requirementCheck, validation_result=False))
                    logger.debug("Added validation issue to the context: %s", c)

        # As above, but for skipped checks which are not failed
        if not shacl_context.fail_fast:
            for requirementCheck in list(shacl_context.result.skipped_checks):
                if not isinstance(requirementCheck, SHACLCheck):
                    continue
                if requirementCheck.requirement.profile != shacl_context.current_validation_profile and \
                        not requirementCheck in failed_requirements_checks and \
                        not requirementCheck.identifier in failed_requirement_checks_notified:
                    failed_requirement_checks_notified.append(requirementCheck.identifier)
                    shacl_context.result.add_executed_check(requirementCheck, True)
                    shacl_context.validator.notify(RequirementCheckValidationEvent(
                        EventType.REQUIREMENT_CHECK_VALIDATION_END, requirementCheck, validation_result=True))

        end_time = timer()
        logger.debug(f"Execution time for parsing the validation result: {end_time - start_time} seconds")

        return failed_requirements_checks

    def __str__(self) -> str:
        return super().__str__() + (f" - {self._shape}" if self._shape else "")

    def __repr__(self) -> str:
        return super().__repr__() + (f" - {self._shape}" if self._shape else "")

    def __eq__(self, __value: object) -> bool:
        if not isinstance(__value, type(self)):
            return NotImplemented
        return super().__eq__(__value) and self._shape == getattr(__value, '_shape', None)

    def __hash__(self) -> int:
        return super().__hash__() + (hash(self._shape) if self._shape else 0)

    @classmethod
    def get_instance(cls, shape: Shape) -> Optional["SHACLCheck"]:
        return cls.__instances__.get(hash(shape), None)

    @classmethod
    def __add_instance__(cls, shape: Shape, check: "SHACLCheck") -> None:
        cls.__instances__[hash(shape)] = check

    @classmethod
    def clear_instances(cls) -> None:
        cls.__instances__.clear()


__all__ = ["SHACLCheck"]
