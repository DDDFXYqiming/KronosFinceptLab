"""Create a Smoothed Full Fine-tuning (SFF) starting checkpoint.

SFF (ICLR 2026, "Lost in the Non-convex Loss Landscape") builds a same-architecture
randomly initialised twin and linearly interpolates:

    theta3 = alpha * theta_parent + (1 - alpha) * theta_random

The random twin is constructed from the parent's ``config.json`` using the model's
default PyTorch initialisation (kaiming/uniform/normal), exactly as the official
Meteor-Stars/SFF implementation does by instantiating a fresh model.

Usage (from the repository root):

    .\\.venv311\\Scripts\\python.exe examples\\make_sff_checkpoint.py \
        --parent external\\Kronos\\finetune_csv\\finetuned_full_small_v3\\basemodel\\best_model \
        --output external\\Kronos\\finetune_csv\\finetuned_largecap_sff_fullv3\\sff_init \
        --alpha 0.85 --seed 42
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import torch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
KRONOS_PKG = PROJECT_ROOT / "external" / "Kronos"


def _ensure_kronos_importable() -> None:
    if str(KRONOS_PKG) not in sys.path:
        sys.path.insert(0, str(KRONOS_PKG))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _state_dict_l2_distance(a: dict[str, torch.Tensor], b: dict[str, torch.Tensor]) -> float:
    total = 0.0
    for key in a:
        total += float((a[key].float() - b[key].float()).pow(2).sum())
    return float(total ** 0.5)


def build_sff_checkpoint(
    parent_path: Path,
    output_path: Path,
    *,
    alpha: float,
    seed: int,
) -> dict[str, object]:
    from model import Kronos

    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be strictly between 0 and 1, got {alpha}")

    torch.manual_seed(seed)
    parent_path = parent_path.resolve()
    output_path = output_path.resolve()

    config = json.loads((parent_path / "config.json").read_text(encoding="utf-8"))
    parent_model = Kronos.from_pretrained(str(parent_path))

    random_model = Kronos(
        s1_bits=config.get("s1_bits", 10),
        s2_bits=config.get("s2_bits", 10),
        n_layers=config.get("n_layers", 12),
        d_model=config.get("d_model", 832),
        n_heads=config.get("n_heads", 16),
        ff_dim=config.get("ff_dim", 2048),
        ffn_dropout_p=config.get("ffn_dropout_p", 0.2),
        attn_dropout_p=config.get("attn_dropout_p", 0.0),
        resid_dropout_p=config.get("resid_dropout_p", 0.2),
        token_dropout_p=config.get("token_dropout_p", 0.0),
        learn_te=config.get("learn_te", True),
    )

    parent_state = parent_model.state_dict()
    random_state = random_model.state_dict()
    if set(parent_state) != set(random_state):
        missing = sorted(set(parent_state) - set(random_state))
        extra = sorted(set(random_state) - set(parent_state))
        raise RuntimeError(
            "parent and random twin state dicts differ "
            f"(missing={missing[:5]}, extra={extra[:5]})"
        )

    with torch.no_grad():
        for key in parent_state:
            mixed = parent_state[key].float() * alpha + random_state[key].float() * (1.0 - alpha)
            parent_state[key].copy_(mixed.to(parent_state[key].dtype))

    parent_model.save_pretrained(str(output_path))

    weights_file = output_path / "model.safetensors"
    metadata = {
        "method": "sff_smoothed_full_finetuning",
        "reference": "Lost in the Non-convex Loss Landscape: How to Fine-tune the Large Time Series Model? (ICLR 2026)",
        "alpha": alpha,
        "seed": seed,
        "parent_path": str(parent_path),
        "parent_config_sha256": _file_sha256(parent_path / "config.json"),
        "output_weights_sha256": _file_sha256(weights_file) if weights_file.exists() else None,
        "parameter_count": sum(p.numel() for p in parent_model.parameters()),
        "note": "theta3 = alpha * theta_parent + (1 - alpha) * theta_random; random twin uses model default init.",
    }
    (output_path / "SFF_README.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Verification: save/load round trip and distance from the parent.
    reloaded = Kronos.from_pretrained(str(output_path))
    reloaded_state = reloaded.state_dict()
    if set(reloaded_state) != set(parent_state):
        raise RuntimeError("reloaded state dict keys differ from the interpolated model")
    for key in reloaded_state:
        if not torch.equal(reloaded_state[key], parent_state[key]):
            raise RuntimeError(f"reloaded weights differ at key: {key}")

    original_parent = Kronos.from_pretrained(str(parent_path))
    l2_distance = _state_dict_l2_distance(parent_state, original_parent.state_dict())
    metadata["l2_distance_from_parent"] = l2_distance
    (output_path / "SFF_README.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[sff] parent={parent_path}")
    print(f"[sff] output={output_path}")
    print(f"[sff] alpha={alpha} seed={seed}")
    print(f"[sff] l2_distance_from_parent={l2_distance:.6f}")
    print(f"[sff] weights_sha256={metadata['output_weights_sha256']}")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--alpha", type=float, default=0.85)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    _ensure_kronos_importable()
    build_sff_checkpoint(args.parent, args.output, alpha=args.alpha, seed=args.seed)


if __name__ == "__main__":
    main()
