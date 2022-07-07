import configparser
import dataclasses
import decimal
import json
import logging
import os
import subprocess
import sys
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from typing import List, Union, Dict, Any, Literal, Optional, Generator

import yaml
from dacite import from_dict, Config
from envyaml import EnvYAML

# from yamlinclude.constructor import YamlIncludeConstructor

from differ import TestWithDiffs

# YamlIncludeConstructor.add_to_loader_class(
#     loader_class=yaml.SafeLoader, base_dir="./test_configs"
# )

framework_config = configparser.ConfigParser(
    interpolation=configparser.ExtendedInterpolation()
)
framework_config.read("tests.conf")


@dataclasses.dataclass
class EnvTestsConfig:
    LOG_LEVEL: Optional[str] = logging.ERROR
    TEST_CONFIGS_DIR: Optional[Path] = Path("./test_configs")
    EXCLUDE_CONFIGS_DIR: Optional[Path] = ""


def _path_resolver(value: Union[str, Path, list]) -> Path:
    path = None
    if isinstance(value, str):
        path = Path(value)
    if isinstance(value, list):
        path = Path(*value)
    if str(path).startswith("."):
        path = path.resolve()
    return path


config = from_dict(
    data_class=EnvTestsConfig,
    data={k: v for k, v in os.environ.items() if hasattr(EnvTestsConfig, k)},
    config=Config(
        type_hooks={
            Path: _path_resolver,
        },
    ),
)

log = logging.getLogger(__name__)
log.setLevel(
    config.LOG_LEVEL
    # if config.LOG_LEVEL is not None
    # else framework_config["logging"].get("level", "WARNING")
)
log_format = framework_config["logging"].get(
    "format", "%(asctime)s - %(name)s - [%(levelname)s] - %(message)s"
)
formatter = logging.Formatter(log_format)

ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(formatter)
log.addHandler(ch)


def _fix_color_mapping(mapping):
    return {k: v.replace("\\u001b[", "\u001b[") for k, v in dict(mapping).items()}


COLORS = _fix_color_mapping(framework_config["changes.colors"])
ACTION_COLOR_MAP = _fix_color_mapping(framework_config["changes.action_color"])


class ImproperlyConfigured(Exception):
    pass


class FlagTypeEnum(Enum):
    STR = "str"
    PATH = "path"
    RESOLVED_PATH = "resolved_path"
    INT = "int"


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
                    self.value = self.value
                case FlagTypeEnum.PATH:
                    self.value = Path(self.value)
                case FlagTypeEnum.RESOLVED_PATH:
                    self.value = Path(self.value).resolve()
                # case _:
                #     self.value = self.value

    # def __str__(self):
    #     if self.value or self.type:
    #         return f"-{self.name} {self.value}"
    #     else:
    #         return f"-{self.name}"

    def build(self):
        log.info(f"Flag.build({self})")
        if self.value:  # or self.type:
            return f"-{self.name}", f"{self.value}"
        else:
            return (f"-{self.name}",)


class TreatableTypes(Enum):
    JSON = "json"
    YAML = "yaml"
    BYTES = "bytes"
    TEXT = "text"


@dataclasses.dataclass
class BaseContent:
    content: Optional[Union[str, bytes, dict, list]]
    encoding: Literal["utf-8"] = "utf-8"
    treat_as: TreatableTypes = TreatableTypes.BYTES
    file_path: Optional[Union[list, Path]] = None

    class Meta:
        least_one_required_fields: List[str] = ()
        not_allowed_together_fields: List[str] = ()

    def __post_init__(self):
        self.validate()

        if isinstance(self.file_path, (list, tuple)):
            log.warning(f"file_path is a list, joining: {self.file_path}")
            self.file_path = Path(*self.file_path)

        # if not self.file_path:
        #     if self.directory and self.file_name:
        #         self.file_path = self.directory / self.file_name

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
                log.info(f"<treated> Converting to json. Length: {len(self.content)}")
                data = json.loads(self.content)
            case TreatableTypes.YAML:
                log.info(f"<treated> Converting to yaml. Length: {len(self.content)}")
                data = EnvYAML(self.content)
        return data


@dataclasses.dataclass
class Content(BaseContent):
    content: Optional[Union[str, bytes, dict, list]]
    # directory: Optional[Path] = None
    # file_name: Optional[str] = None

    class Meta:
        least_one_required_fields = (
            "content",
            "file_path",
        )  # "directory", "file_name")
        not_allowed_together_fields = ("content", "file_path")

    def __bool__(self):
        return bool(self.content)

    def __post_init__(self):
        super().__post_init__()

        if self.file_path:
            self.content = self.file_path.read_text()

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
                self.content = json.loads(self.content)
            case TreatableTypes.YAML:
                log.info(f"Converting {self.file_path} to yaml")
                if self.file_path:
                    self.content = dict(
                        EnvYAML(str(self.file_path))
                    )  # TODO: review it! (self.content)


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

    def build_command(self, bin_path: Path) -> List[str]:
        log.info(self.flags)
        command = (
            # [str(bin_path)]
            ([f for flag in self.flags for f in flag.build()] if self.flags else [])
            + self.arguments
        )
        log.info(f"\n{command}")
        return command
        # return "".join(command)

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
            # executable=self.binary_path,
            args=[str(self.binary_path)] + command,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=self.shell,
            env=self.env,
            cwd=self.cwd,
        )
        output, err = proc.communicate(stdin)
        log.info("\t\tCommunicated")
        log.info(f"STDOUT: {output}")
        log.info(f"STDERR: {err}")

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

        if (
            self.expected_return_code is not None
            and self.expected_return_code != proc.returncode
        ):
            # Return code is different than expected
            yield (
                proc.returncode,
                self.expected_return_code,
                "Return code is different than expected",
            )

        # if self.test_file:
        #     # Compare output with test file
        #     yield (
        #         self.stdout.treated,
        #         self.test_file.content,
        #         "Command stdout and expected test file are different",
        #     )

        if self.expected_stdout:
            yield (
                self.stdout.treated,
                self.expected_stdout.content,
                "Command stdout and expected output are different",
            )
        if self.expected_stderr:
            yield (
                self.stderr.treated,
                self.expected_stderr.content,
                "Stderr and expected error are different",
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
            test.binary_path = self.binary_path
            test.default_parameters = self.default_parameters
            test.yaml_test_file_path = self.yaml_test_file_path
            test.root_env = self.env
            test.root_cwd = self.cwd

    def run_tests(self, verbose=False):
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


def load_configs(
    # tests_config_dir: Optional[Union[Path, str]] = "",
) -> Optional[List[TestConfig]]:
    global config
    tests_config_dir = config.TEST_CONFIGS_DIR
    log.warning(f"Loading configs from {tests_config_dir}")
    gathered_configs = []

    exclude_path = config.EXCLUDE_CONFIGS_DIR
    # os.environ.get("EXCLUDE_CONFIGS_DIR", "")

    # exclude_path: Optional[Path] = None
    # if exclude:
    #     exclude_path: Path = Path(exclude).resolve()
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
            test_config = from_dict(
                data_class=TestConfig,
                data=dict(
                    EnvYAML(
                        str(config_file.absolute()),
                    )
                ),
                config=Config(
                    cast=[FlagTypeEnum, TreatableTypes],
                    type_hooks={
                        Path: _path_resolver,
                    },
                ),
            )
            test_config.yaml_test_file_path = os.path.join(
                tests_config_dir, config_file
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
    return active_configs


class BaseTestCase(TestWithDiffs):
    test: ConfigTestCase

    def run_cases(self):
        for actual, expected, msg in self.test.run():
            log.debug(asdict(self.test))
            self.assertEqual(expected, actual)


def build_test_params(
    tests_config_dir: Optional[Union[Path, str]] = "",
) -> tuple[tuple[str, str], list[tuple[str, ConfigTestCase]]]:
    loaded_configs = load_configs(
        # tests_config_dir=os.environ.get("TEST_CONFIGS_DIR", tests_config_dir)
    )
    log.debug(f"Loaded configs: {loaded_configs}")
    return (
        ("name", "test"),
        [
            (
                f"{test_config.name}_{test.test}",
                test,
            )
            for test_config in loaded_configs
            for test in test_config.tests
        ],
    )
