import pandas as pd

import ditto


class TestAwesome(ditto.DittoTestCase):
    def test_yio(self):
        assert {1: "unittest"} == self.snapshot({1: "unittest"}, identifier="wowow")

    def test_dataframe(self):

        input_data = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 9]})

        def fn(df: pd.DataFrame):
            df["a"] *= 2
            return df

        result = fn(input_data)

        pd.testing.assert_frame_equal(result, self.snapshot(result))
