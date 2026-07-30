# Prerequisites for this example

Unlike the other examples, this one does **not** run out of a fresh clone. It
scores against real CSI300 market data, which is neither in this repository nor
downloaded on demand.

```bash
pip install pyqlib lightgbm mlflow
python -m qlib.run.get_data qlib_data --target_dir ~/.qlib/qlib_data/cn_data --region cn
```

The dataset is roughly 800 MB. A single `--split train` run fits a LightGBM model
over Alpha158 features and takes about 7 minutes, which is why this project's
`.verify` raises `verify_timeout` to 1800.

Without these, `run.py verify examples/qlib-quant` fails with a non-zero exit and
no metric — which is the correct behaviour, not a bug. A verification that cannot
run is a failed verification, never a score of zero.

For an example that runs anywhere with nothing installed, use
[`examples/quant-lab`](../quant-lab/) (synthetic data, pandas + numpy) or
[`examples/tamper-demo`](../tamper-demo/) (no dependencies at all).

## Known issue on some environments

If the run aborts with

    module 'lib' has no attribute 'X509_V_FLAG_NOTIFY_POLICY'

that is an environment problem, not a fault in this example. The chain is:

    run_qlib_backtest.py
      -> qlib.workflow.task.manage   (imported during the workflow)
      -> pymongo                     (optional qlib dependency, for task management)
      -> pymongo.pyopenssl_context
      -> OpenSSL                     (pyOpenSSL too old for the installed cryptography)

qlib tolerates a *missing* optional dependency — that is why CatBoost is simply
skipped — because it catches `ModuleNotFoundError`. Here pymongo is present and
its own import fails with `AttributeError`, which nothing catches.

Resolve it by giving pip a self-consistent set, rather than upgrading pyOpenSSL
alone, which pulls in a `cryptography` newer than mlflow accepts:

    pip install --user "cryptography<49,>=43" "pyOpenSSL<26"

On Debian and Ubuntu, `pyOpenSSL` in `/usr/lib/python3/dist-packages` is owned by
the `python3-openssl` apt package. Install into `--user` so the newer copy
shadows it; do not `pip install -U` over a distro-managed package in the system
interpreter.
