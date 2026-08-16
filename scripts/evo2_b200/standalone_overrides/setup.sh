#!/bin/bash
# Reuse the Arc/NVIDIA container's Blackwell-built Python stack in ToolInstance's
# isolated Python 3.12 worker. Package imports are validated during image build.
set -euo pipefail

python - <<'PY'
import importlib.metadata

import evo2
import flash_attn
import torch
import transformer_engine
import vortex

assert torch.cuda.is_available()
assert importlib.metadata.version("evo2") == "0.5.5"
assert importlib.metadata.version("vtx") == "1.1.0"
PY
