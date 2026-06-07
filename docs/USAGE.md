# Usage

## Entities

The integration creates a compact Home Assistant control surface:

- `light.lightelf_laser`: projector power.
- `switch.lightelf_laser_ble_connection`: hold or release the BLE connection.
- `select.lightelf_laser_svg_image`: selected SVG file.
- `select.lightelf_laser_svg_color`: preserve SVG colors or force a beam color.
- `button.lightelf_laser_display_selected_svg`: show the selected SVG.
- `button.lightelf_laser_rescan_svg_folder`: refresh the SVG file list.
- `text.lightelf_laser_text`: text message.
- `select.lightelf_laser_text_font`: vector font.
- `select.lightelf_laser_text_color`: solid color or rainbow stroke cycling.
- `select.lightelf_laser_text_mode`: static draw or scrolling text.
- `number.lightelf_laser_text_size`: static text size.
- `number.lightelf_laser_text_vertical_position`: static text vertical offset.
- `number.lightelf_laser_scroll_speed`: scrolling text speed.
- `button.lightelf_laser_display_text`: show or scroll the current text.
- `select.lightelf_laser_shape_family`: built-in static shape family.
- `number.lightelf_laser_shape_index`: shape index.
- `select.lightelf_laser_shape_color`: preserve built-in colors or force a color.
- `image.lightelf_laser_shape_preview`: selected static shape preview.
- `button.lightelf_laser_display_shape`: show the selected shape.
- `select.lightelf_laser_animation_family`: firmware-native animation family.
- `number.lightelf_laser_animation_index`: animation index.
- `number.lightelf_laser_animation_speed`: animation speed.
- `image.lightelf_laser_animation_preview`: captured animation preview.
- `button.lightelf_laser_play_animation`: show the selected native animation.
- `switch.lightelf_laser_sound_reactive`: drive the active effect from the
  onboard microphone instead of a fixed speed.
- `number.lightelf_laser_sound_sensitivity`: microphone sensitivity (1-100).
- `number.lightelf_laser_size`: static size for drawn content (10-100%).
- `select.lightelf_laser_motion`: live motion for drawn content (Off /
  Spin vertical / Spin horizontal / Zoom / Horizontal scroll / Vertical scroll /
  Warp / Chaos / Custom).
- `number.lightelf_laser_motion_speed`: master motion speed (1-100%); scales the
  active transform (the FX knobs move to reflect it).
- `number.lightelf_laser_fx_*`: raw transform knobs (Horizontal/Vertical spin,
  Horizontal/Vertical scroll, Warp; 0-255) for fine control; a preset populates
  these.
- `number.lightelf_laser_dmx_address`: DMX-512 start address / base channel
  (1-512); only relevant when the laser is on a DMX rig.

Entity IDs may differ if Home Assistant assigns a suffix.

## SVG Workflow

Starter SVGs are copied into Home Assistant local media automatically on first
run.

Upload your own SVG files from **Settings > Devices & services > LightElf Laser >
Configure**. The integration validates the SVG, saves it under Home Assistant
local media, refreshes the picker, and selects it automatically.

You can also copy files directly to local media if you prefer:

```text
/media/lightelf_laser/svg
```

After manual file copies, press **Rescan SVG folder**. Then choose the SVG,
optionally choose a color mode, and press **Show SVG**.

The same starter SVG files are included in [`examples/svg`](../examples/svg) for
easy browsing from GitHub.

SVG color mode `original` preserves lit stroke colors where possible. A named
color forces every lit stroke to that beam color.

## Text Workflow

Set the text, font, color, and mode, then press **Show Text**.

Mode `none` draws static Hershey vector text. Mode `scroll` sends one
firmware-scrolling text packet and lets the projector perform the marquee.

## Built-In Shapes

Choose a shape family and scrub the zero-based index while watching the preview.
Press **Show Shape** to draw the selected static frame.

Shape color `original` preserves the stored per-point colors. Choosing a named
color forces all lit points to that color.

## Firmware-Native Animations

Choose a family, one-based index, and speed, then press **Show Animation**. These
animations run inside the projector firmware; Home Assistant only selects the
family, index, and speed.

The catalog exposes indices 1 through 50 for each supported family.

## Sound-Reactive Mode

Turn on **Sound reactive** to make the projector drive the currently playing
firmware effect from its onboard microphone instead of the fixed speed. Adjust
**Sound sensitivity** (1-100) for the room's volume. No audio is streamed from
Home Assistant; the reactivity happens entirely inside the projector.

The setting is global and applies to whatever effect is playing, so it pairs
best with the firmware-native animations. Effects with lots of motion react most
visibly; static or title-card patterns barely change. If a firmware effect is
already running when you toggle the switch or change the sensitivity, the effect
is re-issued so the new setting takes effect immediately.

## Size and Motion (drawn content)

These shape your own drawn content — SVGs, vector text, and built-in shapes
(not the firmware-native animations).

- **Size** (`number.lightelf_laser_size`, 10-100%) statically scales the drawing
  uniformly, so you can make a logo or shape smaller to fit your wall.
- **Motion** (`select.lightelf_laser_motion`) applies a firmware-driven live
  transform to the drawing: **Spin** (vertical or horizontal axis), **Zoom**
  (scale in/out), **Horizontal/Vertical scroll**, **Warp** (barrel), and
  **Chaos**. Motion runs projector-side and composes with Size.
- **Motion speed** (`number.lightelf_laser_motion_speed`, 1-100%) scales the
  active motion. The FX knob sliders move to reflect the current speed.
- The **FX knobs** (`number.lightelf_laser_fx_*`, 0-255) are the underlying
  transform parameters. A Motion preset fills them in and Motion speed scales
  them; nudge a knob directly for fine control and the Motion picker will read
  **Custom**. Set them all to 0 (or pick **Off**) to stop.

Size, Motion, and the FX knobs persist across restarts and re-apply to the
current drawing the moment you change them.

## DMX Address

If you run the projector on a DMX-512 lighting rig, **DMX address**
(`number.lightelf_laser_dmx_address`) sets its start address / base channel
(1-512). It is written to the device and read back from it, so you can patch the
fixture from Home Assistant instead of the device menu. It has no effect unless
the projector is receiving DMX.
