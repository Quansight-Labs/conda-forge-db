from pathlib import Path
from tempfile import TemporaryDirectory
import json

from sqlalchemy.orm import Session

from cfdb.populate.utils import (
    traverse_files,
    retrieve_associated_feedstock_from_output_blob,
)
from typing import List
from cfdb.log import logger, progressBar
from cfdb.models.schema import Artifacts, Packages, ArtifactsFilePaths


def _compare_files(artifacts, stored_files_index, root_dir):
    """Retrieve filestem from path to identify the package name and compare with the database. Also, loads the file using json to retrieve the metadata about the version and build."""

    db_files = set()
    stored_files_set = set()

    # Process the artifacts
    for row in artifacts:
        name, package_name, platform, version, build = row
        db_files.add(
            (
                f"{package_name}/conda-forge/{name}.json",
                package_name,
                platform,
                version,
                build,
            )
        )

    # Process the stored files index
    for stored_file in stored_files_index:
        with open(stored_file, "r") as f:
            for line in f:
                file_path, package_name, platform, version, build = line.strip().split(
                    ","
                )
                stored_files_set.add(
                    (file_path, package_name, platform, version, build)
                )

    changed_files = stored_files_set - db_files

    if changed_files:
        num_changed_files = len(changed_files)
        logger.info(f"Detected {num_changed_files} modified files.")

    return changed_files


def _update_artifacts_and_filepaths(
    session: Session,
):
    ...


def _process_artifact_batches(batch_files: List[Path], tmp_file: Path):
    """
    Process artifact batches and extract relevant information into a temporary file.

    This function takes a list of file paths representing batches of artifact data in JSON format
    and extracts essential information from each artifact's index section. The extracted data is
    then formatted as comma-separated values (CSV) and written to a temporary file.

    Parameters:
        batch_files (List[Path]): A list of Path objects representing file paths for artifact batches
                                  in JSON format.

        tmp_file (Path): A Path object representing the file path for the temporary file where the
                         processed data will be written in CSV format.

    Note:
        The function assumes that the JSON files contain a dictionary with an "index" key, which in
        turn contains "subdir", "name", "version", and "build_number" keys to extract the relevant
        information for each artifact.

    """
    processed_data = []

    for file in batch_files:
        with open(file, "r") as blob:
            artifact_contents = json.loads(blob.read())

        index = artifact_contents.get("index", {})
        platform = index.get("subdir")
        package_name = index.get("name")
        version = index.get("version")
        build_number = index.get("build_number")

        _str = f"{file},{package_name},{platform},{version},{build_number}\n"
        processed_data.append(_str)

    with open(tmp_file, "w") as f:
        f.writelines(processed_data)


def sort_tuples_by_package(tuples_list):
    """
    Sort a list of tuples by the package_name and create a dictionary.

    This function takes a list of tuples in the format `(path, package_name, platform, version, build)`
    and sorts the tuples into a dictionary where each key is the `package_name`, and the values are
    lists of tuples containing the corresponding `path`, `platform`, `version`, and `build` values.

    Parameters:
        tuples_list (List[Tuple]): A list of tuples in the format (path, package_name, platform, version, build),
                                   representing the artifacts to be sorted.

    Returns:
        dict: A dictionary where each key is the `package_name`, and the values are lists of tuples
              containing the corresponding `path`, `platform`, `version`, and `build` values.

    Note:
        The function assumes that the input `tuples_list` contains valid tuples, and the elements
        within each tuple are in the expected order: (path, package_name, platform, version, build).
    """
    sorted_dict = {}

    for path, package_name, platform, version, build in tuples_list:
        # Create a tuple without the package_name
        remaining_tuple = (path, platform, version, build)

        # Check if the package_name is already a key in the dictionary
        if package_name in sorted_dict:
            sorted_dict[package_name].append(remaining_tuple)
        else:
            sorted_dict[package_name] = [remaining_tuple]

    return sorted_dict


def update_filepaths_table(
    session: Session, artifact: Artifacts, filepath: Path, root_dir: Path
):
    # retrieve associated filepaths already stored in the database

    filepaths = (
        session.query(ArtifactsFilePaths)
        .filter_by(package_name=artifact.package_name)
        .all()
    )

    with open(root_dir / filepath, "r") as f:
        artifact_contents = json.loads(f.read())

    # retrieve associated path list
    files = artifact_contents.get("files", [])

    if files:
        # check if the filepaths are already stored in the database
        for file in files:
            # check if the filepath is already stored in the database
            if file not in filepaths:
                # create a new ArtifactsFilePaths object
                new_filepath = ArtifactsFilePaths(
                    package_name=artifact.package_name,
                    path=file,
                )
                session.add(new_filepath)
        session.commit()

    return session


def update(session: Session, path: Path):
    """
    Updates all artifacts in the database based on the recent changes from the harvested data.

    Args:
        session (Session): The database session.
        path (Path): The path to the directory containing the JSON files. From "harvesting".
    """
    _tmp_dir = TemporaryDirectory()
    tmp_dir = Path(_tmp_dir.name)
    logger.info(
        "Querying database for Recent Artifacts..."
    )  # query artifacts whose last_update was under the cron range -- hum, need to think more about this...
    artifacts = session.query(
        Artifacts.name,
        Artifacts.package_name,
        Artifacts.platform,
        Artifacts.version,
        Artifacts.build,
    ).all()

    logger.info(f"Traversing files in {path}...")
    # detect number of JSON blobs locally available, and store related paths/hashes into batched index files named stored_files (list)
    stored_files = traverse_files(
        path, tmp_dir, process_function=_process_artifact_batches
    )

    logger.info("Comparing files...")
    changed_files = _compare_files(artifacts, stored_files, root_dir=path)
    _total_artifact_count = len(changed_files)

    if _total_artifact_count == 0:
        logger.info("No changes detected. Exiting...")
        return

    sorted_changed_files = sort_tuples_by_package(changed_files)
    del changed_files

    with progressBar:
        for idx, (package_name, values) in enumerate(
            progressBar.track(
                sequence=sorted_changed_files.items(),
                description="Updating artifacts...",
            )
        ):
            package = (
                session.query(Packages).filter(Packages.name == package_name).first()
            )

            if not package:
                logger.debug(
                    f"Package '{package_name}' not found in database. Proceeding to create it and its related artifacts."
                )
                package = Packages(
                    name=package_name,
                )
                session.add(package)

            for artifact_blob in values:
                file, platform, version, build_number = artifact_blob
                artifact_name = Path(file).stem
                logger.info(f"Updating {package_name} :: {platform} :: {artifact_name}")

                # Updating asv :: conda-forge :: linux-64 :: asv-0.2.1-py35hfc679d8_0.json

                # Create a new artifact record -- artifacts will always be created, never updated

                artifact = Artifacts(
                    name=f"{platform}/{artifact_name}",
                    package_name=package.name,
                    platform=platform,
                    version=version,
                    build=build_number,
                )

                # Add the new artifact to the session
                session.add(artifact)

                update_filepaths_table(session, artifact, Path(file), path)

            #         # Create a new artifact record -- artifacts will always be created, never updated
            #         new_artifact = Artifacts(
            #             name=file.stem,
            #             package_name=package_name,
            #             platform=arch,
            #         )

            #         # session = _link_files_to_artifacts(
            #         #     artifact=new_artifact, file_path=file, session=session, root_dir=path
            #         # )

            if idx % 10 == 0:
                session.commit()

    session.commit()

    # with progressBar:
    #     for idx, (file, file_hash) in enumerate(
    #         progressBar.track(changed_files, description="Updating artifacts...")
    #     ):
    #         ...

    #         if idx % 100 == 0:
    #             session.commit()

    #     session.commit()


# def update(session: Session, path: Path):
#     """
#     Updates all artifacts in the database based on the recent changes from the harvested data.

#     Args:
#         session (Session): The database session.
#         path (Path): The path to the directory containing the JSON files. From "harvesting".
#     """
#     _tmp_dir = TemporaryDirectory()
#     tmp_dir = Path(_tmp_dir.name)

#     logger.info("Querying database for Recent Artifacts...")
#     artifacts = session.query(Artifacts.path, Artifacts.hash, Artifacts.name).all()

#     logger.info(f"Traversing files in {path}...")
#     stored_files = traverse_files(path, tmp_dir)

#     logger.info("Comparing files...")
#     changed_files = _compare_files(artifacts, stored_files, root_dir=path)

#     if len(changed_files) == 0:
#         logger.info("No changes detected. Exiting...")
#         return

#     with progressBar:
#         for idx, (file, file_hash) in enumerate(
#             progressBar.track(changed_files, description="Updating feedstocks...")
#         ):
#             associated_package_name = file.stem
#             associated_feedstocks = retrieve_associated_feedstock_from_output_blob(
#                 file=path / file  # Need to use the absolute path here
#             )
#             logger.debug(
#                 f"Associated package name: '{associated_package_name}' :: Associated feedstocks: '{associated_feedstocks}'"
#             )
#             package = (
#                 session.query(Packages)
#                 .filter(Packages.name == associated_package_name)
#                 .first()
#             )

#             if not package:
#                 logger.debug(
#                     f"Package '{associated_package_name}' not found in database. Proceeding to create it and its feedstock outputs."
#                 )
#                 package = Packages(
#                     name=associated_package_name,
#                 )
#                 session.add(package)

#             for file_name in associated_files:
#                 session = _update_artifact_files(
#                     session=session,
#                     file_rel_path=file,
#                     file_hash=file_hash,
#                     package_name=package.name,
#                 )

#             if idx % 100 == 0:
#                 session.commit()

#             # Add the artifact to the Artifacts table
#             artifact_name = f"{package.name}/{file.name}"
#             artifact = Artifacts(
#                 name=artifact_name,
#                 path=str(file),
#                 hash=file_hash,
#             )
#             session.add(artifact)

#     session.commit()

if __name__ == "__main__":
    from cfdb.handler import CFDBHandler

    path = "/Users/vinicius/Conda-forge/artificial-libcfgraph/small-artifacts"

    db_handler = CFDBHandler("sqlite:///cf-database.db")
    db_handler.update_artifacts(path)
