from ditto import DittoTestCase

    
class TestAwesome(DittoTestCase):
    def test_yio(self):
        assert {1: "unittest"} == self.snapshot({1: "unittest"})
