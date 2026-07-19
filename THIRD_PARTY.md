# Third-party notices

## Javascript Racer

Racer Lab ports the mechanics and implementation of the four-part `v1`–`v4` progression from Jake Gordon's Javascript Racer.

- Source: <https://github.com/jakesgordon/javascript-racer>
- Articles: <https://jakesgordon.com/writing/javascript-racer/>
- Copyright: Copyright (c) 2012, 2013, 2014, 2015, 2016 Jake Gordon and contributors
- License: MIT

The upstream MIT license permits use, modification, publication, distribution, and sublicensing of the software as long as its copyright and permission notices are preserved. The complete notice is included in [LICENSE](LICENSE).

## Upstream media boundary

The upstream README places additional limits on files that are not covered by its general software grant:

- its music was commercially licensed only for that project and must not be reproduced;
- its placeholder sprite graphics were borrowed from the Genesis version of OutRun.

Racer Lab does not include the upstream music or upstream raster sprite files. All current graphics were created for this port and are distributed under the repository's MIT License. The current player-car sources are generated deterministically by [`tools/create-player-car-sprites.py`](tools/create-player-car-sprites.py); other current v3 sources were generated for this project and then extracted, fitted, and refined through the documented texture pipeline.

See [LICENSE](LICENSE) and [`assets/racer/texture-research/README.md`](assets/racer/texture-research/README.md) for the license and asset research record.

Javascript Racer, OutRun, Roblox, and their respective names and marks belong to their respective owners. This port is not affiliated with or endorsed by Jake Gordon, Sega, or Roblox; the repository license grants only the rights held by this project's contributors.
