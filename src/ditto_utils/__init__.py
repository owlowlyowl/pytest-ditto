import importlib.metadata


def is_optional_dependency_installed(package_name: str) -> bool:
    """Check if a package is installed."""
    installed_packages = importlib.metadata.packages_distributions()
    return package_name in installed_packages
