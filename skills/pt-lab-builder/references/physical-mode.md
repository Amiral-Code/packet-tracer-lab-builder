# Physical mode

Current support is intentionally bounded.

The local base contributes one Intercity → City → Building → Wiring Closet → Rack hierarchy. The generator removes unreferenced type-6 device nodes, renames the City/Building/Closet/Rack containers, gives every generated device a fresh physical node, places rackable models in distinct rack positions, and arranges endpoints on a building grid.

Configure names with `[physical]` and individual placement with a device inline table:

```toml
[physical]
city = "Rabat"
building = "Branch Office"
closet = "Branch MDF"
rack = "Rack A"

[[device]]
name = "BR-R1"
model = "router-2911"
physical = { location = "rack", slot = 1 }

[[device]]
name = "BR-PC1"
model = "pc"
physical = { location = "building", x = 172, y = 215 }
```

Valid locations are `rack`, `closet`, and `building`. Routers, switches, multilayer switches, WLCs, and servers default to `rack`; other models default to `building`.

Do not claim these unimplemented capabilities:

- Multiple independently generated cities, buildings, closets, or racks
- Background-image packaging
- Assessment of device placement or rack slot
- Activities where learners create missing physical cables and Check Results grades those cables
- Control of real routers, switches, or cabling

A real-hardware companion can provide rack diagrams, patching instructions, console steps, and verification commands, but a `.pka` does not operate physical hardware. Preserve observed XML facts separately from inferred design choices when extending this layer.
