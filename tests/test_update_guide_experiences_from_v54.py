import copy
import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "update_guide_experiences_from_v54.py"
SPEC = importlib.util.spec_from_file_location("guide_update", MODULE_PATH)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def live(players=None):
    return {
        "schemaVersion": 1,
        "game": "きのこ伝説",
        "updatedAt": "2026-09-01",
        "players": players or [],
    }


def obs(identity, url, pairs, origin="direct_x_post", status="anecdotal_quarantine"):
    return {
        "game": "きのこ伝説",
        "sourceIdentity": identity,
        "url": url,
        "origin": origin,
        "status": status,
        "signals": {
            "progressPairs": [{"day": d, "level": lv} for d, lv in pairs]
        },
    }


def v54(rows):
    return {
        "phase": "PHASE4_POI_GUIDE_EXPERIENCE_V54",
        "generatedAt": "2026-09-02T00:00:00+00:00",
        "observations": rows,
    }


def player_d():
    return {
        "id": "D",
        "label": "プレイヤーD",
        "status": "completed",
        "summary": "37日目でLv119 / 120",
        "milestones": [{"day": 2, "level": 57, "label": "Lv57"}],
        "note": "editorial note",
        "sources": ["https://x.com/nyanreimama/status/111"],
    }


class GuideExperienceUpdateTests(unittest.TestCase):
    def test_existing_x_player_merges_progress_without_overwriting_editorial_fields(self):
        before = player_d()
        doc, diag = mod.merge_game_document(
            live([copy.deepcopy(before)]),
            v54([obs("x:nyanreimama", "https://x.com/nyanreimama/status/222", [(5, 70)])]),
        )
        p = doc["players"][0]
        self.assertEqual(p["status"], before["status"])
        self.assertEqual(p["summary"], before["summary"])
        self.assertEqual(p["note"], before["note"])
        self.assertEqual([(m["day"], m["level"]) for m in p["milestones"]], [(2, 57), (5, 70)])
        self.assertEqual(p["sourceIdentity"], "x:nyanreimama")
        self.assertEqual(diag["matchedPlayers"], 1)
        self.assertEqual(diag["addedMilestones"], 1)

    def test_same_progress_is_idempotent(self):
        row = obs("x:nyanreimama", "https://x.com/nyanreimama/status/222", [(2, 57)])
        first, _ = mod.merge_game_document(live([player_d()]), v54([row]))
        second, diag = mod.merge_game_document(first, v54([row]))
        self.assertEqual(len(second["players"]), 1)
        self.assertEqual(len(second["players"][0]["milestones"]), 1)
        self.assertEqual(diag["addedMilestones"], 0)
        self.assertEqual(diag["newPlayers"], 0)

    def test_new_x_identity_becomes_next_candidate_player(self):
        players = []
        for letter in "ABCDEFGH":
            players.append({
                "id": letter,
                "label": f"プレイヤー{letter}",
                "status": "ongoing",
                "summary": "existing",
                "milestones": [],
                "sources": [],
            })
        doc, diag = mod.merge_game_document(
            live(players),
            v54([obs("x:newperson", "https://x.com/newperson/status/333", [(4, 44), (7, 61)])]),
        )
        p = doc["players"][-1]
        self.assertEqual(p["id"], "I")
        self.assertEqual(p["label"], "プレイヤーI")
        self.assertEqual(p["status"], "ongoing")
        self.assertEqual(p["summary"], "7日目でLv61")
        self.assertEqual(p["reviewStatus"], "new_candidate")
        self.assertEqual(diag["newPlayers"], 1)

    def test_post_without_explicit_day_level_pair_is_ignored(self):
        row = obs("x:someone", "https://x.com/someone/status/1", [])
        doc, diag = mod.merge_game_document(live([]), v54([row]))
        self.assertEqual(doc["players"], [])
        self.assertEqual(diag["noProgressPair"], 1)

    def test_non_direct_x_rows_are_ignored(self):
        row = obs(
            "x:someone",
            "https://x.com/someone/status/1",
            [(3, 50)],
            origin="held_single_source_claim",
        )
        doc, diag = mod.merge_game_document(live([]), v54([row]))
        self.assertEqual(doc["players"], [])
        self.assertEqual(diag["ignoredNonDirectX"], 1)

    def test_identity_mismatch_fails_closed(self):
        row = obs("x:alice", "https://x.com/bob/status/1", [(3, 50)])
        doc, diag = mod.merge_game_document(live([]), v54([row]))
        self.assertEqual(doc["players"], [])
        self.assertEqual(diag["identityMismatch"], 1)

    def test_multiple_observations_same_account_merge_into_one_new_player(self):
        rows = [
            obs("x:alice", "https://x.com/alice/status/1", [(2, 40)]),
            obs("x:alice", "https://x.com/alice/status/2", [(5, 65)]),
        ]
        doc, diag = mod.merge_game_document(live([]), v54(rows))
        self.assertEqual(len(doc["players"]), 1)
        self.assertEqual(
            [(m["day"], m["level"]) for m in doc["players"][0]["milestones"]],
            [(2, 40), (5, 65)],
        )
        self.assertEqual(len(doc["players"][0]["sources"]), 2)
        self.assertEqual(diag["newPlayers"], 1)

    def test_duplicate_live_x_identity_is_rejected(self):
        p1 = player_d()
        p2 = copy.deepcopy(p1)
        p2["id"] = "E"
        with self.assertRaisesRegex(ValueError, "duplicate X identity"):
            mod.merge_game_document(live([p1, p2]), v54([]))


if __name__ == "__main__":
    unittest.main()
