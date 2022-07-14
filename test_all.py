import unittest
from typing import Callable

from parameterized import parameterized_class

from framework import (
    build_test_params,
    BaseTestCase,
)


@parameterized_class(*build_test_params())
class Test(BaseTestCase):
    diffMode = 2
    name: str
    test: Callable

    def test_case(self):
        self.run_cases()


if __name__ == "__main__":
    print("Running tests")
    unittest.main()
    print("Done")