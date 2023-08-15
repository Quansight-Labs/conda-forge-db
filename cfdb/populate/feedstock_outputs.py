from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List, Set, Tuple
from logging import getLogger

from sqlalchemy.orm import Session

from cfdb.log import progressBar
from cfdb.models.schema import FeedstockOutputs, Feedstocks, Packages, uniq_id
from cfdb.populate.utils import (
    retrieve_associated_feedstock_from_output_blob,
    traverse_files,
)

logger = getLogger(__name__)


def _compare_files(
    feedstock_outputs: List[Tuple[str, str, int]],
    stored_files: List[Path],
    root_dir: Path,
) -> Set[Path]:
    """
    Compares the feedstock outputs from the database with the stored files, and returns a set of files that were not present in the database or have changed hashes.

    Args:
        feedstock_outputs (List[Tuple[str, str, int]]): List of tuples containing the path, hash, and id of feedstock outputs from the database.
        stored_files (List[Path]): List of paths to the stored files.
        root_dir (Path): The root directory of the stored files.

    Returns:
        Set[Path]: A set of file paths (relative to root_dir) that were not present in the database or have changed hashes.
    """
    db_files = {(Path(row[0]), row[1]) for row in feedstock_outputs}
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
    file_rel_path: Path,
    file_hash: str,
    package_name: str,
    feedstock_name: str,
) -> Session:
    """
    Update or create the feedstock outputs in the database for a given feedstock.

    Args:
        session (Session): The SQLAlchemy session object.
        file_rel_paht (Path): The path to the feedstock output file (relative to the root directory of the feedstock outputs).
        file_hash (str): The SHA-1 hash of the file.
        package_name (str): The name of the associated package.
        feedstock_name (str): The name of the feedstock.

    Returns:
        Session: The updated SQLAlchemy session object.
    """
    feedstock = (
        session.query(Feedstocks)
        .filter(
            Feedstocks.name == feedstock_name,
        )
        .first()
    )

    if not feedstock:
        logger.debug(
            f"Feedstock [bold blue]{feedstock_name}[/] not found in database. Proceeding to create it and its feedstock output."
        )
        feedstock = Feedstocks(
            name=feedstock_name,
        )
        session.add(feedstock)

    feedstock_output = (
        session.query(FeedstockOutputs)
        .filter(
            FeedstockOutputs.feedstock_name == feedstock.name,
            FeedstockOutputs.package_name == package_name,
        )
        .first()
    )

    if feedstock_output:
        logger.debug(
            f"Feedstock [bold blue]{feedstock_name}[/] found in database. Proceeding to update its feedstock output."
        )
        feedstock_output.hash = file_hash
        session.add(feedstock_output)
        return session

    new_feedstock_output = FeedstockOutputs(
        id=uniq_id(),
        path=file_rel_path.as_posix(),
        feedstock_name=feedstock.name,
        package_name=package_name,
        hash=file_hash,
    )
    session.add(new_feedstock_output)
    return session


def update(session: Session, path: Path):
    """
    Updates feedstock outputs in the database based on the comparison between the stored data and the current data.

    Args:
        session (Session): The database session.
        path (Path): The path to the directory containing the JSON files.
    """
    logger.info("Updating feedstocks...")
    logger.debug("Creating temporary directory...")
    _tmp_dir = TemporaryDirectory()
    tmp_dir = Path(_tmp_dir.name)

    logger.info("Querying database for feedstock outputs...")
    feedstock_outputs = session.query(
        FeedstockOutputs.path, FeedstockOutputs.hash, FeedstockOutputs.id
    ).all()

    logger.info(f"Traversing files in {path}...")
    stored_files = traverse_files(path, tmp_dir)

    logger.info("Comparing files...")
    changed_files = _compare_files(feedstock_outputs, stored_files, root_dir=path)

    if len(changed_files) == 0:
        logger.info("No changes detected. Exiting...")
        return

    with progressBar:
        for idx, (file, file_hash) in enumerate(
            progressBar.track(changed_files, description="Updating feedstocks...")
        ):
            associated_package_name = file.stem
            associated_feedstocks = retrieve_associated_feedstock_from_output_blob(
                file=path / file  # Need to use the absolute path here
            )
            logger.debug(
                f"Associated package name: '{associated_package_name}' :: Associated feedstocks: '{associated_feedstocks}'"
            )
            package = (
                session.query(Packages)
                .filter(Packages.name == associated_package_name)
                .first()
            )

            if not package:
                logger.debug(
                    f"Package '{associated_package_name}' not found in database. Proceeding to create it and its feedstock outputs."
                )
                package = Packages(
                    name=associated_package_name,
                )
                session.add(package)

            for feedstock_name in associated_feedstocks:
                session = _update_feedstock_outputs(
                    session=session,
                    file_rel_path=file,
                    file_hash=file_hash,
                    package_name=package.name,
                    feedstock_name=feedstock_name,
                )

            if idx % 100 == 0:
                session.commit()

        session.commit()
