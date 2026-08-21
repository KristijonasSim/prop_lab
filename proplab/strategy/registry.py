"""Discovery of strategy classes in proplab/strategy/library/."""
from __future__ import annotations

import importlib
import inspect
import pkgutil

from .base import Strategy


def _library():
    from . import library
    return library


def discover() -> dict[str, type[Strategy]]:
    """slug -> Strategy subclass, for every module in the library package."""
    found: dict[str, type[Strategy]] = {}
    lib = _library()
    for mod in pkgutil.iter_modules(lib.__path__):
        module = importlib.import_module(f"{lib.__name__}.{mod.name}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if not (issubclass(obj, Strategy) and obj is not Strategy
                    and obj.__module__ == module.__name__):
                continue
            # A shared base class that never declares a name is scaffolding,
            # not a strategy - registering it would put an "unnamed" row in
            # the registry and let it be run by accident.
            if obj.name == Strategy.name:
                continue
            if obj.name in found and found[obj.name] is not obj:
                raise ValueError(f"Duplicate strategy name {obj.name!r}")
            found[obj.name] = obj
    return found


def get(name: str) -> type[Strategy]:
    reg = discover()
    if name not in reg:
        raise KeyError(f"Unknown strategy {name!r}. Available: {sorted(reg)}")
    return reg[name]


def source_of(cls: type[Strategy]) -> str:
    return inspect.getsource(inspect.getmodule(cls))
