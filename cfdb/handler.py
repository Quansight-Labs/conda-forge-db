from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cfdb.models.schema import Base
from cfdb.populate import artifacts, feedstock_outputs, import_to_package_maps


class CFDBHandler:
    """
    CFDBHandler class handles the database operations for CFDB.

    Args:
        db_url (str): The URL of the database.

    Attributes:
        db_url (str): The URL of the database.
        engine (Engine): SQLAlchemy Engine object.
        Session (sessionmaker): SQLAlchemy sessionmaker object.

    Methods:
        update_feedstock_outputs: Update the feedstock outputs in the database.
        update_artifacts: Update the artifacts in the database.
    """

    def __init__(self, db_url):
        self.db_url = db_url
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def update_feedstock_outputs(self, path):
        """
        Update the feedstock outputs in the database.

        Args:
            path (str): Path to the feedstock outputs directory.
        """
        session = self.Session()
        feedstock_outputs.update(session, path=Path(path))
        session.commit()

    def update_artifacts(self, path):
        """
        Update the artifacts in the database.
        """
        session = self.Session()
        artifacts.update(session, path=Path(path))
        session.commit()

    def update_import_to_package_maps(self, path):
        """
        Update the import to package maps in the database.

        Args:
            path (str): Path to the import to package maps directory.
        """
        session = self.Session()
        import_to_package_maps.update(session, path=Path(path))
        session.commit()
