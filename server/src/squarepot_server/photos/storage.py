# SPDX-License-Identifier: AGPL-3.0-or-later
"""Where photo files are kept: an S3-compatible bucket, or a folder on the server (ADR 0007).

Both hand out addresses that expire: a bucket's own signed addresses, or
addresses of the server's photo file route signed with a key only the server
knows.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, urlencode, urlsplit
from xml.etree import ElementTree

import requests

TIMEOUT_SECONDS = 60
ALGORITHM = "AWS4-HMAC-SHA256"
UNSIGNED = "UNSIGNED-PAYLOAD"
# Keys the server makes: photos/<number>/<name> and sightings/<number>/<name> (ADR 0008).
KEY = re.compile(r"^(photos|sightings)/[0-9]{6}/[A-Za-z0-9_-][A-Za-z0-9_.-]*$")


class PhotoStorageError(Exception):
    """The photo storage could not be reached or refused the request."""


class PhotoStorage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def delete(self, key: str) -> None:
        """Remove the file; a missing file is no error."""
        ...

    def url(self, key: str, expires_at: datetime) -> str:
        """An address that serves the file until `expires_at`, to anyone who has it."""
        ...

    def get(self, key: str) -> bytes: ...

    def keys(self, prefix: str) -> Iterator[str]:
        """Every key that starts with `prefix` and is a key the server makes."""
        ...


def hmac_sha256(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode(), hashlib.sha256).digest()


def amz_date(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def canonical_query(query: dict[str, str]) -> str:
    return "&".join(
        f"{quote(name, safe='-_.~')}={quote(value, safe='-_.~')}"
        for name, value in sorted(query.items())
    )


class Signer:
    """AWS Signature Version 4, for the S3 API that Yandex Object Storage also speaks."""

    def __init__(self, key_id: str, secret: str, region: str) -> None:
        self.key_id = key_id
        self.secret = secret
        self.region = region

    def scope(self, moment: datetime) -> str:
        return f"{moment.astimezone(UTC):%Y%m%d}/{self.region}/s3/aws4_request"

    def signature(
        self,
        method: str,
        path: str,
        query: dict[str, str],
        headers: dict[str, str],
        payload_hash: str,
        moment: datetime,
    ) -> str:
        """The signature of a request; `headers` are the signed ones, lower-case."""
        names = sorted(headers)
        request = "\n".join(
            [
                method,
                quote(path, safe="/-_.~"),
                canonical_query(query),
                "".join(f"{name}:{headers[name].strip()}\n" for name in names),
                ";".join(names),
                payload_hash,
            ]
        )
        text = "\n".join(
            [
                ALGORITHM,
                amz_date(moment),
                self.scope(moment),
                hashlib.sha256(request.encode()).hexdigest(),
            ]
        )
        key = f"AWS4{self.secret}".encode()
        for part in self.scope(moment).split("/"):
            key = hmac_sha256(key, part)
        return hmac.new(key, text.encode(), hashlib.sha256).hexdigest()

    def presign(self, url: str, method: str, expires: int, moment: datetime) -> str:
        """`url` with the query that lets anyone make this request for `expires` seconds."""
        parts = urlsplit(url)
        query = {
            "X-Amz-Algorithm": ALGORITHM,
            "X-Amz-Credential": f"{self.key_id}/{self.scope(moment)}",
            "X-Amz-Date": amz_date(moment),
            "X-Amz-Expires": str(expires),
            "X-Amz-SignedHeaders": "host",
        }
        query["X-Amz-Signature"] = self.signature(
            method, parts.path, query, {"host": parts.netloc}, UNSIGNED, moment
        )
        return f"{url}?{canonical_query(query)}"

    def headers(
        self,
        method: str,
        url: str,
        body: bytes,
        extra: dict[str, str],
        moment: datetime,
        query: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """The headers that sign a request with this body (and this query, sent as is)."""
        parts = urlsplit(url)
        payload_hash = hashlib.sha256(body).hexdigest()
        signed = {
            "host": parts.netloc,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date(moment),
            **{name.lower(): value for name, value in extra.items()},
        }
        signature = self.signature(method, parts.path, query or {}, signed, payload_hash, moment)
        authorization = (
            f"{ALGORITHM} Credential={self.key_id}/{self.scope(moment)}, "
            f"SignedHeaders={';'.join(sorted(signed))}, Signature={signature}"
        )
        return {**signed, "authorization": authorization}


def read_key_file(path: Path) -> tuple[str, str]:
    """The key id and secret from a file holding one on each of its first two lines."""
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    lines = [line for line in lines if line]
    if len(lines) != 2:
        raise ValueError(f"{path} must hold two lines: the key id, then the secret")
    return lines[0], lines[1]


class S3Storage:
    """A bucket of an S3-compatible service, addressed by path: <endpoint>/<bucket>/<key>."""

    def __init__(
        self,
        session: requests.Session,
        base_url: str,
        signer: Signer,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.signer = signer
        self.clock = clock

    def object_url(self, key: str) -> str:
        # Photo keys need no quoting, so the path signed is the path sent.
        if not KEY.fullmatch(key):
            raise PhotoStorageError(f"not a photo key: {key!r}")
        return f"{self.base_url}/{key}"

    def request(
        self, method: str, key: str, body: bytes = b"", extra: dict[str, str] | None = None
    ) -> requests.Response:
        url = self.object_url(key)
        headers = self.signer.headers(method, url, body, extra or {}, self.clock())
        del headers["host"]
        try:
            return self.session.request(
                method, url, data=body, headers=headers, timeout=TIMEOUT_SECONDS
            )
        except requests.RequestException as error:
            raise PhotoStorageError(
                f"the photo storage is unreachable ({type(error).__name__})"
            ) from error

    def put(self, key: str, data: bytes, content_type: str) -> None:
        response = self.request("PUT", key, data, {"content-type": content_type})
        if not response.ok:
            raise PhotoStorageError(f"the photo storage answered {response.status_code}")

    def delete(self, key: str) -> None:
        response = self.request("DELETE", key)
        if not response.ok and response.status_code != 404:
            raise PhotoStorageError(f"the photo storage answered {response.status_code}")

    def url(self, key: str, expires_at: datetime) -> str:
        now = self.clock()
        expires = max(1, int((expires_at - now).total_seconds()))
        return self.signer.presign(self.object_url(key), "GET", expires, now)

    def get(self, key: str) -> bytes:
        response = self.request("GET", key)
        if not response.ok:
            raise PhotoStorageError(f"the photo storage answered {response.status_code}")
        return response.content

    def keys(self, prefix: str) -> Iterator[str]:
        """The bucket's keys under `prefix`, a page of up to 1000 at a time (ListObjectsV2)."""
        token = None
        while True:
            query = {"list-type": "2", "prefix": prefix}
            if token is not None:
                query["continuation-token"] = token
            headers = self.signer.headers("GET", self.base_url, b"", {}, self.clock(), query)
            del headers["host"]
            try:
                response = self.session.request(
                    "GET",
                    f"{self.base_url}?{canonical_query(query)}",
                    data=b"",
                    headers=headers,
                    timeout=TIMEOUT_SECONDS,
                )
            except requests.RequestException as error:
                raise PhotoStorageError(
                    f"the photo storage is unreachable ({type(error).__name__})"
                ) from error
            if not response.ok:
                raise PhotoStorageError(f"the photo storage answered {response.status_code}")
            try:
                root = ElementTree.fromstring(response.content)
            except ElementTree.ParseError as error:
                raise PhotoStorageError(
                    "the photo storage sent a listing it cannot read"
                ) from error
            for element in root.iter():
                if element.tag.rsplit("}", 1)[-1] == "Key" and KEY.fullmatch(element.text or ""):
                    yield element.text or ""
            token = next(
                (
                    element.text
                    for element in root.iter()
                    if element.tag.rsplit("}", 1)[-1] == "NextContinuationToken"
                ),
                None,
            )
            if not token:
                return


class DiskStorage:
    """A folder on the server; the API serves its files at addresses it signs."""

    def __init__(self, root: Path, secret: bytes, route: str) -> None:
        self.root = root
        self.secret = secret
        self.route = route

    def path(self, key: str) -> Path:
        if not KEY.fullmatch(key):
            raise PhotoStorageError(f"not a photo key: {key!r}")
        return self.root / key

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.name + ".partial")
        partial.write_bytes(data)
        os.replace(partial, path)

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)

    def get(self, key: str) -> bytes:
        try:
            return self.path(key).read_bytes()
        except OSError as error:
            raise PhotoStorageError(f"{key} cannot be read ({type(error).__name__})") from error

    def keys(self, prefix: str) -> Iterator[str]:
        for path in sorted(self.root.rglob("*")):
            key = path.relative_to(self.root).as_posix()
            if path.is_file() and key.startswith(prefix) and KEY.fullmatch(key):
                yield key

    def token(self, key: str, expires: int) -> str:
        return hmac.new(self.secret, f"{key}\n{expires}".encode(), hashlib.sha256).hexdigest()

    def url(self, key: str, expires_at: datetime) -> str:
        expires = int(expires_at.timestamp())
        query = urlencode({"expires": expires, "signature": self.token(key, expires)})
        return f"{self.route}/{key}?{query}"

    def open(self, key: str, expires: int, signature: str, now: datetime) -> Path | None:
        """The file a signed address names, while the address is valid."""
        if expires < now.timestamp() or not KEY.fullmatch(key):
            return None
        if not hmac.compare_digest(signature, self.token(key, expires)):
            return None
        path = self.path(key)
        return path if path.is_file() else None
