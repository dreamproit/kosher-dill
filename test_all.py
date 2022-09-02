import unittest
from typing import Callable

from parameterized import parameterized_class, parameterized

from framework import (
    build_test_params,
    BaseTestCase,
)


def get_class_name(cls, num, params_dict):
    """Custom function to setup Test class name."""
    # setting up test number the first value will be 000000.
    num = num / 100000
    num = f"{num:.5f}".replace('.', '')
    test_name = "{test_class_name}_{test_number}_{test_name}".format(
        test_class_name=cls.__name__,
        test_number=num,
        test_name=parameterized.to_safe_name(params_dict["name"]),
    )
    return test_name


@parameterized_class(*build_test_params(), class_name_func=get_class_name)
class Test(BaseTestCase):
    diff_mode = 2
    name: str
    test: Callable

    def test_case(self):
        self.run_cases()


if __name__ == "__main__":
    print("Running tests")
    unittest.main()
    print("Done")
