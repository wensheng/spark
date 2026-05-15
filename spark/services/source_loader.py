"""Dynamic source loading via importlib metapath hooks.

Loads Python source code from zip archives identified by a content hash.
Imports are rewritten via AST manipulation so all loaded modules are
namespaced under the hash prefix, preventing conflicts between different
loaded versions.

Only supports Python 3.10+.
"""

from __future__ import annotations

import ast
import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import logging
import posixpath as _ospath  # zip uses posix notation
import sys
from io import BytesIO
from typing import Any
from zipfile import BadZipFile, ZipFile

_logger = logging.getLogger("spark.source_loader")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SourceHashNotLocallyAvailable(Exception):
    """The source data for a hash is not available locally."""

    def __init__(self, source_hash: str, msg: str = "") -> None:
        super().__init__(msg)
        self.source_hash = source_hash


class InvalidActorSourceHash(Exception):
    """Requested source hash does not match any loaded source."""

    def __init__(self, source_hash: str) -> None:
        super().__init__(f"Source hash {source_hash} does not match any loaded source")
        self.source_hash = source_hash


# ---------------------------------------------------------------------------
# Import rewriting (AST)
# ---------------------------------------------------------------------------


class _ImportRePackage(ast.NodeTransformer):
    """Rewrites imports to include the hash-based namespace prefix."""

    def __init__(self, source_hash_dot: str, topnames: list[str]) -> None:
        super().__init__()
        self._source_hash_dot = source_hash_dot  # e.g. "{{hash}}."
        self._topnames = [_ospath.splitext(n)[0] for n in topnames]

    def visit_Import(self, node: ast.Import) -> ast.Import:
        newnames: list[ast.alias] = []
        for alias in node.names:
            first_name = alias.name.partition(".")[0]
            if first_name in self._topnames:
                if alias.asname is None:
                    # "import foo.bar" -> "import hash.foo as foo; import hash.foo.bar"
                    newnames.append(ast.alias(self._source_hash_dot + first_name, first_name))
                    newnames.append(ast.alias(self._source_hash_dot + alias.name, None))
                else:
                    newnames.append(ast.alias(self._source_hash_dot + alias.name, alias.asname))
            else:
                newnames.append(alias)
        return ast.Import(newnames)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.ImportFrom:
        modname = (
            self._source_hash_dot + node.module
            if node.level == 0 and node.module and node.module.partition(".")[0] in self._topnames
            else node.module
        )
        return ast.ImportFrom(modname, node.names, node.level)


def _fix_imports(source_code: str, filename: str, source_hash_dot: str, toplevel: list[str]) -> Any:
    tree = ast.parse(source_code, filename)
    fixed = _ImportRePackage(source_hash_dot, toplevel).visit(tree)
    ast.fix_missing_locations(fixed)
    return compile(fixed, filename, "exec")


def _hash_importer(hash_prefix: str) -> Any:
    """Return a replacement __import__ that tries hash-prefixed imports first."""
    builtin_import = importlib.__import__
    holes: dict[str, bool] = {}

    def _supplier(name: str, *args: Any, **kw: Any) -> Any:
        if not name.startswith(hash_prefix):
            hash_name = hash_prefix + name
            if hash_name not in holes:
                try:
                    return builtin_import(hash_name, *args, **kw)
                except ImportError:
                    holes[hash_name] = True
        return builtin_import(name, *args, **kw)

    return _supplier


# ---------------------------------------------------------------------------
# Finder and Loader classes
# ---------------------------------------------------------------------------


class HashLoader(importlib.abc.Loader):
    """Loader for a single module or package within a hashed source zip."""

    def __init__(self, finder: SourceHashFinder, is_pkg: bool = False) -> None:
        self.finder = finder
        self.is_pkg = is_pkg

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> None:
        return None  # use default semantics

    def exec_module(self, module: Any) -> None:
        module_name = module.__name__
        hash_root = self.finder.hash_root()
        if module_name.startswith(hash_root):
            module_name = module_name[len(hash_root) :]

        if self.is_pkg:
            name = _ospath.join(*tuple(module_name.split(".") + ["__init__.py"]))
        elif "." in module_name:
            name = _ospath.join(*tuple(module_name.split("."))) + ".py"
        else:
            name = module_name + ".py"

        def _compile_source(source: bytes) -> Any:
            # Strip leading future imports and fix line endings
            source = source.replace(b"\r\n", b"\n") + b"\n"
            # Intercept __import__ in the loaded module
            source_str = source.decode("utf-8")
            return _fix_imports(
                source_str,
                name,
                hash_root,
                self.finder.get_zip_top_level_names(),
            )

        code = self.finder.with_zip_element_source(name, _compile_source)

        # Inject hash-aware __import__
        module.__dict__["__import__"] = self.finder.src_hash_importer

        exec(code, module.__dict__)


class HashRootLoader(importlib.abc.Loader):
    """Loader that 'eats' the top-level hash-root namespace.

    When importing just the hash root, this creates an empty namespace
    package so that sub-modules can be found.
    """

    def __init__(self, finder: SourceHashFinder) -> None:
        self.finder = finder

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> None:
        return None

    def exec_module(self, module: Any) -> None:
        module.__path__ = [self.finder.hash_root()]
        module.__package__ = self.finder.hash_root()


class SourceHashFinder(importlib.abc.MetaPathFinder):
    """MetaPathFinder that looks up modules in a hash-identified zip source.

    Inserted into ``sys.meta_path`` to intercept imports from a specific
    loaded source, namespacing all modules under the hash prefix.
    """

    def __init__(self, src_hash: str, decryptor: Any, enc_zf_src: Any) -> None:
        super().__init__()
        self._decryptor = decryptor
        self._enc_zf_src = enc_zf_src
        self.src_hash = src_hash
        self.src_hash_importer = _hash_importer(self.hash_root())

    def hash_root(self) -> str:
        """Return the namespace prefix for this source."""
        return "{{" + self.src_hash + "}}"

    # -- zip access --

    def _from_zip(self, getter: Any) -> Any:
        plain = self._decryptor(self._enc_zf_src)
        try:
            zf = ZipFile(BytesIO(plain))
        except BadZipFile as exc:
            _logger.error("Invalid zip for source hash %s: %s", self.src_hash, exc)
            raise
        try:
            return getter(zf)
        finally:
            zf.close()

    def get_zip_names(self) -> list[str]:
        return self._from_zip(lambda z: z.namelist())

    def get_zip_top_level_names(self) -> list[str]:
        return list({n.partition("/")[0] for n in self.get_zip_names() if n != "__init__.py"})

    def with_zip_element_source(self, element_name: str, on_source: Any) -> Any:
        return self._from_zip(lambda z: on_source(z.read(element_name)))

    # -- MetaPathFinder protocol --

    def find_spec(
        self,
        fullname: str,
        path: Any = None,
        target: Any = None,
    ) -> importlib.machinery.ModuleSpec | None:
        pkg_mark = self.hash_root()

        if path and not (isinstance(path, str) and path.startswith(pkg_mark)):
            return None

        skip = len(pkg_mark) if fullname.startswith(pkg_mark) else 0
        pathname = _ospath.join(*tuple(fullname[skip:].split(".")))

        if not pathname:
            return importlib.machinery.ModuleSpec(fullname, HashRootLoader(self), origin=pkg_mark, is_package=True)

        try:
            zip_names = self.get_zip_names()
        except BadZipFile:
            return None

        py_file = pathname + ".py"
        pkg_file = pathname + "/__init__.py"

        if py_file in zip_names:
            return importlib.machinery.ModuleSpec(
                fullname,
                HashLoader(self, is_pkg=False),
                origin=pkg_mark,
                is_package=False,
            )
        if pkg_file in zip_names:
            return importlib.machinery.ModuleSpec(
                fullname,
                HashLoader(self, is_pkg=True),
                origin=pkg_mark,
                is_package=True,
            )
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_module_from_hash_source(
    source_hash: str,
    sources: dict,
    mod_name: str,
    mod_class: str,
) -> type:
    """Load an actor class from a previously loaded source hash.

    Args:
        source_hash: The hash identifying the loaded source.
        sources: Dict mapping source hash to source data.
        mod_name: Dotted module name within the source.
        mod_class: Class name within the module.

    Returns:
        The actor class.

    Raises:
        InvalidActorSourceHash: If the hash is unknown.
        SourceHashNotLocallyAvailable: If source data is missing.
    """
    if source_hash not in sources:
        _logger.warning("Specified source hash %s is not currently loaded", source_hash)
        raise InvalidActorSourceHash(source_hash)

    src_data = sources[source_hash]
    if not src_data:
        raise SourceHashNotLocallyAvailable(
            source_hash,
            f"Local Actor does not have sources for hash {source_hash}",
        )

    # Check for an existing finder
    for metapath in sys.meta_path:
        if getattr(metapath, "src_hash", None) == source_hash:
            return _load_module_from_finder(metapath, mod_name, mod_class)

    finder = SourceHashFinder(source_hash, lambda v: v, src_data)
    sys.meta_path.insert(0, finder)
    return _load_module_from_finder(finder, mod_name, mod_class)


def _load_module_from_finder(finder: SourceHashFinder, mod_name: str, mod_class: str) -> type:
    h_root = finder.hash_root()

    # Import the hash-root namespace package first
    importlib.import_module(h_root)

    # Import the actual module with hash prefix
    imp_name = mod_name if mod_name.startswith(h_root) else h_root + mod_name
    mod = importlib.import_module(imp_name)
    return getattr(mod, mod_class)
