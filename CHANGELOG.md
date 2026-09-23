# Changelog

## 0.3.0

- Add downloadable diagnostics with device identity, inferred firmware
  capabilities, actual Bluetooth write settings, and a bounded history of
  command sizes, timings, and outcomes. Exclude user content and raw packets.
- Show the reported hardware class instead of a fixed retail model, and add
  identity and optional firmware-capability sensors.
- Correct protocol-generation detection and settings-format selection.
- Add an onboard Show program selector. Sound adjustments preserve the selected
  program, including changes read back from the projector's controls.
- Report actual Bluetooth chunk size and delay in diagnostic sensors.
- Require a target when actions could address multiple projectors, and respect
  the released BLE connection when requesting device state.

Drawing and scrolling text still use the legacy format. Newer hardware and
64-pattern catalogs are not yet validated; diagnostics make these differences
visible without claiming full compatibility. Animation previews are captures
from the reference device and may differ on other firmware.

## 0.2.0

- Add **sound-reactive ("Music") mode**: a `Sound reactive` switch and a
  `Sound sensitivity` slider drive the active firmware effect from the
  projector's onboard microphone instead of a fixed speed. No host audio
  streaming is used. Both settings persist across restarts.
- Add **live effect transforms** for drawn content (SVG/shape/text): a `Motion`
  picker (Spin vertical/horizontal, Zoom, Horizontal/Vertical scroll, Warp,
  Chaos) backed by raw transform knobs and a `Motion speed` slider, plus a
  `Size` control (10-100%) for static uniform scaling. Transforms run
  firmware-side, compose with each other and with sound mode, re-apply to the
  current drawing live, and persist across restarts.
- Add a **DMX address** control (`number.lightelf_laser_dmx_address`, 1-512) to
  set the projector's DMX-512 start address / base channel over Bluetooth.

## 0.1.0

- Initial release candidate.
- Adds Home Assistant native Bluetooth control for LightElf-compatible BLE laser
  projectors.
- Supports power, SVG drawing, vector text, scrolling text, built-in static
  shapes, and firmware-native animations.
