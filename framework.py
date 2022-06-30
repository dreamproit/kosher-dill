import dataclasses
import json
import logging
import os
import subprocess
import sys
import unittest
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from typing import List, Union, Dict, Any, Literal, Optional

import dictdiffer
from dacite import from_dict, Config
from envyaml import EnvYAML

# from pyaml_env import parse_config
# from pytest_dictsdiff import as_json
from differ import TestWithDiffs

log = logging.getLogger(__name__)
log.setLevel(os.environ.get("LOG_LEVEL", logging.INFO))
formatter = logging.Formatter("%(asctime)s - %(name)s - [%(levelname)s] - %(message)s")

ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(formatter)
log.addHandler(ch)

RED = "\u001b[31m"
GREEN = "\u001b[32m"
YELLOW = "\u001b[33m"
BLUE = "\u001b[34m"
MAGENTA = "\u001b[35m"
WHITE = "\u001b[37m"
RESET = "\u001b[0m"

ACTION_COLOR_MAP = {
    "change": GREEN,
    "add": MAGENTA,
    "remove": RED,
}


class ImproperlyConfigured(Exception):
    pass


def diff_chunk_as_text(chunk):
    action, path, values = chunk
    # path = ".".join(map(str, path)) if isinstance(path, (tuple, list)) else path
    # path = path or '<root>'
    text = f"\n\n{ACTION_COLOR_MAP[action]} => {action.upper()}{RESET}: "
    left, right = values if len(values) == 2 else (values[0], "<None>")
    # if left is None:
    #     text += f"{path} {WHITE}(removed){RESET}"
    # elif right is None:
    #     text += f"{path} {WHITE}(added){RESET}"
    # else:
    #     text += f"{path} {WHITE}({left} -> {right}){RESET}"
    # return text

    if action == "change":
        text += f"""at key {path} values are different 
        {YELLOW}BEFORE{RESET}: {left} 
        {YELLOW}AFTER{RESET}: {right}"""
    elif action == "add":
        text += f"""extra values under {path} key on the right: {left}
        """
    elif action == "remove":
        text += f"""missing values under {path} key on the right: {left}"""

    if not text.startswith("\u001b[") and not text.endswith(RESET):
        text = f"{text.strip()}{RESET}"

    return text


class FlagTypeEnum(Enum):
    STR = "str"
    PATH = "path"
    RESOLVED_PATH = "resolved_path"
    INT = "int"


@dataclasses.dataclass
class Flag:
    name: str
    type: Optional[FlagTypeEnum]
    value: Union[str, Path, int, None]

    def __post_init__(self):
        if self.value or self.type:
            match self.type:
                case FlagTypeEnum.STR:
                    self.value = self.value
                case FlagTypeEnum.PATH:
                    self.value = Path(self.value)
                case FlagTypeEnum.RESOLVED_PATH:
                    self.value = Path(self.value).resolve()
                case _:
                    self.value = self.value

    def __str__(self):
        if self.value or self.type:
            return f"-{self.name} {self.value}"
        else:
            return f"-{self.name}"


class TreatableTypes(Enum):
    JSON = "json"
    YAML = "yaml"
    BYTES = "bytes"
    TEXT = "text"


@dataclasses.dataclass
class Content:
    content: Optional[Union[str, bytes, dict, list]]
    file_path: Optional[Path]
    treat_as: TreatableTypes = TreatableTypes.BYTES
    encoding: Literal["utf-8"] = "utf-8"

    class Meta:
        least_one_required_fields = ("content", "file_path")
        not_allowed_together_fields = ("content", "file_path")

    def __bool__(self):
        return bool(self.content)

    def validate(self):
        if not any(
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
                    log.info("Converting to bytes")
                    data = bytes(self.content, self.encoding)
            case TreatableTypes.TEXT:
                if isinstance(self.content, bytes):
                    data = str(self.content.decode(self.encoding))
            case TreatableTypes.JSON:
                log.info("Converting to json")
                data = json.loads(self.content)
            case TreatableTypes.YAML:
                log.info("Converting to yaml")
                data = EnvYAML(self.content)
        return data

    def __post_init__(self):
        self.validate()

        if self.file_path is not None and not self.content:
            self.content = self.file_path.read_text()

        match self.treat_as:
            case TreatableTypes.BYTES:
                if isinstance(self.content, str):
                    log.info("Converting to bytes")
                    self.content = bytes(self.content, self.encoding)
            case TreatableTypes.TEXT:
                if isinstance(self.content, bytes):
                    self.content = str(self.content.decode(self.encoding))
            case TreatableTypes.JSON:
                log.info("Converting to json")
                self.content = json.loads(self.content)
            case TreatableTypes.YAML:
                log.info("Converting to yaml")
                if self.file_path:
                    self.content = EnvYAML(
                        self.file_path
                    )  # TODO: review it! (self.content)


@dataclasses.dataclass
class WritableContent(Content):
    file_path: Optional[Path] = None

    class Meta:
        least_one_required_fields = ("content", "file_path")
        not_allowed_together_fields = ()

    def __post_init__(self):
        self.validate()

    def save(self):
        log.info(f"Saving {self} \nto\n{self.file_path}")
        if self.file_path is not None:
            if not self.file_path.parent.exists():
                self.file_path.parent.mkdir(parents=True)
            if not self.file_path.exists():
                self.file_path.touch()
            self.file_path.write_text(self.content)
        else:
            log.debug(self.content)


@dataclasses.dataclass
class ToolCommand:
    test: str

    test_file: Optional[Content]
    expected_stdout: Optional[Content]
    expected_stderr: Optional[Content]

    skip: bool = False
    flags: Optional[List[Flag]] = dataclasses.field(default_factory=list)
    arguments: Optional[List[str]] = dataclasses.field(default_factory=list)
    stdin: Optional[Content] = None
    stdout: Optional[WritableContent] = None
    stderr: Optional[WritableContent] = None
    expected_return_code: int = 0

    default_parameters: Optional[dict] = None
    binary_path: Optional[Path] = None
    yaml_test_file_path: Optional[Path] = None
    shell: bool = False
    root_env: Optional[dict] = None
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

    def build_command(self, bin_path: Path):
        command = (
            [str(bin_path)]
            + ([str(flag) for flag in self.flags] if self.flags else [])
            + self.arguments
        )
        log.info(f"\n{command}")
        return command

    def __post_init__(self):
        if self.env or self.root_env:
            env = dict(os.environ, **(self.root_env or {}), **(self.env or {}))
            log.debug(f"env: {env}")
            self.env = env

        log.info(
            f"\n\n\nRESOLVE CWD\nself.cwd={self.cwd}\nself.root_cwd={self.root_cwd}"
        )
        if self.cwd or self.root_cwd:
            self.cwd = self.cwd or self.root_cwd

        required_fields = [
            self.expected_return_code,
            self.expected_stdout,
            self.expected_stderr,
        ]
        if not any([field is not None for field in required_fields]):
            raise ImproperlyConfigured(
                f"[{self.yaml_test_file_path}] At least one of {self.Meta.least_one_required_fields} must be provided"
            )

    def run(self, bin_path: Optional[Path] = None):
        if self.skip:
            return

        bin_path = bin_path or self.binary_path
        stdin = self.stdin.content if self.stdin else None
        log.info("\n")
        log.debug(f"\t{self.test}")
        command = self.build_command(bin_path)

        log.info(
            f"\t\t* RUN: {' '.join(command)} {' < ' + str(self.stdin.file_path) if self.stdin else ''}"
        )
        log.info(f"\t\t* IN: {self.cwd}")
        # log.info(dict(os.environ))
        proc = subprocess.Popen(
            command,
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

        if self.test_file:
            # Compare output with test file
            yield (
                self.stdout.treated,
                self.test_file.content,
                "Command stdout and expected test file are different",
            )

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
class ToolCommandTests:
    binary_path: Path
    default_parameters: Dict[str, Any]
    name: str
    test: Optional[str]
    tests: List[ToolCommand]

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
            log.warning(f"{YELLOW}SKIPPING{RESET} {self.name}")
            return
        log.warning(f"{GREEN}RUNNING{RESET} {self.name}")
        log.debug(f"{self.test}")
        for test in self.tests:
            if test.skip:
                continue
            for exp, out, err in test.run(
                self.binary_path,
            ):
                yield exp, out, err


def load_configs() -> Optional[List[ToolCommandTests]]:
    tests_config_dir: str = os.environ.get("TEST_CONFIGS_DIR", "test_configs/")
    log.info(f"Loading configs from {tests_config_dir}")
    gathered_configs = []

    exclude: str = os.environ.get("EXCLUDE_CONFIGS_DIR", "")

    exclude_path: Optional[Path] = None
    if exclude:
        exclude_path: Path = Path(exclude).resolve()

    for config_file in Path(tests_config_dir).rglob("*.yaml"):
        config_file = config_file.absolute()
        if exclude_path and config_file.is_relative_to(exclude_path):
            log.info(f"Excluding file {config_file}")
            continue
        config = from_dict(
            data_class=ToolCommandTests,
            data=dict(
                EnvYAML(
                    str(config_file.absolute()),
                )
            ),
            config=Config(
                cast=[FlagTypeEnum, TreatableTypes],
                type_hooks={
                    Path: lambda v: Path(v).resolve() if v.startswith(".") else Path(v),
                },
            ),
        )
        config.yaml_test_file_path = os.path.join(tests_config_dir, config_file)
        gathered_configs.append(config)

    if not gathered_configs:
        raise ImproperlyConfigured("No configs found in {}".format(tests_config_dir))

    active_configs = [config for config in gathered_configs if config.skip is not True]

    if not active_configs:
        raise ImproperlyConfigured(
            "No active configs found in {}".format(tests_config_dir)
        )
    return active_configs


def build_test_params():
    return (
        ("name", "test"),
        [
            (
                f"{config.name}",
                test,
            )
            for config in load_configs()
            for test in config.tests
        ],
    )


class BaseTestCase(TestWithDiffs):
    test: ToolCommand

    def run_cases(self):
        for actual, expected, msg in self.test.run():
            log.debug(asdict(self.test))
            if actual == expected:
                return True
            else:
                show_diff: bool = isinstance(expected, str)
                print(show_diff)
                if show_diff:
                    diff_chunks = list(dictdiffer.diff(expected, actual, expand=True))
                    diff = "\n".join(
                        [diff_chunk_as_text(chunk) for chunk in diff_chunks]
                    )
                    self.assertEqual(actual, expected, f"{msg}\n{diff}\n")
                else:
                    self.assertEqual(actual, expected)
                # self.fail(self._formatMessage("Provided values are not equal", diff))
                # self.fail(safe_repr(diff))
            # else:
            #     sep = "\n" + ("=" * 80) + "\n"
            #     msg_lines = [
            #         "Provided items are NOT the same.",
            #         "Left:",
            #         as_json(d1),
            #         sep,
            #         "Right:",
            #         as_json(d2),
            #         sep,
            #         "Diff:",
            #         diff,
            #     ]
            # pytest.fail("\n\n".join(msg_lines))
