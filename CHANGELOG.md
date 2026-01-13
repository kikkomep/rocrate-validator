# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.8.0] - 2026-01-07

### Added

- :white_check_mark: add unit test
- :sparkles: add support for overrides to the `Profile` model
- :sparkles: add utility method to shorten a given path
- :sparkles: add internal utility to shorten paths
- :sparkles: add support for `extra-profiles-path` option in `profile` command
- :sparkles: add support for the `extra-profiles-paths` in the `validate` process
- :sparkles: add support for the `extra-profiles-path` option in the `validate` command
- :test_tube: add unit tests for the `services` module
- :sparkles: add notes on custom validation profiles
- :sparkles: add method to identity dataset and file entities
- :sparkles: add support for relative root path
- :sparkles: add classes for handling BagIt-wrapped RO-Crates
- :sparkles: add factory method to automatically instantiate RO-Crate with the correct subtype
- :white_check_mark: add test data: BagIt folder and BagIt ZIP archive
- :white_check_mark: add unit tests
- :white_check_mark: add integration test for remote RO-Crate
- :sparkles: add support for relative root path option
- :sparkles: add a service method to validate RO-Crate metadata from a dict
- :memo: add notes about programmatic metadata-only validation
- :sparkles: add model classes to explicitly represent validation stats
- :zap: add base output classes
- :sparkles: add classes to format output (results and stats) as text
- :sparkles: add classes to format output (results and stats) as JSON
- :sparkles: add a verbose property to the ValidationSettings class
- :memo: add some note about output formatters
- :memo: add note about ontology graph support and formal definitions
- Add CITATION.cff
- Add Eli and Daniel to authors in CITATION.cff
- Add testing workflow for spell checking
- Add typos to poetry

### Fixed

- :pencil2: fix typo
- :bug: fix unit test assertion
- :art: fix missing whitespaces
- :bug: catch exceptions when destroying a Zip RO-Crate
- :bug: fix missing import
- :rotating_light: fix missing blank line
- :rotating_light: fix linter warning E501
- :rotating_light: fix linter warning E999
- :rotating_light: fix linter warnings W{2,3}91
- :bug: fix initialisation of BagIt objects
- :bug: fix fallback value for root path
- :bug: fix initialisation of BagItROCrate objects
- :bug: use the custom class for remote BagIt RO-Crate objects
- :ambulance: fix availability check of external resources
- :bug: fix RO-Crate path
- :white_check_mark: fix and extend test data
- :bug: fix crate path
- :white_check_mark: fix and extend unit tests
- :rotating_light: fix E713
- :bug: fix test data path
- :rotating_light: fix E999 warning
- :bug: allow initialization of the report layout without an initial state
- Fix import
- :lipstick: fix missing padding
- :adhesive_bandage: restructure logic to process CLI text output of validation result
- :bug: fix formatter parameter
- :recycle: revise logic to detect profile overrides
- :ambulance: fix SHACL nodeKind constraint being too strict
- Fix some typos
- Fix with typos package
- Fix typo in tests
- Fix bug

### Removed

- :bug: remove overridden profiles only if they are already loaded
- :lipstick: remove padding when using using no color console

### Ci

- :lipstick: force color output in CI
- :wrench: Explicitly configure the terminal in CI to avoid issues with assertions on output

### Docs

- :memo: improve description of the `skip-checks` option
- :memo: rephrase `--skip-checks` option description
- :memo: update docs

### Feat

- :sparkles: improve parsing of the `--skip-checks` option
- :sparkles: extend flat JSON-LD check to support value objects
- Extend flat JSON-LD check to support value objects
- :zap: automatically detect overrides during Profile initialization
- :sparkles: extend profiles loader to handle an extra loading path
- :sparkles: extend services to support the extra profiles loading path
- :sparkles: extend profile description to include name and overrides info
- :children_crossing: improve profile loading when the `disable-profile-inheritance` is enabled
- :sparkles: allow to use strings as URIs
- :sparkles: always parse the path before processing it
- :bug: detect and notify access to nonexistent files
- :sparkles: extend Settings model to support metadata only evaluation
- :sparkles: skip file-dependent Python checks when validating metadata only
- :sparkles: extend CLI with the `metadata_only` option
- :sparkles: allow instantiating metadata-only RO-Crates
- :sparkles: allow to access stats from the result object
- :sparkles: extend Context to store the target_validation_profile
- :sparkles: update event notifier to properly update validation stats
- :sparkles: extend Event model to pass the validation context
- :sparkles: restructure and improve CLI output
- :sparkles: extend Stats model to store the validate {profiles, requirements, checks}
- :sparkles: initialize the report layout from the current stats
- :sparkles: detect environment and properly handle Console initialization
- :sparkles: disable interactive mode when running in Jupyter
- :sparkles: issue a warning if RO-Crate references a profile that can't be validated

### Refactor

- :truck: rename internal method to load a single Profile instance
- :recycle: refactor entity availability check with generic ZIP support and path unquoting
- :recycle: improve file and directory availability checks
- :recycle: restructure utility methods
- :art: refactor parse_path methods
- :recycle: move profile finder to the Profile class
- :adhesive_bandage: update serialisation of ValidationSettings instances
- :recycle: move input methods to the `io.input` module
- :recycle: move the Pager class to a dedicated module
- :recycle: Move and extend the base class to handle console output
- :recycle: restructure and simplify the formatter classes
- :recycle: simplify Console class
- :recycle: restructure CLI output handling logic
- :recycle: rename formatting classes
- :recycle: refine logic to detect Jupyter environment
- :recycle: convert utils module into a package
- :truck: move rocv_io into the utils package
- :truck: rename `rocv_io` to `io_helpers`
- :building_construction: reorganize the `utils` package structure

## [0.7.2] - 2025-06-19

### Build

- :sparkles: adjust dependency version ranges for better flexibility

## [0.7.1] - 2025-05-20

### Build

- :arrow_up: upgrade dependencies

## [0.7.0] - 2025-05-16

### Feat

- :sparkles: including files with local identifiers in the crate is not mandatory
- :sparkles: exclude from the definition of File Data Entities any file with a local identifier
- :sparkles: update filter to exclude File entities with local identifiers
- ✨ exclude from the definition of Dataset Data Entities any dataset with a local identifier
- :sparkles: only exclude fragment identifiers that refer to the root data entity

### Refactor

- :sparkles: refactor Python detection of local identifiers

## [0.6.5] - 2025-04-30

### Fixed

- :bug: keep track of the checks that have been notified
- :bug: do not skip overridden checks of the target profile
- :building_construction: fix issue notifications
- :bug: fix return value of SHACL requirement check

### Feat

- :sparkles: allow avoiding duplicated events

## [0.6.4] - 2025-04-24

### Added

- :sparkles: add a singleton class to handle HTTP requests
- :sparkles: add multithreading support

### Removed

- :recycle: remove relative imports

### Refactor

- :building_construction: adopt the `HttpRequester` class
- :recycle: refactor multiple delegator methods into one

## [0.6.3] - 2025-03-25

### Added

- :loud_sound: add debug logs

### Fixed

- :bug: don't skip overridden checks of the target profile
- :white_check_mark: fix unit test

### Feat

- :building_construction: keep track of the checks
- :building_construction: inject `target_profile` and `settings` into the ProgressMonitor

## [0.6.2] - 2025-03-12

### Added

- Add missing test data
- :zap: add getter for archive entry info
- :white_check_mark: add test
- :sparkles: add method to list the entries of a ZIP archive

### Fixed

- :bug: missing object dump
- :pencil2: fix typo
- :bug: update logic to check the availability of archive folders

### Build

- ⬆  update deps

### Ci

- :wrench: update the artifacts uploader to use Sigstore JSON objects

### Feat

- :sparkles: generate a single JSON output for multiple validation profiles
- :bookmark: update JSON format version number

### Refactor

- :recycle: always include the `profile_identifiers` property in the json output format
- :bug: allow empty files and directories within a ZIP file

## [0.6.1] - 2025-02-20

### Added

- :bug: add the missing conformsTo statement
- :white_check_mark: add unit tests

### Fixed

- :bug: fix the candidate profiles collection
- :rotating_light: fix flake8 E501 warning
- :rotating_light: fix flake8 F401 warning

### Ci

- :construction_worker: update github action version

## [0.6.0] - 2025-02-06

### Added

- :sparkles: add class method to derive data entity path from identifier
- :heavy_plus_sign: add missing import
- :sparkles: add utility method to retrieve all data entities
- :white_check_mark: add unit tests
- :sparkles: add method to detect entity absolute paths
- :white_check_mark: add unit tests
- :sparkles: add an initial "How it works" section
- :sparkles: add copyright
- Add guidance on writing a profile

### Fixed

- :bug: trailing slash for Data Entities is recommended not mandatory
- :white_check_mark: fix unit tests
- :sparkles: fix and extend method to fetch entities by type
- :pencil2: replace override with overrides
- :loud_sound: fix log level
- :white_check_mark: fix log level
- :white_check_mark: fix test data
- Fix test data by adding the missing datasets
- :bug: skip the `file://` prefix when parsing an entity identifier
- :lipstick: fix padding
- :pencil2: fix typos
- :bug: minor changes
- :adhesive_bandage: intercept HTTPError when retrieving crate metadata
- :bug: use 'Accept Header' to retrieve JSON-LD context
- :white_check_mark: fix test
- :white_check_mark: fix configuration of the fail-fast flag on the shared test function

### Removed

- :recycle: remove CLI parameters from the global validation settings
- :fire: remove redundant code

### Build

- :arrow_up: upgrade dependencies (version 0.6.0)

### Docs

- :memo: update check description
- :truck: rename api docs file
- :sparkles: update toc
- :recycle: rewrite note
- :pencil2: minor changes
- :truck: restructure toc
- :sparkles: mention the fallback profile
- :lipstick: indent note

### Feat

- :sparkles: expose path/uri of rocrate entities
- :sparkles: display the full check identifier when verbose mode is enabled
- :zap: allow skipping a configurable list of checks
- :sparkles: allow configuring the list of checks to skip via CLI
- :sparkles: check for the existence of data entities
- :sparkles: display check identifier on the error report
- :sparkles: extend entity model to detect local and relative paths
- :sparkles: update check to skip absolute paths
- :sparkles: check recommended existence of absolute local data entities
- :sparkles: check for the compacted JSON-LD format of the file descriptor
- :zap: extend error message
- :sparkles: check if the JSON-LD context can loaded

### Refactor

- :recycle: move the init logic to the `__post__init__` method
- :sparkles: use method to identify remote entities
- :recycle: update the short option to skip checks

## [0.5.0] - 2024-12-17

### Added

- :memo: add docstring of `ValidationSettings` class
- :recycle: add a docstring to the main validation classes
- :memo: add docstrings to the `ValidationResult` class
- :memo: add minimal example of programmatic usage
- :memo: add a comment on `profile_identifier`
- :memo: add badge to the readthedocs documentation
- :sparkles: add link to Github repository
- :memo: add a docstring for the `violatingPropertyValue`
- Add draft class diagram
- :sparkles: add diagram for the `validate` service
- :sparkles: add diagram for the `profiles` service
- :memo: add missing params

### Fixed

- :bug: update the condition when a check should be skipped
- :rotating_light: fix flake8 issues
- Fix code snippet for programmatic validation
- :bug: avoid repeating errors
- :sparkles: skip redundant violation messages
- :bug: fix missing dependency
- :bug: fix copyright
- :bug: fix docs badge
- :wrench: fix missing package installation
- :bug: fix missing dependency
- :memo: fix missing copyright
- Fixes for the readme
- :pencil2: typo
- Raw html object to include the diagram
- :bug: fix link
- :lipstick: fix blanks
- :bug: fix missing link
- :bug: fix flag description
- :bug: fix missing `by`
- Fix svg width
- :sparkles: allow the position property of steps to accept integer values
- :bug: preserve issues with identical messages for different entities
- Workflow run roc: fix formal param workexample

### README

- Update list of supported profiles

### Removed

- :fire: remove internal settings from the `ValidationSettings` interface
- :recycle: remove unused imports
- :fire: remove unused `ontology_path` setting
- :fire: remove cache timeout from validation settings
- :fire: remove obsolete code
- :fire: remove unused function argument
- :recycle: remove redundant method
- :fire: remove redundant method

### Build

- :pushpin: update dependencies

### Ci

- :construction_worker: bootstrap readthedocs configuration
- :fire: disable redundant dependency settings
- :zap: dynamically set the current branch

### Docs

- Extend example
- :bug: simplify path to crate in the programmatic validation example
- :memo: improve code documentation
- :memo: extend the list of features
- :memo: bootstrap sphinx documentation
- :sparkles: dynamically set the version
- :memo: update docstring
- :memo: refine "Core Model" diagram
- :truck: move the diagram files
- :memo: update diagrams
- :memo: extend param description
- :bug: don't expose an internal validate method
- :memo: update flag description
- :bug: don't expose an internal validate method

### Feat

- Swap default behaviour for fail fast
- :wrench: swap default behaviour `fail fast` option in API settings

### Refactor

- :recycle: rename input parameter for the ro-crate uri
- :recycle: update default value
- :recycle: init and validate URI on settings object
- :recycle: link the context with the settings as an object
- :recycle: rename property to enable profile inheritance
- :recycle: rename flag to disable reporting of inherited checks
- :recycle: rename the flag to disable downloading a remote crate
- :recycle: rename link property between result and RO-Crate URI
- :recycle: mark internal methods
- :recycle: the `profile_identifier` should be a positional argument
- :lipstick: improve the readability of the identifier
- :recycle: update the representation of the `ValidationResult` object
- :recycle: update `CheckIssue` representation
- :recycle: Use more descriptive names for `resultPath` and `focusNode`
- :recycle: rename some CheckIssue properties
- :recycle: rename the parameter for ROCrate instantiation
- :recycle: rename some properties of the `ValidationResult` class
- :recycle: rename parameter
- :recycle: rename method
- :recycle: rename method arguments
- :recycle: reorder method args
- :recycle: avoid code repetition

## [0.4.6] - 2024-11-13

### Fixed

- RO-Crate validation should work for nested properties without id

## [0.4.5] - 2024-11-08

### Feat

- Allow to exit cli during interactive input on unix
- Allow to exit cli from pager on unix

## [0.4.4] - 2024-11-07

### Added

- :zap: add function to validate a RO-Crate URI parameter
- :white_check_mark: add unit tests for the URI validation function
- :zap: add the ability to hide Python requirements

### Fixed

- :bug: fix string format of error message
- :loud_sound: fix log level

### Feat

- :zap: always validate the ROCrate URI before instantiating the corresponding object
- Validate ro-crate metadata is flattened

### Refactor

- :recycle: set a default error message in the `ROCrateInvalidURIError` class
- :recycle: use the updated `ROCrateInvalidURIError` class
- :recycle: delegate URI validation from the CLI to the utility function
- :recycle: update default error message
- :recycle: update the error message for resource unavailability

## [0.4.3] - 2024-11-06

### Added

- :sparkles: add utility functions to read and check the minimum required Python version
- :zap: add root requirement check
- :white_check_mark: add and update tests
- :zap: add the ability to dynamically update test data
- :sparkles: add a more comprehensive pattern to detect valid ISO 8601 dates
- :white_check_mark: add more tests for valid and invalid datetimes
- :zap: add check for recommended values of the `RootDataEntity` `datePublished` property

### Fixed

- :bug: do not skip overridden checks when they belong to the target profile
- :bug: missing imports
- Skip counting overridden checks
- :white_check_mark: fix test

### Build

- :pushpin: update the minimum python version to 3.9.20

### Feat

- :sparkles: check the minimum required Python version
- :zap: extend model to include hidden requirement checks
- :zap: extend model to mark root requirement checks
- :sparkles: extend SHACL check initialisation
- :zap: more comprehensive pattern to detect valid ISO 8601 sdDatePublished properties

### Refactor

- :recycle: assign an order of 0 to the root check
- :recycle: restructure the initialisation of shack checks
- :stethoscope: disable version check

## [0.4.2] - 2024-10-30

### Added

- :zap: add property to denote the format of the JSON output
- :zap: add property to denote the format of the JSON output

### Refactor

- :recycle: rename the property to indicate the validator version in the JSON output
- :recycle: rename the property to indicate the validator version in the JSON output

## [0.4.1] - 2024-10-30

### Added

- :sparkles: add minimal dict serializers for the Profile and RequirementCheck models
- :zap: add `to_dict` serializer methods
- :zap: add rocrate-validator version to the JSON output

### Fixed

- :bug: fix severity detection of Python checks
- :pencil2: fix typo
- :loud_sound: fix level of a log message
- :bug: fix missing f-string formatting

### Removed

- :recycle: remove `resultPath` from issue serialisation
- :fire: remove `data_path` e `profiles_path` from JSON output
- :fire: remove `rocrate` path property from JSON output

### Feat

- :sparkles: extend check info on JSON output

### Refactor

- :recycle: determine the issue level and severity based on the check associated with the issue
- :recycle: expose `node_name` getter

## [0.4.0] - 2024-10-24

### Added

- Add provenance run crate profile
- Add test for missing ref to provrc profile
- Add tests for missing refs to other inherited profiles
- Add name and description to the test crates
- Add shape for wf that links to steps
- Add test for wf that links to steps

### Fixed

- Fix some docstrings
- :pencil2: fix typos

### Removed

- Remove obsolete crate generator

### Feat

- :sparkles: check if ParameterConnection instances are referenced through connections
- :sparkles: check `connection` property on computational workflow instances
- :sparkles: check `connection` property on `HowToStep` instances

### Provrc

- Workflow hasPart
- Tool input and output
- Tool environment
- Tool input, output and environment point to FormalParameter
- Action links to tool via instrument
- Workflow step
- Howtostep
- Controlaction
- Organizeaction
- Shapes for control/organize action status/error
- Tests for control/organize action status/error
- Howtostep position type
- Workflow connection
- Howtostep connection
- Parameterconnection
- Tool softwarerequirements and mainentity
- Workflow and step buildinstructions
- Env file encodingformat and conformsto
- Tool action resourceusage
- Resourceusage propertyvalue propertyid and unitcode
- Try parameterconnection cwl convention
- Parameterconnection: make some test cases more focused on the issue
- Parameterconnection: minor fixes

## [0.3.0] - 2024-10-11

### Added

- Workflow run crate: add test case where the RDE does not conform to process run crate
- :memo: add copyright notice
- Add test for conformsto procrc
- Add tests for wf input and output
- :loud_sound: add and update log messages
- :sparkles: support `profiles-path` override on `profiles` subcommand
- :sparkles: add getter for sibling profiles
- :zap: add properties to get parents and siblings of a given profile
- :zap: add a method to find a profile by checking its name
- :white_check_mark: add more tests to verify profile loading
- :sparkles: add build status badge
- :zap: add `pip` as installation method

### Fixed

- :rotating_light: fix flake8 warning E501
- Fix FormalParameter shape
- :construction: fix in progress for detecting overrides
- :pencil2: fix typo
- :bug: update data description
- :white_check_mark: fix test data
- :bug: change severity of the `name`, `description`, `license` properties of the `RootDataEntity`
- :white_check_mark: update test data
- :loud_sound: update logging configuration
- :pencil2: fix `sh:message` for the required `datePublished` of the `RootDataEntity`
- :white_check_mark: fix test
- :bug: fix env url

### Removed

- :fire: remove unnecessary magic methods
- :art: remove blanks

### Docs

- :recycle: update `testing` status and `license` badges
- ♻️ update testing status and license badges
- ✨ add PyPI version badge
- :recycle: reorder status badges

### Feat

- :sparkles: mark a requirement as overridden if all checks are overridden
- :sparkles: do not notify events of overridden requirements
- :sparkles: extend the check model to support multiple overrides
- :sparkles: improve detection of check overrides
- :zap: compute overrides on the fly
- :sparkles: rewrite function to read keyboard input for multi-platform compatibility

### Refactor

- :truck: restore profile.ttl of the workflow-run-crate profile
- :truck: use validator prefixes to denote shapes
- :loud_sound: update logs
- :sparkles: show multiple check overrides
- :recycle: rewrite magic method to sort profiles
- :recycle: simplify profiles parsing
- :recycle: declare the function as class level method
- :recycle: move required properties to a dedicated shape
- :triangular_flag_on_post: disable pagination on Windows systems

### Wfrc

- Minor updates to profile.ttl
- More tests for wf input and output
- Simplify workflow required shape
- Checks for FormalParameter
- FormalParameter workExample
- FormalParameter that maps to a PropertyValue
- FormalParameter that maps to a File, Dataset or Collection
- Workflow environment
- FormalParameter referenced from wf environment

## [0.2.1] - 2024-09-25

### Fixed

- :ambulance: fix version parser

### Build

- 🔖 update version number to 0.2.1

## [0.2.0] - 2024-09-25

### Added

- :memo: add package description
- :sparkles: add `{severity,requirement_level}_from_path` properties to the `Requirement` class
- :white_check_mark: add more unit tests for the cli internals
- :white_check_mark: add unit tests to verify the loading of requirements

### Fixed

- :bug: fix LevelCollection getter
- :loud_sound: update log message
- :wastebasket: clean up
- :recycle: update default `severity` of `CheckIssue` instances
- :recycle: fix output of `profiles describe` command
- :bug: properly initialize `PyRequirement` instances
- :bug: wrong property name
- :rotating_light: fix flake8 warning
- :bug: fix condition to print the mismatch warning
- :bug: use the shape description
- :recycle: update `Requirement.level` definition
- :sparkles: update SHACLRequirement description
- :bug: fix inconsistent severity level
- :sparkles: fix the sorting criteria of the requirements
- :ambulance: report a generic error when the metadata is invalid
- :rotating_light: fix flake8 warning
- :bug: fix mismatch in the requirement level
- :bug: always parse the result graph
- :ambulance: fix the override of the base method
- :bug: fix missing param to sort requirements
- :bug: fix severity of WebDataEntity shapes
- :bug: fix property getter
- :white_check_mark: fix test
- :rotating_light: fix flake8 warning
- :green_heart: fix skip condition on the release pipeline

### Removed

- :fire: remove `level` property from the `Requirement` model
- :sparkles: remove `RequirementCheck.{level,severity}` dependency from `Requirement`
- :coffin: remove short option for `profiles_path`

### Build

- :bookmark: update version number to 0.2.0
- :construction_worker: rename package to `roc-validator`

### Feat

- :building_construction: restructure release pipeline
- :building_construction: restructure testing pipeline
- :sparkles: allow to get declared `severity` of a Shape Node
- :sparkles: set the check severity based on the declared value, or infer it from the path
- :sparkles: filter shapes based on the requirement level
- :sparkles: enable info and warning severity levels in PySHACL
- :sparkles: expose the severity property in the `get_profile` service
- :sparkles: allow to specify the `level` of a Python requirement

### Refactor

- :recycle: update `Requirement` identitifer
- :recycle: update `get_requirements` method
- :recycle: set the conforms property to be computed based on the presence of issues
- :recycle: update the requirements loading process
- :lipstick: update output of `validate` command
- :recycle: safer way to add candidate profiles
- :recycle: restructure fn to generate checks stats
- :lipstick: update `profiles list` to show the number of checks by severity
- :recycle: restructure the logic to set and retrieve the requirement level in SHACL checks logic to set/get requirement level on SHACL checks
- :truck: rename test data files
- :recycle: move WebDataEntity shapes
- :recycle: use the `severity` property to denote the severity level of a Python requirement

## [0.1.2] - 2024-09-19

### Added

- :bug: add missing steps
- Add two shapes
- Add some tests
- Add shape to state that suites must have an instance or definition
- Add shapes for test instance
- Add test definition

### Fixed

- :bug: fix the command to check the tool version
- :recycle: update error message
- Fix shape name

### Build

- :construction_worker: update package version number

### Ci

- :sparkles: check the declared package version
- :construction_worker: refactor CI pipelines
- :sparkles: set up automatic release process

### Feat

- :sparkles: enhance version detection: take Git repository state into account
- :sparkles: declare package version

### Refactor

- :truck: rename jobs

### Wtroc

- Profile.ttl
- Update profile.ttl
- One more shape for test suite
- More tests for test instance
- More tests

## [0.1.1] - 2024-09-18

### Added

- Add utils module
- Add gitignore file
- Add rdflib dependency
- Add pyshacl dependency
- Add click dependency
- Add models
- Add validation services
- :sparkles: add minimal cli entrypoint
- :memo: add description of utility methods
- :package: add pyproject-flake8
- :sparkles: add function to calculate the path of the rocratre descriptor
- :package: add toml package
- :sparkles: add model to represent the global validation result
- :sparkles: add method to expose all requirements levels
- :package: add pylint dev dependency
- :sparkles: add method to determine the requirement name from the file
- :sparkles: add main validator class
- :sparkles: add class loader
- :memo: add missing typing
- :sparkles: add service endpoint to list profiles
- :sparkles: add command to list all available profiles
- :sparkles: add service endpoint to retrieve a profile
- :sparkles: add CLI command to describe a profile
- :package: add rich-click
- :sparkles: add progressive ID to requirement objects
- :lipstick: add order number of requirements and # checks
- :sparkles: add identifier for requirements and checks
- :package: add ipykernel to dev deps
- :sparkles: add option to print the package version
- :white_check_mark: add a first test for the FileDescriptor requirement
- :sparkles: add minimal shape to validate the file descriptor existence
- 📝 docs(shacl): add some method documentation
- ♻️  refactor(utils): add log related with the injection of obj properties
- :memo: add message
- :sparkles: add file descriptor existence requirement
- :white_check_mark: add test for file descriptor existence requirement
- :sparkles: add JSON format requirement for file descriptor
- :sparkles: add JSON-LD context requirement for file descriptor
- :white_check_mark: add test for JSON-LD requirement of file descriptor
- :white_check_mark: add test for @type requirements of JSON-LD entities
- :sparkles: add requirement for Data Root Entity existence
- :sparkles: add requirement for the type of the Root Data Entity
- :white_check_mark: add test for the root data entity type
- :sparkles: add datePublished requirement for Root Data Entity
- :white_check_mark: add test for the required datePublished property of RDE
- :white_check_mark: add test of recommended name of root data entity
- :adhesive_bandage: add missing class type for license entity
- :memo: add description comment
- :sparkles: add shape to validate type of file descriptor entity
- :sparkles: add property shape to validate prop `about` of file descriptor entity
- :sparkles: add `abort_on_first` parameter on test utility fn
- :sparkles: add shape to validate the conformsTo property
- Add test with valid RO-Crate with a date format that passes validation now
- Add some tests for the validate CLI command
- Add type checking in __lt__ Profile comparison
- Add Luca as co-author
- :sparkles: add function to configure default profiles path
- :sparkles: add a recursive method to compute the deep hash of a shape object
- :memo: add docsstrings to several methods
- :sparkles: add ontology support through the "ontology.ttl" file (per profile)
- :sparkles: add dataclass to handle validation settings
- Add hierarchy of requirements loaders
- :sparkles: add severity to Profile instances
- :sparkles: add method to get the index of a property wrt a collection
- :sparkles: add support to group shapes using the sh:group property
- :white_check_mark: add unit tests of validation context profiles
- :white_check_mark: add unit tests for the `ValidationSettings` class
- :sparkles: add file to declare for shared SPARQL prefixes
- :sparkles: add minimal OWL ontology
- :sparkles: add shape to check recommended properties of DataEntity instances
- :sparkles: add triple rule to identity the Root Data Entity
- :sparkles: add triple rule to mark license as Contextual Entity
- :sparkles: add shape to check Root Data Entity value restriction
- :sparkles: add SHOULD check for the relative value of the Root
- :sparkles: add more specific error for duplicated requirements
- :white_check_mark: add test of for the override shape feature
- :sparkles: add rule to identity the file descriptor
- :sparkles: add shape to validate the trailing `/` of Directory Data Entities
- :sparkles: add shape to validate File Data Entity encodings
- :white_check_mark: add tests for the encodingFormat property
- :sparkles: add SHACL rule to identity Web Data Entities
- :building_construction: add `requests` to the list of dependencies
- :sparkles: add shape to check recommended properties of WebData entities
- :sparkles: add missing shape related to DataEntity
- :sparkles: add py-checks for the WebData entity
- :lipstick: add resultPath on CLI validation output
- :sparkles: add shape to validate file with optional web presence
- :sparkles: add shape to validate optional `distribution` property
- :sparkles: add rule to define CreativeAuthor type
- :sparkles: add recommended author property on RooData Entity
- :sparkles: add minimal definition of CrativeWork author
- :sparkles: add shape to validate recommended properties of the Organization entity
- :white_check_mark: add missing test data
- :sparkles: add methods to compute a key for a shape
- :sparkles: add initial sample for workflow ro-crate profile
- Add main workflow type check
- Add main workflow language check
- Add main workflow image check
- Add main workflow cwl desc check
- Add python checks for file existence
- Add checks for readme file
- Add tests for wroc files python checks
- Add check for wroc metadata file descriptor
- Add tests for readme
- Add check for wroc license
- Added check for tests and examples directories
- Add check for bioschemas conformance
- Add pytest-xdist to test dependencies
- :sparkles: add `MultiIndexMap` class
- :sparkles: add getters for the properties of the profile specification
- :sparkles: add methods to get profiles by different criteria
- :sparkles: add setting to disable check for duplicates
- :sparkles: add time evaluation to some steps of the validation procedure
- :white_check_mark: add/update tests for the profiles loader
- :sparkles: add profile spec for the RO-Crate and Workflow RO-Crate profiles
- :card_file_box: add fake profiles for testing
- :recycle: add profiles base path to the init of Profile class
- :sparkles: add explicit `identifier` property to the Profile class
- :sparkles: add profile getters on the validation context
- :art: add the missing type hint
- :sparkles: add class to represent URI objects
- :sparkles: add module to handle ROCrate archives and metadata
- :sparkles: add more specific error classes
- :white_check_mark: add test data
- Process run crate: add checks on root data entity
- Add check on SoftwareApplication that has both version and softwareVersion
- Add must checks on process run crate action
- Add check that action is mentioned by the root data entity
- Add checks for name, description, endTime
- Add check for datetime format
- Add check for agent
- Add check for result
- Process run crate: add profile.ttl file
- Add check for startTime
- Added check for action with error and no FailedActionStatus
- Add check for action object and actionstatus
- Add check for action with no error
- Add constraint on object and result entities type
- Add checks for collections
- Action: add checks for containerImage property
- :sparkles: add `utils` module for the `cli` package
- :sparkles: support for validation events
- :sparkles: add details CLI option
- :sparkles: add methods `to_dict` and `to_json` methods on `ValidationResult`
- :sparkles: add options to write the validation output to a file
- :sparkles: add method to autodetect rocrate profile
- :sparkles: add multiple-choice prompt function
- :lipstick: add severity on short validation report
- :sparkles: add shape to validate the existence of the `mainEntity` property
- Add test for wroc with no mainEntity
- :sparkles: add class to configure the CLI pager
- :sparkles: add -y/--no-interactive option
- :sparkles: add option to configure output line width
- :sparkles: add an explicit reference to the overridden check
- :sparkles: add an option to disable the auto-detection of validation profiles
- Add acknowledgement of funding sources to README
- :rocket: add EU logos
- :art: add EU logo to the README file
- :memo: add copyright notice
- :memo: add copyright notice
- :sparkles: add profile getter by name
- :white_check_mark: add unit to validate hidden shapes
- :memo: add copyright notice
- :green_heart: add the badge for the GitHub testing pipeline

### Fixed

- :bug: log info only when available
- :pencil2: instances
- :alembic: try to assign weight to severity levels
- :rotating_light: fix line too long
- :bug: set base URI for shapes loading
- :bug: ensure trailing '/' for the publicID
- :bug: update import
- :bug: capitalize camel case output
- :loud_sound: change log level
- Fix(core):
- :bug: missing parameter
- :lock: check if the profile path exists
- :goal_net: handle and report generic errors
- :art: missing import
- :pencil2: typo
- :bug: preserve order of checks
- :pencil2: wrong type name
- Fix(shacl):
- :ambulance: missing methods to compare checks
- :bug: pass strings not node objects
- :lipstick: fix highlighting
- :bug: extract check name from decorator
- :bug: missing publicID parameter
- 🐛 fix(core): fix missing publicID parameter
- :bug: fix SHACLCheck initialisation
- :bug: store graph before properties init
- :bug: use concrete check py class
- :bug: safe extraction of public ID from path
- :bug: use shape graph if no shape property
- :bug: set publicID when loading ontologies
- :rotating_light: minor changes to suppress linter warnings
- :sparkles: missing function from previous commits
- :wrench: fix string to denote owl inference type
- :bug: fix test data
- :bug: fix nodeKind of about property
- :bug: make the pyproject path relative to the tool root
- :bug: link property shape property wrapper to the parent node wrapper
- :bug: fix reference to onto graph
- Fix(shacl):
- :construction: workaround to resolve ex: prefix on sh:select strings
- :bug: singleton pattern
- :loud_sound: update log message
- :pencil2: typos in log messages
- :sparkles: implement handling for the global shapes graph
- :recycle: define default profile_name using a constant value
- :bug: disable verbose logs
- :bug: set the right ctx on SHACL check
- :bug: fix fail fast
- :bug: properly order requirement checks
- :bug: missing defaults to configure SHACL validator
- :goal_net: notify error when a shape cannot be fetched
- :adhesive_bandage: update the ontology loader functionality
- :lipstick: update color of the check identifier
- :lipstick: update title and footnote of the main table
- :lipstick: update colors
- :bug: allow skipping properties from auto-injection
- :bug: apply the proper severity in tests
- :bug: don't reverse the profiles order by default
- :wrench: fix path of profiles
- :sparkles: load the right set of profiles on validation context
- :bug: read the right property `inherit_profiles` from settings
- :bug: fix loading of inherited profiles
- :bug: return profiles dict
- :ambulance: define the date requirement as RECOMMENDED
- :art: fix indentation
- :white_check_mark: fix test
- :bug: fix test data
- :pencil2: fix typo
- :white_check_mark: fix test data
- :bug: redefine check of value restriction of directory identifier
- :sparkles: update query to identify Directory DataEntity instances
- :bug: allow to store parent nodes
- :bug: fix requirements loading
- :bug: properly set flag to enable/disable profile inheritance
- :ambulance: fix shape target
- :bug: value is not always present in a violationResult
- :bug: wrong URI to reference the focusNode
- :white_check_mark: fix missing encodings on valid crate
- :pencil2: Folders -> Directories
- :bug: missing property injection
- :bug: improve validation of contentSize check
- :pencil2: fix sdDatePublished
- :sparkles: custom pattern to validate datePublished of WebData entities
- :ambulance: missing severity param on output formatter
- :truck: fix Web-based Entity references
- :white_check_mark: update test data
- :ambulance: fix fail fast evaluation
- :ambulance: fix the sorting issue with profiles
- :ambulance: allow more generic DataEntity instances
- :white_check_mark: fix missing contextual entities for some encoding format
- :white_check_mark: update test data
- :ambulance: update rule to define the CreativeWorkAuthor as subclass of person
- :sparkles: an organization can act as root data entity author
- :fire: clean up
- :white_check_mark: update test data to fix publisher property of valid rocrate
- :bug: the `resultPath` is optional
- :bug: remote : from sh:name and sh:description
- Fix valid wroc
- :bug: skip `profile.ttl` during the shape parsing
- :bug: fix missing severity of the `get_profiles` service method
- Fix(shacl):
- :bug: fix profile label
- fix(utils): :bug: update specs property getter to `None` as return
- :bug: update logic to compute inherited profiles
- :bug: update log messages
- :bug: update instantiation of some exceptions
- :bug: fix log level
- :truck: move pytest configuration file
- :sparkles: always sort profiles by deps
- :bug: preserve alphabetical order of profiles
- :loud_sound: fix log level of some messages
- :recycle: catch errors when loading the data graph
- :recycle: update function to make URIs relative
- :lipstick: fix output of the validation command
- Fix checks for action starttime
- Fix checks for action error with no failedactionstatus
- Fix actionStatus; add checks for environment
- :bug: update detection of ProfileNotFound error
- :goal_net: fix exception type
- :lipstick: fix layout
- :lipstick: fix input reader
- :bug: skip details when when the validation is ok
- :recycle: extend `get_profile`service
- :sparkles: use context severity by default
- :bug: fix issue with the exception instantiation
- :lipstick: fix output layout
- :ambulance: fix missing checks notifications
- :bug: fix inverted returned values
- :ambulance: use the right violation object
- :bug: fix issue reporting
- :lipstick: fix spaces on CLI output
- :lipstick: update padding
- :sparkles: ensure an entity is always returned, even if details are missing
- :bug: check if candidate profiles is defined
- :white_check_mark: fix cli test
- :lipstick: fix height of short report layout
- :lipstick: fix severity color on short report
- :lipstick: update padding
- :loud_sound: update logs on some pycheck
- :bug: fix missing issue on `MainWorkflowFileExistence`
- :bug: safely delete candidate profiles
- :bug: notify that previously skipped checks have been executed
- :fire: clean up
- :ambulance: missing positional argument
- :loud_sound: fix and extend debug logs
- :ambulance: better identification of requirements and checks
- :bug: details will be reported on file only if validation fails
- :bug: resolve the duplicate variable issue
- :ambulance: fix main console configuration
- :bug: properly set the verbose option on validate subcmd
- :bug: fix missing notification of executed checks
- :bug: update the flag name to enable shape overriding
- :bug: do not apply overrides to shapes of the target profile
- :bug: fix the link to the pipeline page
- :sparkles: take into account the `conformsTo` property of the Root Data Entity
- :loud_sound: fix log level
- :lipstick: hide `overridden by` label
- :ambulance: fix `fail fast` condition
- :bug: do not count the number of checks twice
- :white_check_mark: update test
- :bug: update EU logo link
- :coffin: disable unused pypi badge
- :art: fix badge alignment
- :memo: fix usage section: missing `validate` subcmd
- :adhesive_bandage: fix link
- :adhesive_bandage: fix test for membership
- :rotating_light: fix flake8 warning E713
- :rotating_light: fix flake8 warning E501
- :rotating_light: fix flake8 warning F541
- :rotating_light: fix flake8 warning F401
- :rotating_light: fix flake8 warning F841
- :rotating_light: fix flake8 warning E266
- :rotating_light: fix flake8 warning W291
- :rotating_light: fix flake8 warning F601
- :rotating_light: fix flake8 warning E501
- :sparkles: suppress the `stdout` output when the `-o` option is specified

### Removed

- :bug: remove cyclic dependency
- :fire: remove obsolete code
- :fire: remove obsolete files
- :mute: remove log
- :pencil2: remove \ escape char
- :coffin: remove unused import
- :wastebasket: remove unused imports
- :recycle: remove useless replace
- ♻️  refactor(shacl): remove obsolete comment
- 💄 ui(cli): remove []
- 🚨 fix-lint(cli): remove useless escape
- :mute: remove log
- :wastebasket: remove old profiles from develop
- :coffin: remove obsolete comment
- :coffin: remove unused import
- Remove extra escape from console message
- Remove color from models module
- :memo: remove CRs between badges
- Remove redundant references in RequirementCheck
- Remove unused OutOfValidationContext exception
- Remove dead code
- Remove RO-Crate path from main output message. Resolves issue #2
- :rotating_light: remove unused imports
- :fire: remove obsolete 'shapes' folder
- :fire: remove dead code
- :fire: remove dead code
- :mute: remove verbose logs
- :mute: remove logs
- :pencil2: remove wrong commas
- Remove named individuals so tests pass
- :ambulance: remove overly restrictive value for the about property
- :bug: remove inappropriate `sh:class` property
- :coffin: remove obsolete shape definition
- :fire: remove unused import
- :white_check_mark: update test data: remove authors and full affiliation data
- :fire: remove duplicate shape
- :recycle: remove hardwired default profile name
- :recycle: remove hardwired default profile name
- Remove duplicate entry
- :wastebasket: remove obsolete descriptor_path property
- :recycle: remove duplicate code by using the ROCrate object within the context
- :fire: remove unnecessary commit
- :bug: remove copyright notice
- :bug: remove copyright notice
- :fire: remove profile stub
- :wastebasket: remove unused prefixes
- :wastebasket: remove internal settings from the JSON report

### Build

- Init poetry project
- :package: Update Python packages
- :rocket: configure the `rocrate-validator` script
- :see_no_evil: Update ignore file
- :pushpin: update dependencies
- :package: move test dependencies to the test group
- :wrench: include pyproject.toml, LICENSE and README files in the distribution package
- :building_construction: include the 'profiles' folder in the distribution packages
- :arrow_up: upgrade PySHACL to 0.26.0
- :arrow_up: upgrade rich to 13.8.0
- :arrow_up: upgrade rich-click to 1.8.3
- :bookmark: update version number

### Ci

- :construction_worker: update cache key
- :construction_worker: initialise testing workflow
- :fire: disable flake8
- :white_check_mark: set up test job

### Docs

- :memo: just one note about the CLI entrypoint
- :memo: update description of JSON format requirement check
- :memo: update description of check context
- :memo: initial README
- :page_facing_up: update license badge
- :memo: update list of authors

### Feat

- Initial minimal shapes
- :sparkles: re-implement base classes to represent checks
- :sparkles: allow confiruging folders to skip
- :sparkles: allow to read config options
- :sparkles: extend the issue model with the link to the related check
- :sparkles: extend list of Requirement Levels
- :sparkles: better representation of requirement levels
- :sparkles: refactor shacl check validator
- :art: improve CLI output
- :lipstick: make node URIs relative to the ro-crate path
- :sparkles: expose severity at check level
- :sparkles: print check severity
- :sparkles: configure file extensions for filtering
- :zap: lazy loading of profile requirements
- :sparkles: expose method to load all profiles
- :sparkles: allow to describe a profile through a README.md
- :sparkles: color by severity name
- :sparkles: integrate severity-color mapping on model classes
- :sparkles: expose check description at requirement level
- :sparkles: enable comparison between profiles
- :sparkles: extend profile with inherited profiles
- :sparkles: extend validation process to include inherited profiles
- :sparkles: improve comparison between objects
- :sparkles: allow to filter profile requirements by severity
- :sparkles: improve shapes loading
- :sparkles: associate IDs to the requirement checks
- :bug: update query to parse shapes
- :sparkles: always return sorted object from validation result
- :technologist: configure logging
- :sparkles: more direct getters for Requirement and RequirementCheck classes
- :sparkles: expose rocrate_path on ValidationContext
- :building_construction: improve SHACL object network and its parser
- :sparkles: constraint the shapes graph to the current property shape
- :sparkles: expose shape property on SHACL requirement
- :safety_vest: parse requirement level input
- :sparkles: check definition of ids of JSON-LD entities
- :sparkles: require @type for JSON-LD entities
- :sparkles: recommended name of Root Data Entity
- :sparkles: recommended description of Root Data Entity
- :sparkles: requirement for optional license properties
- :sparkles: redefine shape to check existence of file descriptor entity
- :zap: improve loading of shacl shapes
- :sparkles: advanced feature should be enabled by default
- :sparkles: allow to retrieve shapes by hash
- :sparkles: allow to retrieve check instances by shape hash
- :sparkles: expose the global graph of shapes
- :sparkles: always perform checks using the global graph of shapes
- :sparkles: enable support for SHACL rules by default
- :sparkles: set to owlrl the default inference mode when an ontology is provided
- :sparkles: introduce SHACL context object
- :sparkles: export more SHACL classes
- :sparkles: preserve the total order while populating the list of issues
- :sparkles: map Shape sh:severity to a concrete requirement level
- :sparkles: make folder structure optional
- :goal_net: signal syntax errors when bad syntax occurs
- :sparkles: allow to get requirement checks by severity level
- :sparkles: enable verbose mode for the `profiles describe` command
- :sparkles: expose profiles_path on ValidationContext
- :sparkles: reorder requirements appropriately
- :sparkles: augment the data model with the File Data Entity instances
- :sparkles: augment the data model with the Directory Data Entity instances
- :sparkles: declare the RootDataEntity class
- :sparkles: declare the `Directory` class
- :sparkles: minimal shape to validate license
- :sparkles: allow marking requirements as hidden
- :sparkles: allow the use of node shape name and description as fallback for children shape properties
- :sparkles: allow to specify PyRequirement name and desc via decorator
- :sparkles: make the finder of RootDataEntity hidden
- :sparkles: redefine shape to check Root Data Entity type
- :sparkles: make the rule to mark licence entities hidden
- :sparkles: improve the validation of profiles that use inheritance
- :sparkles: more methods to manage shapes of a registry
- :sparkles: enhance logging functionality
- :sparkles: representation of the hasPart relationship bw Root and DataEntities
- :sparkles: extend CheckIssue model to store focusNode and value
- :sparkles: set focusNode and value on issue instances
- :sparkles: report the `focusNode` for every violation
- :sparkles: report violation value when available
- :sparkles: define the Shape to valid the WebSite entity
- :sparkles: inject resultPath of violation result on check issue instances
- :lipstick: enable markdown on issue description
- :sparkles: recommend a Contextual Entity for the organizational affiliation
- :sparkles: allow more complex types of MIME types for the encodingFormat pronom
- :sparkles: Value restriction of the recommended `publisher` property
- :sparkles: validate RECOMMENDED publisher value
- :sparkles: define the default filename for the profile specification
- :sparkles: globally define the PROF and SCHEMA.org Namespaces
- :sparkles: load the `profile.ttl` specification when profile is instantiated
- :sparkles: compute profile dependencies according to the specs properties
- :sparkles: allow to get profile by token
- :sparkles: update the `profiles list` output
- :sparkles: allow to extract profile version according to different criteria
- :sparkles: allow to get Profile instances by identifier
- :sparkles: enable more flexible folder structure for profiles
- :sparkles: enable simplified profile selection using the latest version
- :sparkles: fail fast SHACL validation when JSON data are invalid
- :lipstick: improve output of `list profiles` command
- :lipstick: improve output of `profiles describe` command
- :lipstick: report the total number of reqs and checks
- :sparkles: extend validation service to support zip (local or remote)
- :sparkles: update validate cmd to support zipped RO-Crates
- :sparkles: more methods to inspect URI
- :sparkles: init ROCrate object on validation context
- :sparkles: set remote validation to default
- :zap: enable http cache by default
- :sparkles: enable paging by default
- :sparkles: build Severity from string
- :sparkles: provide more info about the validation
- :sparkles: allow to automatically register subscribers
- :goal_net: centralise error handling
- :sparkles: keep track of performed and skipped checks
- :sparkles: improve handling of SHACL check results
- :sparkles: use context severity by default
- :sparkles: expose `conforms_to` property on ROCrate objects
- :sparkles: expose profile detection at service level
- :sparkles: improve existing prompt function
- :sparkles: enable autodetection and interactive selection of profiles
- :sparkles: report logs at the end of its execution
- :sparkles: enhance property getter to support list on entities
- :sparkles: initialise the CLI pager
- :sparkles: configure pager on subcommands
- :lipstick: better configuration of the file output layout
- :sparkles: auto detection of no-interactive mode
- :sparkles: show overrides on `profiles describe` subcmd
- :construction_worker: integrate a Gitlab CI pipeline
- :sparkles: configure badge status
- :sparkles: do not prompt for the validation profile in non-interactive mode
- :sparkles: allow specifying multiple profiles to validate
- :sparkles: allow selecting multiple profiles
- :sparkles: do not prompt for profile selection if reasonable candidate profiles are available
- :sparkles: define a local prefix for the validator entities
- :sparkles: programmatically disallow property injection
- :sparkles: automatically generate name and description of nodes and properties
- :building_construction: generalize the check of processed nodes to avoid infinite loops
- :sparkles: enable a step to check code linting
- :sparkles: wrap console object
- :sparkles: do not print formatted validation report when format is different `text`
- :sparkles: output JSON to stdout when `--format=json`

### Perf

- :zap: evaluate all shapes at once
- :zap: optimize logger initialisation: one handler per level
- :zap: simplify base ontology on the RO-Crate profile
- :zap: improve fail fast mode

### Procrc

- ContainerImage SHOULD checks
- ContainerImage MAY checks
- Software dependencies checks

### Refactor

- Move ttl file
- Move code to the src folder
- Move code to the rocrate-validator folder
- Move shape to shapes folder
- :recycle: generic function to load graphs from paths
- :fire: disable ontologies parameter
- :truck: move SHACL validator to a dedicated package
- :recycle: use constant module to define allowed values of params
- :recycle: use format to denote graph types
- :recycle: move constants to the constants module
- :recycle: rename enum to represent the severity level
- :recycle: move shacl code to a dedicated package
- :recycle: move shacl code within checks package
- :recycle: rewrite validation service using the Validator class
- :art: improve navigation between objects
- :fire: rename module containing services
- :wrench: rename cli option
- :art: reorganize cli into a package
- :building_construction: reorganize the validation process around a context
- :truck: rename `type` prop to `severity`
- :recycle: reorganize method to initialise checks
- :recycle: rename property to denote obj order
- :lipstick: minor change on output of validate cmd
- :wheelchair: auto convert string path to Path object
- :building_construction: make Requirement class abstract
- :recycle: make RequirementCheck concrete
- :recycle: extend Requirement loader; add concrete PyRequirement class
- :recycle: abort_on_first=True by default
- :sparkles: restore class and suffix (optional) filters
- :building_construction: rename table title
- :label: more specific typings
- :loud_sound: update log level
- :recycle: redefine sh:property uri
- :recycle: minor changes
- :art: reorganize imports
- :truck: rename requirements files
- :truck: rename test data
- :truck: rename shape for root data entity
- :memo: update license definition
- :truck: rename path of tests data
- :truck: rename test data for root data entity
- :recycle: redefine shape of Root Data Entity
- :wrench: update test data
- :recycle: update shared function to test RO-Crate entities
- :recycle: minor changes to the MetadataFileDescriptorDefinition
- :goal_net: catch all unexpected errors at the CLI entry point
- :truck: move profiles to the folder 'rocrate_profiles'
- :coffin: revert to a single profiles folder
- :truck: move profiles to `rocrate_validator/profiles`
- :truck: rename shape object associated with the SHACLCheck
- :truck: move severity map function
- :truck: move to utils the function for making relative URIs
- :recycle: reorganize imports
- :recycle: restructure the hierarchy of SHACL Shape objects
- :recycle: refactor parsing of SHACL violation with lazy loading strategy
- :fire: simplify profiles loader
- :truck: rename param of ontology path
- :recycle: configure defaults using constants for improved maintainability
- :art: move validation state to the context object
- :recycle: update factory of ShapeRegistry instances
- :recycle: update SHACL check
- :recycle: generalize Shape as specialisation of the generic SHACLNode
- :recycle: generalise NodeShape as specialisation of Shape, NodeCollection
- :lipstick: update colors and styles of validation results
- :lipstick: update colors and styles of the `profiles describe` command
- :lipstick: update colors on footnotes
- :sparkles: improve profile loader without inheritance
- :recycle: use the `RootDataEntity` class to select the shape focus
- :truck: rename pyrequirements
- :art: update names of some requirements
- :truck: rename check of descriptor existence
- :truck: update descriptor existence textual definition
- :recycle: update labels of file descriptor metadata shapes
- :recycle: minor changes to the name of some requirements
- :truck: update name and description of Root Data Entity shape (RECOMMENDED)
- :recycle: update name and description of some shapes
- :recycle: update description of shape for Root RECOMMENDED properties
- :truck: rename entities
- :recycle: reorder DataEntity shapes
- :truck: rename file containing shapes
- :lipstick: minor update of CLI validation output
- :truck: rename file with web-based data entity definitions
- :sparkles: update description of file with optional web presence
- :recycle: redefine hash for shape objects
- :recycle: update `ShapeRegistry` to use reference shapes by key
- :building_construction: simplify getter of the sourceShape property
- :recycle: use the appropriate function of retrieve the shape from the registry
- :recycle: refactor profiles loader
- :recycle: refactor profile loading
- :recycle: update initialisation of profiles before validation
- :recycle: update SHACL context initialisation
- :bug: safe get of entity @id
- :recycle: restructure ProfileSpecification errors
- :recycle: map Profile name to specs label
- :recycle: identity the profile within the context using the `identifier` property
- :recycle: update default profile value
- :bug: display the profile identifier on the profiles table
- :recycle: rename `profile_name` param as `profile_identifier`
- :lipstick: minor change to cli output
- :recycle: update `publicID` URI
- :children_crossing: improve error handling
- :lipstick: update header style
- :lipstick: minor changes to the layout of validate cmd
- :recycle: factorise initialisation of validator object
- :recycle: update `get_conforms_to` implementation
- :art: remote blank line
- :lipstick: update style of multiple choice element
- :lipstick: update layout of validate output
- :recycle: hide the shape that only expand the data graph
- :loud_sound: update log
- :art: ensure that skipped checks are tracked
- :recycle: rename option `details` to `verbose`
- :sparkles: refactor the code to allow overriding checks
- :recycle: rename output format option
- :necktie: update log message
- :lipstick: update output message
- :lipstick: update output message
- :lipstick: better output message for the fallback profile
- :loud_sound: update log messages
- Update title format
- :recycle: check hidden shape by using the local prefix
- :recycle: use the `validator:HiddenShape` entity
- :truck: use local prefix to denote entities defined by rules
- :recycle: use the local prefix to denote shapes of the ro-crate profile
- :recycle: use the local prefix to denote shapes of the workflow-ro-crate profile
- :recycle: use the local prefix to denote shapes of the process-run-crate profile
- :recycle: use local prefix to declare SPARQL prefixes
- :sparkles: avoid infinite loops when parsing cyclic shapes graphs

### Style

- :recycle: sort imports
- :lipstick: update layout of CLI output messages
- :memo: strip on descriptions
- :lipstick:

[0.8.0]: https://github.com///compare/0.7.2..0.8.0
[0.7.2]: https://github.com///compare/0.7.1..0.7.2
[0.7.1]: https://github.com///compare/0.7.0..0.7.1
[0.7.0]: https://github.com///compare/0.6.5..0.7.0
[0.6.5]: https://github.com///compare/0.6.4..0.6.5
[0.6.4]: https://github.com///compare/0.6.3..0.6.4
[0.6.3]: https://github.com///compare/0.6.2..0.6.3
[0.6.2]: https://github.com///compare/0.6.1..0.6.2
[0.6.1]: https://github.com///compare/0.6.0..0.6.1
[0.6.0]: https://github.com///compare/0.5.0..0.6.0
[0.5.0]: https://github.com///compare/0.4.6..0.5.0
[0.4.6]: https://github.com///compare/0.4.5..0.4.6
[0.4.5]: https://github.com///compare/0.4.4..0.4.5
[0.4.4]: https://github.com///compare/0.4.3..0.4.4
[0.4.3]: https://github.com///compare/0.4.2..0.4.3
[0.4.2]: https://github.com///compare/0.4.1..0.4.2
[0.4.1]: https://github.com///compare/0.4.0..0.4.1
[0.4.0]: https://github.com///compare/0.3.0..0.4.0
[0.3.0]: https://github.com///compare/0.2.1..0.3.0
[0.2.1]: https://github.com///compare/0.2.0..0.2.1
[0.2.0]: https://github.com///compare/0.1.2..0.2.0
[0.1.2]: https://github.com///compare/0.1.1..0.1.2
[0.1.1]: https://github.com///tree/0.1.1

<!-- generated by git-cliff -->
