"""
example script on how to query the database for information
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.engine.url import URL
from sqlalchemy.orm import sessionmaker

from cfdb.models.schema import (
    ArtifactsFilePaths,
    RelationsMapFilePaths,
)

db_url = URL.create(
    drivername=os.environ.get("CFDB_DB_DRIVER", "sqlite"),
    username=os.environ.get("CFDB_DB_USER"),
    password=os.environ.get("CFDB_DB_PASSWORD"),
    host=os.environ.get("CFDB_DB_HOST"),
    port=os.environ.get("CFDB_DB_PORT"),
    database=os.environ.get("CFDB_DB_PATH", "cf-database.db"),
).render_as_string()
engine = create_engine(db_url)
Session = sessionmaker(bind=engine)


def search_file_in_artifacts(file_name):
    session = Session()
    file_row = (
        session.query(ArtifactsFilePaths)
        .filter(ArtifactsFilePaths.path == file_name)
        .first()
    )
    if file_row is None:
        return None

    artifacts = [
        row.artifact_name
        for row in session.query(RelationsMapFilePaths)
        .filter(file_row.id == RelationsMapFilePaths.file_path_id)
        .all()
    ]
    return artifacts
