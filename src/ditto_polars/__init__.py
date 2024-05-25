from ditto_utils import is_optional_dependency_installed


if not is_optional_dependency_installed("polars"):
    _msg = (
        "Required dependencies are not installed. "
        "Please install using `pip install pytest-ditto[polars]`"
    )
    raise Exception(_msg)