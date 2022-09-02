import dataclasses
import decimal
import json
import logging
import os
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from typing import (Any, Callable, Dict, Generator, List, Literal, Optional,
                    Type, Union)
from unittest.mock import ANY

from dacite import Config, from_dict
from envyaml import EnvYAML

from constants import COLORS, config, log_format
from differ import TestWithDiffs

# YamlIncludeConstructor.add_to_loader_class(
#     loader_class=yaml.SafeLoader, base_dir="./test_configs"
# )


def path_resolver_wrapper(
        yaml_test_file_path: Path,
) -> Callable[[Union[str, Path, list]], Path]:
    def _path_resolver(value: Union[str, Path, list]) -> Path:
        path = yaml_test_file_path.parent
        if isinstance(value, str):
            path = Path(value)
        if isinstance(value, list):
            path = Path(*value)
        if str(path).startswith(".") and yaml_test_file_path:
            path = yaml_test_file_path.parent.joinpath(path)
        return path

    return _path_resolver


log = logging.getLogger(__name__)
log.setLevel(
    config.LOG_LEVEL
    # if config.LOG_LEVEL is not None
    # else framework_config["logging"].get("level", "WARNING")
)

formatter = logging.Formatter(log_format)

ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(formatter)
log.addHandler(ch)


class ImproperlyConfigured(Exception):
    pass


class FlagTypeEnum(Enum):
    STR = "str"
    PATH = "path"
    RESOLVED_PATH = "resolved_path"
    INT = "int"


class TreatableTypes(Enum):
    JSON = "json"
    YAML = "yaml"
    BYTES = "bytes"
    TEXT = "text"


@dataclasses.dataclass
class Flag:
    name: str
    type: Optional[FlagTypeEnum]
    value: Optional[Union[str, Path, int, float, decimal.Decimal]]  # = None

    def __post_init__(self):
        log.info(f"Flag.__post_init__({self})")
        if self.value and self.type:
            match self.type:
                # case FlagTypeEnum.INT:
                #     self.value = int(self.value)
                case FlagTypeEnum.STR:
                    self.value = str(self.value)
                case FlagTypeEnum.PATH:
                    self.value = Path(self.value)
                case FlagTypeEnum.RESOLVED_PATH:
                    self.value = Path(self.value).resolve()
                # case _:
                #     self.value = self.value

    def build(self):
        log.info(f"Flag.build({self})")
        if self.value:  # or self.type:
            return f"-{self.name}", f"{self.value}"
        else:
            return (f"-{self.name}",)


@dataclasses.dataclass
class BaseContent:
    content: Optional[Union[str, bytes, dict, list]]
    encoding: Literal["utf-8"] = "utf-8"
    treat_as: TreatableTypes = TreatableTypes.BYTES
    file_path: Optional[Union[list, Path]] = None
    yaml_test_file_path: Optional[Path] = None
    directory: Optional[Union[str, Path]] = None

    class Meta:
        least_one_required_fields: List[str] = []
        not_allowed_together_fields: List[str] = []

    def __str__(self):
        shorten_content = self.content if len(self.content) > 1000 else self.content[:100] + '...' + self.content[-100:]
        return (
            f"{self.__class__.__name__}("
            f"content={shorten_content}, "
            f"encoding={self.encoding}, "
            f"treat_as={self.treat_as}, "
            f"file_path={self.file_path}, "
            f"yaml_test_file_path={self.yaml_test_file_path}, "
            f"directory={self.directory})"
        )

    def __post_init__(self):
        self.validate()

        if isinstance(self.file_path, (list, tuple)):
            log.warning(f"file_path is a list, joining: {self.file_path}")
            self.file_path = Path(*self.file_path)

    def validate(self):
        if self.Meta.least_one_required_fields and not any(
                getattr(self, field) is not None
                for field in self.Meta.least_one_required_fields
        ):
            raise ImproperlyConfigured(
                f"At least one of {self.Meta.least_one_required_fields} must be provided"
            )
        if self.Meta.not_allowed_together_fields and all(
                getattr(self, field) is not None
                for field in self.Meta.not_allowed_together_fields
        ):
            raise ImproperlyConfigured(
                f"Only one of {self.Meta.not_allowed_together_fields} must be set"
            )

        if self.treat_as == TreatableTypes.BYTES and not self.encoding:
            raise ImproperlyConfigured("Encoding must be set when treating as bytes")

    @property
    def treated(self):
        data = self.content
        if data is None or data == "":
            return ""
        try:
            match self.treat_as:
                case TreatableTypes.BYTES:
                    if isinstance(self.content, str):
                        log.info(
                            f"<treated> Converting to bytes. Length: {len(self.content)}"
                        )
                        data = bytes(self.content, self.encoding)
                case TreatableTypes.TEXT:
                    if isinstance(self.content, bytes):
                        log.info(
                            f"<treated> Converting to text. Length: {len(self.content)}"
                        )
                        data = str(self.content.decode(self.encoding))
                case TreatableTypes.JSON:
                    log.info(
                        f"<treated> Converting to json. Length: {len(self.content)}. File path: {self.file_path}"
                    )
                    data = json.loads(self.content)
                case TreatableTypes.YAML:
                    log.info(
                        f"<treated> Converting to yaml. Length: {len(self.content)}"
                    )
                    data = EnvYAML(self.content)
            return data
        except Exception as e:
            raise ImproperlyConfigured(
                f"Error '{e}' in {type(self)} treating content: {self.content[:100]}"
            )


@dataclasses.dataclass
class Content(BaseContent):
    content: Optional[Union[str, bytes, dict, list]] = None
    ignore_fields: Optional[List[str]] = None

    class Meta:
        least_one_required_fields = (
            "content",
            "file_path",
        )
        not_allowed_together_fields = ("content", "file_path")

    def __bool__(self):
        return bool(self.content)

    def __post_init__(self):
        super().__post_init__()

        if self.file_path:
            self.content = (
                self.file_path.read_text()
                if not self.yaml_test_file_path
                else (
                    self.yaml_test_file_path.parent.joinpath(self.file_path).read_text()
                )
            )
        if (
                self.treat_as not in (TreatableTypes.JSON, TreatableTypes.YAML)
                and self.ignore_fields is not None
        ):
            raise ImproperlyConfigured(
                "ignore_fields can only be set when treating as JSON or YAML"
            )

        match self.treat_as:
            case TreatableTypes.BYTES:
                if isinstance(self.content, str):
                    log.info(f"Converting {self.file_path} to bytes")
                    self.content = bytes(self.content, self.encoding)
            case TreatableTypes.TEXT:
                if isinstance(self.content, bytes):
                    self.content = str(self.content.decode(self.encoding))
            case TreatableTypes.JSON:
                log.info(f"Converting {self.file_path} to json")
                self.content = self.__replace_json_paths(json.loads(self.content))
            case TreatableTypes.YAML:
                log.info(f"Converting {self.file_path} to yaml")
                if self.file_path:
                    self.content = self.__replace_json_paths(
                        dict(
                            EnvYAML(str(self.file_path))
                        )  # TODO: review it! (self.content)
                    )

    @staticmethod
    def __get_item_form_object(d, key):
        try:
            if isinstance(d, dict):
                d = d[key]
            elif isinstance(d, (list, tuple)):
                if key != "*":
                    d = d[int(key)]
                else:
                    log.info("<replace_by_path> key is '*', returning all items")
            else:
                log.warning(f"{d} is not a dict or list")
            return d
        except (KeyError, IndexError):
            # Now we making a warning about missing key to ignore.
            log.warning(f"ignore field: '{key}' not found in expected result.")

    @staticmethod
    def __value_to_int(value):
        try:
            return int(value)
        except ValueError:
            return None

    @staticmethod
    def __replace_by_path(data: Union[list, tuple, dict], path: str):
        _path = []
        local_data = data
        path_parts = path.split(".")

        for part in path_parts[:-1]:
            _path.append(part)
            local_data = Content.__get_item_form_object(local_data, part)

        if local_data:
            last_key = path_parts[-1]
            intable_key = Content.__value_to_int(last_key)

            if last_key in local_data:
                local_data[last_key] = ANY
            if (intable_key is not None and len(local_data) >= intable_key) or (
                    isinstance(local_data, Mapping) and local_data.get(intable_key) is not None
            ):
                local_data[intable_key] = ANY

            return data

    def __replace_json_paths(self, content):
        if self.ignore_fields is not None:
            for path_to_skip in self.ignore_fields:
                content = self.__replace_by_path(content, path_to_skip)
        return content


@dataclasses.dataclass
class WritableContent(BaseContent):
    def save(self):
        if self.file_path is not None:
            if not self.file_path.parent.exists():
                self.file_path.parent.mkdir(parents=True)
            if not self.file_path.exists():
                self.file_path.touch()
            log.warning(f"Saving to {self.file_path}")
            self.file_path.write_text(self.content)
        else:
            log.warning("No file path provided")


@dataclasses.dataclass
class ConfigTestCase:
    test: str

    expected_stdout: Optional[Content]
    expected_stderr: Optional[Content]

    flags: Optional[List[Flag]]  # = dataclasses.field(default_factory=list)
    arguments: Optional[List[str]] = dataclasses.field(default_factory=list)

    skip: bool = False
    stdin: Optional[Content] = None

    stdout: Optional[WritableContent] = None
    stderr: Optional[WritableContent] = None

    expected_return_code: int = 0

    default_parameters: Optional[dict] = None
    binary_path: Optional[Path] = None
    yaml_test_file_path: Optional[Path] = None
    shell: bool = False

    root_env: Optional[dict] = dataclasses.field(default_factory=dict)
    env: Optional[dict] = dataclasses.field(default_factory=dict)
    cwd: Optional[Path] = None
    root_cwd: Optional[Path] = None
    show_results_diff: bool = True

    class Meta:
        least_one_required_fields = (
            "expected_stdout",
            "expected_stderr",
            "expected_return_code",
        )

    def build_command(self, bin_path: Path = None) -> List[str]:
        log.debug(self.flags)
        command = (
            ([f for flag in self.flags for f in flag.build()] if self.flags else [])
            + self.arguments
        )
        log.info(f"\n{command}")
        return command

    def __post_init__(self):
        if self.env or self.root_env:
            env = dict(os.environ, **(self.root_env or {}), **(self.env or {}))
            log.debug(f"env: {env}")
            self.env = env

        log.debug(
            f"\n\n\nRESOLVE CWD\nself.cwd={self.cwd}\nself.root_cwd={self.root_cwd}"
        )
        if self.cwd or self.root_cwd:
            self.cwd = self.cwd or self.root_cwd

        if not any(
                [field is not None for field in self.Meta.least_one_required_fields]
        ):
            raise ImproperlyConfigured(
                f"[{self.yaml_test_file_path}] At least one of {self.Meta.least_one_required_fields} must be provided"
            )
        # print(self)

    def run(self, bin_path: Optional[Path] = None):
        if self.skip:
            return

        bin_path = bin_path or self.binary_path
        stdin = self.stdin.content if self.stdin else None
        log.info("\n")
        log.debug(f"\t{self.test}")
        command = self.build_command(bin_path)

        log.info(
            f"\t\t* RUN: {self.binary_path} {' '.join(command)} "
            f"{' < ' + str(self.stdin.file_path.resolve()) if self.stdin else ''}"
        )
        log.info(f"\t\t* In directory: {self.cwd}")
        # log.info(dict(os.environ))
        proc = subprocess.Popen(
            args=[str(self.binary_path)] + command,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=self.shell,
            env=self.env,
            cwd=self.cwd,
        )
        output, err = proc.communicate(stdin)
        shorten_string = (
            lambda s, ln: f"{s[:ln]} \n...\n {s[-ln:]}" if len(s) > ln else s
        )
        log.info(f"PROCESS STDOUT: {shorten_string(output.decode(), 200)}")
        log.info(f"PROCESS STDERR: {shorten_string(err.decode(), 200)}")

        if self.stdout is None:
            self.stdout = WritableContent(content=output)
        else:
            self.stdout.content = output.decode(self.stdout.encoding)
            if self.stdout.content:
                self.stdout.save()

        if self.stderr is None:
            self.stderr = WritableContent(content=err)
        else:
            self.stderr.content = err.decode(self.stderr.encoding)
            if self.stderr.content:
                self.stderr.save()

        if self.expected_stdout:
            # Returned stdout is different than expected
            yield (
                self.stdout.treated,
                self.expected_stdout.content,
                f"{self.test} - Command stdout and expected output are different",
            )
        if self.expected_stderr:
            # Returned stderr is different than expected
            yield (
                self.stderr.treated,
                self.expected_stderr.content,
                f"{self.test} - Stderr and expected error are different",
            )

        if (
                self.expected_return_code is not None
                and self.expected_return_code != proc.returncode
        ):
            # Returned return code is different than expected
            yield (
                proc.returncode,
                self.expected_return_code,
                f"{self.test} - Return code is different than expected",
            )


@dataclasses.dataclass
class TestConfig:
    binary_path: Path
    default_parameters: Dict[str, Any]
    name: str
    description: Optional[str]
    tests: List[ConfigTestCase]

    yaml_test_file_path: Optional[Path] = None

    skip: bool = False
    env: Optional[dict] = dataclasses.field(default_factory=dict)
    cwd: Optional[Path] = None

    def __post_init__(self):
        log.info(f"ToolCommandTests.cwd = {self.cwd}")
        for test in self.tests:
            # Bind binary path and default parameters to test
            test.binary_path = test.binary_path or self.binary_path
            test.default_parameters = self.default_parameters
            test.yaml_test_file_path = self.yaml_test_file_path
            test.root_env = self.env
            test.root_cwd = test.cwd or self.cwd
            test.cwd = test.cwd or self.yaml_test_file_path

    def run_tests(self):
        if self.skip:
            log.warning(f"{COLORS['yellow']}SKIPPING{COLORS['reset']} {self.name}")
            return
        log.warning(f"{COLORS['green']}RUNNING{COLORS['reset']} {self.name}")
        log.debug(f"{self.description}")
        for test in self.tests:
            if test.skip:
                continue
            for exp, out, err in test.run(
                    self.binary_path,
            ):
                yield exp, out, err


def _content_resolver_wrapper(
        cls: Union[Type[Content], Type[WritableContent]], yaml_test_file_path: Path
) -> Callable[[Dict], Union[Content, WritableContent]]:
    def content_resolver(content: Dict[Any, Any]) -> Union[Content, WritableContent]:
        return from_dict(
            data_class=cls,
            data=dict(yaml_test_file_path=yaml_test_file_path, **content),
            config=Config(
                cast=[FlagTypeEnum, TreatableTypes],
            ),
            # **kwargs
        )

    return content_resolver


def load_configs() -> Optional[List[TestConfig]]:
    tests_config_dir = config.TEST_CONFIGS_DIR
    log.warning(f"Loading configs from {tests_config_dir}")
    gathered_configs = []

    exclude_path = config.EXCLUDE_CONFIGS_DIR
    config_files_list: Union[list, tuple, Generator] = ()
    if tests_config_dir.is_dir():
        config_files_list = Path(tests_config_dir).rglob("*.yaml")
    elif tests_config_dir.is_file():
        # handle case if config dir path is pointed to file
        config_files_list = [tests_config_dir]

    for config_file in config_files_list:
        log.info(f"Loading config from {config_file}")
        config_file = config_file.absolute()
        if exclude_path and config_file.is_relative_to(exclude_path):
            log.info(f"Excluding file {config_file}")
            continue
        try:
            additional_data = {
                "yaml_test_file_path": Path(os.path.join(tests_config_dir, config_file))
            }
            path_resolver = path_resolver_wrapper(**additional_data)
            test_config = from_dict(
                data_class=TestConfig,
                data=dict(
                    **dict(
                        EnvYAML(
                            str(config_file.absolute()),
                        )
                    ),
                    **additional_data,
                ),
                config=Config(
                    cast=[FlagTypeEnum, TreatableTypes],
                    type_hooks={
                        Path: path_resolver,
                        Content: _content_resolver_wrapper(
                            Content,
                            **additional_data,
                        ),
                        WritableContent: _content_resolver_wrapper(
                            cls=WritableContent,
                            **additional_data,
                        ),
                    },
                ),
            )
            gathered_configs.append(test_config)
        except Exception as e:
            log.error(f"Error loading config {config_file}: {e}")
            raise e

    if not gathered_configs:
        raise ImproperlyConfigured("No configs found in {}".format(tests_config_dir))

    active_configs = [config for config in gathered_configs if config.skip is not True]

    if not active_configs:
        raise ImproperlyConfigured(
            "No active configs found in {}".format(tests_config_dir)
        )
    validate_configs(active_configs)

    return active_configs


def validate_configs(active_congfigs: list[TestConfig]) -> list[TestConfig]:
    """Validate TestConfig to make sure it us properly configured."""
    validate_test_file_paths_uniqueness(active_congfigs)
    for active_config in active_congfigs:
        validate_output_content_type(active_config)
        validate_test_names_uniqueness(active_config)


def validate_output_content_type(active_config: TestConfig) -> TestConfig:
    """Validate output content type for each: stdout, stderr and expected_stdout, expected_stderr."""
    for config_test in active_config.tests:
        if (
            config_test.stdout and config_test.expected_stdout and not check_output_content_type(
                config_test.stdout, config_test.expected_stdout)
        ):
            raise ImproperlyConfigured(
                f"Test '{config_test.test}' stdout content type: "
                f"'{config_test.stdout.treat_as.name}' does not match "
                f"expected_stdout content type: '{config_test.expected_stdout.treat_as.name}'."
            )
        if (
            config_test.stderr and config_test.expected_stderr and not check_output_content_type(
                config_test.stderr, config_test.expected_stderr)
        ):
            raise ImproperlyConfigured(
                f"Test '{config_test.test}' stderr content type: "
                f"'{config_test.stderr.treat_as.name}' does not match "
                f"expected_stderr content type: '{config_test.expected_stderr.treat_as.name}'."
            )
    return active_config


def check_output_content_type(actual_output: Union[Content, WritableContent], expected_output: Content) -> bool:
    """Check .treat_as property of the outputs and raise exception if type doesn't match."""
    return actual_output.treat_as.value == expected_output.treat_as.value


def validate_test_names_uniqueness(active_config: TestConfig) -> TestConfig:
    """Check test names for uniqueness."""
    test_names = [test.test for test in active_config.tests]
    names_count_map = {name: test_names.count(name) for name in test_names}
    if len(test_names) != len(names_count_map):
        raise ImproperlyConfigured(
            f"Test with name: '{', '.join(test_name for test_name, cnt in names_count_map.items() if cnt > 1)}' "
            "already exists in yaml file."
        )
    return active_config


def validate_test_file_paths_uniqueness(active_congfigs: list[TestConfig]) -> list[TestConfig]:
    """Check test stdout, stderr 'file_path' for uniqueness."""
    ALL_CONFIGS_FILE_PATHS = {
        'stdout': set(),
        'stderr': set(),
    }
    for active_config in active_congfigs:
        for config_test in active_config.tests:
            for field in ALL_CONFIGS_FILE_PATHS:
                file_path = getattr(getattr(config_test, field, None), 'file_path', None)
                if file_path:
                    if file_path in ALL_CONFIGS_FILE_PATHS[field]:
                        raise ImproperlyConfigured(
                            f"Test with {field} file_path: '{file_path}' already exists in yaml file."
                        )
                    else:
                        ALL_CONFIGS_FILE_PATHS[field].add(file_path)
    return active_congfigs


class BaseTestCase(TestWithDiffs):
    test: ConfigTestCase

    def run_cases(self):
        for actual, expected, msg in self.test.run():
            log.debug(asdict(self.test))
            log.debug(f"expected={expected}, actual={actual}")
            log.info(f"msg={msg}")
            self.assertEqual(expected, actual, msg)


def build_test_params(
        tests_config_dir: Optional[Union[Path, str]] = "",
) -> tuple[tuple[str, str], list[tuple[str, ConfigTestCase]]]:
    loaded_configs = load_configs(
        # tests_config_dir=os.environ.get("TEST_CONFIGS_DIR", tests_config_dir)
    )
    log.debug(f"Loaded configs: {loaded_configs}")
    configs_to_run = (("name", "test"), [])
    for test_config in loaded_configs:
        for test in test_config.tests:
            test_to_run = (f"{test_config.name}_{test.test}", test)
            configs_to_run[1].append(test_to_run)
    return configs_to_run
