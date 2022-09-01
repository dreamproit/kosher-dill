from differ import TestWithDiffs


class DummyTest(TestWithDiffs):
    def test_dummy(self):
        pass

    def test_characthersDiffModeExample1(self):
        self.diffMode = 0
        expected = (
            "1. Duplicated target language name defined in your grammar on: "
            "[@-1,63:87='Abstract Machine Language'<__ANON_3>,3:19]\n"
            "2. Duplicated master scope name defined in your grammar on: "
            "[@-1,138:147='source.sma'<__ANON_3>,5:20]"
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

        # print("\nerror.exception\n%s\n" % str(error.exception))
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

    # @unittest.skip
    def test_wordsDiffModeExample1(self):
        self.diffMode = 1
        expected = (
            "1. Duplicated target language name defined in your grammar on: "
            "[@-1,63:87='Abstract Machine Language'<__ANON_3>,3:19]\n"
            "2. Duplicated master scope name defined in your grammar on: "
            "[@-1,138:147='source.sma'<__ANON_3>,5:20]"
        )

        actual = (
            "1. Duplicated target language name defined in your grammar on:"
            " free_input_string\n"
            "  text_chunk_end  Abstract Machine Language\n"
            "\n"
            "2. Duplicated master scope name defined in your grammar on:"
            " free_input_string\n"
            "  text_chunk_end  source.sma"
        )
        with self.assertRaises(AssertionError) as error:
            self.assertEqual(expected, actual)

        # print("\nerror.exception\n%s\n" % str(error.exception))
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

    # @unittest.skip
    def test_linesDiffModeExample1(self):
        self.diffMode = 2
        expected = (
            "1. Duplicated target language name defined in your grammar on: "
            "[@-1,63:87='Abstract Machine Language'<__ANON_3>,3:19]\n"
            "2. Duplicated master scope name defined in your grammar on: "
            "[@-1,138:147='source.sma'<__ANON_3>,5:20]"
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

        # print("\nerror.exception\n%s\n" % str(error.exception))
        self.assertEqual(
            "The strings does not match...\n"
            "- 1. Duplicated target language name defined in your grammar on: "
            "[@-1,63:87='Abstract Machine Language'<__ANON_3>,3:19]\n"
            "- 2. Duplicated master scope name defined in your grammar on: "
            "[@-1,138:147='source.sma'<__ANON_3>,5:20]\n"
            "+ 1. Duplicated target language name defined in your grammar on: free_input_string\n"
            "+   text_chunk_end  Abstract Machine Language\n"
            "+ \n"
            "+ 2. Duplicated master scope name defined in your grammar on: free_input_string\n"
            "+   text_chunk_end  source.sma",
            str(error.exception),
        )
