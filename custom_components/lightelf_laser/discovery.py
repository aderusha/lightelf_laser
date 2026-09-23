"""Bounded, opt-in compatibility scan using fixed, non-personal test content."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .const import DEFAULT_TEXT_FONT, SCROLL_UNIT
from .protocol import (
    PROJECT_SELECTED,
    ProjectSelection,
    draw_points_command,
    mode_command,
    point_play_command,
    power_command,
)
from .scroll_text import build_scroll_a0

if TYPE_CHECKING:
    from .coordinator import LightElfLaserDataUpdateCoordinator


SCAN_SCHEMA_VERSION = 1
_STAR = Path(__file__).parent / "starter_svgs" / "star.svg"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Probe:
    key: str
    visual_cue: str
    expected_mode: int | None
    packets: tuple[tuple[str, str], ...]


def _animation(index: int) -> tuple[tuple[str, str], ...]:
    return (
        ("clear_point_play", point_play_command("")),
        (f"select_animation_{index}", mode_command(
            mode=3,
            color=9,
            speed_percent=70,
            projects={3: ProjectSelection(
                py_mode=PROJECT_SELECTED,
                selected_patterns=(index,),
                preview_pattern=index,
            )},
        )),
    )


def _mode(mode: int) -> str:
    return mode_command(
        mode=mode,
        color=9,
        size_percent=100,
        speed_percent=50,
        distance_percent=50,
    )


def _line(color: int, *, new_format: bool = False, point_time: bool = False) -> str:
    """A tiny fixed three-segment glyph, safely below every draw budget."""
    points = [
        [-70, 60, 0, 2], [-70, 60, color, 0],
        [0, -60, color, 0], [70, 60, color, 3],
    ]
    return draw_points_command(
        points,
        cmd_new_type=new_format,
        text_stop_time=point_time,
        tx_point_time=50,
    )


async def build_probes(coordinator: LightElfLaserDataUpdateCoordinator) -> list[Probe]:
    """Create the fixed scan packet matrix without reading user content."""
    features = coordinator.client._features
    star = await coordinator.hass.async_add_executor_job(
        coordinator._build_svg_command, str(_STAR), 5, None, 1.0
    )
    static_h = await coordinator.hass.async_add_executor_job(
        coordinator._build_text_command,
        "H", DEFAULT_TEXT_FONT, 150, 7, 0, None, 1.0,
    )
    scroll_h = await coordinator.hass.async_add_executor_job(
        build_scroll_a0, "H", DEFAULT_TEXT_FONT, SCROLL_UNIT, 5, 7
    )
    scroll_i = await coordinator.hass.async_add_executor_job(
        build_scroll_a0, "I", DEFAULT_TEXT_FONT, SCROLL_UNIT, 5, 7
    )
    scroll_feature = await coordinator.hass.async_add_executor_job(
        _feature_scroll, features
    )
    text_mode = mode_command(
        mode=4, color=9, size_percent=100, speed_percent=50,
        distance_percent=50, run_direction=255, arb_play=True,
    )
    mode8 = _mode(8)
    mode8_features = mode_command(
        mode=8, color=9, size_percent=100, speed_percent=50,
        distance_percent=50,
        arb_play=bool(features and features.arb_play),
        new_prjs=bool(features and features.new_projects),
        cmd_new_type=bool(features and features.cmd_new_type),
        text_stop_time=bool(features and features.text_stop_time),
    )
    probes = [
        Probe("power_on", "Laser powers on", None,
              (("power_on_legacy", power_command(True, cmd_new_type=False)),)),
        Probe("animation_1", "Animation index 1", 3, _animation(1)),
        Probe("svg_direct_from_animation", "Cyan star, or animation continues", 8,
              (("legacy_svg", star),)),
        Probe("animation_reset_1", "Animation index 1 again", 3, _animation(1)),
        Probe("select_draw_mode", "Stored hand-drawn image or blank", 8,
              (("select_mode_8", mode8),)),
        Probe("svg_after_draw_mode", "Cyan star", 8, (("legacy_svg", star),)),
        Probe("select_draw_mode_again", "Stored hand-drawn image or blank", 8,
              (("select_mode_8", mode8),)),
        Probe("static_h_after_draw_mode", "White H", 8,
              (("legacy_static_h", static_h),)),
        Probe("animation_reset_2", "Animation index 1 again", 3, _animation(1)),
        Probe("draw_mode_power_then_svg", "Cyan star, or animation resumes", 8,
              (("select_mode_8", mode8),
               ("power_on_legacy_again", power_command(True, cmd_new_type=False)),
               ("legacy_svg", star))),
        Probe("animation_reset_3", "Animation index 1 again", 3, _animation(1)),
        Probe("legacy_draw_with_point_time", "Red small chevron", 8,
              (("select_mode_8", mode8),
               ("legacy_draw_point_time", _line(1, point_time=True)))),
        Probe("animation_reset_4", "Animation index 1 again", 3, _animation(1)),
        Probe("new_format_draw", "Green small chevron, or unchanged animation", 8,
              (("select_mode_8", mode8),
               ("new_format_draw", _line(2, new_format=True)))),
        Probe("animation_reset_4b", "Animation index 1 again", 3, _animation(1)),
        Probe("feature_mode_draw", "Cyan star with inferred mode flags", 8,
              (("select_mode_8_feature_flags", mode8_features),
               ("legacy_svg", star))),
        Probe("animation_10", "Animation index 10, distinct from index 1", 3,
              _animation(10)),
        Probe("animation_reset_5", "Animation index 1 again", 3, _animation(1)),
        Probe("scroll_current_order", "Scrolling H", 4,
              (("legacy_text_h", scroll_h), ("select_text_mode", text_mode))),
        Probe("animation_reset_6", "Animation index 1 again", 3, _animation(1)),
        Probe("scroll_mode_first", "Scrolling I", 4,
              (("select_text_mode", text_mode), ("legacy_text_i", scroll_i),
               ("reselect_text_mode", text_mode))),
        Probe("animation_reset_7", "Animation index 1 again", 3, _animation(1)),
        Probe("scroll_inferred_encoding", "Scrolling X", 4,
              (("select_text_mode", text_mode),
               ("feature_encoded_text_x", scroll_feature),
               ("reselect_text_mode", text_mode))),
    ]
    if features is not None and features.cmd_new_type:
        probes.insert(1, Probe(
            "power_on_new_format", "Laser powers on with newer power frame", None,
            (("power_on_new", power_command(True, cmd_new_type=True)),),
        ))
    return probes


def _feature_scroll(features: Any) -> str:
    return build_scroll_a0(
        "X", DEFAULT_TEXT_FONT, SCROLL_UNIT, 5, 7,
        text_stop_time=bool(features and features.text_stop_time),
        cmd_new_type=bool(features and features.cmd_new_type),
        text_decimal_time=bool(features and features.text_decimal_time),
    )


def _packet_metadata(packets: tuple[tuple[str, str], ...]) -> list[dict[str, Any]]:
    return [
        {
            "label": label,
            "bytes": len(packet) // 2,
            "sha256": sha256(bytes.fromhex(packet)).hexdigest(),
        }
        for label, packet in packets
    ]


async def run_scan(
    coordinator: LightElfLaserDataUpdateCoordinator,
) -> dict[str, Any]:
    """Run the fixed matrix, recording every result and ending with output off."""
    client = coordinator.client
    report: dict[str, Any] = {
        "schema_version": SCAN_SCHEMA_VERSION,
        "status": "running",
        "started_at": _now(),
        "finished_at": None,
        "fixed_test_content": True,
        "visual_detection": "not_available; compare cues with the laser or a short video",
        "transport_at_start": client.diagnostic_snapshot(),
        "identity_at_start": None,
        "inferred_capabilities": None,
        "steps": [],
        "power_off": None,
    }
    client.discovery_active = True
    try:
        baseline = await client.async_probe_packets([], first_delay=0, second_delay=0.35)
        report["baseline"] = baseline
        report["identity_at_start"] = client.diagnostic_snapshot()["last_query"]
        if client._features is not None:
            report["inferred_capabilities"] = asdict(client._features)
        if not any(item.get("result") == "ok" for item in baseline["readbacks"]):
            report["status"] = "failed"
            report["failure_reason"] = "initial_query_failed"
            return report

        probes = await build_probes(coordinator)
        report["planned_steps"] = len(probes)
        consecutive_query_failures = 0
        had_transport_failure = False
        for number, probe in enumerate(probes, 1):
            coordinator._set_discovery_progress(number, len(probes), probe.key)
            started = _now()
            result = await client.async_probe_packets(list(probe.packets))
            step = {
                "number": number,
                "key": probe.key,
                "started_at": started,
                "finished_at": _now(),
                "expected_visual_cue": probe.visual_cue,
                "expected_mode": probe.expected_mode,
                "packets": _packet_metadata(probe.packets),
                "result": result,
            }
            settled = next(
                (item for item in reversed(result["readbacks"])
                 if item.get("result") == "ok"),
                None,
            )
            reported_mode = (
                (settled.get("mode_state") or {}).get("mode")
                if settled and (settled.get("parsed_blocks") or {}).get("mode")
                else None
            )
            step["observed_mode"] = reported_mode
            step["mode_matches_expected"] = (
                reported_mode == probe.expected_mode
                if probe.expected_mode is not None and reported_mode is not None
                else None
            )
            step["observed_power_on"] = settled.get("device_on") if settled else None
            report["steps"].append(step)
            await coordinator._save_discovery_report(report)
            if result.get("error_type") or any(
                item.get("result") != "ok" for item in result["readbacks"]
            ):
                had_transport_failure = True
            if not any(item.get("result") == "ok" for item in result["readbacks"]):
                consecutive_query_failures += 1
            else:
                consecutive_query_failures = 0
            if consecutive_query_failures >= 2:
                report["status"] = "partial"
                report["failure_reason"] = "two_consecutive_query_failures"
                break
        else:
            report["status"] = "partial" if had_transport_failure else "complete"
    except asyncio.CancelledError:
        report["status"] = "cancelled"
        report["failure_reason"] = "integration_unloaded"
    except Exception as err:
        report["status"] = "failed"
        report["failure_reason"] = "unexpected_error"
        report["error_type"] = type(err).__name__
    finally:
        # OFF is sent twice, matching normal power control. A failed cleanup is
        # explicit in the report; it must never masquerade as a safe shutdown.
        off_packets = [
            ("power_off_legacy", power_command(False, cmd_new_type=False)),
            ("power_off_legacy_repeat", power_command(False, cmd_new_type=False)),
        ]
        if client._features is not None and client._features.cmd_new_type:
            off_packets.extend((
                ("power_off_new", power_command(False, cmd_new_type=True)),
                ("power_off_new_repeat", power_command(False, cmd_new_type=True)),
            ))
        try:
            report["power_off"] = await client.async_probe_packets(
                off_packets,
                first_delay=0.2,
                second_delay=0.4,
            )
        except Exception as err:
            report["power_off"] = {"result": "failed", "error_type": type(err).__name__}
        readbacks = report["power_off"].get("readbacks", [])
        report["power_off_confirmed"] = bool(
            readbacks and readbacks[-1].get("result") == "ok"
            and readbacks[-1].get("device_on") is False
        )
        if report["status"] == "complete" and not report["power_off_confirmed"]:
            report["status"] = "partial"
            report["failure_reason"] = "power_off_not_confirmed"
        report["summary"] = {
            "steps_recorded": len(report["steps"]),
            "mode_readback_matches": [
                step["key"] for step in report["steps"]
                if step["mode_matches_expected"] is True
            ],
            "mode_readback_mismatches": [
                step["key"] for step in report["steps"]
                if step["mode_matches_expected"] is False
            ],
            "transport_error_steps": [
                step["key"] for step in report["steps"]
                if step["result"].get("error_type") or any(
                    readback.get("result") != "ok"
                    for readback in step["result"]["readbacks"]
                )
            ],
            "visual_outcomes_measured": False,
        }
        report["finished_at"] = _now()
        client.discovery_active = False
        await coordinator._save_discovery_report(report)
    return report
