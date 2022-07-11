import configparser
import dataclasses
import logging
import os
from pathlib import Path
from typing import Optional, Union, Dict

from dacite import from_dict, Config

# from yamlinclude.constructor import YamlIncludeConstructor

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

log_format = framework_config["logging"].get(
    "format",
    "%(asctime)s - %(name)s - [%(levelname)s] - %(message)s",
)


def _fix_color_mapping(mapping: Dict[str, str]) -> Dict[str, str]:
    return {k: v.replace("\\u001b[", "\u001b[") for k, v in mapping.items()}


COLORS = _fix_color_mapping(dict(framework_config["changes.colors"]))
ACTION_COLOR_MAP = _fix_color_mapping(dict(framework_config["changes.action_color"]))
