from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy.orm import Session

from cfdb.populate.utils import (
    traverse_files,
    retrieve_associated_feedstock_from_output_blob,
)
from cfdb.log import logger, progressBar
from cfdb.models.schema import (
    Artifacts,
    ArtifactsFilePathsLinux,
    ArtifactsFilePathsMac,
    ArtifactsFilePathsNoArch,
    ArtifactsFilePathsWin,
    Packages,
)


def _compare_files(artifacts, stored_files, root_dir):
    """
    Compares the Artifacts outputs from the database with the stored files (harvested), and returns a set of files that were not present in the database or were updated.

    Args:

    Returns:
    """
    db_files = {(Path(row[0]), row[1]) for row in artifacts}
    stored_files_set = set()

    for stored_file in stored_files:
        with open(stored_file, "r") as f:
            for line in f:
                file_path, file_hash = line.strip().split(",")
                stored_files_set.add((Path(file_path).relative_to(root_dir), file_hash))

    changed_files = stored_files_set - db_files

    if len(changed_files) > 0:
        logger.info(f"Detected {len(changed_files)} modified files.")

    return changed_files


def _update_feedstock_outputs(
    session: Session,
) -> Session:
    """
    Update or create the artifacts in the database based on the comparison between the stored data and the current data.

    Args:
        session (Session): The SQLAlchemy session object.

    Returns:
        Session: The updated SQLAlchemy session object.
    """
    artifacts = session.query(Artifacts).all()

    return session


import json


def _link_files_to_artifacts(
    session: Session, artifact: Artifacts, file_path: Path, root_dir: Path
):
    """
    Link the file path to the artifact in the database.

    Args:
        session (Session): The SQLAlchemy session object.
        artifact (Artifacts): The artifact object.
        file_path (Path): The path to the file.
    """
    try:
        with open(root_dir / file_path, "r") as f:
            yaml_json = json.load(f)

    except Exception as e:
        if "YAML" in str(e):
            logger.warning(f"Could not parse YAML file {file_path}.")
        elif "JSON" in str(e):
            logger.warning(f"Could not parse JSON file {file_path}.")
        elif "No such file" in str(e):
            logger.warning(f"File {file_path} does not exist.")
        else:
            logger.warning(f"Could not parse file {file_path}. Skipping...")
        return session

    files = yaml_json["files"]

    #  "index": {
    #     "arch": "aarch64",
    #     "build": "1_gnu",
    #     "build_number": 14,
    #     "constrains": [
    #     "openmp_impl 9999"
    #     ],
    #     "depends": [
    #     "libgomp >=7.5.0"
    #     ],
    #     "license": "BSD-3-Clause",
    #     "name": "_openmp_mutex",
    #     "platform": "linux",
    #     "subdir": "linux-aarch64",
    #     "timestamp": 1596413239930,
    #     "version": "4.5"
    #     },

    _up_to_add = []
    if len(files) > 0:
        platform = yaml_json["index"]["platform"]
        if not platform:
            # consider noarch
            for path in files:
                artifact_file_path = ArtifactsFilePathsNoArch(
                    artifact=artifact.name,
                    parent_dir=Path(path).parts[0],
                    path=str(path),
                )
                _up_to_add.append(artifact_file_path)
        elif "linux" in platform:
            for path in files:
                artifact_file_path = ArtifactsFilePathsLinux(
                    artifact=artifact.name,
                    parent_dir=Path(path).parts[0],
                    path=str(path),
                )
                _up_to_add.append(artifact_file_path)
        elif "win" in platform:
            for path in files:
                artifact_file_path = ArtifactsFilePathsWin(
                    artifact=artifact.name,
                    parent_dir=Path(path).parts[0],
                    path=str(path),
                )
                _up_to_add.append(artifact_file_path)
        elif "osx" in platform:
            for path in files:
                artifact_file_path = ArtifactsFilePathsMac(
                    artifact=artifact.name,
                    parent_dir=Path(path).parts[0],
                    path=str(path),
                )
                _up_to_add.append(artifact_file_path)

        session.add_all(_up_to_add)

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
        Artifacts.name, Artifacts.package_name, Artifacts.platform
    ).all()

    logger.info(f"Traversing files in {path}...")
    stored_files = traverse_files(path, tmp_dir)

    logger.info("Comparing files...")
    changed_files = _compare_files(artifacts, stored_files, root_dir=path)

    if len(changed_files) == 0:
        logger.info("No changes detected. Exiting...")
        return

    with progressBar:
        for idx, (file, file_hash) in enumerate(
            progressBar.track(changed_files, description="Updating feedstocks...")
        ):
            # print(retrieve_associated_feedstock_from_output_blob(file))
            print(f"File: {file}")
            package_name, channel, arch, artifact_name = str(file).split("/")
            logger.info(
                f"Updating {package_name} :: {channel} :: {arch} :: {artifact_name}"
            )

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

            # Create a new artifact record -- artifacts will always be created, never updated
            new_artifact = Artifacts(
                name=file.stem,
                package_name=package_name,
                platform=arch,
            )

            # Add the new artifact to the session
            session.add(new_artifact)

            session = _link_files_to_artifacts(
                artifact=new_artifact, file_path=file, session=session, root_dir=path
            )

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
