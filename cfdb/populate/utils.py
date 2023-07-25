import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import glob
import hashlib
import json
from pathlib import Path
from typing import List, Callable

from cfdb.log import logger


def hash_file(filename: str) -> str:
    """
    Returns the SHA-1 hash of the file passed into it.

    Args:
        filename (str): The path to the file.

    Returns:
        str: The hexadecimal representation of the file's SHA-1 hash.
    """
    h = hashlib.sha1()

    with open(filename, "rb") as file:
        chunk = file.read(1024)
        while chunk:
            h.update(chunk)
            chunk = file.read(1024)

    return h.hexdigest()


def process_batch(batch_files: List[Path], tmp_file: Path) -> None:
    """
    Process a batch of files, calculate their hashes, and write the list of file paths
    and hashes to the temporary file.

    Args:
        batch_files (List[Path]): The list of files in the batch.
        tmp_file (Path): The path to the temporary file.
    """
    with open(tmp_file, "w") as f:
        for file in batch_files:
            file_hash = hash_file(file)
            f.write(f"{file},{file_hash}\n")


def retrieve_associated_feedstock_from_output_blob(file: Path):
    """
    Retrieves the associated feedstocks from the output blob file.

    Args:
        file (Path): The path to the output blob file.

    Returns:
        List[str]: A list of associated feedstock names.
    """
    with open(file, "r") as f:
        payload = json.loads(f.read())

    _, associated_feedstocks = payload.popitem()
    return associated_feedstocks


def retrieve_import_maps_from_output_blob(file: Path):
    """

    Args:
        file (Path): The path to the output blob file.

    Returns:
        List[str]: A list of associated feedstock names.
    """
    with open(file, "r") as f:
        payload = json.loads(f.read())

    packages_to_imports = {}
    for import_name, _set in payload.items():
        elements = _set["elements"]  # should return a list
        for element in elements:
            if element not in packages_to_imports:
                packages_to_imports[element] = [import_name]
            else:
                packages_to_imports[element].append(import_name)

    return packages_to_imports


def traverse_files(
    path: Path, output_dir: Path = None, process_function: Callable = process_batch
) -> List[Path]:
    """
    Traverses a directory of JSON files, generating a list of dictionaries
    with file paths and hashes. These dictionaries are written to an output directory.

    The hashes allow comparison between the directory and a database for necessary updates.
    Files are processed in batches of 1000 to optimize memory usage.

    Args:
        path (Path): The path to the directory containing the JSON files.
        output_dir (Path, optional): The output directory to store the list of dictionaries.
            If not provided, the current directory will be used. Defaults to None.

    Returns:
        List[Path]: A list of paths to the stored files.
    """
    if not path.is_dir():
        raise NotADirectoryError(f"{path} is not a directory.")

    files = list(glob.iglob(f"{path}/**/*.json", recursive=True))

    num_of_files = len(files)
    num_of_batches = num_of_files // 1000

    if num_of_files % 1000 != 0:
        num_of_batches += 1

    logger.debug(f"JSON blob files: {num_of_files} (in {num_of_batches} batches)")

    if output_dir is None:
        output_dir = Path(".")

    stored_files = []

    with ThreadPoolExecutor() as executor:
        for i in range(num_of_batches):
            tmp_file = output_dir / f"batch_{i}.json"
            logger.debug(f"Creating temporary file {tmp_file}...")
            batch_files = files[i * 1000 : (i + 1) * 1000]
            batch_files.reverse()

            executor.submit(process_function, batch_files, tmp_file)

            stored_files.append(tmp_file)

    del files

    return stored_files
