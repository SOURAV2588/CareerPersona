"""
Backing store for the persona's background material.

The three background files that feed the system prompt
(:mod:`services.profile`) are read from one of two places:

* a **private Hugging Face Dataset repository**, when the
  :envvar:`RESOURCES_DATASET_REPO` environment variable is set, or
* the local ``resources/`` directory, when it is not.

The local path is the fallback so that development runs and the unit/eval
suites keep working unchanged, with no token and no network. Deployment sets
the env var and the same code reads from the Hub instead.

Files are fetched **once per process** and cached in memory. This is a
deliberate change from the previous read-fresh-on-every-request behaviour:
a network round trip per chat turn would be unacceptable, and the material
does not change between edits. The cost is that editing the dataset requires
a process restart to take effect — see :func:`clear_cache`.

Environment variables
---------------------

:envvar:`RESOURCES_DATASET_REPO`
    Dataset repo id, e.g. ``sourav/career-persona-resources``. Unset means
    "read from the local ``resources/`` directory".
:envvar:`RESOURCES_DATASET_REVISION`
    Git revision to pin to. Defaults to ``main``. Pin to a commit SHA if you
    want eval runs reproducible against a fixed snapshot of the material.
:envvar:`HF_TOKEN`
    Read-scoped Hugging Face token with access to the dataset repo. Required
    only when :envvar:`RESOURCES_DATASET_REPO` is set.
"""

import logging
import os
import threading

logger = logging.getLogger(__name__)

#: Repo id of the private dataset holding the background files, or ``None``
#: to read from the local ``resources/`` directory instead.
DATASET_REPO = os.getenv("RESOURCES_DATASET_REPO")

#: Git revision of the dataset repo to read from.
DATASET_REVISION = os.getenv("RESOURCES_DATASET_REVISION", "main")

#: Directory used when :data:`DATASET_REPO` is unset. Resolved from this
#: file's location rather than the cwd, matching ``services/profile.py``.
LOCAL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "resources",
)

_cache: dict[str, str] = {}
_lock = threading.Lock()


class ResourceUnavailable(RuntimeError):
    """
    Raised when a background file cannot be read from either backend.

    Callers in the chat path do not catch this — ``app.chat()``'s outer
    ``except Exception`` turns it into ``FALLBACK_GENERIC`` and logs the
    traceback, consistent with how resource-file read failures are already
    handled.
    """


def _read_local(filename: str) -> str:
    """
    Read a background file from the local ``resources/`` directory.

    :param filename: Bare filename, e.g. ``SUMMARY.md``.
    :type filename: str
    :return: File contents, decoded as UTF-8.
    :rtype: str
    :raises ResourceUnavailable: If the file is missing or unreadable.
    """
    path = os.path.join(LOCAL_DIR, filename)
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        raise ResourceUnavailable(
            f"Could not read {filename} from {LOCAL_DIR}: {exc}"
        ) from exc


def _read_hub(filename: str) -> str:
    """
    Download a background file from the private dataset repo and read it.

    ``hf_hub_download`` caches to the local Hugging Face cache directory, so
    a repeat call within the same container is served from disk rather than
    re-downloaded. On an ephemeral host the cache is lost on restart, which
    is fine — the fetch happens once per process either way.

    :param filename: Path within the dataset repo, e.g. ``SUMMARY.md``.
    :type filename: str
    :return: File contents, decoded as UTF-8.
    :rtype: str
    :raises ResourceUnavailable: If the download or read fails, for any
        reason (missing file, bad/absent token, network failure).
    """
    from huggingface_hub import hf_hub_download

    token = os.getenv("HF_TOKEN")
    if not token:
        raise ResourceUnavailable(
            "RESOURCES_DATASET_REPO is set but HF_TOKEN is not; "
            "a private dataset cannot be read anonymously."
        )

    try:
        path = hf_hub_download(
            repo_id=DATASET_REPO,
            filename=filename,
            repo_type="dataset",
            revision=DATASET_REVISION,
            token=token,
        )
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except Exception as exc:
        raise ResourceUnavailable(
            f"Could not fetch {filename} from dataset "
            f"{DATASET_REPO}@{DATASET_REVISION}: {exc}"
        ) from exc


def get_resource(filename: str) -> str:
    """
    Return the contents of a background file, fetching it on first use.

    Thread-safe: Gradio serves turns concurrently, and the lock stops two
    simultaneous cold-cache callers both hitting the network. The lock is
    held across the fetch rather than only around the dict write, which
    trades a little contention on the very first turn for exactly one
    download per file.

    :param filename: Bare filename as stored in the dataset repo or the
        local ``resources/`` directory, e.g. ``SUMMARY.md``.
    :type filename: str
    :return: File contents.
    :rtype: str
    :raises ResourceUnavailable: If the file cannot be read.
    """
    cached = _cache.get(filename)
    if cached is not None:
        return cached

    with _lock:
        # Re-check: another thread may have populated it while we waited.
        cached = _cache.get(filename)
        if cached is not None:
            return cached

        if DATASET_REPO:
            logger.info("Fetching %s from dataset %s", filename, DATASET_REPO)
            content = _read_hub(filename)
        else:
            logger.info("Reading %s from %s", filename, LOCAL_DIR)
            content = _read_local(filename)

        _cache[filename] = content
        return content


def warm_cache(filenames: list[str]) -> None:
    """
    Fetch every background file up front, at process start.

    Call this from ``app.py``'s ``__main__`` block so a bad token or a
    missing file surfaces in the startup logs, rather than as a mysterious
    ``FALLBACK_GENERIC`` reply to whoever happens to be the first visitor.

    :param filenames: Files to fetch.
    :type filenames: list[str]
    :raises ResourceUnavailable: On the first file that cannot be read.
    """
    for filename in filenames:
        get_resource(filename)
    logger.info("Warmed %d background file(s)", len(filenames))


def clear_cache() -> None:
    """
    Drop every cached file so the next read re-fetches.

    Intended for tests, and as a manual hook if you ever want to pick up
    edited material without a full restart.

    :return: ``None``
    :rtype: None
    """
    with _lock:
        _cache.clear()