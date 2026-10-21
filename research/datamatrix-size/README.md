# Data Matrix 10x10 vs 12x12 at the same label size

Which reads more reliably from a phone: today's 10x10 symbol with 1.2 mm
modules, or a 12x12 symbol with 1.0 mm modules, both 12 mm wide? The
question, method and results are written up in
[docs/research](../../docs/research/); this folder reproduces them.

## Run

In GitHub Actions: run the workflow **Research: Data Matrix size** (Actions,
Run workflow), first with *smoke* checked, then without. The results come back
as the workflow's artifacts.

Elsewhere, with Python 3.12 and libdmtx:

```sh
pip install -r requirements.txt
python run.py all            # check, every frame, analysis -> results/
python run.py all --smoke    # 3 frames per point -> results-smoke/
```

`python run.py --help` lists the steps the workflow runs one by one.

## Files

- `config.yaml`: the experiment: seed, frame, sizes, every condition and its values.
- `symbols.py`: the two symbols, from the server's own encoder.
- `check.py`: the symbols are standard (the server, libdmtx, zxing-cpp).
- `scene.py`: paired scenes, the same frame drawn with each symbol.
- `vendor/render.py`: frame rendering adapted from
  [libscanner/datamatrix-benchmark](https://github.com/libscanner/datamatrix-benchmark),
  MIT No Attribution ([vendor/LICENSE](vendor/LICENSE)).
- `run.py`: the steps; `analyze.py`: tables and plots.
- `results/`: the committed results of the full run.
