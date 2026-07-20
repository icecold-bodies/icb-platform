"""v1.43 — unit tests for scripts.add_no_rear_doors_option.add_no_rear_doors.

The pure draft mutation that gives explosive bodies their "NO REAR DOORS
(SIDE DOORS ONLY)" radio: locates the door group STRUCTURALLY (the common
parent of DRD- and SRD-labelled radio folders), appends a childless radio
folder, and is additive + idempotent. No DB access.
"""
import copy

from scripts.add_no_rear_doors_option import NRD_LABEL, add_no_rear_doors


def _draft():
    return {
        "rootIds": ["1"],
        "nodes": {
            "1": {"type": "folder", "label": "DOOR TYPE", "childIds": ["node-23", "node-24"]},
            "node-23": {"type": "folder", "label": "DRD DOORS", "folderMode": "radio",
                        "parentId": "1", "childIds": ["c1"]},
            "node-24": {"type": "folder", "label": "SRD DOORS", "folderMode": "radio",
                        "parentId": "1", "childIds": ["c2"]},
            "c1": {"type": "category", "sourceCategoryKey": "DRD", "parentId": "node-23"},
            "c2": {"type": "category", "sourceCategoryKey": "SRD", "parentId": "node-24"},
        },
    }


def test_adds_childless_radio_folder_to_door_group():
    d = _draft()
    changed, reason = add_no_rear_doors(d, node_id="node-nrd-1")
    assert changed, reason
    n = d["nodes"]["node-nrd-1"]
    assert n == {"type": "folder", "label": NRD_LABEL, "folderMode": "radio",
                 "parentId": "1", "childIds": []}
    assert d["nodes"]["1"]["childIds"][-1] == "node-nrd-1"


def test_idempotent_second_run_skips():
    d = _draft()
    assert add_no_rear_doors(d, node_id="node-nrd-1")[0] is True
    snapshot = copy.deepcopy(d)
    changed, reason = add_no_rear_doors(d, node_id="node-nrd-1b")
    assert changed is False
    assert "already present" in reason
    assert d == snapshot


def test_no_door_group_skips():
    d = {"rootIds": [], "nodes": {"x": {"type": "folder", "label": "FLOOR TYPE",
                                        "folderMode": "radio", "parentId": None}}}
    changed, reason = add_no_rear_doors(d, node_id="n")
    assert changed is False and "no DRD+SRD" in reason


def test_ambiguous_door_groups_skip():
    d = _draft()
    # A second DRD/SRD radio pair under a different parent → ambiguous.
    d["nodes"]["2"] = {"type": "folder", "label": "OTHER", "childIds": ["a", "b"]}
    d["nodes"]["a"] = {"type": "folder", "label": "DRD ALT", "folderMode": "radio", "parentId": "2"}
    d["nodes"]["b"] = {"type": "folder", "label": "SRD ALT", "folderMode": "radio", "parentId": "2"}
    changed, reason = add_no_rear_doors(d, node_id="n")
    assert changed is False and "ambiguous" in reason


def test_node_id_collision_skips():
    d = _draft()
    d["nodes"]["node-nrd-1"] = {"type": "flag", "label": "X"}
    # Structural search still finds the group, but the id is taken.
    changed, reason = add_no_rear_doors(d, node_id="node-nrd-1")
    assert changed is False and "already taken" in reason
