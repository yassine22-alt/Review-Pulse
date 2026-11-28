"""Score every tile of each query's pool with a visual search model (docs/progress/M35). Needs torch and transformers.

    python visual_cluster.py <folder with tasks.json and tiles/> <out folder> [--model vidore/colqwen2-v1.0-hf] [--check]

Nothing of this repository is imported. ``--check`` loads the processor, reads every picture and loads no weights.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tasks", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--model", default="vidore/colqwen2-v1.0-hf")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    import torch
    from PIL import Image
    from transformers import ColQwen2ForRetrieval, ColQwen2Processor

    work = json.loads((args.tasks / "tasks.json").read_text(encoding="utf-8"))
    tiles, queries = work["tiles"], work["queries"]
    processor = ColQwen2Processor.from_pretrained(args.model)
    if args.check:
        for t in tiles:
            Image.open(args.tasks / t["file"]).convert("RGB")
        print(f"{len(tiles)} tiles read, {len(queries)} queries, processor loaded")
        return
    model = ColQwen2ForRetrieval.from_pretrained(args.model, torch_dtype=torch.bfloat16).to("cuda").eval()
    started = time.time()

    def embed(make, items, size):
        out = []
        for i in range(0, len(items), size):
            inputs = make(items[i:i + size]).to(model.device)
            with torch.no_grad():
                emb = model(**inputs).embeddings
            mask = inputs["attention_mask"].bool()
            out += [e[m].float().cpu() for e, m in zip(emb, mask)]          # the padding of a batch is not part of a tile
        return out

    pictures = embed(lambda batch: processor(images=[Image.open(args.tasks / t["file"]).convert("RGB") for t in batch],
                                             return_tensors="pt"), tiles, 4)
    print(f"{len(pictures)} tiles embedded in {time.time() - started:.0f} s", flush=True)
    words = sorted({q["what"] for q in queries})
    texts = embed(lambda batch: processor(text=batch, return_tensors="pt"), words, 8)
    where = {t["id"]: i for i, t in enumerate(tiles)}
    scores = {}
    for q in queries:
        scored = processor.score_retrieval([texts[words.index(q["what"])]], [pictures[where[i]] for i in q["pool"]])[0]
        scores[q["id"]] = {i: float(s) for i, s in zip(q["pool"], scored)}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "scores.json").write_text(json.dumps({"model": args.model, "scores": scores}, indent=1), encoding="utf-8")
    print(f"{len(scores)} queries scored; done in {time.time() - started:.0f} s")


if __name__ == "__main__":
    main()
