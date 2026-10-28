"""Dispatch ``rp eval <task> --dataset <public dataset>`` to the right adapter."""

from __future__ import annotations

from pathlib import Path


def run_public_eval(task: str, dataset: str, n: int = 30, out_dir: Path = Path("reports"),
                    data_dir: Path = Path("data"), method: str = "rules", oracle: str = "off"):
    from ..cli import write_report

    if dataset == "floorplancad":
        from . import floorplancad

        split = "test"
        scale_mode = "estimated" if "estimated" in method else "oracle"
        floorplancad.write_mapping(data_dir.parent if data_dir.name == "data" else Path("."))
        learned = "learned" in method
        res, worst = floorplancad.run(n, split, data_dir, scale_mode, learned)
        tag = ("learned-" if learned else "rules-") + f"{scale_mode}-scale"
        return write_report(f"{task}_floorplancad", dataset, tag, res["files"],
                            "scale" if scale_mode == "oracle" else "off", res, worst, out_dir)
    if dataset == "archcad":
        from . import archcad

        scale_mode = "estimated" if "estimated" in method else "oracle"
        learned = "learned" in method
        res, worst = archcad.run(n, "test", data_dir, scale_mode, learned)
        tag = ("learned-" if learned else "rules-") + f"{scale_mode}-scale"
        return write_report(f"{task}_archcad", dataset, tag, res["files"],
                            "scale" if scale_mode == "oracle" else "off", res, worst, out_dir)
    if dataset == "resplan":
        from . import resplan

        res, worst = resplan.run(n, data_dir, oracle)
        return write_report(f"{task}_resplan", dataset, method, res["plans"], oracle, res, worst, out_dir)
    raise NotImplementedError(f"no adapter for dataset {dataset!r} yet")
