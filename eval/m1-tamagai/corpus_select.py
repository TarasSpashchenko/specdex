"""Load the corpus definition an evaluation script runs against (`--corpus-def FILE`, default corpus_def.py here).

It is read before the scripts build their module-level constants, so it is taken from the command line early.
"""
import argparse
import importlib.util
from pathlib import Path
from types import ModuleType

DEFAULT = Path(__file__).resolve().parent / "corpus_def.py"


def corpus_def_path() -> Path:
    early = argparse.ArgumentParser(add_help=False)
    early.add_argument("--corpus-def", type=Path, default=DEFAULT)
    return early.parse_known_args()[0].corpus_def


def load() -> ModuleType:
    path = corpus_def_path().resolve()
    spec = importlib.util.spec_from_file_location(f"corpus_def_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
