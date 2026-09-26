"""Engine tests on graphs small enough to solve by hand."""
import geopandas as gpd
import igraph as ig
import numpy as np
from shapely.geometry import LineString, box

from hazardnet import (Hazard, RoadGraph, accessibility, component_sizes,
                       efficiency_sampled, load_roads, overlay, remove_and_measure)


def toy():
    # community {0,1} -> target {5}
    #   0->2 (100)  1->3 (50)  2->5 (30)  3->5 (80)  2->3 (1000)
    # max-flow: 2->5 carries 30, 3->5 carries 80 -> 110 (unique min cut {2->5, 3->5})
    g = ig.Graph(n=6, directed=True, edges=[(0, 2), (1, 3), (2, 5), (3, 5), (2, 3)])
    g.es["capacity_vph"] = [100, 50, 30, 80, 1000]
    g.es["travel_s"] = [1, 1, 1, 1, 1]
    g.es["hazard_max"] = [0, 0, 0, 3, 0]
    return g


def test_accessibility_by_hand():
    t = accessibility(toy(), {"c": [0, 1]}, [5], hazard="hazard_max", threshold=3,
                      population={"c": 220}).iloc[0]
    assert t.n_disjoint == 2
    assert t.capacity_vph == 110
    assert t.tt_min == 2
    assert np.isclose(t.efficiency, 0.5)             # both vertices 2 s away
    assert np.isclose(t.exposed_share, 80 / 110)
    assert np.isclose(t.people_per_capacity, 2.0)


def test_remove_hazard_edges():
    g = toy()
    rg = RoadGraph(g=g, source="toy")
    mask = np.asarray(g.es["hazard_max"]) >= 3
    r = remove_and_measure(
        rg, lambda h, k: accessibility(h, {"c": [0, 1]}, [5]).iloc[0].to_dict(),
        mask=mask, element="edge")
    assert r["before"]["capacity_vph"] == 110
    assert r["after"]["capacity_vph"] == 30
    assert r["after"]["n_disjoint"] == 1


def test_cut_off_counts_as_zero_efficiency():
    g = ig.Graph(n=3, directed=True, edges=[(0, 1)])
    g.es["travel_s"] = [1]
    t = accessibility(g, {"c": [0]}, [2]).iloc[0]
    assert t.cut_off and t.efficiency == 0 and t.capacity_vph == 0


def test_efficiency_path_graph():
    g = ig.Graph(n=3, edges=[(0, 1), (1, 2)])
    assert np.isclose(efficiency_sampled(g, 3, np.array([0, 1, 2])), 5 / 6)
    # a removed source counts as zero in the estimate
    assert np.isclose(efficiency_sampled(g, 3, np.array([0, -1])), 1.5 / 4)


def test_node_removal_curve_star():
    g = ig.Graph.Star(5)                              # centre 0, leaves 1..4
    rg = RoadGraph(g=g, source="toy")
    df = remove_and_measure(
        rg, lambda h, k: {"s1": component_sizes(h)[0] / 5},
        ranking=np.array([0, 1, 2, 3, 4]), fractions=[0, 0.2], element="node")
    assert list(df.s1) == [1.0, 0.2]


def test_edgelist_dedupes_both_directions(tmp_path):
    p = tmp_path / "e.txt"
    p.write_text("# c\n10\t20\n20\t10\n20\t30\n30\t30\n")
    rg = load_roads(source="edgelist", path=p)
    assert rg.n == 3 and rg.m == 2                    # self-loop dropped


def test_polygon_overlay_share():
    crs = "EPSG:3310"
    edges = gpd.GeoDataFrame(geometry=[LineString([(0, 0), (10, 0)]),
                                       LineString([(0, 50), (10, 50)])], crs=crs)
    g = ig.Graph(n=4, directed=True, edges=[(0, 1), (2, 3)])
    rg = RoadGraph(g=g, source="toy", crs=crs, edges=edges)
    hz = Hazard(kind="polygon", levels={1: "m", 2: "h", 3: "vh"},
                gdf=gpd.GeoDataFrame({"level": [3]}, geometry=[box(-1, -1, 4, 1)], crs=crs))
    overlay(rg, hz, metric_crs=crs)
    assert rg.g.es["hazard_max"] == [3, 0]
    assert np.isclose(rg.g.es["hazard_share_3"][0], 0.4)


def test_clm_selfish_throughput_toy():
    # Self-routed: 0->2->5 and 1->3->5 each carry half; 2->5 (cap 30) jams at
    # D = 60. Re-routing 0's traffic via 2->3->5 overloads 3->5 instead, so the
    # system cannot settle above ~60, although max-flow is 110.
    from hazardnet.clm import selfish_throughput
    r = selfish_throughput(toy(), {0: 1.0, 1: 1.0}, [5], managed=100)
    assert abs(r["D_strict"] - 60) <= 1.2
    # rationed: origin 0 is held to 30 by 2->5; origin 1 to 50 by 1->3 -> 80
    assert abs(r["rationed"] - 80) <= 1.2


def test_clm_managed_throughput_toy():
    # Each origin must send D/2: 1->3 (cap 50) binds at D = 100, below the
    # unrestricted max-flow of 110 - the like-for-like bound for D* = 60.
    from hazardnet.clm import managed_throughput
    D, binding = managed_throughput(toy(), {0: 1.0, 1: 1.0}, [5], upper=110)
    assert abs(D - 100) <= 1.2
    assert 1 in binding                     # arc 1->3 (cap 50) is what binds


def test_contraflow_and_widen_toy():
    # add 5->2 (cap 30) so 2->5 can take its lanes under contraflow
    from hazardnet.clm import managed_throughput
    from hazardnet.interventions import contraflow, managed_flow, widen
    g = toy()
    g.add_edges([(5, 2)]); g.es[5]["capacity_vph"] = 30; g.es[5]["travel_s"] = 1
    g.es[5]["hazard_max"] = 0
    g.es["length_m"] = [100.0] * g.ecount()
    h, metres = contraflow(g, [2])                     # 2->5 gains 5->2's 30
    assert h.es[2]["capacity_vph"] == 60 and h.es[5]["capacity_vph"] == 0 and metres == 100
    # widening 1->3 (the managed bottleneck, 50) by 50 lifts the fixed-split bound
    D0, _ = managed_throughput(g, {0: 1.0, 1: 1.0}, [5], upper=200)
    D1, _ = managed_throughput(widen(g, 1, 50), {0: 1.0, 1: 1.0}, [5], upper=200)
    assert D1 > D0 + 5
    f = managed_flow(g, {0: 1.0, 1: 1.0}, [5], D0)
    assert abs(f[0] + f[1] - D0) < 1e-6                # all demand leaves the origins


def test_contract_degree2():
    # junction 0 -- 1 -- 2 -- 3 junction (1, 2 are shape points), plus
    # 0-4, 0-5, 3-6, 3-7 so 0 and 3 are real junctions (degree 3)
    from hazardnet import contract_degree2
    g = ig.Graph(n=8, edges=[(0, 1), (1, 2), (2, 3), (0, 4), (0, 5), (3, 6), (3, 7)])
    c = contract_degree2(RoadGraph(g=g, source="toy")).g
    assert c.vcount() == 6 and c.ecount() == 5            # chain 1-2 became edge 0-3
    orig = c.vs["orig_index"]
    assert c.are_adjacent(orig.index(0), orig.index(3))
