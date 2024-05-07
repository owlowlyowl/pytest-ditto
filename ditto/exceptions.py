class DittoException(Exception):
    pass


class AdditionalMarkError(DittoException):
    def __init__(self):
        super().__init__("Only one record mark is allowed per test.")
