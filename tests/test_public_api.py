"""The published surface of the package.

Everything a user is allowed to depend on is named in `scenet.__all__`. These tests
exist so that surface cannot change by accident -- a name silently dropped, an error
that stops being catchable, or the PEP 561 marker going missing from the wheel.
"""

import importlib
import pkgutil
import sys
from pathlib import Path

import pytest

import scenet
from scenet import errors


class TestPublicNames:
    def test_every_exported_name_exists(self):
        missing = [name for name in scenet.__all__ if not hasattr(scenet, name)]
        assert missing == []

    def test_no_duplicates(self):
        assert len(scenet.__all__) == len(set(scenet.__all__))

    def test_version_is_a_string(self):
        assert isinstance(scenet.__version__, str)
        assert scenet.__version__

    def test_every_exported_name_is_in_its_own_module_s_all(self):
        """Autodoc documents what a module's `__all__` names, where it has one. A public
        name left out of it is documented on no page of the API reference."""
        left_out: list[str] = []
        for name in scenet.__all__:
            module = sys.modules.get(getattr(getattr(scenet, name), "__module__", None) or "")
            if module is not None and name not in getattr(module, "__all__", (name,)):
                left_out.append(f"{module.__name__}.{name}")
        assert left_out == []

    def test_every_exported_name_is_documented(self):
        """A name a user can reach must explain itself. No exceptions."""
        undocumented = [
            name
            for name in scenet.__all__
            if not name.startswith("__") and not (getattr(scenet, name).__doc__ or "").strip()
        ]
        assert undocumented == []


class TestTypeMarker:
    def test_py_typed_marker_is_present(self):
        """Without this file, PEP 561 says downstream type checkers must ignore our
        annotations -- so the entire typing effort would be invisible to users."""
        marker = Path(scenet.__file__).parent / "py.typed"
        assert marker.is_file()


class TestErrorHierarchy:
    CONCRETE = [
        errors.BalloonPlacementError,
        errors.CompositionError,
        errors.LayoutError,
        errors.PanelSyntaxError,
        errors.ScriptSyntaxError,
        errors.UnknownPuppetError,
        errors.RenderError,
        errors.UnknownActorError,
        errors.FileReadError,
        errors.MissingFileError,
        errors.MalformedAssetError,
        errors.CoreSyntaxError,
    ]

    @pytest.mark.parametrize("error", CONCRETE)
    def test_everything_is_a_scenet_error(self, error: type[Exception]):
        assert issubclass(error, errors.ScenetError)

    @pytest.mark.parametrize(
        ("error", "builtin"),
        [
            (errors.PanelSyntaxError, ValueError),
            (errors.ScriptSyntaxError, ValueError),
            (errors.CompositionError, ValueError),
            (errors.LayoutError, ValueError),
            (errors.BalloonPlacementError, ValueError),
            (errors.UnknownPuppetError, KeyError),
            (errors.RenderError, ValueError),
            (errors.UnknownActorError, KeyError),
            (errors.FileReadError, OSError),
            (errors.MissingFileError, FileNotFoundError),
            (errors.MalformedAssetError, ValueError),
            (errors.CoreSyntaxError, ValueError),
        ],
    )
    def test_builtin_bases_are_preserved(self, error: type[Exception], builtin: type[Exception]):
        """Code written before `ScenetError` existed caught these built-ins. It must
        keep working."""
        assert issubclass(error, builtin)

    def test_source_and_solver_errors_are_disjoint(self):
        assert not issubclass(errors.SourceError, errors.SolverError)
        assert not issubclass(errors.SolverError, errors.SourceError)

    def test_a_bad_document_raises_a_source_error(self):
        with pytest.raises(errors.SourceError):
            scenet.compile_source("panel: {size: [0, 100]}")

    def test_a_missing_file_is_one_that_cannot_be_read(self):
        assert issubclass(errors.MissingFileError, errors.FileReadError)

    def test_a_malformed_asset_is_an_asset_error(self):
        assert issubclass(errors.MalformedAssetError, errors.AssetError)

    def test_an_unknown_puppet_is_still_no_value_error(self):
        """`AssetError` stays off `ValueError`, or `except ValueError` would catch a miss."""
        assert not issubclass(errors.AssetError, ValueError)
        assert not issubclass(errors.UnknownPuppetError, ValueError)

    def test_every_public_error_is_public(self):
        """Each error a caller can catch is named in `scenet.__all__`, so it imports from
        `scenet` like the rest."""
        public = {
            name for name in errors.__all__ if issubclass(getattr(errors, name), errors.ScenetError)
        }
        assert sorted(public - set(scenet.__all__)) == []

    def test_errors_module_exports_match_its_contents(self):
        for name in errors.__all__:
            assert hasattr(errors, name), name


class TestNothingLeaksAtImport:
    def test_importing_the_package_imports_no_optional_extras(self):
        """`import scenet` must stay cheap enough for a CLI to feel instant."""
        module = importlib.import_module("scenet")
        assert module is scenet

    def test_every_submodule_imports_cleanly(self):
        """A module that only ever gets imported by one code path can rot unnoticed."""
        package = Path(scenet.__file__).parent
        for info in pkgutil.walk_packages([str(package)], prefix="scenet."):
            importlib.import_module(info.name)
