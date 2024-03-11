
import logging
from typing import Optional

from ...constants import SHACL_NS
from ...models import Check as BaseCheck
from ...models import Requirement, Validator
from .validator import Validator as SHACLValidator

logger = logging.getLogger(__name__)


class SHACLCheck(BaseCheck):
    def __init__(self,
                 requirement: Requirement,
                 validator: Validator,
                 name: Optional[str] = None,
                 description: Optional[str] = None,
                 ) -> None:
        super().__init__(requirement, validator, name, description)

    @property
    def name(self):
        if not self._name and self.shapes_graph is None:
            return "SHACL Check"

        if not self._name:
            query = """
                SELECT ?name
                WHERE {
                    ?shape a sh:NodeShape ;
                        sh:name ?name .
                }
            """
            # Execute the query
            results = [_ for _ in self.shapes_graph.query(query, initNs={"sh": SHACL_NS})]
            if results:
                self._name = results[0][0]

        return self._name

    @property
    def description(self):
        if not self._description and self.shapes_graph is None:
            return "SHACL Check"

        if not self._description:
            # Query to get the description of the shape
            query = """
                SELECT ?description
                WHERE {
                    ?shape a sh:NodeShape ;
                        sh:description ?description .
                }
            """
            # Execute the query
            results = [_ for _ in self.shapes_graph.query(query, initNs={"sh": SHACL_NS})]
            if results:
                self._description = results[0][0]

        return self._description

    @property
    def shapes_graph(self):
        return self.validator.get_graph_of_shapes(self.requirement.name)

    def check(self):
        shapes_graph = self.shapes_graph
        ontology_graph = self.validator.ontologies_graph
        data_graph = self.validator.data_graph

        shacl_validator = SHACLValidator(
            shapes_graph=shapes_graph, ont_graph=ontology_graph)
        result = shacl_validator.validate(
            data_graph=data_graph,
            **self.validator.validation_settings
        )
        logger.debug("Validation conforms: %s", result.conforms)
        if not result.conforms:
            logger.debug("Validation failed")
            logger.debug("Validation result: %s", result)
            for issue in result.violations:
                logger.debug("Validation issue: %s", issue.message)
                self.result.add_issue(issue)

            return False
        return True