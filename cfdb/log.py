import logging
import os
from datetime import datetime
from pathlib import Path

from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)


def initialize_logging(logging_dir: Path = None):
    # use package name to affect all descendants
    logger = logging.getLogger('cfdb')  
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        # The logger already has handlers attached to it
        return
        
    # Create a rich handler
    rich_handler = RichHandler()
    rich_handler.setLevel(logging.INFO)

    # Create a formatter
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
    )

    # Add the handlers to the logger
    logger.addHandler(rich_handler)

    # Create a file handler in non-interactive sessions
    # Set the formatter for the file handler
    if logging_dir is None:
        logging_dir = os.environ.get('CFDB_LOGGING_DIR', Path.cwd() / '.logs')
    logging_dir.mkdir(parents=True, exist_ok=True)
    filename = f'{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.log'
    file_handler = logging.FileHandler(filename=logging_dir / filename)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

#: progress bar columns for rich progress bar
progressBar = Progress(
    TextColumn("[progress.description]{task.description}"),
    BarColumn(
        bar_width=None,
        pulse_style="bright_black",
    ),
    TaskProgressColumn(),
    TimeRemainingColumn(),
    MofNCompleteColumn(),
    expand=True,
)
