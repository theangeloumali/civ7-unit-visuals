# Unit visuals mapping

Source of truth: `tools/unit_sizes.json`, read by `tools/unit_scale.py`. This page is the same data, written out for review.
Sizes multiply each figure's shipped `UniformScale`. Figures are the drawn models per unit (Asset Quality High).

## Size by class

| Class    | Scale |
| -------- | ----- |
| default  | 0.85  |
| infantry | 0.85  |
| cavalry  | 0.85  |
| siege    | 0.7   |
| naval    | 0.85  |
| air      | 0.85  |

## Size by unit (overrides the class)

| Unit                              | Scale |
| --------------------------------- | ----- |
| `UNIT_ASSAULT_GUN`                | 0.7   |
| `UNIT_BARBARY_CORSAIR`            | 0.95  |
| `UNIT_BARBARY_CORSAIR_2`          | 0.95  |
| `UNIT_BARBARY_CORSAIR_3`          | 0.95  |
| `UNIT_BATTLESHIP`                 | 1.35  |
| `UNIT_CANOE`                      | 0.95  |
| `UNIT_CARRIER_COMMANDER`          | 1.5   |
| `UNIT_CATAPULT`                   | 0.9   |
| `UNIT_CHANG_BEUN`                 | 0.8   |
| `UNIT_COG`                        | 0.95  |
| `UNIT_CRUISER`                    | 1.25  |
| `UNIT_DESTROYER`                  | 1.2   |
| `UNIT_DHOW`                       | 0.95  |
| `UNIT_DREADNOUGHT`                | 1.3   |
| `UNIT_EMBARK`                     | 1.15  |
| `UNIT_EMBARK_CAVALRY`             | 1.15  |
| `UNIT_EMBARK_COMMANDER`           | 1.15  |
| `UNIT_EMBARK_COMMANDER_Trung_Nhi` | 1.15  |
| `UNIT_EMBARK_EXPLORER`            | 1.15  |
| `UNIT_EMBARK_HEAVY`               | 1.15  |
| `UNIT_EMBARK_LIGHT`               | 1.15  |
| `UNIT_EMBARK_MARINE`              | 1.15  |
| `UNIT_FRIGATE`                    | 1.1   |
| `UNIT_GALLEY`                     | 0.95  |
| `UNIT_HEAVY_ARTILLERY`            | 0.6   |
| `UNIT_IRONCLAD`                   | 1.1   |
| `UNIT_KNIGHT`                     | 0.72  |
| `UNIT_LANDSHIP`                   | 0.75  |
| `UNIT_MIKASA`                     | 1.35  |
| `UNIT_MIKASA_2`                   | 1.35  |
| `UNIT_PRIVATEER`                  | 0.95  |
| `UNIT_PRIVATEER_2`                | 0.95  |
| `UNIT_QUADRIREME`                 | 0.95  |
| `UNIT_SUBMARINE`                  | 1.1   |
| `UNIT_TANK`                       | 0.8   |
| `UNIT_TRADE_SHIP`                 | 0.95  |
| `UNIT_TREASURE_FLEET_EMBARKED`    | 1.15  |
| `UNIT_TURTLE_SHIP`                | 0.95  |
| `UNIT_TURTLE_SHIP_2`              | 0.95  |
| `UNIT_TURTLE_SHIP_3`              | 0.95  |

## Figures per unit

Formations show at least 10 slots.

| Class or unit          | Figures |
| ---------------------- | ------- |
| cavalry (class)        | 6       |
| siege (class)          | 3       |
| air (class)            | 3       |
| `UNIT_ASSAULT_GUN`     | 3       |
| `UNIT_AT_GUN`          | 3       |
| `UNIT_CHANG_BEUN`      | 3       |
| `UNIT_FIELD_CANNON`    | 3       |
| `UNIT_FIELD_GUN`       | 3       |
| `UNIT_HEAVY_ARTILLERY` | 3       |
| `UNIT_KATYUSHA`        | 3       |
| `UNIT_LANDSHIP`        | 3       |
| `UNIT_MORTAR`          | 3       |
| `UNIT_TANK`            | 3       |

Ships and commanders always keep one figure.

## Formation swaps

Formation_AirPatrol is Firaxis's fixed-slot V: point at (0,0), wings at (-15,+-15), (-30,+-30); 1.1x keeps a 3-vehicle V inside one hex.

| Unit                   | Formation             |
| ---------------------- | --------------------- |
| `UNIT_ASSAULT_GUN`     | `Formation_AirPatrol` |
| `UNIT_AT_GUN`          | `Formation_AirPatrol` |
| `UNIT_BALLISTA`        | `Formation_AirPatrol` |
| `UNIT_BOMBARD`         | `Formation_AirPatrol` |
| `UNIT_CATAPULT`        | `Formation_AirPatrol` |
| `UNIT_CHANG_BEUN`      | `Formation_AirPatrol` |
| `UNIT_CHARIOT`         | `Formation_AirPatrol` |
| `UNIT_FIELD_CANNON`    | `Formation_AirPatrol` |
| `UNIT_FIELD_GUN`       | `Formation_AirPatrol` |
| `UNIT_HEAVY_ARTILLERY` | `Formation_AirPatrol` |
| `UNIT_HWACHA`          | `Formation_AirPatrol` |
| `UNIT_HWACHA_2`        | `Formation_AirPatrol` |
| `UNIT_HWACHA_3`        | `Formation_AirPatrol` |
| `UNIT_KATYUSHA`        | `Formation_AirPatrol` |
| `UNIT_KATYUSHA_2`      | `Formation_AirPatrol` |
| `UNIT_LANDSHIP`        | `Formation_AirPatrol` |
| `UNIT_MORTAR`          | `Formation_AirPatrol` |
| `UNIT_TANK`            | `Formation_AirPatrol` |
| `UNIT_TREBUCHET`       | `Formation_AirPatrol` |

| Formation             | Slot spread |
| --------------------- | ----------- |
| `Formation_AirPatrol` | 1.1x        |

## Formation layout rules

First matching rule wins. `stackedOnly` rules skip formations that already spread their members.

| Formations (regex)                                                                                                 | Values                                                                                                                                                     | Why                                                                            |
| ------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| `^Formation_Tank_Mod3$`                                                                                            | SpacingMultiplier 1.0, FirstRowWidth 1, PerRowIncrement 1.0, RandomLeftRight 0.5, RandomFrontBack 0.5, SpacingX 52.0, SpacingY 44.0, StaggerIncrement 0.5  | arrowhead (rows of 1, 2, 3) spaced for the Landship, the longest hull on it    |
| `^Formation_Catapult$`                                                                                             | SpacingMultiplier 1.0, FirstRowWidth 1, PerRowIncrement 1.0, RandomLeftRight 0.5, RandomFrontBack 0.5, SpacingX 46.0, SpacingY 40.0, StaggerIncrement -0.5 | arrowhead spaced for the Howitzer's barrel                                     |
| `^Formation_SingleCenter$`                                                                                         | SpacingMultiplier 1.0, FirstRowWidth 1, PerRowIncrement 1.0, RandomLeftRight 0.5, RandomFrontBack 0.5, SpacingX 38.0, SpacingY 32.0, StaggerIncrement 0.5  | arrowhead for guns, siege and bombers; single-figure ships share it unaffected |
| `^Formation_HeavyBomber_Bin$`                                                                                      | AbsoluteOverride 0, SpacingX 18.0, SpacingY 18.0, SpacingMultiplier 1.0, FirstRowWidth 2                                                                   | heavy bombers stacked on one point                                             |
| `TREBUCHET\|Catapult\|BOMBARD\|Ballista\|FIELD_GUN\|HEAVY_ARTILLERY\|AT_GUN\|ASSAULT_GUN\|Tank\|Chariot\|Elephant` | SpacingX 19.0, SpacingY 15.0, SpacingMultiplier 1.0, FirstRowWidth 3 (stacked only)                                                                        | copied from Formation_Cavalry_3 so big machines don't overlap                  |
| `.*`                                                                                                               | SpacingMultiplier 1.0, FirstRowWidth 2 (stacked only)                                                                                                      | spread any other stacked formation                                             |

## Why this is not a Workshop mod

Civ VII loads art packages only from `<game>/DLC/<project>`, `Overrides/Branch/DLC/<project>` and `Overrides/Local/DLC/<project>`, never from a mod folder (`ArtDef.log`: "No Packages found for project"). The visuals are installed into `Overrides/Local` by `tools/unit_scale.py`.
