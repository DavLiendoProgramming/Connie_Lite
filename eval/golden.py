"""Hand-written golden items: the 6 demo turns (one conversation) and 4 unanswerable questions."""
from __future__ import annotations

from dataclasses import dataclass, field

from connie_lite.graph.ingest import FOCAL_ID
from connie_lite.schema import PROFILE_SOURCE

Edge = tuple[str, str, str]


@dataclass
class GoldenItem:
    id: str
    question: str
    answerable: bool
    expected_edges: set[Edge] = field(default_factory=set)
    expected_sources: set[str] = field(default_factory=set)   # alert ids (+ PROFILE) that should back the answer
    multi_hop: bool = False
    conversation: str | None = None                           # items sharing a value run in one session, in order
    must_contain: list[str] = field(default_factory=list)


F = FOCAL_ID
HAND_ITEMS = [
    GoldenItem("demo1", "Which of Solstice's suppliers carry commodity risk, and which commodity?", True,
               {(F, "HAS_SUPPLIER", "company:ferrotech-alloys"), ("company:ferrotech-alloys", "EXPOSED_TO", "commodity:rare-earth-magnets")},
               {"a09", PROFILE_SOURCE}, multi_hop=True, conversation="demo", must_contain=["Ferrotech Alloys", "rare earth magnets"]),
    GoldenItem("demo2", "And what about their exposure to tariffs?", False, expected_sources={"a09"},
               conversation="demo", must_contain=["Not found:"]),
    GoldenItem("demo3", "Are any of Solstice's competitors pushing into the same end markets as its customers?", True,
               {(F, "COMPETES_WITH", "company:kestrel-automation"), ("company:kestrel-automation", "OPERATES_IN", "market:warehouse-automation"),
                ("company:northline-logistics", "OPERATES_IN", "market:warehouse-automation"), (F, "HAS_CUSTOMER", "company:northline-logistics"),
                ("company:bayview-fulfillment", "OPERATES_IN", "market:warehouse-automation"), (F, "HAS_CUSTOMER", "company:bayview-fulfillment"),
                ("company:orion-freight-systems", "OPERATES_IN", "market:warehouse-automation"), (F, "HAS_CUSTOMER", "company:orion-freight-systems")},
               {"a05", "a04", "a12", "a22"}, multi_hop=True, conversation="demo",
               must_contain=["Kestrel Automation", "warehouse automation"]),
    GoldenItem("demo4", "Does Solstice have any supplier or customer relationships that aren't in its profile?", True,
               {(F, "HAS_SUPPLIER", "company:hanley-precision-casting"), (F, "HAS_CUSTOMER", "company:orion-freight-systems")},
               {"a21", "a22"}, conversation="demo", must_contain=["Hanley Precision Casting", "Orion Freight Systems", "newly discovered"]),
    GoldenItem("demo5", "Could new export controls hit Solstice's supply chain?", True,
               {(F, "HAS_SUPPLIER", "company:delta-servo-corp"), ("company:delta-servo-corp", "PRESENT_IN", "country:south-korea"),
                ("regulator:us-department-of-commerce", "AFFECTS", "country:south-korea")},
               {"a10", "a13", PROFILE_SOURCE}, multi_hop=True, conversation="demo",
               must_contain=["Delta Servo Corp", "South Korea"]),
    GoldenItem("demo6", "Who is Solstice's CEO?", False, expected_sources={"a02"}, conversation="demo", must_contain=["Not found:"]),
    GoldenItem("unans1", "What is Solstice's market share in Japan?", False, must_contain=["Not found:"]),
    GoldenItem("unans2", "Which supplier makes Solstice's batteries?", False, must_contain=["Not found:"]),
    GoldenItem("unans3", "What is Kestrel Automation's exposure to interest rates?", False, must_contain=["Not found:"]),
    GoldenItem("unans4", "Who is Ferrotech Alloys' CEO?", False, must_contain=["Not found:"]),
]
