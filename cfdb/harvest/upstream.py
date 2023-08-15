import bz2
import io
import json
from collections import defaultdict
from logging import getLogger
from typing import Dict

import requests
import requests_cache

logger = getLogger(__name__)

channel_list = [
    "https://conda.anaconda.org/conda-forge/linux-64",
    "https://conda.anaconda.org/conda-forge/osx-64",
    "https://conda.anaconda.org/conda-forge/win-64",
    "https://conda.anaconda.org/conda-forge/noarch",
    "https://conda.anaconda.org/conda-forge/linux-ppc64le",
    "https://conda.anaconda.org/conda-forge/linux-aarch64",
    "https://conda.anaconda.org/conda-forge/osx-arm64",
]


# Enable caching with requests_cache (when debugging)
# Use a local SQLite database to store the cached responses
# You can customize the cache name and expiration time as needed
requests_cache.install_cache(
    cache_name="arch_cache", expire_after=3600
)  # Cache expires after 1 hour (3600 seconds)


def fetch_arch(arch):
    """
    Fetches the repository data for a given channel/arch combination.

    Args:
        arch (str): The architecture for which to fetch the repository data.

    Yields:
        tuple: A tuple containing package name, file name, and package URL.
    """
    # Generate a set of URLs to fetch for a channel/arch combo
    logger.info(f"Fetching {arch}")

    # Fetch the repodata.json.bz2 file
    url = f"{arch}/repodata.json.bz2"
    response = requests.get(url)

    if response.status_code != 200:
        logger.error(f"Failed to fetch {url}. Status code: {response.status_code}")

    repodata = json.load(bz2.BZ2File(io.BytesIO(response.content)))

    # Display the number of .conda and .tar.bz2 artifacts found in the repodata
    conda_artifacts_count = len(repodata.get("packages.conda", []))
    tar_bz2_artifacts_count = len(repodata.get("packages", []))

    logger.info(f"Found {conda_artifacts_count} .conda artifacts")
    logger.info(f"Found {tar_bz2_artifacts_count} .tar.bz2 artifacts")

    for package_type in ["conda", "tar.bz2"]:
        package_key = "packages.conda" if package_type == "conda" else "packages"
        extension = ".conda" if package_type == "conda" else ".tar.bz2"

        for p, v in repodata[package_key].items():
            package_url = f"{arch}/{p}"
            file_name = package_url.replace("https://conda.anaconda.org/", "").replace(
                extension, ".json"
            )
            yield v["name"], file_name, package_url


def fetch() -> Dict[str, Dict[str, str]]:
    package_urls = defaultdict(dict)
    for channel_arch in channel_list:
        for package_name, filename, url in fetch_arch(channel_arch):
            package_urls[package_name][filename] = url
    return package_urls
