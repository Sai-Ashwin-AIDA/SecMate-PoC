import os
import subprocess
from pathlib import Path

import pytest

from local_document_agent.contracts import DocumentError
from local_document_agent.filesystem import FilesystemRoots, RAW_LIMIT, verify_handle


@pytest.mark.parametrize("path", [
    "../outside.txt", "/outside.txt", "C:/outside.txt", "C:outside.txt",
    "//server/share/a.txt", r"\\?\C:\outside.txt", "a.txt:secret",
    r"sub\a.txt", "./a.txt", "sub//a.txt", "CON.txt", "LPT1.md", "bad./a.txt",
    "a.txt ", "bad\nname.txt",
])
def test_bad_paths_never_read(roots, path):
    with pytest.raises(DocumentError) as error:
        roots.read_bytes(path, lambda: None)
    assert error.value.error.code == "INVALID_PATH"


def test_overlapping_missing_and_file_roots(tmp_path, roots):
    nested = roots.input / "nested"
    nested.mkdir()
    for source, destination in (
        (roots.input, roots.input), (roots.input, nested), (nested, roots.input)
    ):
        with pytest.raises(DocumentError, match="non-overlapping"):
            FilesystemRoots(source, destination)
    with pytest.raises(DocumentError) as error:
        FilesystemRoots(tmp_path / "missing", roots.output)
    assert error.value.error.code == "NOT_FOUND"
    file = tmp_path / "file.txt"
    file.write_text("ordinary")
    with pytest.raises(DocumentError):
        FilesystemRoots(file, roots.output)
    for remote in (Path("//server/share/input"), Path(r"\\?\C:\input")):
        with pytest.raises(DocumentError):
            FilesystemRoots(remote, roots.output)


def test_actual_handle_boundary_hardlinks_and_bounded_read(roots, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"outside")
    with outside.open("rb") as stream:
        with pytest.raises(DocumentError, match="outside"):
            verify_handle(stream, roots.input, outside)
    linked = roots.input / "linked.txt"
    os.link(outside, linked)
    with pytest.raises(DocumentError, match="Hard-linked"):
        roots.read_bytes("linked.txt", lambda: None)
    oversized = roots.input / "large.txt"
    oversized.write_bytes(b"x" * (RAW_LIMIT + 1))
    with pytest.raises(DocumentError) as error:
        roots.read_bytes("large.txt", lambda: None)
    assert error.value.error.code == "FILE_TOO_LARGE"


def test_junction_escape_and_root_rejected(roots, tmp_path):
    if os.name != "nt":
        pytest.skip("Windows junction test requires Windows.")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "hidden.txt").write_text("must not read")
    junction = roots.input / "junction"
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        capture_output=True, text=True, timeout=10,
    )
    if completed.returncode:
        pytest.skip("Host cannot create a Windows junction fixture.")
    try:
        with pytest.raises(DocumentError) as error:
            roots.read_bytes("junction/hidden.txt", lambda: None)
        assert error.value.error.code == "REPARSE_POINT"
        inventory = roots.inventory(lambda: None)
        assert not inventory.files
        assert inventory.issues[0].code == "REPARSE_POINT"
        with pytest.raises(DocumentError):
            FilesystemRoots(junction, roots.output)
    finally:
        junction.rmdir()  # Remove this link only, never its destination.


def test_symlink_rejected(roots, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("must not read")
    link = roots.input / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Host lacks symlink creation privileges/developer mode.")
    try:
        with pytest.raises(DocumentError) as error:
            roots.read_bytes("link.txt", lambda: None)
        assert error.value.error.code == "REPARSE_POINT"
    finally:
        link.unlink()


def test_exclusive_write_and_partial_failure_are_not_success(roots, monkeypatch):
    path = roots.output / "existing.md"
    path.write_bytes(b"preserve me")
    with pytest.raises(DocumentError) as error:
        roots.create_bytes("existing.md", b"overwrite", lambda: None)
    assert error.value.error.code == "FILE_EXISTS"
    assert path.read_bytes() == b"preserve me"

    def broken_fsync(fd):
        raise OSError("sensitive OS error")

    monkeypatch.setattr(os, "fsync", broken_fsync)
    with pytest.raises(DocumentError) as error:
        roots.create_bytes("partial.md", b"harmless", lambda: None)
    assert error.value.error.code == "WRITE_FAILED"
    assert "partial" in str(error.value)
    assert "sensitive" not in str(error.value)


def test_inventory_depth_and_count_limits(roots):
    path = roots.input
    for _ in range(9):
        path = path / "nested"
        path.mkdir()
    with pytest.raises(DocumentError) as error:
        roots.inventory(lambda: None)
    assert error.value.error.code == "SEARCH_LIMIT"


def test_inventory_count_limit_includes_unsupported_files(roots):
    for index in range(1001):
        (roots.input / f"{index}.bin").touch()
    with pytest.raises(DocumentError) as error:
        roots.inventory(lambda: None)
    assert error.value.error.code == "SEARCH_LIMIT"


def test_exclusive_open_preserves_a_racing_creator(roots, monkeypatch):
    original_open = Path.open
    target = roots.output / "race.md"

    def racing_open(path, mode="r", *args, **kwargs):
        if path == target and mode == "xb":
            with original_open(path, "wb") as stream:
                stream.write(b"other creator wins")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", racing_open)
    with pytest.raises(DocumentError) as error:
        roots.create_bytes("race.md", b"must not overwrite", lambda: None)
    assert error.value.error.code == "FILE_EXISTS"
    assert target.read_bytes() == b"other creator wins"
