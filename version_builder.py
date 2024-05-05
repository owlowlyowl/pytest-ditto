import subprocess


def _version():
    # ensure clone isn't shallow to get all tags
    process = subprocess.run(
        ["git", "fetch", "--unshallow"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
    )

    try:
        process.check_returncode()
    except subprocess.CalledProcessError as exc:
        if (
            "unshallow on a complete repository does not make sense"
            not in process.stdout
        ):
            raise RuntimeError(process.stdout) from exc

    process = subprocess.run(
        ["git", "describe", "--tags", "--long"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
    )
    try:
        process.check_returncode()
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(process.stdout) from exc

    version, build_num, sha = process.stdout.strip().split("-")
    if build_num == "0":
        version_str = version
    else:
        version_str = f"{version}.post.dev{int(build_num):03d}+{sha[1:]}"

    return version_str


if __name__ == "__main__":
    if version := _version():
        print(version)
    else:
        print("Error: Failed to get version.")
