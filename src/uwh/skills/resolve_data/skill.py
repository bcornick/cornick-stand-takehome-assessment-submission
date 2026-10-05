# ABOUTME: The resolve_data skill (9.3, 9.4): each provider lookup the runtime made becomes a fetched fact, a stated default tagged assumed, or nothing while the lookup is blocked.
# ABOUTME: Deterministic. Derived fields are recomputed by the ledger when their input changes (7.3 rule 5), so no derivation runs here.
from typing import Literal

from pydantic import JsonValue

from uwh.providers.models import ProviderResult
from uwh.rules.models import NotBuilt, StrictModel

# 9.3 step 4: the value taken when the provider does not find the field.
ASSUMED_WHEN_NOT_FOUND: dict[str, JsonValue] = {"protection_class": "9"}


class ResolveDataInput(StrictModel):
    provider_results: dict[str, ProviderResult]  # field -> the lookup the runtime made


class ResolvedFact(StrictModel):
    key: str
    value: JsonValue
    source: Literal["fetched", "assumed"]
    evidence: dict[str, JsonValue]  # the provider, or the default's reason


class ResolveDataOutput(StrictModel):
    facts: list[ResolvedFact]


def run(input: ResolveDataInput) -> ResolveDataOutput:
    """A blocked lookup yields no fact: its missing inputs are asks of their own. Raises NotBuilt for an
    answer the build does not handle and ValueError for an unavailable provider."""
    facts: list[ResolvedFact] = []
    for key, result in input.provider_results.items():
        if result.status == "found":
            facts.append(
                ResolvedFact(
                    key=key,
                    value=result.value,
                    source="fetched",
                    evidence={"provider": result.source},
                )
            )
        elif result.status == "not_found" and key in ASSUMED_WHEN_NOT_FOUND:
            facts.append(
                ResolvedFact(
                    key=key,
                    value=ASSUMED_WHEN_NOT_FOUND[key],
                    source="assumed",
                    evidence={"default": f"{result.source} did not find {key}"},
                )
            )
        elif result.status == "not_found":
            raise NotBuilt(
                f"{result.source} did not find {key}; the review that answers is not built"
            )
        elif result.status == "unavailable":
            raise ValueError(f"the {result.source} provider is unavailable for {key}")
    return ResolveDataOutput(facts=facts)
