from __future__ import annotations

import contextlib
import io
import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


DEFAULT_BEATS = 8
DEFAULT_EDO = 12
DEFAULT_GROOVE = "straight"
DEFAULT_METER = "4/4"
DEFAULT_SEED = 42
DEFAULT_TEMPO_BPM = 120.0


def _mettaclaw_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _candidate_music_roots() -> list[Path]:
    roots = []
    env_root = os.environ.get("MUSIC_GENERATION_ROOT")
    if env_root:
        roots.append(Path(env_root))

    mettaclaw_root = _mettaclaw_root()
    roots.extend(
        [
            mettaclaw_root.parent / "musicGeneration",
            mettaclaw_root / "musicGeneration",
            mettaclaw_root / "repos" / "musicGeneration",
            Path.home() / "Desktop" / "musicGeneration",
        ]
    )
    return roots


def _music_root() -> Path:
    for root in _candidate_music_roots():
        if (root / "aimusic").is_dir():
            return root.resolve()
    candidates = ", ".join(str(path) for path in _candidate_music_roots())
    raise FileNotFoundError(
        "Could not find the musicGeneration project. Set MUSIC_GENERATION_ROOT "
        f"to its folder. Tried: {candidates}"
    )


def _site_package_dirs(root: Path) -> list[Path]:
    dirs = [root / "venv" / "Lib" / "site-packages"]
    dirs.extend((root / "venv" / "lib").glob("python*/site-packages"))
    return [path for path in dirs if path.is_dir()]


def _ensure_music_imports() -> Path:
    root = _music_root()
    paths = [root, *_site_package_dirs(root)]
    for path in reversed(paths):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
    return root


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"1", "yes", "true", "on", "sample", "sampled"}


def _ascii_safe(text: str) -> str:
    replacements = {
        "\U0001f7e2": "OK",
        "\U0001f534": "FAILED",
        "\u2588": "#",
        "\xf6": "o",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.encode("ascii", errors="backslashreplace").decode("ascii")


def _coerce_value(value: str) -> Any:
    lowered = value.strip().lower()
    if lowered in {"true", "false", "yes", "no", "on", "off"}:
        return _parse_bool(lowered)
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value.strip()


def _parse_spec(spec: str | None) -> dict[str, Any]:
    text = "" if spec is None else str(spec).strip()
    if not text:
        return {}

    if text.startswith("{"):
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("music generation JSON spec must be an object.")
        return data

    options: dict[str, Any] = {}
    for key, value in re.findall(r"([A-Za-z_][A-Za-z0-9_-]*)\s*=\s*([^\s]+)", text):
        options[key.replace("-", "_").lower()] = _coerce_value(value)

    normalized = text.lower()
    keyword_patterns = {
        "beats": r"\bbeats?\s*:?\s*(\d+)",
        "seed": r"\bseed\s*:?\s*(\d+)",
        "edo": r"\bedo\s*:?\s*(\d+)|(\d+)\s*-\s*edo",
        "tempo_bpm": r"\b(?:tempo|bpm|tempo_bpm)\s*:?\s*(\d+(?:\.\d+)?)",
        "meter": r"\bmeter\s*:?\s*(\d+/\d+)|\b(\d+/\d+)\b",
    }
    for key, pattern in keyword_patterns.items():
        match = re.search(pattern, normalized)
        if match:
            value = next(group for group in match.groups() if group is not None)
            options.setdefault(key, _coerce_value(value))

    for groove in ("straight", "syncopated", "swing"):
        if groove in normalized:
            options.setdefault("groove_family", groove)

    if "sample" in normalized or "sampling" in normalized:
        options.setdefault("sample_path", True)

    return options


def _output_dir(value: Any) -> Path:
    if value is None or str(value).strip() == "":
        return _mettaclaw_root() / "music_outputs"
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = _mettaclaw_root() / path
    return path


def _generate_args(options: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        seed=int(options.get("seed", DEFAULT_SEED)),
        beats=int(options.get("beats", options.get("total_beats", DEFAULT_BEATS))),
        edo=int(options.get("edo", DEFAULT_EDO)),
        meter=str(options.get("meter", DEFAULT_METER)),
        groove_family=str(options.get("groove_family", options.get("groove", DEFAULT_GROOVE))),
        tempo_bpm=float(options.get("tempo_bpm", options.get("tempo", DEFAULT_TEMPO_BPM))),
        sample_path=_parse_bool(options.get("sample_path", options.get("sample", False))),
        subbeats_per_beat=int(options.get("subbeats_per_beat", 4)),
        drum_density=float(options.get("drum_density", 0.75)),
        bass_density=float(options.get("bass_density", 0.60)),
        comping_density=float(options.get("comping_density", 0.55)),
        lead_density=float(options.get("lead_density", 0.45)),
        base_tuning=int(options.get("base_tuning", 0)),
        pitch_bend_range=int(options.get("pitch_bend_range", 2)),
        rendering_method=str(options.get("rendering_method", "MPE")),
        track_program=[],
        drum_track=[],
        out=str(_output_dir(options.get("out", options.get("output", None)))),
    )


def _latest_manifest(output_dir: Path) -> Path | None:
    manifests = sorted(
        output_dir.glob("*_manifest.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return manifests[0] if manifests else None


def _latest_file(output_dir: Path, pattern: str) -> Path | None:
    files = sorted(
        output_dir.glob(pattern),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _state_from_dict(data: dict[str, Any]):
    from aimusic.core.core_types import BeatState

    return BeatState(
        meter_id=int(data["meter_id"]),
        beat_in_bar=int(data["beat_in_bar"]),
        boundary_lvl=int(data["boundary_lvl"]),
        key_id=int(data["key_id"]),
        chord_id=int(data["chord_id"]),
        role_id=int(data["role_id"]),
        head_id=int(data["head_id"]),
        groove_id=int(data["groove_id"]),
    )


def _state_from_spec_value(value: Any):
    if isinstance(value, dict):
        return _state_from_dict(value)
    parts = [int(part.strip()) for part in str(value).split(",") if part.strip()]
    if len(parts) != 8:
        raise ValueError("BeatState values must have 8 comma-separated integers.")
    return _state_from_dict(
        {
            "meter_id": parts[0],
            "beat_in_bar": parts[1],
            "boundary_lvl": parts[2],
            "key_id": parts[3],
            "chord_id": parts[4],
            "role_id": parts[5],
            "head_id": parts[6],
            "groove_id": parts[7],
        }
    )


def _score_from_dict(data: dict[str, Any]):
    from aimusic.core.core_types import NoteEvent, Score

    events = []
    for event in data.get("note_events", ()):
        events.append(
            NoteEvent(
                ton=int(event["ton"]),
                toff=int(event["toff"]),
                h=int(event["h"]),
                v=float(event["v"]),
                e=tuple(float(item) for item in event.get("e", ())),
                track=str(event.get("track", "default")),
            )
        )
    return Score(
        note_events=tuple(events),
        ticks_per_beat=int(data.get("ticks_per_beat", 480)),
        tempo_bpm=float(data.get("tempo_bpm", DEFAULT_TEMPO_BPM)),
    )


def _path_artifact_from_options(options: dict[str, Any]) -> Path:
    explicit = options.get("path", options.get("plan", None))
    if explicit:
        path = Path(str(explicit)).expanduser()
        return path if path.is_absolute() else _mettaclaw_root() / path
    out_dir = _output_dir(options.get("out", options.get("output", None)))
    latest = _latest_file(out_dir, "*_path.json")
    if latest is None:
        raise FileNotFoundError(f"No *_path.json artifact found in {out_dir}.")
    return latest


def _score_artifact_from_options(options: dict[str, Any]) -> Path:
    explicit = options.get("score", options.get("file", None))
    if explicit:
        path = Path(str(explicit)).expanduser()
        return path if path.is_absolute() else _mettaclaw_root() / path
    out_dir = _output_dir(options.get("out", options.get("output", None)))
    latest = _latest_file(out_dir, "*_score.json")
    if latest is None:
        raise FileNotFoundError(f"No *_score.json artifact found in {out_dir}.")
    return latest


def _midi_artifact_from_options(options: dict[str, Any]) -> Path:
    explicit = options.get("midi", options.get("file", None))
    if explicit:
        path = Path(str(explicit)).expanduser()
        return path if path.is_absolute() else _mettaclaw_root() / path
    out_dir = _output_dir(options.get("out", options.get("output", None)))
    latest = _latest_file(out_dir, "*.mid")
    if latest is None:
        raise FileNotFoundError(f"No *.mid artifact found in {out_dir}.")
    return latest


def generate(spec: str = "") -> str:
    """Generate a score/MIDI/manifest through the sibling musicGeneration project."""
    try:
        _ensure_music_imports()
        from aimusic.app.cli import handle_generate

        options = _parse_spec(spec)
        args = _generate_args(options)
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)

        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            handle_generate(args)

        return _ascii_safe(
            "MUSIC-GENERATE-SUCCESS\n"
            f"engine_root: {_music_root()}\n"
            f"resolved: beats={args.beats} seed={args.seed} edo={args.edo} "
            f"meter={args.meter} groove={args.groove_family} tempo_bpm={args.tempo_bpm} "
            f"sample_path={args.sample_path}\n"
            f"{stream.getvalue().strip()}"
        )
    except Exception as exc:
        return f"MUSIC-GENERATE-ERROR: {type(exc).__name__}: {exc}"


def gttm_energy(spec: str = "") -> str:
    """Compute GTTM transition energy for two BeatStates."""
    try:
        _ensure_music_imports()
        from aimusic.core.config import PriorWeights, StyleConfig
        from aimusic.core.vocab import build_default_vocabularies
        from aimusic.scoring.gttm_features import (
            calculate_gttm_energy,
            transition_family_scores,
            weighted_feature_breakdown,
        )

        options = _parse_spec(spec)
        prev_state = _state_from_spec_value(
            options.get("prev", "0,0,3,0,0,0,1,0")
        )
        next_state = _state_from_spec_value(
            options.get("next", "0,1,0,0,0,1,2,0")
        )
        time_index = int(options.get("time", options.get("t", 0)))
        edo = int(options.get("edo", DEFAULT_EDO))
        vocabs = build_default_vocabularies(StyleConfig(key_vocabulary_size=edo))
        weights = PriorWeights()

        energy = calculate_gttm_energy(
            prev_state,
            next_state,
            time_index,
            vocabularies=vocabs,
            edo=edo,
            weights=weights,
        )
        families = transition_family_scores(
            prev_state,
            next_state,
            time_index,
            vocabularies=vocabs,
            edo=edo,
        )
        features = weighted_feature_breakdown(
            prev_state,
            next_state,
            time_index,
            vocabularies=vocabs,
            edo=edo,
            weights=weights,
        )
        top_features = sorted(features.items(), key=lambda item: abs(item[1]), reverse=True)[:6]
        return _ascii_safe(
            "MUSIC-GTTM-ENERGY-SUCCESS\n"
            f"energy: {energy:.6f}\n"
            f"prev: {prev_state.pretty(vocabs)}\n"
            f"next: {next_state.pretty(vocabs)}\n"
            f"families: {families}\n"
            f"top_features: {dict(top_features)}"
        )
    except Exception as exc:
        return f"MUSIC-GTTM-ENERGY-ERROR: {type(exc).__name__}: {exc}"


def plan_method_a(spec: str = "") -> str:
    """Run Method A planning and save only the BeatState path/diagnostics."""
    try:
        _ensure_music_imports()
        from aimusic.core.config import DecodeConfig, StyleConfig
        from aimusic.planning.plans import MethodARunConfig, run_method_a

        options = _parse_spec(spec)
        out_dir = _output_dir(options.get("out", options.get("output", None)))
        out_dir.mkdir(parents=True, exist_ok=True)
        style_config = StyleConfig(
            allowed_meters=(str(options.get("meter", DEFAULT_METER)),),
            groove_families=(str(options.get("groove_family", options.get("groove", DEFAULT_GROOVE))),),
            key_vocabulary_size=int(options.get("edo", DEFAULT_EDO)),
        )
        decode_config = DecodeConfig(
            subbeats_per_beat=int(options.get("subbeats_per_beat", 4)),
            drum_density=float(options.get("drum_density", 0.75)),
            bass_density=float(options.get("bass_density", 0.60)),
            comping_density=float(options.get("comping_density", 0.55)),
            lead_density=float(options.get("lead_density", 0.45)),
        )
        run_config = MethodARunConfig(
            total_beats=int(options.get("beats", options.get("total_beats", DEFAULT_BEATS))),
            seed=int(options.get("seed", DEFAULT_SEED)),
            use_sampling=_parse_bool(options.get("sample_path", options.get("sample", False))),
            style_config=style_config,
            decode_config=decode_config,
            edo=int(options.get("edo", DEFAULT_EDO)),
        )
        result = run_method_a(run_config)
        run_id = str(options.get("run_id", f"method_a_seed{run_config.seed}_beats{run_config.total_beats}_edo{run_config.edo}"))
        path_path = out_dir / f"{run_id}_path.json"
        data = {
            "kind": "method_a_path",
            "run_id": run_id,
            "config": {
                "beats": run_config.total_beats,
                "seed": run_config.seed,
                "edo": run_config.edo,
                "sample_path": run_config.use_sampling,
                "meter": style_config.allowed_meters[0],
                "groove_family": style_config.groove_families[0],
            },
            "path_score": result.path_score,
            "diagnostics": {
                "section_tags": list(result.diagnostics.section_tags),
                "graph_layer_sizes": list(result.diagnostics.graph_layer_sizes),
                "bridge_iterations": result.diagnostics.bridge_iterations,
                "bridge_converged": result.diagnostics.bridge_converged,
                "path_mode": result.diagnostics.path_mode,
            },
            "states": [state.to_dict(result.vocabularies) for state in result.path],
        }
        _write_json(path_path, data)
        return _ascii_safe(
            "MUSIC-PLAN-METHOD-A-SUCCESS\n"
            f"path_json: {path_path}\n"
            f"states: {len(result.path)}\n"
            f"bridge_converged: {result.diagnostics.bridge_converged}\n"
            f"layer_sizes: {list(result.diagnostics.graph_layer_sizes)}"
        )
    except Exception as exc:
        return f"MUSIC-PLAN-METHOD-A-ERROR: {type(exc).__name__}: {exc}"


def decode_score(spec: str = "") -> str:
    """Decode a saved Method A path artifact into a Score JSON."""
    try:
        _ensure_music_imports()
        from aimusic.core.config import DecodeConfig, StyleConfig
        from aimusic.core.vocab import build_default_vocabularies
        from aimusic.decode import decode_path_to_score

        options = _parse_spec(spec)
        path_path = _path_artifact_from_options(options)
        data = json.loads(path_path.read_text(encoding="utf-8"))
        config = data.get("config", {})
        edo = int(options.get("edo", config.get("edo", DEFAULT_EDO)))
        tempo_bpm = float(options.get("tempo_bpm", options.get("tempo", DEFAULT_TEMPO_BPM)))
        style_config = StyleConfig(
            allowed_meters=(str(options.get("meter", config.get("meter", DEFAULT_METER))),),
            groove_families=(str(options.get("groove_family", config.get("groove_family", DEFAULT_GROOVE))),),
            key_vocabulary_size=edo,
        )
        vocabs = build_default_vocabularies(style_config)
        path = tuple(_state_from_dict(state) for state in data["states"])
        decode_config = DecodeConfig(
            subbeats_per_beat=int(options.get("subbeats_per_beat", 4)),
            drum_density=float(options.get("drum_density", 0.75)),
            bass_density=float(options.get("bass_density", 0.60)),
            comping_density=float(options.get("comping_density", 0.55)),
            lead_density=float(options.get("lead_density", 0.45)),
        )
        score = decode_path_to_score(
            path,
            decode_config=decode_config,
            vocabularies=vocabs,
            edo=edo,
            tempo_bpm=tempo_bpm,
        )
        out_dir = _output_dir(options.get("out", options.get("output", path_path.parent)))
        run_id = str(options.get("run_id", data.get("run_id", path_path.stem.replace("_path", ""))))
        score_path = out_dir / f"{run_id}_partition_score.json"
        _write_json(score_path, score.to_dict())
        return _ascii_safe(
            "MUSIC-DECODE-SCORE-SUCCESS\n"
            f"score_json: {score_path}\n"
            f"events: {len(score)}\n"
            f"tracks: {score.track_event_counts()}"
        )
    except Exception as exc:
        return f"MUSIC-DECODE-SCORE-ERROR: {type(exc).__name__}: {exc}"


def render_midi_partition(spec: str = "") -> str:
    """Render a saved Score JSON into MIDI."""
    try:
        _ensure_music_imports()
        from aimusic.core.config import EDOConfig, MicrotonalRendering
        from aimusic.render import render_midi
        from aimusic.theory.edo import EDO

        options = _parse_spec(spec)
        score_path = _score_artifact_from_options(options)
        score = _score_from_dict(json.loads(score_path.read_text(encoding="utf-8")))
        edo = int(options.get("edo", DEFAULT_EDO))
        rendering_method = str(options.get("rendering_method", "MPE"))
        output = options.get("midi", options.get("output_midi", None))
        if output:
            midi_path = Path(str(output)).expanduser()
            if not midi_path.is_absolute():
                midi_path = _mettaclaw_root() / midi_path
        else:
            midi_path = score_path.with_suffix(".mid")
        midi_path.parent.mkdir(parents=True, exist_ok=True)
        render_midi(
            score,
            EDO(
                EDOConfig(
                    n=edo,
                    base_tuning=float(options.get("base_tuning", 0)),
                    pitch_bend_range=int(options.get("pitch_bend_range", 2)),
                    microtonal_rendering_method=MicrotonalRendering[rendering_method],
                )
            ),
            str(midi_path),
        )
        return _ascii_safe(
            "MUSIC-RENDER-MIDI-SUCCESS\n"
            f"midi: {midi_path}\n"
            f"score_json: {score_path}\n"
            f"edo: {edo}"
        )
    except Exception as exc:
        return f"MUSIC-RENDER-MIDI-ERROR: {type(exc).__name__}: {exc}"


def summarize_midi_partition(spec: str = "") -> str:
    """Summarize a MIDI artifact for quick verification."""
    try:
        _ensure_music_imports()
        from aimusic.render import summarize_midi

        options = _parse_spec(spec)
        midi_path = _midi_artifact_from_options(options)
        summary = summarize_midi(str(midi_path))
        return _ascii_safe(
            "MUSIC-SUMMARIZE-MIDI-SUCCESS\n"
            f"midi: {midi_path}\n"
            f"total_notes: {summary.total_notes}\n"
            f"unique_channels: {summary.unique_channels}\n"
            f"pitch_bend_events: {summary.pitch_bend_events}\n"
            f"timbre_events: {summary.timbre_events}\n"
            f"pressure_events: {summary.pressure_events}"
        )
    except Exception as exc:
        return f"MUSIC-SUMMARIZE-MIDI-ERROR: {type(exc).__name__}: {exc}"


def list_outputs(spec: str = "") -> str:
    """List recent music artifacts from the configured output directory."""
    try:
        options = _parse_spec(spec)
        out_dir = _output_dir(options.get("out", options.get("output", None)))
        if not out_dir.exists():
            return f"MUSIC-LIST: no output directory at {out_dir}"

        items = sorted(out_dir.glob("*"), key=lambda path: path.stat().st_mtime, reverse=True)[:30]
        if not items:
            return f"MUSIC-LIST: no artifacts in {out_dir}"
        lines = [f"MUSIC-LIST {out_dir}"]
        lines.extend(str(path) for path in items)
        return _ascii_safe("\n".join(lines))
    except Exception as exc:
        return f"MUSIC-LIST-ERROR: {type(exc).__name__}: {exc}"


def inspect(spec: str = "") -> str:
    """Inspect a manifest path, or the latest manifest in the output directory."""
    try:
        _ensure_music_imports()
        from aimusic.app.cli import handle_inspect

        options = _parse_spec(spec)
        path_text = str(options.get("manifest", options.get("file", ""))).strip()
        if not path_text and spec and "=" not in spec:
            path_text = spec.strip()

        manifest_path = Path(path_text).expanduser() if path_text else None
        if manifest_path is None or str(manifest_path) == ".":
            out_dir = _output_dir(options.get("out", options.get("output", None)))
            manifest_path = _latest_manifest(out_dir)
            if manifest_path is None:
                return f"MUSIC-INSPECT: no manifest found in {out_dir}"

        if not manifest_path.is_absolute():
            manifest_path = _mettaclaw_root() / manifest_path

        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            handle_inspect(SimpleNamespace(file=str(manifest_path)))
        return _ascii_safe(stream.getvalue().strip())
    except SystemExit as exc:
        return f"MUSIC-INSPECT-ERROR: inspect command exited with {exc.code}"
    except Exception as exc:
        return f"MUSIC-INSPECT-ERROR: {type(exc).__name__}: {exc}"
