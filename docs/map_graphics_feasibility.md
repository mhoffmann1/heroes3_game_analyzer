# Rendering the Heroes III adventure map

The terrain renderer is shared by the standalone Map Helper and the
dashboard's Fog of War Exploration view. The dashboard applies the selected
player's fog mask for the selected historical day before sending map images
to the browser; the standalone helper uses the latest processed turn. The
dashboard uses a compact cached version of the original map for quick day
changes; objects that changed during play may still look as they did at map
creation.

## What we verified locally

- The standalone helper reads the latest player exploration masks from
  `combined_player_data.json` and stores manual pins in the processed game.
- A processed 144 × 144, two-level HotA game has 41,472 map tile records in
  its latest save. Its generated `.h3m` is in the installation's `random_maps`
  directory. The first six bytes of the save's tile record matched the
  corresponding seven-byte `.h3m` terrain record for 41,468 of 41,472 tiles.
  The existing save tile extractor starts four tiles after the actual `.h3m`
  terrain start for this save. The renderer detects that shift from the map's
  object-template section and uses the `.h3m` tile coordinates. The seventh
  byte differs in the save, so matching does not rely on it. This is **one
  verified example**, not a general compatibility guarantee.
- The installed `Data/H3sprite.lod` contains `DIRTTL.def`, `GRASTL.def`,
  `Snowtl.def`, and `rocktl.def`. The installation also has `H3bitmap.lod`,
  `HotA.lod`, and other sprite archives. The HotA map editor executable is
  present. These assets are available locally but are not part of the repo.
- The standalone helper now renders 32 × 32 terrain frames plus road and river
  overlays from `H3sprite.lod`. The example game produced a 4608 × 4608 PNG
  with 4,775 explored surface tiles; covered tiles were filled dark before
  sending the PNG to the browser. It draws a plain-color tile when a terrain
  type lacks a decoded sprite.
- The HotA 1.8 archive reader now resolves its hashed names and masked index.
  The tested installation supplied all 124 Highlands and all 124 Wasteland
  terrain tiles. On a matched 216 × 216 HotA map, 4,399 tile records use
  Highlands and 2,933 use Wasteland; both now render from their real images.
- The same matched map has 5,045 property-free static scenery objects before
  its first object with variable properties. The renderer now draws their
  mountain, tree, rock, and decoration DEF sprites, then clears every covered
  tile from the composited object layer before encoding the PNG. A sample crop
  was visually checked against the expected terrain shapes.
- The helper now locates fixed-layout monolith, portal, and subterranean gate
  objects in the matched map, draws their DEF sprites when present in a readable
  local archive, and adds automatic pins only on explored anchor tiles. The
  tested HotA 1.8 map contained 18 colored monoliths and 20 subterranean gates.
  All 38 transport sprites and all 757 unique sprites in the initial scenery
  run resolved with the new archive reader.

## Practical rendering path

1. **Match the exact map.** Implemented for processed games with source save
   metadata. Search `random_maps` as well as `Maps`; names alone
   are insufficient when a random map was generated several times. Compare a
   sample of terrain records from the save with each candidate `.h3m`, then
   verify dimensions and a large set of tile positions. Reject ambiguous or
   weak matches. The save itself also appears to contain terrain records, so
   that may eventually remove the `.h3m` dependency once record alignment is
   fully validated.
2. **Draw terrain first.** Implemented for the standard and HotA sprite archives. An `.h3m` stores terrain in `[level][y][x]` order;
   each tile has terrain type, terrain view, river type/direction, road
   type/direction, and flags. Extract the matching terrain DEF frames from the
   installed LOD archives, apply the tile view and flags, and compose a local
   raster for each level. Roads and rivers are layered over the terrain.
   [VCMI's H3M loader](https://github.com/vcmi/vcmi/blob/develop/lib/mapping/MapFormatH3M.cpp)
   documents this record layout in its `readTerrain` function. HotA Highlands
   and Wasteland each use numbered 32 × 32 PCX-like tiles in `HotA.lod`.
   [Heroes 3 Living Map's format notes](https://github.com/Alamion/heroes_III_ts/blob/testing/THIRD_PARTY_NOTICES.md)
   and [terrain table](https://github.com/Alamion/heroes_III_ts/blob/testing/src/core/data/terrain.ts)
   provided the archive and tile layout reference; the decoder here uses the
   installed game files directly and keeps them outside this repository.
3. **Draw static scenery, then use the save for current objects.** The first
   property-free object run in the matched `.h3m` is now read for mountains,
   trees, rocks, and decorations. [The H3M object layout](https://github.com/alexanderbelous/h3mtxt/blob/master/doc/h3m_specification.MD)
   describes the template names and bottom-right placement coordinates. The
   parser stops when it encounters an object requiring variable-length
   properties, so a differently ordered map can omit some scenery. Fixed-layout
   transport objects can be found by their template signatures; this targeted
   scan is not a full H3M object parser. Mines,
   artifacts, creatures, heroes, and other objects can change during a game.
   Rendering those accurately needs the latest save's object state, not just
   the original map. VCMI's loader reads object templates and objects after terrain; its
   [object template definition](https://github.com/vcmi/vcmi/blob/develop/lib/mapObjects/ObjectTemplate.h)
   points to the animation file and multi-tile footprint. This is the largest
   remaining parsing and compositing task.
4. **Apply fog to the final image.** Terrain, roads, rivers, and multi-tile
   scenery sprites are clipped to explored tiles before the PNG is sent to the
   browser. Unmasked image tiles and object metadata stay on the server. Pins
   remain a separate, per-player overlay.

The [VCMI map editor documentation](https://vcmi.eu/modders/Map_Editor/)
confirms it can load `.h3m` maps. Its engine and editor source are useful
references, but an editor screenshot by itself would only show the original
map; it would not represent changed objects from a later save. VCMI also
[uses the original Heroes III data files](https://vcmi.eu/players/Installation_Windows/),
which supports local extraction from the user's installation rather than
committing game artwork to this repository.

## Recommended next slice

Compare surface and underground screenshots to the game editor at known
coordinates. Parse the full H3M object stream so scenic objects after mutable
objects are also shown. Add current object sprites from the latest save. The
explored grid remains the fallback when a map or archive cannot be matched.
