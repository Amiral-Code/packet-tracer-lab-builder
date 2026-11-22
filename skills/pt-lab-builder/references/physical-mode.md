# Physical mode

## Sites

Each `[[site]]` is a building with its own wiring closet and rack. Sites with the same `city` share a city;
a new city name creates a new city on the intercity map. Devices not listed in any site go to the first site.

```toml
[[site]]
name = "HQ"
city = "Casablanca"
building = "Northstar HQ"
closet = "HQ Main Distribution Frame"
rack = "HQ Rack A"
devices = ["HQ-EDGE", "CORE1", "HQ-SW1", "HQ-PC1"]

[[site]]
name = "Branch"
city = "Rabat"
building = "Rabat Branch"
devices = ["BR-R1", "BR-SW1", "BR-PC1"]
```

`closet` and `rack` default to "<name> Wiring Closet" and "<name> Rack". Without `[[site]]`, a single
`[physical]` table (`city`, `building`, `closet`, `rack`) renames the one inherited site.

The first site keeps the base's power distribution unit. Packet Tracer adds a power unit by itself to any other
rack when the file opens.

## Placement

Routers, switches, multilayer switches, WLCs and servers default to the site's **rack**; everything else goes to the
building floor. Override per device:

```toml
physical = "closet"                                   # beside the rack in the wiring closet
physical = "building"                                 # automatic floor grid, right of the closet icon
physical = { location = "rack", slot = 1 }            # slot = order from the top of the rack
physical = { location = "building", x = 600, y = 240 }
```

Rack devices are stacked from the top by their real height (measured in Packet Tracer 9.0.1: 1RU gear 4 units,
2911 7, 1941 8, server 15, WLC 5, each with room for its label; the rack holds about 124). `ptlab lint` rejects a rack that overflows; split
devices into sites or move some to the closet. In the building view, the wiring-closet icon covers about
x/y 40-400. The floor grid starts at x 470, and `ptlab lint` warns about explicit positions under the icon.

Cable-length effects are always switched off in generated activities, so the distance between buildings never
takes a link down.

## Cabling labs

Mark a link `student = true` and it is left out of the start network (and of the troubleshooting start, where it
reads as "someone unplugged it"). Every such link is graded automatically:

- in Packet Tracer: **Port Up** on both ends (a switch or router port is only up with a working cable of the
  right type); add `ping` tests for the end-to-end result;
- by `ptlab check`: a cable between exactly those two ports, of the expected type (straight-through or
  crossover, from the device classes, or `cable = "eCrossOver"` on the link).

The answer guide lists every cable with its type. For a cabling-only lab use `kind = "mixed"` with complete
`[config.answer]` and no `[config.start]` overlay: the devices start configured and only the cables are missing.
`cable DEV PORT DEV PORT` grades a cable explicitly (for example in a troubleshooting lab).

## Not implemented

- Background-image packaging
- Assessment of rack position or which room a device is in
- Packet Tracer's native "Link to" assessment item (its value format is not documented; Port Up + ping is used)
- Control of real routers, switches, or cabling

A real-hardware companion can provide rack diagrams, patching instructions, console steps and verification
commands, but a `.pka` does not operate physical hardware.
