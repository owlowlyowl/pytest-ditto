from ditto_utils import is_optional_dependency_installed


if not is_optional_dependency_installed("pandas"):
    _msg = (
        "Required dependencies are not installed. "
        "Please install using `pip install ditto[pandas]`"
    )
    raise Exception(_msg)