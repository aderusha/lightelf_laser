# Troubleshooting

## One-Button Compatibility Scan

If power or animations work but drawing or text does not, use the **Run
compatibility scan** diagnostic button on the LightElf Laser device. Aim the
laser at a safe projection surface first. The scan replaces the current
projection with fixed, short test images and text, checks several protocol
formats and mode-change orders, and turns the output off at the end. It does
not alter DMX settings, mount orientation, or firmware. It can replace the
projector's last hand-drawn image or saved text.

The **Compatibility scan status** sensor shows `running`, `complete`, `partial`,
or `failed`, with the current step in its attributes. Wait for it to finish,
then download diagnostics from **Settings > Devices & services > LightElf Laser >
three-dot menu > Download diagnostics**. The latest scan survives a Home
Assistant restart and remains in the diagnostic download until another scan
replaces it. If `power_off_confirmed` is false, turn the output off manually.

Attach the JSON report to a compatibility issue after reviewing it. If easy,
add a short video of the projection during the scan, or tell us which named
visual cues appeared. The scan can read back device mode and power but cannot
detect what the laser actually projects. Each probe in the report includes a
timestamp and expected visual cue so a video can be matched to the command.
The report contains fixed-command fingerprints and parsed read-backs, not your
text or uploaded files. It also excludes raw Bluetooth replies, addresses,
passwords, and challenge values. Home Assistant adds environment information
to the diagnostic download; review the complete file before posting it.

If the scan fails because Bluetooth disconnects, leave the mobile controller
disconnected, turn the **BLE connection** switch on, and try once more. No
terminal, packet capture, factory reset, or firmware update is required.

## Share A Diagnostic Report

After reproducing a problem, open **Settings > Devices & services > LightElf
Laser** and use the configuration entry's three-dot menu to **Download
diagnostics**. Attach the JSON file to your issue, or paste its contents in a
code block. Include your retail projector model and whether Home Assistant uses
a local Bluetooth adapter or an ESPHome proxy, with its model.

The integration's report includes the last successful identity query, inferred
firmware capabilities, mode readback, actual write settings, and the last 32
operations since integration startup. It excludes Bluetooth addresses, device
names, text content, filenames, passwords, challenge tokens, and packet payloads.
Downloading it reads cached state and does not connect or change laser output.
Review the complete Home Assistant diagnostic file before posting it.

Download soon after testing: routine polling eventually replaces older history.
`written` means the Bluetooth stack accepted the write, not that the projector
displayed it. A failed operation records the exception type, not its potentially
private message. The last successful query may predate a disconnect; its timestamp
and current connection status are both included. A null identity means no
successful query has been recorded since startup.

For additional transport errors, enable **debug logging** from the integration
menu, reproduce the issue, then disable debug logging to download the log.
Review logs before sharing: they can contain addresses and filenames.

## Power Works But Drawings Or Animation Selection Do Not

Related projector models can use different command formats and animation banks.
Run the compatibility scan above first. Its fixed samples cover simple SVG,
static text, and scrolling text without using your content. If the scan itself
cannot finish, try a simple SVG, one letter in static text mode, and the same
letter in scrolling mode. Note whether each leaves the previous image unchanged,
produces malformed output, or works. Press the display button after making each
selection. Aim at a safe projection surface and turn output off after testing.

The report separates **inferred firmware capabilities** from **integration
behavior**. Version 0.3.0 still sends legacy drawing and scrolling-text packets;
detecting a newer protocol does not mean those features work on that hardware.
Capability sensors describe inferred firmware features, not available integration
actions. The 64-pattern flag does not expand the current reference catalog.

## Device Not Found

The projector accepts one BLE connection at a time. If another controller is
connected, Home Assistant may not see the projector. Disconnect the other
controller, wait a few seconds, and try setup again.

Bluetooth proxies can also take time to refresh advertisements. If setup still
does not see the projector, restart the projector and try again from a nearby
Bluetooth adapter or proxy.

## Entities Are Unavailable

Check `switch.lightelf_laser_ble_connection`. When it is off, Home Assistant has
released the BLE connection and draw/power entities will be unavailable.

Turn the switch on to reconnect.

## Draws Are Truncated Or Scrambled

Large point streams are timing-sensitive over Bluetooth proxy links. This
integration paces unacknowledged BLE writes and caps generated point frames to
fit the projector's draw-assembly window. If you modify the protocol code or
increase point budgets, verify multi-stroke text and dense SVGs on real hardware.  Firmware has no native curve or arc support, so any curved features become a series of lines and may impact your overall frame budget.  Only very simple line drawings are likely to work.

## SVG Does Not Appear In The Picker

Make sure the file ends in `.svg` and is uploaded under:

```text
/media/lightelf_laser/svg
```

Then press **Rescan SVG folder**.

## Animation Preview Looks Different From Projection

Animation previews are camera captures of firmware-native effects. They are
representative previews, not streamed source frames. The projector firmware owns
the exact timing and transitions. These captures come from the reference device;
other firmware may have different images or ordering at the same index.
