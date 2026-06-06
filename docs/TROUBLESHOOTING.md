# Troubleshooting

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
the exact timing and transitions.
