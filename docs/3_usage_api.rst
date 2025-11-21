..
    Copyright (c) 2024 CRS4

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.


Programmatic Validation
=======================

.. toctree::
    :maxdepth: 5
    :caption: Getting Started

.. toctree::
    :maxdepth: 5
    :caption: Resources

.. include:: ../README.md
    :parser: myst_parser.sphinx_
    :start-line: 121
    :end-line: 162


Metadata-only Validation
------------------------

In addition to full validation, which checks both metadata and data files,
the library also supports metadata-only validation. This is useful when you
want to ensure that the metadata conforms to the expected schema without
checking the actual data files.

To perform metadata-only validation, you can use the `validate_metadata_as_dict` 
from the `rocrate_validator.services` module. This function takes a dictionary
representing the metadata and validates it against a given validation profile. 

.. code-block:: python

    import json
    from rocrate_validator.services import validate_metadata_as_dict

    settings = {
        "profile_identifier": "workflow-ro-crate-1.0"
    }

    with open('tests/data/crates/invalid/0_main_workflow/main_workflow_bad_type/ro-crate-metadata.json', 'r') as f:
        # load the metadata from the JSON file
        rocrate_metadata = json.load(f)
        
        # validate the metadata dictionary
        result = validation_report = validate_metadata_as_dict(rocrate_metadata, settings=settings)

        # process the validation result as needed
        ...
