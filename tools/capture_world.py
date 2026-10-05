# ABOUTME: Runs Stand's unmodified leadgen generator in process with a recording wrapper and writes the provider fixture for one seed.
# ABOUTME: The wrapper records each lead's clean base and each archetype's effect; --check fails when the fixture file is absent or differs.
import argparse
import copy
import difflib
import json
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sim-harness"))
# The tool wraps Stand's modules; the path above makes them importable.
import leadgen  # noqa: E402
from leadgen import archetypes, generator  # noqa: E402

from uwh.runtime.hashing import hash_json  # noqa: E402

DATA_DIR = ROOT / "src" / "uwh" / "providers" / "data"
CONFIG_PATH = Path(leadgen.__file__).with_name("generator_config.yaml")
# The queue the app reads: POST /queue?count=10&seed=<seed> with the service's default difficulty.
COUNT = 10
DIFFICULTY = "mixed"

# The section 9.4 provider fields. roof_classification and siding_classification have no provider.
PROVIDER_FIELDS = (
    "broker_tier",
    "has_primary_policy_with_stand",
    "replacement_cost",
    "protection_class",
    "kyc_score",
    "p_f",
    "slope_angle_deg",
    "min_distance_to_neighbor_ft",
    "vegetation_clearance",
    "road_access",
)
# Provider fields whose provider answers not_found when this archetype nulled the value.
NOT_FOUND_WHEN_NULLED_BY = {"protection_class": "pc_9_10_rural", "kyc_score": "profile_kyc"}


class GuaranteePassFired(RuntimeError):
    """The generator added an archetype after the per-lead pass, which the fixture does not replay."""


@dataclass
class ArchetypeEffect:
    archetype: str
    set_values: dict[str, Any]  # field -> the value the archetype put on the lead
    nulled: list[str]  # fields the archetype set to None


@dataclass
class LeadRecord:
    lead_id: str = ""
    # as _base_lead returned it, before any archetype
    base: dict[str, Any] = field(default_factory=dict)
    effects: list[ArchetypeEffect] = field(default_factory=list)


@dataclass
class Recorder:
    leads: list[LeadRecord] = field(default_factory=list)


@contextmanager
def recording() -> Iterator[Recorder]:
    """Patch the generator's `_base_lead`, `generate_lead` and each archetype for one generation.

    `generate_lead` is wrapped only to tell an archetype call made inside a lead's own pass from
    one made by the guarantee pass in `generate_queue`; the latter raises GuaranteePassFired.
    The wrappers pass arguments and results through unchanged. The originals are restored on exit.
    """
    recorder = Recorder()
    original_base_lead = generator._base_lead
    original_generate_lead = generator.generate_lead
    original_archetypes = dict(archetypes.ARCHETYPES)
    current: list[LeadRecord] = []  # the lead being generated; empty outside generate_lead

    def base_lead(rng: Any) -> dict[str, Any]:
        fields: dict[str, Any] = original_base_lead(rng)
        current[0].base = copy.deepcopy(fields)
        return fields

    def generate_lead(*args: Any, **kwargs: Any) -> dict[str, Any]:
        record = LeadRecord()
        current.append(record)
        try:
            lead: dict[str, Any] = original_generate_lead(*args, **kwargs)
        finally:
            current.clear()
        record.lead_id = lead["lead_id"]
        recorder.leads.append(record)
        return lead

    def wrap_archetype(name: str, original: Callable[..., Any]) -> Callable[..., Any]:
        def call(fields: dict[str, Any], rng: Any) -> Any:
            if not current:
                raise GuaranteePassFired(
                    f"the guarantee pass applied {name}; the fixture replays only the per-lead pass"
                )
            touches = original(fields, rng)
            current[0].effects.append(
                ArchetypeEffect(
                    archetype=name,
                    set_values={
                        t["field"]: copy.deepcopy(fields[t["field"]])
                        for t in touches
                        if t["kind"] == "archetype_set"
                    },
                    nulled=[t["field"] for t in touches if t["kind"] == "archetype_null"],
                )
            )
            return touches

        return call

    generator._base_lead = base_lead
    generator.generate_lead = generate_lead
    for name, original in original_archetypes.items():
        archetypes.ARCHETYPES[name] = wrap_archetype(name, original)
    try:
        yield recorder
    finally:
        generator._base_lead = original_base_lead
        generator.generate_lead = original_generate_lead
        archetypes.ARCHETYPES.update(original_archetypes)


def load_config() -> dict[str, Any]:
    """Stand's generator_config.yaml, loaded as the leadgen service loads it."""
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        config: dict[str, Any] = yaml.safe_load(handle)
    return config


def capture_queue(seed: int, config: dict[str, Any]) -> tuple[list[dict[str, Any]], Recorder]:
    """The queue the generator makes for `seed`, with the recording of one wrapped generation.

    Raises AssertionError when the wrapped output differs from the unwrapped output and
    GuaranteePassFired when the guarantee pass added an archetype.
    """
    unwrapped = generator.generate_queue(seed, COUNT, DIFFICULTY, copy.deepcopy(config))
    with recording() as recorder:
        wrapped = generator.generate_queue(seed, COUNT, DIFFICULTY, copy.deepcopy(config))
    assert wrapped == unwrapped, f"the recording wrapper changed the output for seed {seed}"
    return wrapped, recorder


def provider_entry(lead: dict[str, Any], record: LeadRecord) -> dict[str, Any]:
    """The fixture entry for one lead.

    `provider_values` holds what the provider returns for each provider field when the lead's
    value is missing: the clean base value, or not_found where the field's archetype nulled it.
    `archetype_set` holds the provider fields' values an archetype set; they stay on the lead.
    """
    archetype_set = {
        name: value
        for effect in record.effects
        for name, value in effect.set_values.items()
        if name in PROVIDER_FIELDS
    }
    provider_values: dict[str, Any] = {}
    for name in PROVIDER_FIELDS:
        not_found = any(
            effect.archetype == NOT_FOUND_WHEN_NULLED_BY.get(name) and name in effect.nulled
            for effect in record.effects
        )
        if not_found:
            provider_values[name] = {"status": "not_found", "value": None}
        else:
            provider_values[name] = {"status": "found", "value": record.base[name]}
    return {
        "fingerprint": hash_json(lead["fields"]),
        "provider_values": provider_values,
        "archetype_set": archetype_set,
        "fields": lead["fields"],
    }


def build_world(seed: int, config: dict[str, Any]) -> dict[str, Any]:
    leads, recorder = capture_queue(seed, config)
    assert [r.lead_id for r in recorder.leads] == [ld["lead_id"] for ld in leads]
    return {
        "seed": seed,
        "count": COUNT,
        "difficulty": DIFFICULTY,
        "leads": {
            ld["lead_id"]: provider_entry(ld, record)
            for ld, record in zip(leads, recorder.leads, strict=True)
        },
    }


def render(world: dict[str, Any]) -> str:
    return json.dumps(world, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def world_path(seed: int) -> Path:
    return DATA_DIR / f"world-{seed}.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--check", action="store_true", help="compare with the file; write nothing")
    args = parser.parse_args(argv)
    path = world_path(args.seed)
    text = render(build_world(args.seed, load_config()))
    regenerate = f"run: uv run python tools/capture_world.py --seed {args.seed}"
    if not args.check:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        return 0
    if not path.is_file():
        print(f"{path} is missing; {regenerate}", file=sys.stderr)
        return 1
    actual = path.read_bytes().decode("utf-8")
    if actual == text:
        return 0
    diff = difflib.unified_diff(
        actual.splitlines(keepends=True), text.splitlines(keepends=True), str(path), "captured", n=1
    )
    print(f"{path} differs from the captured world; {regenerate}", file=sys.stderr)
    sys.stderr.writelines(list(diff)[:40])
    return 1


if __name__ == "__main__":
    sys.exit(main())
