# Protocol Notes

These notes are intended for users building their own controller or validating
behavior against similar BLE laser projectors.

## BLE Profiles

Common profile:

```text
Service: 0000FF00-0000-1000-8000-00805F9B34FB
Notify:  0000FF01-0000-1000-8000-00805F9B34FB
Write:   0000FF02-0000-1000-8000-00805F9B34FB
```

Alternate profile:

```text
Service:      0000FFE0-0000-1000-8000-00805F9B34FB
Write/notify: 0000FFE1-0000-1000-8000-00805F9B34FB
```

## Connection Model

The projector has a single BLE connection slot and usually stops advertising
while connected. A controller should connect once, subscribe to notifications,
perform the query/unlock exchange, then send commands over the write
characteristic.

## Query And Unlock

The query command returns device state and challenge bytes. The integration uses
the challenge response implemented in `protocol.py` before sending draw or mode
commands.

The decoded query state includes whether output is on, protocol generation,
firmware version fields, settings, and mode/project selection state.

## Command Blocks

Common block markers:

```text
E0E1E2E3 ... E4E5E6E7  query/reply envelope
B0B1B2B3 ... B4B5B6B7  power
C0C1C2C3 ... C4C5C6C7  mode/playback parameters
00010203 ... 04050607  device settings
A0A1A2A3 ... A4A5A6A7  scrolling text coordinate stream
F0F1...   ... F4F5F6F7  hand-draw point stream
D0D1D2D3 ... D4D5D6D7  project/pattern item
90919293 ... 94959697  image/list selection
70717073 ... 74757677  point/image play selector
```

## Draw Streams

Static SVGs, shapes, and text are converted to F0/F4 point streams. Points use
projector-space coordinates and a color/control byte. The integration preserves
stroke boundaries, travel points, and stroke endpoints when thinning dense
frames.

Over Bluetooth proxy links, acknowledged writes can be too slow for large draw
frames, while unacknowledged writes sent too quickly can arrive out of order. The
integration uses paced unacknowledged writes and a conservative point budget.

## Scrolling Text

Scrolling text is firmware-driven. The controller sends an A0 text coordinate
packet, then a C0 mode command that selects text mode and speed. The projector
then performs the marquee without host-side frame streaming.

## Firmware-Native Animations

Native animations run inside the projector. The controller selects a mode,
project family, one-based pattern index, and speed with a C0 mode command. The
integration exposes the tested 1 through 50 range for supported families.

## Sound-Reactive Mode

The C0 mode command carries a run-mode byte and a sound-sensitivity byte. Setting
the run-mode byte to `255` puts the projector in sound-reactive ("Music") mode:
the active effect advances from the onboard microphone level instead of the fixed
speed value, and the sensitivity byte (a 0-100 percentage scaled to 0-255) sets
the microphone gain. No audio is streamed from the host; the reactivity is
entirely firmware-side. The setting is global and applies to whichever effect is
currently playing.
