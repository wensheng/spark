"""Director — management of loadable sources with versioning and lifecycle.

The Director is optional functionality for managing groups of dynamically
loaded actor sources. It provides:

* **Director actor** — manages groups, activates/deactivates source versions,
  restarts actors on source change, and tracks running actors per source.
* **SourceAuthority actor** — validates source packages using RSA signatures.
* **SourceEncoding** — encodes/decodes signed ``.tls`` source files.
* **GroupLoadableFiles** — discovers and version-sorts source files.
* **DirectorControl CLI** — command-line tool for interacting with the Director.
"""

from __future__ import annotations

import glob
import hashlib
import inspect
import json
import logging
import os
import subprocess
import sys
from asyncio import sleep
from collections import defaultdict
from collections.abc import Coroutine
from datetime import datetime, timedelta
from io import BytesIO
from typing import Any, cast
from zipfile import ZipFile

from ..actor.address import ActorAddress
from ..actor.base import Actor
from ..core.message import Message
from ..core.messages import (
    ActorExitRequest,
    ChildActorExited,
    LoadedSource,
    UnloadedSource,
    ValidatedSource,
    ValidateSource,
)
from ..services.rsasig import extract_ascii, key_factors, verify
from ..system import Syndicate

_logger = logging.getLogger("spark.director")

MINIMUM_STARTED_TIME = timedelta(seconds=2)

# ---------------------------------------------------------------------------
# Director actor
# ---------------------------------------------------------------------------


class Director(Actor):
    """Actor that manages groups of loadable sources.

    Sources are arranged into *groups*. Only one loaded source per group
    is "active" at a time (the most recently loaded valid source).

    Messages are Python dicts with a ``"DirectorOp"`` string key.
    """

    def __init__(self) -> None:
        super().__init__()
        self.groups: dict[str, dict] = {}
        self.pending_loads: dict[str, str] = {}
        self.loaded: dict[str, list[_LoadedSourceInfo]] = defaultdict(list)
        self.active_sources: dict[str, str | None] = defaultdict(lambda: None)
        self.watching_sources = False
        self.notification_reqs: list[ActorAddress] = []

    async def process(self, message: Message) -> None:
        msg = message.content
        sender = message.sender
        if isinstance(msg, ChildActorExited):
            await self._on_child_exited(ActorAddress(msg.child_id))
            return
        if isinstance(msg, LoadedSource):
            await self._on_source_loaded(msg.source_hash, msg.source_info)
            return
        if isinstance(msg, UnloadedSource):
            await self._on_source_unloaded(msg.source_hash)
            return
        if not isinstance(msg, dict):
            return
        op = msg.get("DirectorOp", "")
        handler = getattr(self, "_op_" + op, None)
        if handler is not None:
            result = handler(msg, sender)
            if inspect.isawaitable(result):
                await result
        else:
            _logger.warning("Director does not handle op: %s", op)

    # -- Operations --

    async def _op_RequestNotification(self, msg: dict, sender: ActorAddress | None) -> None:
        if sender is not None and sender not in self.notification_reqs:
            self.notification_reqs.append(sender)

    async def _op_DefineGroup(self, msg: dict, sender: ActorAddress | None) -> None:
        self.groups[msg["Group"]] = {
            "Actors": _default_actor_def(),
            "AutoUnload": msg.get("AutoUnload", False),
        }
        if "Actors" in msg:
            for actor_name in msg["Actors"]:
                self.groups[msg["Group"]]["Actors"][actor_name] = _nested_default()
                for section in msg["Actors"][actor_name]:
                    self.groups[msg["Group"]]["Actors"][actor_name][section] = msg["Actors"][actor_name][section]
        if sender:
            await self.tell({"DirectorResponse": "DeclaredGroup", "Success": True}, sender)

    async def _op_LoadSource(self, msg: dict, sender: ActorAddress | None) -> None:
        # Trigger source loading through the actor system
        source_hash = self._load_source(msg["Source"])
        self.pending_loads[source_hash] = msg["Group"]
        if sender:
            await self.tell(
                {
                    "DirectorResponse": "SourceLoading",
                    "Success": True,
                    "SourceHash": source_hash,
                },
                sender,
            )

    async def _op_RetrieveAll(self, msg: dict, sender: ActorAddress | None) -> None:
        group_filter = msg.get("Group")
        result: dict[str, dict] = {}
        for group_name in self.groups:
            if group_filter and group_name != group_filter:
                continue
            result[group_name] = {
                "ActiveHash": self.active_sources[group_name],
                "Loaded": [lsi.source_hash for lsi in self.loaded[group_name]],
                "Running": {
                    lsi.source_hash: [
                        {
                            "ActorClass": ri.classname,
                            "Role": ri.role,
                            "ActorAddress": ri.address,
                            "StartTime": st,
                        }
                        for ri, st in lsi.actorinfo
                    ]
                    for lsi in self.loaded[group_name]
                },
            }
        if sender:
            await self.tell(
                {"DirectorResponse": "AllAddresses", "Success": True, "Groups": result},
                sender,
            )

    async def _op_RetrieveRole(self, msg: dict, sender: ActorAddress | None) -> None:
        group_filter = msg.get("Group")
        role_name = msg.get("Role")
        for group_name in self.loaded:
            if group_filter and group_name != group_filter:
                continue
            for lsi in self.loaded[group_name]:
                if lsi.source_hash != self.active_sources[group_name]:
                    continue
                for ri, st in lsi.actorinfo:
                    if ri.role == role_name:
                        if sender:
                            await self.tell(
                                {
                                    "DirectorResponse": "RoleAddress",
                                    "Success": True,
                                    "Group": group_name,
                                    "SourceHash": lsi.source_hash,
                                    "ActorClass": ri.classname,
                                    "Role": ri.role,
                                    "ActorAddress": ri.address,
                                    "StartTime": st,
                                },
                                sender,
                            )
                        return
        if sender:
            await self.tell(
                {
                    "DirectorResponse": "RoleAddress",
                    "Success": False,
                    "Group": group_filter,
                    "SourceHash": None,
                    "ActorClass": None,
                    "Role": role_name,
                    "ActorAddress": None,
                },
                sender,
            )

    # -- System message handlers --

    async def _on_child_exited(self, child: ActorAddress) -> None:
        """Restart actors from the active source if they exit."""
        now = datetime.now()
        for group_name in self.active_sources:
            for lsi in self.loaded[group_name]:
                if lsi.source_hash == self.active_sources[group_name]:
                    for ri, start_time in lsi.actorinfo:
                        if ri.address == child:
                            if now - start_time < MINIMUM_STARTED_TIME:
                                _logger.warning(
                                    "Actor %s only ran for %s; not restarting",
                                    ri.classname,
                                    now - start_time,
                                )
                            else:
                                ri.address = await self._start_actor(
                                    ri.classname,
                                    lsi.source_hash,
                                    ri.role,
                                    global_name=ri.global_name,
                                    start_msg=ri.activate_msg,
                                )
        # Remove from non-active entries
        for group_name in self.loaded:
            for lsi in self.loaded[group_name]:
                for ri, _ in lsi.actorinfo:
                    if ri.address == child:
                        ri.address = None

    async def on_child_exited(self, child: ActorAddress, reason: str) -> None:
        await self._on_child_exited(child)

    # -- Source lifecycle callbacks --

    async def _on_source_loaded(self, source_hash: str, source_info: str) -> None:
        """Called when a source has been validated and loaded."""
        group_name = self.pending_loads.pop(source_hash, None)
        if not group_name:
            return
        lsi = _LoadedSourceInfo(
            source_hash,
            source_info,
            self.groups[group_name].get("AutoUnload", False),
        )

        # Deactivate old active source
        active_hash = self.active_sources[group_name]
        for loaded in self.loaded[group_name]:
            if loaded.source_hash == active_hash:
                for ri, _ in loaded.actorinfo:
                    await self._deactivate_actor(ri)

        self.active_sources[group_name] = source_hash

        # Start new actors
        for actor_name in self.groups[group_name].get("Actors", {}):
            agi = self.groups[group_name]["Actors"][actor_name]
            onload = agi.get("OnLoad", {}) or {}
            ri = _RunningActorInfo(
                address=await self._start_actor(
                    actor_name,
                    source_hash,
                    onload.get("Role"),
                    global_name=onload.get("GlobalName"),
                    start_msg=onload.get("Message"),
                ),
                role=onload.get("Role"),
                global_name=onload.get("GlobalName"),
                classname=actor_name,
                activate_msg=onload.get("Message"),
                deactivate_msg=(agi.get("OnDeactivate", {}) or {}).get("Message"),
                reactivate_msg=(agi.get("OnReactivate", {}) or {}).get("Message"),
            )
            lsi.add_actor(ri)

        self.loaded[group_name].append(lsi)

        # Auto-unload old versions
        kept = 1
        for loaded in self.loaded[group_name][-2::-1]:
            auto = loaded.auto_unload
            unload = auto if isinstance(auto, bool) else (kept >= auto)
            if unload:
                self._unload_source(loaded.source_hash)
            else:
                kept += 1

        await self._send_notifications()

    async def _on_source_unloaded(self, source_hash: str) -> None:
        """Called when a source has been unloaded."""
        self.pending_loads.pop(source_hash, None)
        for group_name in self.loaded:
            for idx, loaded in enumerate(self.loaded[group_name]):
                if loaded.source_hash == source_hash:
                    is_active = self.active_sources[group_name] == source_hash
                    for ri, _ in loaded.actorinfo:
                        if ri.address:
                            if is_active and ri.deactivate_msg:
                                await self.tell(ri.deactivate_msg, ri.address)
                            await self.tell(ActorExitRequest("source unloaded"), ri.address)
                    self.loaded[group_name].pop(idx)
                    if self.loaded[group_name]:
                        new_active = self.loaded[group_name][-1]
                        self.active_sources[group_name] = new_active.source_hash
                        for ri, _ in new_active.actorinfo:
                            if ri.address:
                                await self.tell(ri.reactivate_msg, ri.address)
                            else:
                                ri.address = await self._start_actor(
                                    ri.classname,
                                    new_active.source_hash,
                                    global_name=ri.global_name,
                                    start_msg=ri.activate_msg,
                                )
                    else:
                        self.active_sources[group_name] = None
                    await self._send_notifications()

    # -- Internal helpers --

    def _load_source(self, path: str) -> str:
        """Load a source file and return its hash."""
        with open(path, "rb") as f:
            data = f.read()
        return hashlib.md5(data).hexdigest()

    def _unload_source(self, source_hash: str) -> None:
        """Unload a source by hash."""
        # In a full implementation, this removes the SourceHashFinder from sys.meta_path
        pass

    async def _start_actor(
        self,
        actor_class: type[Actor] | str,
        source_hash: str,
        role: str | None = None,
        global_name: str | None = None,
        start_msg: Any = None,
    ) -> ActorAddress | None:
        if not isinstance(actor_class, type) or not issubclass(actor_class, Actor):
            _logger.warning(
                "Director cannot start actor %r from source %s; dynamic source resolution is not available",
                actor_class,
                source_hash,
            )
            return None
        if global_name:
            _logger.warning("Director global name %r is not supported by this Spark runtime", global_name)
        addr = await self.create_actor(actor_class)
        if start_msg:
            await self.tell(start_msg, addr)
        return addr

    async def _deactivate_actor(self, ri: _RunningActorInfo) -> None:
        if ri.deactivate_msg and ri.address:
            await self.tell(ri.deactivate_msg, ri.address)

    async def _send_notifications(self) -> None:
        for addr in self.notification_reqs:
            await self.tell({"DirectorResponse": "NotificationOfUpdate", "Success": True}, addr)
        self.notification_reqs.clear()


# -- Internal data classes --


class _LoadedSourceInfo:
    __slots__ = ("source_hash", "source_info", "auto_unload", "actorinfo")

    def __init__(self, source_hash: str, source_info: str, auto_unload: Any) -> None:
        self.source_hash = source_hash
        self.source_info = source_info
        self.auto_unload = auto_unload
        self.actorinfo: list[tuple[_RunningActorInfo, datetime]] = []

    def add_actor(self, ri: _RunningActorInfo) -> None:
        self.actorinfo.append((ri, datetime.now()))


class _RunningActorInfo:
    __slots__ = (
        "address",
        "role",
        "global_name",
        "classname",
        "activate_msg",
        "deactivate_msg",
        "reactivate_msg",
    )

    def __init__(
        self,
        address: ActorAddress | None,
        role: str | None,
        global_name: str | None,
        classname: type[Actor] | str,
        activate_msg: Any,
        deactivate_msg: Any,
        reactivate_msg: Any,
    ) -> None:
        self.address = address
        self.role = role
        self.global_name = global_name
        self.classname = classname
        self.activate_msg = activate_msg
        self.deactivate_msg = deactivate_msg
        self.reactivate_msg = reactivate_msg


def _default_actor_def() -> defaultdict:
    return defaultdict(lambda: defaultdict(dict))


def _nested_default() -> defaultdict:
    return defaultdict(dict)


# ---------------------------------------------------------------------------
# SourceAuthority actor
# ---------------------------------------------------------------------------


class SourceAuthority(Actor):
    """Actor that validates loadable source packages against RSA public keys.

    On startup, receives a ``"Startup:<sources_dir>"`` string message
    with the path to the directory containing ``*_tls.key`` public key files.
    """

    def __init__(self) -> None:
        super().__init__()
        self.sources_dir = ""

    async def process(self, message: Message) -> None:
        msg = message.content
        sender = message.sender

        if isinstance(msg, str) and msg.startswith("Startup:"):
            self.sources_dir = msg[len("Startup:") :]

        elif isinstance(msg, ValidateSource):
            if sender is None:
                return
            for keyfile in glob.glob(os.path.join(self.sources_dir, "*_tls.key")):
                with open(keyfile) as kf:
                    public_key = kf.read()
                sdata = SourceEncoding.tls_to_zip(msg.source_data, public_key)
                if sdata:
                    _logger.info(
                        "Validated source %s (%s)",
                        msg.source_hash,
                        msg.source_info or "no-info",
                    )
                    await self.tell(
                        ValidatedSource(
                            source_hash=msg.source_hash,
                            source_data=sdata,
                            source_info=msg.source_info or "",
                        ),
                        sender,
                    )
                    return
            _logger.warning("Invalid source not loaded (%s)", msg.source_hash)


# ---------------------------------------------------------------------------
# SourceEncoding — signed .tls file format
# ---------------------------------------------------------------------------


class SourceEncoding:
    """Encode/decode signed loadable source ``.tls`` files.

    The ``.tls`` format wraps a zip file with an RSA signature for
    integrity and authenticity verification.
    """

    @staticmethod
    def zip_to_tls(
        zfpath: str,
        private_keyfile: str,
        fmt: str | None = None,
        verbose: Any = lambda *a: None,
    ) -> str:
        """Sign a zip file, producing a ``.tls`` file.

        Requires ``openssl`` on the system PATH.
        """
        fmt = fmt or "SparkDirectorFMT1"
        sfdir = os.path.dirname(zfpath)
        sfname = os.path.splitext(os.path.basename(zfpath))[0] + GroupLoadableFiles.src_suffix
        sfpath = os.path.join(sfdir, sfname)
        sftmp = os.path.join(sfdir, "." + sfname)

        shasig = subprocess.Popen(
            ["openssl", "dgst", "-sha256", "-sign", private_keyfile, zfpath],
            stdout=subprocess.PIPE,
        ).communicate()[0]

        try:
            with open(sftmp, "wb") as sf:
                verbose("Signing %s", sfpath)
                encoder = getattr(
                    SourceEncoding,
                    "_ztt_" + (fmt or "SparkDirectorFMT1"),
                )
                encoder(zfpath, sf, shasig)
            os.rename(sftmp, sfpath)
            return sfpath
        finally:
            try:
                os.remove(sftmp)
            except OSError:
                pass

    @staticmethod
    def _ztt_SparkDirectorFMT1(zfpath: str, sf: Any, shasig: bytes) -> None:
        sf.write(b"SparkDirectorFMT1-sha256\n")
        with open(zfpath, "rb") as zf:
            sf.write(str(len(shasig)).encode() + b"\n")
            zf_data = zf.read()
            zfc_split = zf_data.split(b"PK\x05\x06")
            sf.write(str(len(zfc_split[0])).encode() + b"\n")
            assert len(zfc_split) == 2
            sf.write(zfc_split[0])
            sf.write(zfc_split[1])
            sf.write(shasig)

    @staticmethod
    def tls_to_zip(tlsdata: bytes, public_key: str, verbose: Any = None) -> bytes | None:
        """Validate and extract a zip from a signed ``.tls`` file."""
        try:
            hdr, data = extract_ascii(tlsdata, 200)
            l1e = hdr.find("\n")
            l1 = hdr[:l1e]
            l1pf, l1ph = l1.split("-")
            hashfunc = getattr(hashlib, l1ph)

            if l1pf.startswith("SparkDirectorFMT1"):
                l2e = hdr.find("\n", l1e + 1)
                l3e = hdr.find("\n", l2e + 1)
                return SourceEncoding._decode_fmt_d1(
                    tlsdata,
                    public_key,
                    hdr[l1e + 1 : l2e],
                    hdr[l2e + 1 : l3e],
                    l3e,
                    hashfunc,
                )
            elif l1pf.startswith("ViceroyFMT"):
                l2e = hdr.find("\n", l1e + 1)
                fmtnum = l1pf[len("ViceroyFMT") :]
                decoder = getattr(SourceEncoding, "_decode_fmt_v" + fmtnum, None)
                if decoder:
                    return cast(
                        bytes | None,
                        decoder(tlsdata, public_key, hdr[l1e + 1 : l2e], l2e, hashfunc),
                    )
        except (ValueError, IndexError, KeyError):
            pass
        return None

    @staticmethod
    def _decode_fmt_d1(
        inpdata: bytes,
        public_key: str,
        hdr_l2: str,
        hdr_l3: str,
        hdr_end: int,
        hashfunc: Any,
    ) -> bytes | None:
        siglen = int(hdr_l2)
        eocdp = int(hdr_l3)
        inp_list = list(inpdata)
        sig = inp_list[-siglen:]
        dta = (
            inp_list[hdr_end + 1 : hdr_end + 1 + eocdp] + list(b"PK\x05\x06") + inp_list[hdr_end + eocdp + 1 : -siglen]
        )
        mod_n, e = key_factors(public_key)
        import array

        if not verify(dta, sig, mod_n, e, hashfunc):
            return None
        return array.array("B", dta).tobytes()

    @staticmethod
    def _decode_fmt_v1(
        inpdata: bytes,
        public_key: str,
        hdr_l2: str,
        hdr_end: int,
        hashfunc: Any,
    ) -> bytes | None:
        siglen = int(hdr_l2)
        inp_list = list(inpdata)
        sig = inp_list[hdr_end + 1 : hdr_end + 1 + siglen]
        dta = inp_list[hdr_end + 1 + siglen :]
        # Character substitution decryption
        dec_map = dict(zip(map(ord, ":ai \n="), map(ord, " \n=ia:"), strict=True))
        dec_data = [dec_map.get(b, b) for b in dta]
        mod_n, e = key_factors(public_key)
        import array

        if not verify(dec_data, sig, mod_n, e, hashfunc):
            return None
        return array.array("B", dec_data).tobytes()

    @staticmethod
    def _decode_fmt_v2(
        inpdata: bytes,
        public_key: str,
        hdr_l2: str,
        hdr_end: int,
        hashfunc: Any,
    ) -> bytes | None:
        siglen = int(hdr_l2)
        inp_list = list(inpdata)
        sig = inp_list[-siglen:]
        dta = inp_list[hdr_end + 1 : -siglen]
        mod_n, e = key_factors(public_key)
        import array

        if not verify(dta, sig, mod_n, e, hashfunc):
            return None
        return array.array("B", dta).tobytes()


# ---------------------------------------------------------------------------
# GroupLoadableFiles — file discovery and version sorting
# ---------------------------------------------------------------------------


class GroupLoadableFiles:
    """Discovers and version-sorts loadable source files in a directory."""

    info_suffix = ".tli"
    src_suffix = ".tls"

    def __init__(self, director_dir: str, group_name: str) -> None:
        self.dirdir = director_dir
        self.group_name, ext = os.path.splitext(os.path.basename(group_name))
        if ext == self.src_suffix:
            self.group_name = self.group_name.split("-")[0]

    def tli_filename(self) -> str:
        return os.path.join(self.dirdir, self.group_name + self.info_suffix)

    def tli_contents(self) -> dict | None:
        try:
            with open(self.tli_filename()) as f:
                return cast(dict, json.loads(f.read()))
        except (json.JSONDecodeError, FileNotFoundError):
            return None

    @staticmethod
    def version_extract(base_name: str, extension: str = ".tls") -> Any:
        class _VerPart:
            __slots__ = ("_vp",)

            def __init__(self, verpart: Any) -> None:
                self._vp = verpart

            def __lt__(self, other: Any) -> bool:
                try:
                    return bool(self._vp < other._vp)
                except TypeError:
                    return isinstance(self._vp, int)

            def __eq__(self, other: Any) -> bool:
                try:
                    return bool(self._vp == other._vp)
                except TypeError:
                    return False

            def __call__(self) -> Any:
                return self._vp

        def _get_ver_part(name: str) -> list[_VerPart]:
            base = os.path.basename(name)
            if not base.startswith(base_name):
                return []
            tail = base[len(base_name) :]
            if tail.endswith(extension):
                tail = tail[: -len(extension)]
            is_num: int | None = None
            is_str: str | None = None
            ret: list[Any] = []
            for ch in tail:
                if ch in "0123456789":
                    if is_str is not None:
                        ret.append(is_str)
                        is_str = None
                    is_num = int(ch) if is_num is None else (is_num * 10 + int(ch))
                else:
                    if is_num is not None:
                        ret.append(is_num)
                        is_num = None
                    is_str = ch if is_str is None else (is_str + ch)
            return [_VerPart(x) for x in filter(None, ret + [is_str, is_num])]

        return _get_ver_part

    def tls_filenames(self) -> list[str]:
        tls_file = os.path.join(self.dirdir, self.group_name + self.src_suffix)
        tls_files = glob.glob(os.path.join(self.dirdir, self.group_name + "-*" + self.src_suffix))
        if os.path.exists(tls_file):
            tls_files.append(tls_file)
        tls_files.sort(key=self.version_extract(self.group_name), reverse=True)
        return tls_files


# ---------------------------------------------------------------------------
# DirectorControl CLI
# ---------------------------------------------------------------------------


class DirectorControl:
    """Command-line tool for managing the Director and loadable sources.

    Usage::

        dc = DirectorControl(sources_dir="/opt/spark/sources")
        dc("load", "mygroup")
        dc("list")
        dc("shutdown")
    """

    ask_wait = timedelta(seconds=5)

    def __init__(
        self,
        sources_dir: str | None = None,
        system_base: str = "multiprocTCPBase",
        admin_port: int = 1900,
    ) -> None:
        default_sources_dir = "C:/spark/director" if os.name == "nt" else "/opt/spark/director"
        self.sources_dir: str = sources_dir or os.getenv("SPARK_DIRECTOR_DIR") or default_sources_dir
        self.system_base = system_base
        self.admin_port = admin_port
        self.verbose: Any = lambda fmt, *args: None

    def __call__(self, cmd: str, *args: Any) -> int:
        if cmd == "verbose":
            self.verbose = lambda fmt, *args: (
                sys.stdout.write(fmt % args),
                sys.stdout.write("\n" if fmt[-1] != "\n" else ""),
                sys.stdout.flush(),
            )
            cmd = args[0] if args else "help"
            args = args[1:] if args else ()
        handler = getattr(self, "cmd_" + cmd, self._bad_cmd)
        result = handler(*args)
        if inspect.isawaitable(result):
            return int(Syndicate.run(cast(Coroutine[Any, Any, Any], result)))
        return result

    def _bad_cmd(self, *args: Any) -> int:
        print("Unrecognized command; use 'help' for usage.")
        return 2

    # -- Commands --

    def cmd_help(self, *args: Any) -> int:
        if args:
            h = getattr(self, "cmd_" + args[0], None)
            if h and h.__doc__:
                print(h.__doc__)
            else:
                print(f"No help for '{args[0]}'")
        else:
            print("Director commands: help config start shutdown avail gensrc tlsinfo load refresh unload list")
        return 0

    def cmd_config(self) -> int:
        print(f"   Sources location: {self.sources_dir}")
        print(f"        System Base: {self.system_base}")
        print(f"         Admin Port: {self.admin_port}")
        return 0

    async def cmd_start(self, and_wait: str = "") -> int:
        """Start the ActorSystem and Director."""
        asys = await self._get_asys()
        director = await self._get_director(asys)
        await asys.tell(director, "start")
        if and_wait:
            while True:
                await sleep(3600)
        return 0

    async def cmd_shutdown(self) -> int:
        asys = await self._get_asys(no_startup=True)
        await asys.shutdown()
        print("Shutdown completed")
        return 0

    def cmd_avail(self) -> int:
        print(f"SPARK_DIRECTOR_DIR={self.sources_dir}")
        for glf in self._all_groups():
            entries = []
            for fname in glf.tls_filenames():
                shown = fname[len(self.sources_dir) + 1 :] if fname.startswith(self.sources_dir + "/") else fname
                with open(fname, "rb") as source_file:
                    digest = hashlib.md5(source_file.read()).hexdigest()
                entries.append(f"{shown}    {digest}")
            print(f"{glf.group_name}: " + ("\n" + " " * (len(glf.group_name)) + "+ ").join(entries))
        return 0

    def cmd_gensrc(self, group_name: str, private_keyfile: str, src_dir: str, *srcs: str) -> int:
        """Generate a signed loadable source file.

        gensrc group_name private_keyfile sources_dir srcfile [...]
        """
        opts: dict[str, str | None] = {"deps": None, "tli": None, "fmt": None, "version": None}
        srcs_list = list(srcs)
        while srcs_list and ":" in srcs_list[0]:
            opt, _, val = srcs_list[0].partition(":")
            if opt in opts:
                opts[opt] = val
            srcs_list.pop(0)

        zfname = group_name
        version = opts.get("version")
        if version:
            zfname += f"-{version}"
        zfname += ".zip"
        zfpath = os.path.join(self.sources_dir, zfname)

        os.chdir(src_dir)
        sys.path.insert(0, ".")
        try:
            with ZipFile(zfpath, "w") as zf:
                for src in srcs_list:
                    for filename in glob.glob(src):
                        zf.write(filename)
            fmt = opts.get("fmt") or "SparkDirectorFMT1"
            sfpath = SourceEncoding.zip_to_tls(zfpath, private_keyfile, fmt, self.verbose)
            print("Wrote", sfpath)
            return 0
        finally:
            try:
                os.remove(zfpath)
            except OSError:
                pass

    def cmd_tlsinfo(self, tlsfname: str, subcmd: str = "") -> int:
        """Show info about a .tls file."""
        if not os.path.exists(tlsfname):
            f2 = os.path.join(self.sources_dir, tlsfname)
            if not os.path.exists(f2):
                sys.stderr.write(f'TLS file "{tlsfname}" does not exist\n')
                return 4
            tlsfname = f2
        with open(tlsfname, "rb") as f:
            tlsdata = f.read()
        for keyfile in glob.glob(os.path.join(self.sources_dir, "*_tls.key")):
            with open(keyfile) as kf:
                public_key = kf.read()
            sdata = SourceEncoding.tls_to_zip(tlsdata, public_key)
            if sdata:
                with ZipFile(BytesIO(sdata)) as zf:
                    if not subcmd:
                        bf = zf.testzip()
                        if bf:
                            sys.stderr.write(f"Bad file in zip: {bf}\n")
                            return 6
                        print(f'Validated "{tlsfname}" with key {keyfile}')
                    elif subcmd == "contents":
                        for info in zf.infolist():
                            print(f" {info.file_size:>6}  {info.filename}")
                    else:
                        print(zf.read(subcmd).decode("utf-8"))
                return 0
        sys.stderr.write(f'Could not validate signature on "{tlsfname}"\n')
        return 7

    async def cmd_load(self, group_or_file: str) -> int:
        """Load a loadable source."""
        glf = GroupLoadableFiles(self.sources_dir, group_or_file)
        tli = glf.tli_contents() or {}
        tli["DirectorOp"] = "DefineGroup"
        tli["Group"] = glf.group_name
        asys = await self._get_asys()
        director = await self._get_director(asys)
        r = await asys.ask(director, tli, timeout=5)
        if not r or not r.get("Success"):
            return 1
        fnames = glf.tls_filenames()
        if not fnames:
            print(f"No TLS files found for group {glf.group_name}")
            return 1
        r = await asys.ask(
            director,
            {
                "DirectorOp": "LoadSource",
                "Source": fnames[0],
                "Group": glf.group_name,
            },
            timeout=5,
        )
        if r and r.get("Success"):
            print(f'Loaded "{glf.group_name}" {fnames[0]}: {r["SourceHash"]}')
            return 0
        return 1

    async def cmd_refresh(self) -> int:
        for glf in self._all_groups():
            r = await self.cmd_load(glf.group_name)
            if r:
                return r
        return 0

    async def cmd_list(self, group: str = "") -> int:
        asys = await self._get_asys()
        director = await self._get_director(asys)
        req: dict = {"DirectorOp": "RetrieveAll"}
        if group:
            req["Group"] = group
        r = await asys.ask(director, req, timeout=5)
        if not r or not r.get("Success"):
            return 1
        for gname in sorted(r.get("Groups", {})):
            print(f"Group {gname}::")
            gi = r["Groups"][gname]
            for srchash in gi.get("Loaded", []):
                print(f"  Source hash {srchash}" f'{"  [ACTIVE]" if srchash == gi.get("ActiveHash") else ""}')
                for actor in gi.get("Running", {}).get(srchash, []):
                    role = actor.get("Role")
                    print(
                        f'      {actor.get("ActorAddress") or "LOAD FAILED"}'
                        f' -- {actor["ActorClass"]}'
                        f'{f" ({role})" if role else ""}'
                        f'  (since {actor.get("StartTime", "?")})'
                    )
        return 0

    async def cmd_unload(self, source_hash: str) -> int:
        asys = await self._get_asys()
        unload_actor_source = getattr(asys, "unload_actor_source", None)
        if unload_actor_source is None:
            print("Source unloading is not supported by this Syndicate")
            return 1
        result = unload_actor_source(source_hash)
        if inspect.isawaitable(result):
            await result
        return 0

    # -- Internal helpers --

    @property
    def _asys(self) -> Syndicate | None:
        if not hasattr(self, "__asys"):
            self.__asys: Syndicate | None = None
        return self.__asys

    async def _get_asys(self, no_startup: bool = False) -> Syndicate:
        if self._asys is None and not no_startup:
            asys = Syndicate(backend="inprocess")
            # Start source authority
            sa = await asys.create_actor(SourceAuthority)
            asys.name_registry.register("Director Source Authority", sa)
            await asys.tell(sa, f"Startup:{self.sources_dir}")
            self.__asys = asys
        if self._asys is None:
            return Syndicate(backend="inprocess")
        return self._asys

    async def _get_director(self, asys: Syndicate) -> ActorAddress:
        director = asys.name_registry.resolve("Director")
        if director is not None:
            return director
        director = await asys.create_actor(Director)
        asys.name_registry.register("Director", director)
        return director

    def _all_groups(self) -> list[GroupLoadableFiles]:
        return [GroupLoadableFiles(self.sources_dir, f) for f in glob.glob(os.path.join(self.sources_dir, "*.tli"))]


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    sys.exit(DirectorControl()(*tuple(sys.argv[1:] or ["help"])))
