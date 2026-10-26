# SPDX-License-Identifier: AGPL-3.0-or-later
"""Photo storage: request signing by the AWS examples, the S3 calls, and the server's folder."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from squarepot_server.photos.storage import (
    DiskStorage,
    PhotoStorageError,
    S3Storage,
    Signer,
    read_key_file,
)

# The example credentials and moment of the AWS Signature Version 4 documentation for S3.
EXAMPLE = Signer("AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "us-east-1")
MOMENT = datetime(2013, 5, 24, tzinfo=UTC)


def test_a_request_is_signed_as_in_the_aws_example() -> None:
    url = "https://examplebucket.s3.amazonaws.com/test.txt"
    headers = EXAMPLE.headers("GET", url, b"", {"Range": "bytes=0-9"}, MOMENT)
    assert headers["authorization"] == (
        "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request, "
        "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, "
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
    )


def test_an_address_is_presigned_as_in_the_aws_example() -> None:
    url = EXAMPLE.presign("https://examplebucket.s3.amazonaws.com/test.txt", "GET", 86400, MOMENT)
    parts = urlsplit(url)
    assert parts.path == "/test.txt"
    assert {name: values[0] for name, values in parse_qs(parts.query).items()} == {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": "AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request",
        "X-Amz-Date": "20130524T000000Z",
        "X-Amz-Expires": "86400",
        "X-Amz-SignedHeaders": "host",
        "X-Amz-Signature": "aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404",
    }


def answer(status: int) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result._content = b""
    return result


@dataclass
class RecordingSession:
    status: int = 200
    calls: list[tuple[str, str, bytes, dict[str, str]]] = field(default_factory=list)

    def request(
        self, method: str, url: str, data: bytes, headers: dict[str, str], timeout: float
    ) -> requests.Response:
        self.calls.append((method, url, data, headers))
        return answer(self.status)


def bucket(status: int = 200) -> tuple[S3Storage, RecordingSession]:
    session = RecordingSession(status)
    signer = Signer("key-id", "secret", "ru-central1")
    storage = S3Storage(
        cast(requests.Session, session),
        "https://storage.yandexcloud.net/square-pot-photos/",
        signer,
        lambda: MOMENT,
    )
    return storage, session


def test_a_file_is_put_into_the_bucket_by_path() -> None:
    storage, session = bucket()
    storage.put("photos/004217/a b.jpg", b"jpeg", "image/jpeg")
    [(method, url, data, headers)] = session.calls
    assert (method, data) == ("PUT", b"jpeg")
    assert url == "https://storage.yandexcloud.net/square-pot-photos/photos/004217/a%20b.jpg"
    assert headers["content-type"] == "image/jpeg"
    assert "host" not in headers
    assert headers["authorization"].startswith(
        "AWS4-HMAC-SHA256 Credential=key-id/20130524/ru-central1/s3/aws4_request, "
        "SignedHeaders=content-type;host;x-amz-content-sha256;x-amz-date, Signature="
    )


@pytest.mark.parametrize("status", [403, 500])
def test_a_refused_put_is_an_error(status: int) -> None:
    storage, _ = bucket(status)
    with pytest.raises(PhotoStorageError, match=f"answered {status}"):
        storage.put("photos/004217/x.jpg", b"", "image/jpeg")


def test_deleting_a_missing_file_is_no_error() -> None:
    storage, session = bucket(404)
    storage.delete("photos/004217/x.jpg")
    assert session.calls[0][0] == "DELETE"


def test_a_bucket_address_expires_when_asked() -> None:
    storage, _ = bucket()
    url = storage.url("photos/004217/x.jpg", MOMENT + timedelta(hours=6))
    query = parse_qs(urlsplit(url).query)
    assert query["X-Amz-Expires"] == ["21600"]
    assert url.startswith("https://storage.yandexcloud.net/square-pot-photos/photos/004217/x.jpg?")


def test_an_unreachable_bucket_does_not_reveal_its_address() -> None:
    @dataclass
    class Down:
        def request(self, *args: Any, **kwargs: Any) -> requests.Response:
            raise requests.ConnectionError("https://storage.yandexcloud.net/square-pot-photos")

    storage = S3Storage(cast(requests.Session, Down()), "https://x/b", EXAMPLE)
    with pytest.raises(PhotoStorageError) as caught:
        storage.put("photos/004217/x.jpg", b"", "image/jpeg")
    assert str(caught.value) == "the photo storage is unreachable (ConnectionError)"


def test_the_key_file_holds_the_id_then_the_secret(tmp_path: Path) -> None:
    path = tmp_path / "photos-key"
    path.write_text("\n  key-id \nsecret\n\n", encoding="utf-8")
    assert read_key_file(path) == ("key-id", "secret")
    path.write_text("key-id\n", encoding="utf-8")
    with pytest.raises(ValueError, match="two lines"):
        read_key_file(path)


def test_a_folder_serves_a_file_only_at_its_signed_address(tmp_path: Path) -> None:
    storage = DiskStorage(tmp_path, b"secret", "/api/v1/photo-files")
    storage.put("photos/004217/x.jpg", b"jpeg", "image/jpeg")
    assert (tmp_path / "photos/004217/x.jpg").read_bytes() == b"jpeg"
    url = storage.url("photos/004217/x.jpg", MOMENT + timedelta(hours=6))
    parts = urlsplit(url)
    assert parts.path == "/api/v1/photo-files/photos/004217/x.jpg"
    query = {name: values[0] for name, values in parse_qs(parts.query).items()}
    expires, signature = int(query["expires"]), query["signature"]
    key = "photos/004217/x.jpg"
    assert storage.open(key, expires, signature, MOMENT) == tmp_path / key
    assert storage.open(key, expires, signature, MOMENT + timedelta(hours=7)) is None
    assert storage.open(key, expires + 1, signature, MOMENT) is None
    assert storage.open("photos/004217/y.jpg", expires, signature, MOMENT) is None
    storage.delete(key)
    storage.delete(key)
    assert storage.open(key, expires, signature, MOMENT) is None


@pytest.mark.parametrize(
    "key", ["../x.jpg", "photos/004217/..", "photos/004217/../../x", "photos/4217/x.jpg", "x"]
)
def test_a_folder_takes_only_photo_keys(tmp_path: Path, key: str) -> None:
    storage = DiskStorage(tmp_path, b"secret", "/files")
    with pytest.raises(PhotoStorageError, match="not a photo key"):
        storage.put(key, b"", "image/jpeg")
