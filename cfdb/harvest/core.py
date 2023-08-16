import json
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from time import localtime, strftime
from logging import getLogger

import requests

from cfdb.harvest.harvester import harvest, harvest_dot_conda
from cfdb.harvest.local import fetch_db, fetch_jsonblobs
from cfdb.harvest.upstream import fetch as upstream_fetch
from cfdb.harvest.utils import expand_file_and_mkdirs
from cfdb.log import progressBar

logger = getLogger(__name__)

def diff(path):
    missing_files = set()
    upstream = upstream_fetch()

    if not isinstance(path, Path):
        path = Path(path)
        if path.is_dir():
            # assume we've been given the root of the jsonblob directory
            local = fetch_jsonblobs(path)
        elif path.is_file() and path.suffix == ".db":
            local = fetch_db(f"sqlite:///{path}")
        else:
            raise ValueError(f"Unknown path type: {path}")

    missing_packages = set(upstream.keys()) - set(local.keys())
    present_packages = set(upstream.keys()) & set(local.keys())

    for package in missing_packages:
        missing_files.update((package, k, v) for k, v in upstream[package].items())

    for package in present_packages:
        upstream_artifacts = upstream[package]
        present_artifacts = local[package]

        missing_artifacts = set(upstream_artifacts) - set(present_artifacts)
        missing_files.update(
            (package, k, v)
            for k, v in upstream_artifacts.items()
            if k in missing_artifacts
        )

    return missing_files


class ReapFailure(Exception):
    def __init__(self, package, src_url, msg):
        super().__init__(f"Failed to reap package '{package}' from '{src_url}': {msg}")
        self.package = package
        self.src_url = src_url
        self.msg = msg

    def write_to_file(self):
        with open("reap_failures.txt", "a") as f:
            f.write(f"{self.package}\t{self.src_url}\t{self.msg}\n")


def fetch_url(src_url):
    try:
        response = requests.get(src_url, timeout=60 * 2)
        response.raise_for_status()
        return response.content
    except Exception as e:
        fail = ReapFailure("Unknown", src_url, str(e))
        fail.write_to_file()
        raise fail


def reap_package(package_data):
    package, dst_path, src_url = package_data
    try:
        file_content = fetch_url(src_url)

        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_pth = os.path.join(tmpdir, os.path.basename(src_url))
            with open(pkg_pth, "wb") as file:
                file.write(file_content)

            with open(pkg_pth, "rb") as filelike:
                if pkg_pth.endswith(".tar.bz2"):
                    harvested_data = harvest(filelike)
                elif pkg_pth.endswith(".conda"):
                    harvested_data = harvest_dot_conda(filelike, pkg_pth)
                else:
                    raise RuntimeError(
                        f"File '{pkg_pth}' is not a recognized conda format!"
                    )
        # Obtain the root path from the environment variable CFDB_ARTIFACTS_PATH,
        # to be used to store the harvested data
        root_path = os.environ.get("CFDB_ARTIFACTS_PATH", dst_path.split(os.sep)[0])

        dir_path = Path(root_path) / "artifacts" / package
        os.makedirs(dir_path, exist_ok=True)

        with open(expand_file_and_mkdirs((dir_path / dst_path).as_posix()), "w") as fo:
            json.dump(harvested_data, fo, indent=1, sort_keys=True)

        channel, arch, name = dst_path.split(os.sep)
        name = os.path.splitext(name)[0]
        harvested_data.update(
            {
                "path": os.path.join(package, dst_path),
                "pkg": package,
                "channel": channel,
                "arch": arch,
                "name": name,
            }
        )
        return harvested_data
    except Exception as e:
        raise ReapFailure(package, src_url, str(e))


def reap(comparing_source_path, known_bad_packages=(), max_workers=20):
    sorted_files = list(diff(comparing_source_path))
    total_outstanding_artifacts = len(sorted_files)
    logger.info(f"Found {total_outstanding_artifacts} artifacts to reap")

    # Restricting the number of artifacts seems only reasonable on a daily basis;
    # in case of a complete migration, we would want to reap all artifacts
    sorted_files = sorted_files[:1000]

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = []
        for package_data in sorted_files:
            if package_data[2] in known_bad_packages:
                continue
            futures.append(pool.submit(reap_package, package_data))

        n_total = len(futures)
        start = time.time()
        logger.info(
            f"Reaping {n_total} artifacts, starting at {strftime('%Y-%m-%d %H:%M:%S', localtime(start))}"
        )

        with progressBar:
            for _, f in enumerate(
                progressBar.track(
                    sequence=as_completed(futures, timeout=None),
                    description="Reaping artifacts...",
                    total=n_total,
                ),
                1,
            ):
                try:
                    f.result()
                except Exception as e:
                    logger.exception(e)


if __name__ == "__main__":
    print("Testing reap")
    reap("/home/vcerutti/Quansight/Projects/CZI/czi-conda-forge-db/cf-database.db")
