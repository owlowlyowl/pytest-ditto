import ditto

    
class TestAwesome(ditto.DittoTestCase):
    def test_yio(self):
        assert {1: "unittest"} == self.snapshot({1: "unittest"}, suffix="yio", io_type="yaml")
