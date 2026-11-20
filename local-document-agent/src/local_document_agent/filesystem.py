"""Bounded local filesystem operations; no shell, network, or editable originals."""

import ctypes
import hashlib
import os
import re
import stat
import time
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import BinaryIO, Callable

from .contracts import DocumentError, ErrorCode, SearchIssue

RAW_LIMIT = 256 * 1024
OUTPUT_LIMIT = 64 * 1024
SUPPORTED = {".txt", ".md", ".eml"}
RESERVED = re.compile(r"^(CON|CONIN\$|CONOUT\$|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])$", re.IGNORECASE)


def map_os_error(error: OSError, *, writing: bool = False) -> DocumentError:
    if isinstance(error, FileExistsError):
        return DocumentError("FILE_EXISTS", "The output file already exists; nothing was overwritten.")
    if isinstance(error, FileNotFoundError):
        return DocumentError("NOT_FOUND", "The requested local path does not exist.")
    if isinstance(error, PermissionError):
        return DocumentError("PERMISSION_DENIED", "Access to the local path was denied.")
    return DocumentError(
        "WRITE_FAILED" if writing else "IO_ERROR",
        "A local write failed; a partial output file may remain." if writing else "A local file operation failed.",
    )


def validate_relative(value: str) -> list[str]:
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        raise DocumentError("INVALID_PATH", "The path must contain valid Unicode text.") from None
    windows = PureWindowsPath(value)
    if (
        not value or len(value) > 240 or windows.drive or windows.root
        or "\\" in value or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise DocumentError("INVALID_PATH", "Use a bounded input-relative path with / separators.")
    components = value.split("/")
    for part in components:
        if (
            not part or part in (".", "..") or part.endswith((".", " "))
            or any(char in part for char in ':*?"<>|')
            or RESERVED.fullmatch(part.split(".")[0].rstrip(" ."))
        ):
            raise DocumentError("INVALID_PATH", "The path contains a prohibited component.")
    return components


def validate_output_name(value: str) -> None:
    validate_relative(value)
    if (
        len(value) > 80
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.(txt|md)", value) is None
    ):
        raise DocumentError("INVALID_PATH", "Use a flat ASCII .txt or .md output basename.")


def reject_reparse(path: Path) -> os.stat_result:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise DocumentError("REPARSE_POINT", "Symlinks, junctions, and other reparse points are not allowed.")
    return info


def check_components(path: Path) -> None:
    for component in reversed((path, *path.parents)):
        reject_reparse(component)


def contained(path: Path, root: Path) -> bool:
    return path.is_relative_to(root)


def windows_final_path(stream: BinaryIO) -> Path:
    """Resolve an opened handle using the documented Win32 final-path API."""
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    function = kernel.GetFinalPathNameByHandleW
    function.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    function.restype = wintypes.DWORD
    handle = wintypes.HANDLE(msvcrt.get_osfhandle(stream.fileno()))
    buffer = ctypes.create_unicode_buffer(32768)
    length = function(handle, buffer, len(buffer), 0)
    if length == 0 or length >= len(buffer):
        raise DocumentError("IO_ERROR", "Could not verify the opened file location.")
    value = buffer.value
    if value.startswith("\\\\?\\UNC\\"):
        raise DocumentError("OUTSIDE_ROOT", "Remote opened-file locations are not allowed.")
    if value.startswith("\\\\?\\"):
        value = value[4:]
    return Path(value).resolve(strict=True)


def verify_handle(stream: BinaryIO, root: Path, expected: Path) -> None:
    info = os.fstat(stream.fileno())
    if not stat.S_ISREG(info.st_mode):
        raise DocumentError("NOT_REGULAR_FILE", "Only regular files are supported.")
    if info.st_nlink > 1:
        raise DocumentError("INVALID_PATH", "Hard-linked files are not supported.")
    actual = windows_final_path(stream) if os.name == "nt" else expected.resolve(strict=True)
    if not contained(actual, root) or actual != expected:
        raise DocumentError("OUTSIDE_ROOT", "The opened file is outside the configured location.")


def validate_root(value: Path) -> Path:
    # abspath normalizes relative configuration, but inspect the original chain first.
    raw = str(value)
    windows = PureWindowsPath(raw)
    if (
        raw.startswith(("\\\\", "//")) or (windows.drive and not windows.root)
        or ".." in value.parts
    ):
        raise DocumentError("INVALID_PATH", "Roots must be absolute local directories, not network/device paths.")
    absolute = Path(os.path.abspath(value))
    check_components(absolute)
    resolved = absolute.resolve(strict=True)
    if not resolved.is_dir():
        raise DocumentError("NOT_REGULAR_FILE", "Each root must be an existing directory.")
    if os.name == "nt":
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
        kernel.GetDriveTypeW.restype = wintypes.UINT
        # Unknown/no-root/network/CD-ROM drives are not accepted.
        if kernel.GetDriveTypeW(resolved.anchor) not in (2, 3, 6):
            raise DocumentError("INVALID_PATH", "Roots must reside on an available local drive.")
    return resolved


@dataclass(frozen=True)
class Inventory:
    files: tuple[str, ...]
    issues: tuple[SearchIssue, ...]


@dataclass(frozen=True, init=False)
class FilesystemRoots:
    input: Path
    output: Path

    def __init__(self, input_dir: Path, output_dir: Path) -> None:
        try:
            source = validate_root(input_dir)
            destination = validate_root(output_dir)
            if contained(source, destination) or contained(destination, source):
                raise DocumentError("OUTSIDE_ROOT", "Input and output roots must be separate, non-overlapping directories.")
            # Advisory only: Windows ACLs can still reject an actual operation.
            if not os.access(source, os.R_OK) or not os.access(destination, os.W_OK):
                raise DocumentError("PERMISSION_DENIED", "Required root access is unavailable.")
            with os.scandir(source) as entries:
                next(entries, None)
            object.__setattr__(self, "input", source)
            object.__setattr__(self, "output", destination)
        except OSError as error:
            raise map_os_error(error) from None

    def input_path(self, relative: str) -> Path:
        parts = validate_relative(relative)
        try:
            check_components(self.input)
            candidate = self.input.joinpath(*parts)
            check_components(candidate)
            resolved = candidate.resolve(strict=True)
            if not contained(resolved, self.input):
                raise DocumentError("OUTSIDE_ROOT", "The input path is outside the configured root.")
            info = reject_reparse(resolved)
            if not stat.S_ISREG(info.st_mode):
                raise DocumentError("NOT_REGULAR_FILE", "Only regular input files are supported.")
            if info.st_nlink > 1:
                raise DocumentError("INVALID_PATH", "Hard-linked input files are not supported.")
            if resolved.suffix.casefold() not in SUPPORTED:
                raise DocumentError("UNSUPPORTED_TYPE", "Only .txt, .md, and .eml input files are supported.")
            return resolved
        except OSError as error:
            raise map_os_error(error) from None

    def read_bytes(
        self, relative: str, check: Callable[[], None], *, byte_budget: int | None = None
    ) -> bytes:
        try:
            check()
            candidate = self.input_path(relative)
            if candidate.stat().st_size > RAW_LIMIT:
                raise DocumentError("FILE_TOO_LARGE", "The raw file exceeds 256 KiB.")
            # Revalidate immediately before open, then validate the actual handle.
            candidate = self.input_path(relative)
            with candidate.open("rb") as stream:
                verify_handle(stream, self.input, candidate)
                check()
                size = os.fstat(stream.fileno()).st_size
                if size > RAW_LIMIT:
                    raise DocumentError("FILE_TOO_LARGE", "The raw file exceeds 256 KiB.")
                if byte_budget is not None and size > byte_budget:
                    raise DocumentError("SEARCH_LIMIT", "The remaining aggregate search byte budget is insufficient.")
                cap = RAW_LIMIT + 1 if byte_budget is None else min(RAW_LIMIT + 1, byte_budget)
                data = stream.read(cap)
                if os.fstat(stream.fileno()).st_size > len(data):
                    raise DocumentError(
                        "SEARCH_LIMIT" if byte_budget is not None else "FILE_TOO_LARGE",
                        "The file changed beyond the permitted bounded read.",
                    )
            if len(data) > RAW_LIMIT:
                raise DocumentError("FILE_TOO_LARGE", "The raw file exceeds 256 KiB.")
            check()
            return data
        except OSError as error:
            raise map_os_error(error) from None

    def inventory(self, check: Callable[[], None]) -> Inventory:
        files: list[str] = []
        issues: list[SearchIssue] = []
        count = 0

        def issue(relative: str, code: ErrorCode) -> None:
            # Never send an unbounded or control-bearing filename to the model.
            safe = ascii(relative)[1:-1][:240]
            issues.append(SearchIssue(path=safe, code=code))

        def visit(directory: Path, depth: int) -> None:
            nonlocal count
            check()
            check_components(directory)
            # Bound enumeration before sorting, including unsupported entries.
            entries: list[Path] = []
            with os.scandir(directory) as iterator:
                for entry in iterator:
                    check()
                    count += 1
                    if count > 1000:
                        raise DocumentError("SEARCH_LIMIT", "The search inventory exceeds 1000 entries.")
                    entries.append(Path(entry.path))
            entries.sort(key=lambda p: (p.name.casefold(), p.name))
            for path in entries:
                check()
                relative = path.relative_to(self.input).as_posix()
                try:
                    validate_relative(relative)
                    info = reject_reparse(path)
                    if stat.S_ISDIR(info.st_mode):
                        if depth >= 8:
                            raise DocumentError("SEARCH_LIMIT", "The search exceeds eight directory levels.")
                        visit(path, depth + 1)
                    elif stat.S_ISREG(info.st_mode) and path.suffix.casefold() in SUPPORTED:
                        self.input_path(relative)
                        files.append(relative)
                    elif not stat.S_ISREG(info.st_mode):
                        issue(relative, "NOT_REGULAR_FILE")
                except DocumentError as error:
                    if error.error.code in ("SEARCH_LIMIT", "SEARCH_TIMEOUT", "LIMIT_EXCEEDED"):
                        raise
                    issue(relative, error.error.code)
                except OSError as error:
                    issue(relative, map_os_error(error).error.code)

        try:
            visit(self.input, 0)
        except OSError as error:
            raise map_os_error(error) from None
        return Inventory(
            files=tuple(sorted(files, key=lambda p: (p.casefold(), p))),
            issues=tuple(sorted(issues, key=lambda i: (i.path.casefold(), i.path, i.code))),
        )

    def create_bytes(self, filename: str, data: bytes, check: Callable[[], None]) -> tuple[int, str]:
        validate_output_name(filename)
        if len(data) > OUTPUT_LIMIT:
            raise DocumentError("FILE_TOO_LARGE", "The framed output exceeds 64 KiB.")
        candidate = self.output / filename
        created = False
        try:
            check()
            check_components(self.output)
            if self.output.resolve(strict=True) != self.output:
                raise DocumentError("OUTSIDE_ROOT", "The output root has changed.")
            if os.path.lexists(candidate):
                reject_reparse(candidate)
                raise DocumentError("FILE_EXISTS", "The output file already exists; nothing was overwritten.")
            check()
            # xb is O_EXCL; preflight existence is not the overwrite protection.
            stream = candidate.open("xb")
            created = True
            with stream:
                verify_handle(stream, self.output, candidate)
                check()
                count = stream.write(data)
                if count != len(data):
                    raise OSError("Short write")
                stream.flush()
                os.fsync(stream.fileno())
            # Success requires successful close and post-write location validation.
            check_components(candidate)
            if candidate.resolve(strict=True) != candidate or candidate.stat().st_size != len(data):
                raise DocumentError("WRITE_FAILED", "Output verification failed; a partial file may remain.")
            return count, hashlib.sha256(data).hexdigest()
        except (OSError, DocumentError) as error:
            safe = error if isinstance(error, DocumentError) else map_os_error(error, writing=True)
            if created:
                raise DocumentError(
                    safe.error.code,
                    f"{safe.error.message} Possible partial output: output/{filename}.",
                    possible_output=filename,
                ) from None
            raise safe from None


def search_deadline(context_check: Callable[[], None]) -> Callable[[], None]:
    deadline = time.monotonic() + 5

    def check() -> None:
        context_check()
        if time.monotonic() >= deadline:
            raise DocumentError("SEARCH_TIMEOUT", "The five-second search deadline expired.")

    return check
