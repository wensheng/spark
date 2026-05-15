"""Tests for source loading, RSA signatures, and Director functionality."""

import hashlib
import os
import tempfile
from io import BytesIO
from typing import Any
from zipfile import ZipFile

import pytest

from spark.contrib.director import (
    Director,
    GroupLoadableFiles,
    SourceEncoding,
)
from spark.core.message import Message
from spark.services.rsasig import extract_ascii, key_factors, verify


class TestRsaSignature:
    def test_extract_ascii_header_from_binary(self) -> None:
        data = b"DirectorFMT1-sha256\n123\n456\n\x00\xff\xfe"
        hdr, rest = extract_ascii(data, 200)
        assert "DirectorFMT1-sha256" in hdr
        assert len(rest) > 0

    def test_extract_ascii_all_ascii(self) -> None:
        data = b"hello world"
        hdr, rest = extract_ascii(data, 200)
        assert hdr == "hello world"
        assert rest == b""

    def test_key_factors_from_generated_key(self) -> None:
        import subprocess

        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = os.path.join(tmpdir, "test_key.pem")
            pub_path = os.path.join(tmpdir, "test_key.pub.pem")
            subprocess.run(
                [
                    "openssl",
                    "genpkey",
                    "-algorithm",
                    "RSA",
                    "-pkeyopt",
                    "rsa_keygen_bits:2048",
                    "-out",
                    key_path,
                ],
                capture_output=True,
                check=False,
            )
            subprocess.run(
                [
                    "openssl",
                    "rsa",
                    "-pubout",
                    "-in",
                    key_path,
                    "-out",
                    pub_path,
                ],
                capture_output=True,
                check=False,
            )
            if os.path.exists(pub_path):
                with open(pub_path) as f:
                    pub_key = f.read()
                mod_n, e = key_factors(pub_key)
                assert mod_n > 0
                assert e > 0

    def test_verify_signature(self) -> None:
        message = [1, 2, 3, 4, 5]
        sig = [0] * 256
        result = verify(message, sig, 3, 65537)
        assert result is False


class TestSourceLoader:
    def test_invalid_source_hash_raises(self) -> None:
        from spark.services.source_loader import InvalidActorSourceHash

        with pytest.raises(InvalidActorSourceHash):
            from spark.services.source_loader import load_module_from_hash_source

            load_module_from_hash_source("nonexistent_hash", {}, "mod", "Cls")

    def test_source_hash_finder_creation(self) -> None:
        from spark.services.source_loader import SourceHashFinder

        buf = BytesIO()
        with ZipFile(buf, "w") as zf:
            zf.writestr("mymod.py", b"class MyActor:\n    pass\n")
        zip_data = buf.getvalue()
        h = hashlib.md5(zip_data).hexdigest()

        finder = SourceHashFinder(h, lambda v: v, zip_data)
        assert finder.src_hash == h
        assert finder.hash_root() == "{{" + h + "}}"
        names = finder.get_zip_names()
        assert "mymod.py" in names

    def test_source_hash_finder_top_level_names(self) -> None:
        from spark.services.source_loader import SourceHashFinder

        buf = BytesIO()
        with ZipFile(buf, "w") as zf:
            zf.writestr("mymod.py", b"x = 1")
            zf.writestr("other/__init__.py", b"")
        zip_data = buf.getvalue()
        h = hashlib.md5(zip_data).hexdigest()

        finder = SourceHashFinder(h, lambda v: v, zip_data)
        top = finder.get_zip_top_level_names()
        assert "mymod.py" in top
        assert "other" in top


class TestDirector:
    @pytest.mark.asyncio
    async def test_director_define_group(self) -> None:
        from spark.actor.base import _disable_actor_auto_start

        with _disable_actor_auto_start():
            director = Director()
        director._bind_context(_fake_context())

        msg = {
            "DirectorOp": "DefineGroup",
            "Group": "testgroup",
            "Actors": {
                "TestActor": {
                    "OnLoad": {
                        "Role": "worker",
                        "GlobalName": "myworker",
                        "Message": "start",
                    },
                    "OnDeactivate": {"Message": "stop"},
                    "OnReactivate": {"Message": "restart"},
                }
            },
        }
        await director.process(Message(content=msg))
        assert "testgroup" in director.groups
        assert director.groups["testgroup"]["Actors"]["TestActor"]["OnLoad"]["Role"] == "worker"

    @pytest.mark.asyncio
    async def test_director_request_notification(self) -> None:
        from spark.actor.address import ActorAddress
        from spark.actor.base import _disable_actor_auto_start
        from spark.core.identity import ActorId, SyndicateId

        with _disable_actor_auto_start():
            director = Director()
        director._bind_context(_fake_context())

        _sid = SyndicateId.from_name("sender")
        await director.process(
            Message(
                content={"DirectorOp": "RequestNotification"},
                sender=ActorAddress(ActorId(syndicate_id=_sid)),
            )
        )
        assert len(director.notification_reqs) == 1

    @pytest.mark.asyncio
    async def test_director_retrieve_all_empty(self) -> None:
        from spark.actor.base import _disable_actor_auto_start

        with _disable_actor_auto_start():
            director = Director()
        director._bind_context(_fake_context())

        director.groups["g"] = {}
        await director.process(Message(content={"DirectorOp": "RetrieveAll"}))


class TestSourceEncoding:
    def test_tls_to_zip_invalid_data(self) -> None:
        result = SourceEncoding.tls_to_zip(b"garbage data", "fake key")
        assert result is None

    def test_zip_to_tls_and_back(self) -> None:
        import subprocess

        with tempfile.TemporaryDirectory() as tmpdir:
            zfpath = os.path.join(tmpdir, "test.zip")
            with ZipFile(zfpath, "w") as zf:
                zf.writestr("mymod.py", b"class TestActor:\n    pass\n")

            key_path = os.path.join(tmpdir, "test_key.pem")
            pub_path = os.path.join(tmpdir, "test_key_tls.key")
            result = subprocess.run(
                [
                    "openssl",
                    "genpkey",
                    "-algorithm",
                    "RSA",
                    "-pkeyopt",
                    "rsa_keygen_bits:2048",
                    "-out",
                    key_path,
                ],
                capture_output=True,
            )
            if result.returncode != 0:
                pytest.skip("openssl not available")

            subprocess.run(
                [
                    "openssl",
                    "rsa",
                    "-pubout",
                    "-in",
                    key_path,
                    "-out",
                    pub_path,
                ],
                capture_output=True,
                check=True,
            )

            sfpath = SourceEncoding.zip_to_tls(zfpath, key_path, "SparkDirectorFMT1")
            assert os.path.exists(sfpath)

            with open(sfpath, "rb") as f:
                tlsdata = f.read()
            with open(pub_path) as f:
                pub_key = f.read()

            tls_result = SourceEncoding.tls_to_zip(tlsdata, pub_key)
            assert tls_result is not None

            with ZipFile(BytesIO(tls_result)) as zf:
                assert zf.read("mymod.py") == b"class TestActor:\n    pass\n"


class TestGroupLoadableFiles:
    def test_version_sorting(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            for ver in ["1", "2", "10", "05"]:
                fname = os.path.join(tmpdir, f"mygroup-{ver}.tls")
                with open(fname, "w") as f:
                    f.write(f"version {ver}")

            glf = GroupLoadableFiles(tmpdir, "mygroup")
            files = glf.tls_filenames()
            assert len(files) >= 4
            assert "mygroup-10.tls" in os.path.basename(files[0])

    def test_tli_filename(self) -> None:
        glf = GroupLoadableFiles("/tmp/test", "mygroup")
        assert glf.tli_filename() == "/tmp/test/mygroup.tli"

    def test_group_name_from_tls_file(self) -> None:
        glf = GroupLoadableFiles("/tmp/test", "mygroup-20200101.tls")
        assert glf.group_name == "mygroup"


def _fake_context() -> Any:
    from spark.actor.address import ActorAddress
    from spark.core.identity import ActorId, SyndicateId

    _sid = SyndicateId.from_name("test")
    _aid = ActorId(syndicate_id=_sid)

    class FakeContext:
        actor_id = _aid
        address = ActorAddress(_aid)
        parent = None

        def __init__(self) -> None:
            self.sent: list[Any] = []
            self.created: list[Any] = []

        async def tell(self, target: Any, message: Any) -> None:
            self.sent.append((target, message))

        async def ask(self, target: Any, message: Any, timeout: float | None = None) -> None:
            return None

        async def create_actor(self, actor_class: Any, *args: Any, **kwargs: Any) -> Any:
            self.created.append((actor_class, args, kwargs))
            return ActorAddress(ActorId(syndicate_id=_sid))

        def schedule_after(self, timeout: float, payload: Any = None) -> None:
            pass

        async def watch(self, *, read: Any = (), write: Any = ()) -> None:
            pass

        async def stop(self) -> None:
            pass

        def notify_on_system_registration_changes(self, enable: bool = True) -> None:
            pass

        def pre_register_remote_system(self, addr: Any, caps: Any) -> None:
            pass

        def de_register_remote_system(self, addr: Any) -> None:
            pass

        async def syndicate_shutdown(self) -> None:
            pass

    return FakeContext()
