import ditto


class TestAwesome(ditto.DittoTestCase):
    def test_dict(self):
        
        def fn(x: dict[str, int]) -> dict[str, int]:
            return {k: v + 1 for k, v in x.items()}

        result = fn({"unittest": 0})

        assert result == self.snapshot(result, key="wowow")
