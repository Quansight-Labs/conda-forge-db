from collections import defaultdict
from typing import Dict, Set

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from cfdb.models.schema import Artifacts

from .utils import recursive_ls


def query_existing_artifacts(db_path):
    with Session(create_engine(db_path)) as session:
        artifacts = session.query(Artifacts.name, Artifacts.package_name).all()

    return artifacts


def _sort_existing_artifacts_by_package_name(artifacts):
    artifacts_by_package_name = defaultdict(list)
    for artifact in artifacts:
        artifacts_by_package_name[artifact.package_name].append(artifact.name)

    return artifacts_by_package_name


def fetch_db(db_path):
    artifacts = query_existing_artifacts(db_path)
    artifacts_by_package_name = _sort_existing_artifacts_by_package_name(artifacts)
    return artifacts_by_package_name


def fetch_jsonblobs(path) -> Dict[str, Set[str]]:
    existing_dict = defaultdict(set)
    for pak, path in recursive_ls(path):
        existing_dict[pak].add(path)
    return existing_dict
