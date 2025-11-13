import json

import rocrate_validator.log as logging
from rocrate_validator.io.output.console import Console
from rocrate_validator.models import (AggregatedValidationStatistics,
                                      CustomEncoder, ValidationResult,
                                      ValidationStatistics)
from rocrate_validator.utils import get_version

# set up logging
logger = logging.getLogger(__name__)


def format_validation_result(data: ValidationResult,
                             console: Console = None,
                             settings: dict = None) -> str:
    return format_validation_results({data.profile.identifier: data}, console=console, settings=settings)


def format_validation_results(data: dict[str, ValidationResult],
                              console: Console = None,
                              settings: dict = None) -> str:

    # Initialize an empty JSON output
    json_output = {
        "meta": {
            "generated_by": "rocrate-validator",
            "version": get_version(),
        }
    }

    # Return empty JSON if no data is provided
    if not data or len(data) == 0:
        return json.dumps(json_output, indent=4, cls=CustomEncoder)

    # Determine verbosity from settings
    verbose = settings.get("verbose", False) if settings else False

    # Extract results from the profile -> ValidationResult mapping
    results = list(data.values())

    # Initialize validation settings
    settings = results[0].validation_settings
    json_output["validation_settings"] = settings.to_dict()

    # Set the list of validation profiles
    json_output["validation_settings"]["profile_identifiers"] = [
        profile_identifier for profile_identifier in data.keys()
    ]

    # Initialize the overall passed status
    json_output["passed"] = True

    # Initialize the profile results dictionary
    _RESULTS_KEY = "validation_results_by_profile"
    if verbose:
        json_output[_RESULTS_KEY] = {}

    # Iterate over each validation result
    for profile_identifier, result in data.items():
        result_dict = result.to_dict()
        # Remove the validation settings from the individual result
        result_dict.pop("validation_settings", None)
        # Add statistics if available
        if verbose and result.statistics:
            result_dict["statistics"] = result.statistics.to_dict()
        # Add the result to the profiles dictionary in verbose mode
        if verbose:
            json_output[_RESULTS_KEY][profile_identifier] = result_dict
        # Update the overall passed status
        json_output["passed"] = json_output["passed"] and result.passed()
        # Update the overall list of issues
        if "issues" not in json_output:
            json_output["issues"] = []
        json_output["issues"].extend(result_dict.get("issues", []))

    # Add overall statistics
    stats = AggregatedValidationStatistics([r.statistics for r in results if r.statistics])
    if stats:
        stats_dict = stats.to_dict()
        # If not verbose, remove detailed lists from statistics
        if not verbose:
            for key in ["passed_requirements", "failed_requirements",
                        "passed_checks", "failed_checks", "checks", "requirements"]:
                if key in stats_dict:
                    stats_dict.pop(key, None)
        json_output["statistics"] = stats_dict

    # Return the formatted JSON output
    return json.dumps(json_output, indent=4, cls=CustomEncoder)


def format_validation_statistics(data: ValidationStatistics,
                                 console: Console = None,
                                 settings: dict = None) -> str:
    return json.dumps(data.to_dict(), indent=4, cls=CustomEncoder)
