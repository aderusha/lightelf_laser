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
