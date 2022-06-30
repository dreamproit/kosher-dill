import logging
import os
import sys
import unittest

from parameterized import parameterized_class

from framework import (
    build_test_params,
    BaseTestCase,
)

log = logging.getLogger(__name__)
log.setLevel(os.environ.get("LOG_LEVEL", logging.INFO))
formatter = logging.Formatter("%(asctime)s - %(name)s - [%(levelname)s] - %(message)s")

ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(formatter)
log.addHandler(ch)


@parameterized_class(*build_test_params())
class TestAllCases(BaseTestCase):
    def test_case(self):
        self.run_cases()


if __name__ == "__main__":
    print("Running tests")
    unittest.main()
    print("Done")
