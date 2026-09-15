#!/usr/bin/env python3
"""Deterministic publication gate for a fully researched new-game content package.

This module makes no network/API calls. It validates an already prepared package
before V30 is allowed to add a new game. Discovery queries or AI prose alone are
never enough: research lanes must record completion, factual guide text must point
to concrete source records, progress identities must be deduplicated, and an image
with explicit provenance/rights plus a guide HTML file must be present before final
publication. The same validator can be used in pre-render mode to create that HTML.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIR = ROOT / "data" / "new_game_content_packages"
REQUIRED_CHANNELS = ("web", "x", "youtube", "instagram", "pointSites")
ALLOWED_IMAGE_PROVENANCE = {"generated", "official_permitted", "licensed", "user_supplied"}


class ContentHold(ValueError):
    pass


def norm(value):
    return re.sub(r"\s+", "", str(value or "")).casefold()


def safe_slug(value):
    raw = str(value or "").strip().casefold()
    ascii_slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    if ascii_slug:
        return ascii_slug[:80]
    import hashlib
    return "game-" + hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:12]


def safe_https(url):
    try:
        p = urlparse(str(url or "").strip())
    except Exception:
        return False
    return p.scheme == "https" and bool(p.hostname) and p.username is None and p.password is None


def _relative_public_path(value, prefix):
    raw = str(value or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/") or ".." in Path(raw).parts:
        return ""
    if not raw.startswith(prefix):
        return ""
    return raw


def package_path(game, content_dir=CONTENT_DIR):
    directory = Path(content_dir)
    preferred = directory / f"{safe_slug(game)}.json"
    if preferred.exists():
        return preferred
    if directory.exists():
        for path in sorted(directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if norm(payload.get("game")) == norm(game):
                return path
    return preferred


def load_for_game(game, content_dir=CONTENT_DIR):
    path = package_path(game, content_dir)
    if not path.exists():
        raise ContentHold("content_package_missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ContentHold("content_package_invalid_json") from exc
    return payload, path


def validate(payload, game, root=ROOT, require_guide_file=True):
    if not isinstance(payload, dict) or payload.get("schemaVersion") != 1:
        raise ContentHold("content_package_schema_invalid")
    if norm(payload.get("game")) != norm(game):
        raise ContentHold("content_package_game_mismatch")
    if payload.get("publicationReady") is not True:
        raise ContentHold("content_package_not_ready")

    research = payload.get("research")
    if not isinstance(research, dict):
        raise ContentHold("research_missing")
    source_ids = set()
    all_sources = {}
    for channel in REQUIRED_CHANNELS:
        lane = research.get(channel)
        if not isinstance(lane, dict) or lane.get("searched") is not True or lane.get("complete") is not True:
            raise ContentHold(f"research_channel_incomplete:{channel}")
        sources = lane.get("sources")
        if not isinstance(sources, list):
            raise ContentHold(f"research_sources_invalid:{channel}")
        for index, source in enumerate(sources):
            if not isinstance(source, dict):
                raise ContentHold(f"research_source_invalid:{channel}")
            source_id = str(source.get("id") or f"{channel}:{index}").strip()
            url = str(source.get("url") or "").strip()
            if not source_id or source_id in source_ids or not safe_https(url):
                raise ContentHold(f"research_source_identity_invalid:{channel}")
            source_ids.add(source_id)
            all_sources[source_id] = source
    factual = [s for s in all_sources.values() if str(s.get("claim") or "").strip() and safe_https(s.get("url"))]
    if len(factual) < 2:
        raise ContentHold("insufficient_factual_research")

    guide = payload.get("guide")
    if not isinstance(guide, dict):
        raise ContentHold("guide_missing")
    for key in ("title", "intro", "overview", "tips"):
        if len(str(guide.get(key) or "").strip()) < 8:
            raise ContentHold(f"guide_field_missing:{key}")
    sections = guide.get("sections")
    if not isinstance(sections, list) or len(sections) < 3:
        raise ContentHold("guide_sections_incomplete")
    used_refs = set()
    for section in sections:
        if not isinstance(section, dict) or len(str(section.get("heading") or "").strip()) < 2:
            raise ContentHold("guide_section_invalid")
        text = str(section.get("text") or "").strip()
        refs = section.get("sourceRefs")
        if len(text) < 20 or not isinstance(refs, list) or not refs:
            raise ContentHold("guide_section_evidence_missing")
        if any(ref not in all_sources for ref in refs):
            raise ContentHold("guide_section_unknown_source")
        used_refs.update(refs)
    if len(used_refs) < 2:
        raise ContentHold("guide_source_diversity_insufficient")

    progress = payload.get("progress")
    if not isinstance(progress, list) or not progress:
        raise ContentHold("progress_missing")
    identities = set()
    for row in progress:
        if not isinstance(row, dict):
            raise ContentHold("progress_invalid")
        identity = str(row.get("identityKey") or "").strip().casefold()
        source_ref = str(row.get("sourceRef") or "").strip()
        summary = str(row.get("summary") or "").strip()
        if not identity or identity in identities:
            raise ContentHold("progress_identity_duplicate_or_missing")
        if source_ref not in all_sources or len(summary) < 8:
            raise ContentHold("progress_evidence_invalid")
        identities.add(identity)

    image = payload.get("image")
    if not isinstance(image, dict) or image.get("rightsConfirmed") is not True:
        raise ContentHold("image_rights_unconfirmed")
    if image.get("provenance") not in ALLOWED_IMAGE_PROVENANCE:
        raise ContentHold("image_provenance_invalid")
    image_path = _relative_public_path(image.get("path"), "assets/game-art/")
    if not image_path or not (Path(root) / image_path).is_file():
        raise ContentHold("image_file_missing")

    guide_path = str(payload.get("guidePath") or "").strip().replace("\\", "/")
    if (not guide_path or guide_path.startswith("/") or ".." in Path(guide_path).parts
            or not guide_path.endswith("-guide.html") or "/" in guide_path):
        raise ContentHold("guide_path_invalid")
    if require_guide_file and not (Path(root) / guide_path).is_file():
        raise ContentHold("guide_html_missing")

    days = str(payload.get("days") or "").strip()
    difficulty = str(payload.get("difficulty") or "").strip()
    if not days or days == "調査中" or not difficulty or difficulty == "調査中":
        raise ContentHold("catalog_fields_incomplete")

    return {
        "game": str(payload.get("game") or "").strip(),
        "image": image_path,
        "guidePath": guide_path,
        "overview": str(guide["overview"]).strip(),
        "tips": str(guide["tips"]).strip(),
        "days": days,
        "difficulty": difficulty,
        "sourceCount": len(all_sources),
        "progressCount": len(progress),
    }


def validate_for_game(game, content_dir=CONTENT_DIR, root=ROOT, require_guide_file=True):
    payload, path = load_for_game(game, content_dir)
    result = validate(payload, game, root=root, require_guide_file=require_guide_file)
    result["packagePath"] = str(path)
    return result
