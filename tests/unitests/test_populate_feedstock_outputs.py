from pathlib import Path
import pytest
from cfdb.populate.feedstock_outputs import traverse_files
from cfdb.populate.utils import hash_file


@pytest.fixture
def json_dir(tmpdir):
    # Create a temporary directory
    root_dir = tmpdir.mkdir("test_outputs")

    # Create sample JSON files in the directory
    file1 = root_dir.join("file1.json")
    file1.write('{"feedstocks": ["feedstock1", "feedstock2"]}')

    file2 = root_dir.join("file2.json")
    file2.write('{"feedstocks": ["feedstock3"]}')

    file3 = root_dir.mkdir("subdir").join("file3.json")
    file3.write('{"feedstocks": ["feedstock4", "feedstock5", "feedstock6"]}')

    yield Path(root_dir)

    # Clean up the temporary directory
    root_dir.remove()


def test_traverse_files(json_dir):
    # Call the traverse_files function
    output_dir = json_dir  # Use the same directory as the input for simplicity
    stored_files = traverse_files(json_dir, output_dir)

    # Assert that the returned value is a list of paths
    assert isinstance(stored_files, list)
    assert all(isinstance(file, Path) for file in stored_files)

    # Assert that the number of stored files matches the expected count
    expected_num_files = 1  # The total number of batch files created
    assert len(stored_files) == expected_num_files

    # Assert that each stored file is a valid path
    assert all(file.exists() for file in stored_files)
    assert all(file.is_file() for file in stored_files)

    # Assert the contents of the stored files (optional)
    for file in stored_files:
        assert (
            "batch_" in file.name
        )  # Check if the file name matches the expected pattern

    file_contents = []
    for file in stored_files:
        with open(file, "r") as f:
            for line in f:
                file_contents.append(line.strip().split(","))

    # Assert the contents of the stored files (optional)
    assert all(Path(file[0]).exists() for file in file_contents)

    # Assert the hashes of the stored files (optional)
    for file, hash in file_contents:
        with open(file, "rb") as f:
            assert hash == hash_file(file)

    # Assert the number of feedstocks in each file corresponds to the expected count
    assert len(file_contents) == 3


def test_compare_files():
    ...
