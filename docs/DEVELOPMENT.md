# Development

This document is for contributors who want to improve the Home Assistant
integration or use it as a reference while building their own BLE controller.

## Repository Layout

The integration lives here:

```text
custom_components/lightelf_laser
```

Important modules:

- `bluetooth_client.py`: native Home Assistant Bluetooth connection, notify
  setup, query/unlock, write pacing, and command dispatch.
- `protocol.py`: packet builders/parsers for power, query, mode selection,
  settings, draw streams, and native animation selection.
- `coordinator.py`: integration state, file/catalog loading, and high-level draw
  actions.
- `svg.py`: SVG parsing and conversion to projector point streams.
- `hershey.py` and `scroll_text.py`: static vector text and firmware scrolling
  text packet building.
- `preview.py` and `image.py`: local previews for SVGs, text, shapes, and native
  animations.

## Local Checks

Run a syntax check from the repository root:

```powershell
python -m py_compile (Get-ChildItem -LiteralPath custom_components\lightelf_laser -Filter *.py | ForEach-Object { $_.FullName })
```

For larger changes, test in a Home Assistant instance with Bluetooth available.
The most useful smoke tests are:

- Add the integration through the UI.
- Toggle the light on and off.
- Turn the BLE connection switch off and back on.
- Draw a simple SVG.
- Draw multi-stroke text.
- Start and stop a firmware-native animation.

## BLE And Safety

The projector accepts one BLE connection at a time. During development, release
the Home Assistant BLE connection before testing another controller.

This is laser hardware. Test with the projector aimed at a safe projection
surface, avoid eye exposure, and leave output off when testing is done.

## Bluetooth Write Timing

Draw streams are sent as 20-byte BLE chunks. The integration deliberately uses
paced write-without-response chunks for draw data:

- Acknowledged writes can be too slow over Bluetooth proxy links.
- Unacknowledged writes sent too quickly can arrive out of order.
- The current pacing and point budget were chosen to keep dense multi-stroke
  frames reliable on proxy-backed Home Assistant Bluetooth setups.

Changes to write pacing or point budgets should be verified on real hardware
with dense SVGs and multi-stroke text, not only with a single continuous shape.

## Protocol Notes

Protocol behavior documented in this repository comes from BLE traffic captures
and live-device validation. If you add support for another model or firmware
variant, include:

- advertised BLE name and service UUIDs,
- query response fields if they differ,
- which commands were tested,
- which visual behaviors were verified on hardware.

Avoid hard-coding a behavior from one unit if it can be represented as a
model-specific capability or a parsed device-state field.

## Preview Assets

Static shape thumbnails and native animation previews are bundled so Home
Assistant can show useful image entities without requiring camera hardware.

If previews are regenerated, keep catalog paths stable and verify that image
entities still update when the selected shape or animation changes.
