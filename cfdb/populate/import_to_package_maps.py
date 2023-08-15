from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List, Set, Tuple
from logging import getLogger
from sqlalchemy.orm import Session

from cfdb.log import progressBar
from cfdb.models.schema import ImportToPackageMaps, Packages, uniq_id
from cfdb.populate.utils import traverse_files, retrieve_import_maps_from_output_blob

logger = getLogger(__name__)


def _decompose_filename(filename_handle: str):
    try:
        package_name, partition = filename_handle.split(".")
    except ValueError as e:
        # We assume that typeerror will only happen when filename
        # is likely name.. (with the extra dot)
        package_name = filename_handle
        partition = ""
    return package_name, partition


def _compare_files(
    feedstock_outputs: List[Tuple[str, str, int]],
    stored_files: List[Path],
    root_dir: Path,
) -> Set[Path]:
    # (package_name.partition, hash)
    db_files = {(Path(f"{row[0]}.{row[1]}.json"), row[2]) for row in feedstock_outputs}
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


def update(session: Session, path: Path):
    """
    Updates Import to Package maps in the database  based on the comparison between the stored data and the current data.

    Args:
        session (Session): The SQLAlchemy session object.
        path (Path): The path to import to package maps directory containing the JSON blobs
        (relative to the root directory of "libcfgraph" or viable alternative).
    """
    logger.info("Updating feedstocks...")
    logger.debug("Creating temporary directory...")
    _tmp_dir = TemporaryDirectory()
    tmp_dir = Path(_tmp_dir.name)

    logger.info("Querying database for current mappings...")
    _database_mappings = session.query(
        ImportToPackageMaps.parent_package_name,
        ImportToPackageMaps.partition,
        ImportToPackageMaps.hash,
    ).all()

    logger.info(f"Traversing files in {path}...")
    stored_files = traverse_files(path, tmp_dir)

    logger.info("Comparing files...")
    changed_files = _compare_files(_database_mappings, stored_files, root_dir=path)

    with progressBar:
        for idx, (file, file_hash) in enumerate(
            progressBar.track(changed_files, description="Updating import maps")
        ):
            _, partition = _decompose_filename(file.stem)

            import_map_data_blob = retrieve_import_maps_from_output_blob(
                file=path / file  # absolute path
            )
            # now we will have a dictionary containing the package names and their respective imports

            for package_name, imports in import_map_data_blob.items():
                package = (
                    session.query(Packages)
                    .filter(Packages.name == package_name)
                    .first()
                )

                if not package:
                    logger.debug(
                        f"Package '{package_name}' not found in database. Proceeding to create it and its feedstock outputs."
                    )
                    package = Packages(
                        name=package_name,
                    )
                    session.add(package)

                for _import in imports:
                    _mapping = ImportToPackageMaps(
                        id=uniq_id(),
                        import_name=_import,
                        parent_package_name=package.name,
                        partition=partition,
                        hash=file_hash,
                    )
                    session.add(_mapping)

            if idx % 100 == 0:
                session.commit()

        session.commit()
