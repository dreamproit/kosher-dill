import logging
import os
import sys
import unittest
from dataclasses import asdict

import dictdiffer
from parameterized import parameterized

from framework import load_configs, ToolCommand, diff_chunk_as_text

log = logging.getLogger(__name__)
log.setLevel(os.environ.get("LOG_LEVEL", logging.INFO))
formatter = logging.Formatter("%(asctime)s - %(name)s - [%(levelname)s] - %(message)s")

ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(formatter)
log.addHandler(ch)

configs = []


class TestDemonstrateSubtest(unittest.TestCase):
    @parameterized.expand(
        [
            (
                f"{config.name} {test.test}",
                test,
            )
            for config in load_configs()
            for test in config.tests
        ]
    )
    def test(self, case_name: str, test: ToolCommand):
        for actual, expected, msg in test.run():
            log.debug(asdict(test))
            log.warning(f"ACT={type(actual)}\nEXP={type(expected)}\nMSG={msg}")
            if actual == expected:
                return True
            else:
                diff_chunks = list(dictdiffer.diff(expected, actual, expand=True))
                diff = "\n".join([diff_chunk_as_text(chunk) for chunk in diff_chunks])
                self.assertEqual(actual, expected, f"{msg}\n{diff}\n")
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


if __name__ == "__main__":
    print("Running tests")
    unittest.main()
    print("Done")
