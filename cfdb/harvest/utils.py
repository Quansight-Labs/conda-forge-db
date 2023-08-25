import os
import glob

from xonsh.tools import expand_path


def recursive_ls(root):
    """
    Recursively lists JSON files in subdirectories of a given root directory.

    Args:
        root (str): Root directory to start listing files from.

    Yields:
        tuple: A tuple containing package name and the relative path of each JSON file found.
    """
    packages = os.listdir(root)
    for package in packages:
        files = glob.glob(f"{root}/{package}/*/*/*.json")
        for file_path in files:
            relative_path = file_path.replace(f"{root}/{package}/", "")
            yield package, relative_path


def expand_file_and_mkdirs(x):
    """Expands a variable that represents a file, and ensures that the
    directory it lives in actually exists.
    """
    x = os.path.abspath(expand_path(x))
    d = os.path.dirname(x)
    os.makedirs(d, exist_ok=True)
    return x
