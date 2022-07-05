import re
import unittest

import textwrap

import dictdiffer
import diff_match_patch


class DiffMatchPatch(diff_match_patch.diff_match_patch):
    def diff_prettyText(self, diffs):
        """Convert a diff array into a pretty Text report.
        Args:
          diffs: Array of diff tuples.
        Returns:
          Text representation.
        """
        results_diff = []
        cut_next_new_line = [False]
        # print('\ndiffs:\n%s\n' % diffs)

        operations = (self.DIFF_INSERT, self.DIFF_DELETE)

        def parse(sign):
            # print('new1:', text.encode( 'ascii' ))

            if text:
                new = text

            else:
                return ""

            new = textwrap.indent("%s" % new, sign, lambda line: True)

            # force the diff change to show up on a new line for highlighting
            if len(results_diff) > 0:
                new = "\n" + new

            if new[-1] == "\n":

                if (
                    op == self.DIFF_INSERT
                    and next_text
                    and new[-1] == "\n"
                    and next_text[0] == "\n"
                ):
                    cut_next_new_line[0] = True

                    # Avoids a double plus sign showing up when the diff has the element (1, '\n')
                    if len(text) > 1:
                        new = new + "%s\n" % sign

            elif next_op not in operations and next_text and next_text[0] != "\n":
                new = new + "\n"

            # print('new2:', new.encode( 'ascii' ))
            return new

        for index in range(len(diffs)):
            op, text = diffs[index]
            if index < len(diffs) - 1:
                next_op, next_text = diffs[index + 1]
            else:
                next_op, next_text = (0, "")

            if op == self.DIFF_INSERT:
                results_diff.append(parse("+ "))

            elif op == self.DIFF_DELETE:
                results_diff.append(parse("- "))

            elif op == self.DIFF_EQUAL:
                # print('new3:', text.encode( 'ascii' ))
                text = textwrap.indent(text, "  ")

                if cut_next_new_line[0]:
                    cut_next_new_line[0] = False
                    text = text[1:]

                results_diff.append(text)
                # print('new4:', text.encode( 'ascii' ))

        return "".join(results_diff)

    def diff_linesToWords(self, text1, text2, delimiter=re.compile("\n")):
        """
        Split two texts into an array of strings.  Reduce the texts to a string
        of hashes where each Unicode character represents one line.

        95% of this function code is copied from `diff_linesToChars` on:
            https://github.com/google/diff-match-patch/blob/895a9512bbcee0ac5a8ffcee36062c8a79f5dcda/python3/diff_match_patch.py#L381

        Copyright 2018 The diff-match-patch Authors.
        https://github.com/google/diff-match-patch
        Licensed under the Apache License, Version 2.0 (the "License");
        you may not use this file except in compliance with the License.
        You may obtain a copy of the License at
          http://www.apache.org/licenses/LICENSE-2.0

        Args:
            text1: First string.
            text2: Second string.
            delimiter: a re.compile() expression for the word delimiter type

        Returns:
            Three element tuple, containing the encoded text1, the encoded text2 and
            the array of unique strings.  The zeroth element of the array of unique
            strings is intentionally blank.
        """
        lineArray = []  # e.g. lineArray[4] == "Hello\n"
        lineHash = {}  # e.g. lineHash["Hello\n"] == 4

        # "\x00" is a valid character, but various debuggers don't like it.
        # So we'll insert a junk entry to avoid generating a null character.
        lineArray.append("")

        def diff_linesToCharsMunge(text):
            """Split a text into an array of strings.  Reduce the texts to a string
            of hashes where each Unicode character represents one line.
            Modifies linearray and linehash through being a closure.
            Args:
                text: String to encode.
            Returns:
                Encoded string.
            """
            chars = []
            # Walk the text, pulling out a substring for each line.
            # text.split('\n') would would temporarily double our memory footprint.
            # Modifying text would create many large strings to garbage collect.
            lineStart = 0
            lineEnd = -1
            while lineEnd < len(text) - 1:
                lineEnd = delimiter.search(text, lineStart)

                if lineEnd:
                    lineEnd = lineEnd.start()

                else:
                    lineEnd = len(text) - 1

                line = text[lineStart : lineEnd + 1]

                if line in lineHash:
                    chars.append(chr(lineHash[line]))
                else:
                    if len(lineArray) == maxLines:
                        # Bail out at 1114111 because chr(1114112) throws.
                        line = text[lineStart:]
                        lineEnd = len(text)
                    lineArray.append(line)
                    lineHash[line] = len(lineArray) - 1
                    chars.append(chr(len(lineArray) - 1))
                lineStart = lineEnd + 1
            return "".join(chars)

        # Allocate 2/3rds of the space for text1, the rest for text2.
        maxLines = 666666
        chars1 = diff_linesToCharsMunge(text1)
        maxLines = 1114111
        chars2 = diff_linesToCharsMunge(text2)
        return (chars1, chars2, lineArray)


class TestWithDiffs(unittest.TestCase):
    ## Set the maximum size of the assertion error message when Unit Test fail
    maxDiff = None

    ## Whether `characters diff=0`, `words diff=1` or `lines diff=2` will be used
    diffMode = 1

    def __init__(self, *args, **kwargs):
        diffMode = kwargs.pop("diffMode", -1)
        if diffMode > -1:
            self.diffMode = diffMode

        super(TestWithDiffs, self).__init__(*args, **kwargs)

    def setUp(self):
        if diff_match_patch:
            self.addTypeEqualityFunc(str, self.assertEqual)

    @staticmethod
    def diff_chunk_as_text(
        chunk, colors: dict[str, str] = None, color_map: dict[str, str] = None
    ):
        if not colors:
            from framework import COLORS as colors
        if not color_map:
            from framework import ACTION_COLOR_MAP as color_map
        action, path, values = chunk
        text = f"\n\n{color_map[action]} => {action.upper()}{colors['reset']}: "
        left, right = values if len(values) == 2 else (values[0], "<None>")

        if action == "change":
            text += f"""at key {path} values are different 
            {colors['yellow']}BEFORE{colors['reset']}: {left} 
            {colors['yellow']}AFTER{colors['reset']}: {right}"""
        elif action == "add":
            text += f"""extra values under {path} key on the right: {left}
            """
        elif action == "remove":
            text += f"""missing values under {path} key on the right: {left}"""

        if not text.startswith("\u001b[") and not text.endswith(colors["reset"]):
            text = f"{text.strip()}{colors['reset']}"

        return text

    def assertEqual(self, expected, actual, msg=""):
        """
        How to wrap correctly the unit testing diff?
        https://stackoverflow.com/questions/52682351/how-to-wrap-correctly-the-unit-testing-diff
        """
        # print( '\n\nexpected\n%s' % expected )
        # print( '\n\nactual\n%s' % actual )

        if (
            not isinstance(expected, (str, bytes))
            and not isinstance(actual, (str, bytes))
            and expected != actual
        ):
            diff_chunks = list(dictdiffer.diff(expected, actual, expand=True))
            diff = "\n".join(
                [
                    self.diff_chunk_as_text(chunk)  # , COLORS, ACTION_COLOR_MAP)
                    for chunk in diff_chunks
                ]
            )
            # return self.fail(f"{msg}\n{diff}\n")
            return super().assertEqual(expected, actual, msg)

        if isinstance(expected, bytes):
            expected = expected.decode("utf-8")
        if isinstance(actual, bytes):
            actual = actual.decode("utf-8")

        if expected != actual:
            diff_match = DiffMatchPatch()
            print("DIFF MODE: ", self.diffMode)
            if self.diffMode == 0:
                diffs = diff_match.diff_main(expected, actual)

            else:
                diff_struct = diff_match.diff_linesToWords(
                    expected,
                    actual,
                    re.compile(r"\b") if self.diffMode == 1 else re.compile(r"\n"),
                )

                lineText1 = diff_struct[0]  # .chars1;
                lineText2 = diff_struct[1]  # .chars2;
                lineArray = diff_struct[2]  # .lineArray;

                diffs = diff_match.diff_main(lineText1, lineText2, False)
                diff_match.diff_charsToLines(diffs, lineArray)
                diff_match.diff_cleanupSemantic(diffs)

            if msg:
                msg += "\n"

            else:
                msg = "The strings does not match...\n"

            self.fail(msg + diff_match.diff_prettyText(diffs))


@unittest.skip
class DummyTest(TestWithDiffs):
    def test_dummy(self):
        pass

    def test_characthersDiffModeExample1(self):
        self.diffMode = 0
        expected = (
            "1. Duplicated target language name defined in your grammar on: [@-1,63:87='Abstract Machine Language'<__ANON_3>,3:19]\n"
            "2. Duplicated master scope name defined in your grammar on: [@-1,138:147='source.sma'<__ANON_3>,5:20]"
        )

        actual = (
            "1. Duplicated target language name defined in your grammar on: free_input_string\n"
            "  text_chunk_end  Abstract Machine Language\n"
            "\n"
            "2. Duplicated master scope name defined in your grammar on: free_input_string\n"
            "  text_chunk_end  source.sma"
        )
        with self.assertRaises(AssertionError) as error:
            self.assertEqual(expected, actual)

        print("\nerror.exception\n%s\n" % str(error.exception))
        self.assertEqual(
            "The strings does not match...\n"
            "  1. Duplicated target language name defined in your grammar on: \n"
            "- [@-1,63:87='\n"
            "+ free_input_string\n"
            "+   text_chunk_end  \n"
            "  Abstract Machine Language\n"
            "- '<__ANON_3>,3:19]\n"
            "+ \n"
            "  2. Duplicated master scope name defined in your grammar on: \n"
            "- [@-1,138:147='\n"
            "+ free_input_string\n"
            "+   text_chunk_end  \n"
            "  source.sma\n"
            "- '<__ANON_3>,5:20]",
            str(error.exception),
        )

    @unittest.skip
    def test_wordsDiffModeExample1(self):
        self.diffMode = 1
        expected = (
            "1. Duplicated target language name defined in your grammar on: [@-1,63:87='Abstract Machine Language'<__ANON_3>,3:19]\n"
            "2. Duplicated master scope name defined in your grammar on: [@-1,138:147='source.sma'<__ANON_3>,5:20]"
        )

        actual = (
            "1. Duplicated target language name defined in your grammar on: free_input_string\n"
            "  text_chunk_end  Abstract Machine Language\n"
            "\n"
            "2. Duplicated master scope name defined in your grammar on: free_input_string\n"
            "  text_chunk_end  source.sma"
        )
        with self.assertRaises(AssertionError) as error:
            self.assertEqual(expected, actual)

        print("\nerror.exception\n%s\n" % str(error.exception))
        self.assertEqual(
            "The strings does not match...\n"
            "  1. Duplicated target language name defined in your grammar on: \n"
            "- [@-1,63:87='Abstract Machine Language'<__ANON_3>,3:19]\n"
            "+ free_input_string\n"
            "+   text_chunk_end  Abstract Machine Language\n"
            "+ \n"
            "  2. Duplicated master scope name defined in your grammar on: \n"
            "- [@-1,138:147='source.sma'<__ANON_3>,5:20]\n"
            "+ free_input_string\n"
            "+   text_chunk_end  source.sma",
            str(error.exception),
        )

    @unittest.skip
    def test_linesDiffModeExample1(self):
        self.diffMode = 2
        expected = (
            "1. Duplicated target language name defined in your grammar on: [@-1,63:87='Abstract Machine Language'<__ANON_3>,3:19]\n"
            "2. Duplicated master scope name defined in your grammar on: [@-1,138:147='source.sma'<__ANON_3>,5:20]"
        )

        actual = (
            "1. Duplicated target language name defined in your grammar on: free_input_string\n"
            "  text_chunk_end  Abstract Machine Language\n"
            "\n"
            "2. Duplicated master scope name defined in your grammar on: free_input_string\n"
            "  text_chunk_end  source.sma"
        )
        with self.assertRaises(AssertionError) as error:
            self.assertEqual(expected, actual)

        print("\nerror.exception\n%s\n" % str(error.exception))
        self.assertEqual(
            "The strings does not match...\n"
            "- 1. Duplicated target language name defined in your grammar on: [@-1,63:87='Abstract Machine Language'<__ANON_3>,3:19]\n"
            "- 2. Duplicated master scope name defined in your grammar on: [@-1,138:147='source.sma'<__ANON_3>,5:20]\n"
            "+ 1. Duplicated target language name defined in your grammar on: free_input_string\n"
            "+   text_chunk_end  Abstract Machine Language\n"
            "+ \n"
            "+ 2. Duplicated master scope name defined in your grammar on: free_input_string\n"
            "+   text_chunk_end  source.sma",
            str(error.exception),
        )


# unittest.main(failfast=True, verbosity=2)
