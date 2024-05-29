import ditto


class TestAwesome(ditto.DittoTestCase):
    def test_dict(self):
        assert {1: "unittest"} == self.snapshot({1: "unittest"}, key="wowow")
