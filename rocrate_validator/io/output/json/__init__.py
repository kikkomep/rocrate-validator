
from typing import Optional
import rocrate_validator.log as logging
from rocrate_validator.io.output.console import Console
from rocrate_validator.io.output import BaseOutputFormatter
from rocrate_validator.io.output.json.formatters import (
    format_validation_results, format_validation_statistics)
from rocrate_validator.io.output.text.formatters import \
    format_validation_result
from rocrate_validator.models import (ValidationResult,
                                      ValidationStatistics)

# set up logging
logger = logging.getLogger(__name__)


class JSONOutputFormatter(BaseOutputFormatter):

    def __init__(self,
                 console: Optional[Console] = None,
                 settings: dict = None,):
        super().__init__(console=console, settings=settings)
        self.add_type_formatter(ValidationResult, format_validation_result)
        self.add_type_formatter(dict, format_validation_results)
        self.add_type_formatter(ValidationStatistics, format_validation_statistics)
