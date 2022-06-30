import argparse
from framework import load_configs

# create the top-level parser
parser = argparse.ArgumentParser(prog="Testing tools")
parser.add_argument("--foo", action="store_true", help="foo help")
subparsers = parser.add_subparsers(help="commands")

# create the parser for the "a" command
parser_generate_test_files = subparsers.add_parser(
    "generate-test-files", help="generate test files"
)
parser_generate_test_files.add_argument("bar", type=int, help="bar help")

# create the parser for the "b" command
parser_b = subparsers.add_parser("b", help="b help")
parser_b.add_argument("--baz", choices="XYZ", help="baz help")

# parse some argument lists
print(parser.parse_args())
# ['a', '12'])

# parser.parse_args()  # ['--foo', 'b', '--baz', 'Z'])


# configs = load_configs()
