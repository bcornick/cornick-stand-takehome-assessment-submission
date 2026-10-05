# ABOUTME: The Registration a vertical fills in and the runtime reads: its names for statuses, blocker kinds, owners, item kinds, message kinds and observation sources.
# ABOUTME: It also names the role each runtime-opened blocker, assigned owner, created item and human ruling plays, so the runtime holds no vertical vocabulary (section 7).
from dataclasses import dataclass


@dataclass(frozen=True)
class Registration:
    """Plain data. The runtime refers to a role by its field name here, never by a literal.

    Each role name is a member of the tuple beside it: the three blocker kinds the runtime opens
    itself, the two blocker owners it assigns, the four item kinds it creates and the observation
    source of a human ruling.
    """

    statuses: tuple[str, ...]
    terminal_statuses: tuple[str, ...]
    transitions: tuple[tuple[str, str], ...]  # allowed (from, to) status pairs
    blocker_kinds_by_priority: tuple[str, ...]  # highest priority first
    blocker_owners: tuple[str, ...]
    message_kinds: tuple[str, ...]  # the intent kinds
    item_kinds: tuple[str, ...]  # the approvals item kinds
    observation_sources: tuple[str, ...]

    delivery_unknown_kind: str  # blocker kinds the runtime opens itself
    human_review_kind: str
    data_kind: str
    human_owner: str  # blocker owners the runtime assigns
    data_owner: str
    draft_item_kind: str  # item kinds the runtime creates
    observation_item_kind: str
    delivery_unknown_item_kind: str
    review_item_kind: str
    human_source: str  # the observation source of a human ruling

    def __post_init__(self) -> None:
        for name in (
            "statuses",
            "blocker_kinds_by_priority",
            "blocker_owners",
            "message_kinds",
            "item_kinds",
            "observation_sources",
        ):
            names: tuple[str, ...] = getattr(self, name)
            if len(set(names)) != len(names):
                raise ValueError(f"{name} holds a repeated name")
        for role, names_field in _ROLE_SETS.items():
            if getattr(self, role) not in getattr(self, names_field):
                raise ValueError(f"{role} is not in {names_field}")
        for status in self.terminal_statuses:
            if status not in self.statuses:
                raise ValueError(f"terminal_statuses names {status!r}, which is not in statuses")
        for pair in self.transitions:
            for status in pair:
                if status not in self.statuses:
                    raise ValueError(f"transitions names {status!r}, which is not in statuses")


# Role field -> the tuple field its name belongs to.
_ROLE_SETS = {
    "delivery_unknown_kind": "blocker_kinds_by_priority",
    "human_review_kind": "blocker_kinds_by_priority",
    "data_kind": "blocker_kinds_by_priority",
    "human_owner": "blocker_owners",
    "data_owner": "blocker_owners",
    "draft_item_kind": "item_kinds",
    "observation_item_kind": "item_kinds",
    "delivery_unknown_item_kind": "item_kinds",
    "review_item_kind": "item_kinds",
    "human_source": "observation_sources",
}
