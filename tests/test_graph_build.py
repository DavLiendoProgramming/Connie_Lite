import pytest

FOCAL = "company:solstice-robotics"


def provenance(edge):
    return {(s.source, s.provenance) for s in edge.supports}


def test_ferrotech_supplier_confirmed(store):
    e = store.edge(FOCAL, "HAS_SUPPLIER", "company:ferrotech-alloys")
    assert e is not None
    assert provenance(e) == {("PROFILE", "profile"), ("a09", "annotation")}
    assert e.status == "confirmed"
    assert e.annotation_only


def test_ferrotech_rare_earth(store):
    e = store.edge("company:ferrotech-alloys", "EXPOSED_TO", "commodity:rare-earth-magnets")
    assert provenance(e) == {("a09", "co_mention")}


@pytest.mark.parametrize(
    "rel,dst,source",
    [("HAS_SUPPLIER", "company:hanley-precision-casting", "a21"), ("HAS_CUSTOMER", "company:orion-freight-systems", "a22")],
)
def test_discovered_relationships(store, rel, dst, source):
    e = store.edge(FOCAL, rel, dst)
    assert provenance(e) == {(source, "text")}
    assert e.status == "discovered"


@pytest.mark.parametrize(
    "src,rel,dst,source",
    [
        ("company:kestrel-automation", "OPERATES_IN", "market:warehouse-automation", "a05"),
        ("company:delta-servo-corp", "PRESENT_IN", "country:south-korea", "a10"),
        ("regulator:us-department-of-commerce", "AFFECTS", "country:south-korea", "a13"),
        ("company:hanley-precision-casting", "PRESENT_IN", "country:vietnam", "a21"),
    ],
)
def test_co_mention_edges(store, src, rel, dst, source):
    e = store.edge(src, rel, dst)
    assert e is not None, f"missing {src} {rel} {dst}"
    assert source in e.sources


def test_segment_not_company(store):
    assert not store.has_node("company:e-commerce-fulfillment-customers")
    assert store.has_node("segment:e-commerce-fulfillment-customers")
    # segments get no relation edges, only MENTIONS
    assert [e.rel for e in store.semantic_edges("segment:e-commerce-fulfillment-customers")] == []


def test_northline_text_provenance(store):
    e = store.edge(FOCAL, "HAS_CUSTOMER", "company:northline-logistics")
    assert ("a04", "text") in provenance(e)


def test_site_and_executive(store):
    assert store.edge(FOCAL, "HAS_SITE", "site:monterrey-mexico") is not None
    assert store.edge("site:monterrey-mexico", "LOCATED_IN", "country:mexico") is not None
    e = store.edge(FOCAL, "HAS_EXECUTIVE", "person:elena-marsh")
    assert e.attrs["role"] == "CFO"


def test_theme_related(store):
    assert store.edge("theme:reshoring", "RELATED_TO", "theme:tariffs") is not None


def test_mentions_not_in_traversal(store):
    rels = {e.rel for path in store.walk("company:ferrotech-alloys", 2, set()) for e in path}
    assert "MENTIONS" not in rels


def test_walk_does_not_pass_through_hub(store):
    paths = store.walk("company:ferrotech-alloys", 2, {FOCAL})
    assert any(p[-1].src == FOCAL for p in paths)                      # the supplier edge itself is kept
    assert not any(len(p) == 2 and FOCAL in (p[0].src, p[0].dst) for p in paths)  # nothing beyond the client
