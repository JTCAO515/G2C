from importlib import import_module


def test_jt_subpackages_are_importable():
    for name in ("common", "synthetic", "workbench", "engine", "eval"):
        import_module(f"jt.{name}")
