# Voxel_realms

## About this fork

- Exact output texture size (`config.svg.output_size: 2000`)
- Rescale and remove padding from the SVG view box
- Render the height map at full size (no scaling, no blurring)
- Carve rivers into mountains instead of lowering them to sea level
- Use original river widths, not thicker
- Removed cities from the height map
- Disabled colors render
- Disabled underwater topology
- Added alpha channel (Sea is zero)

#### TODO

- We lost some mountain heights. Fix it! (compare with original)
- Carve rivers into land, do not level at sea.
- Move cities to the river sides, they are above water!
- Extract metadata
	- Cities position in viewbox, km grid, and tile
	- Cities height
	- Cities sizes (radius)
	- Cities strategic position (by the sea, by a river, on an island)
	- Region names
	- Region areas
	- Cities region (if possible)
	- Height map hash/checksum that can validate an x/y pixel to its height on-chain (if possible)


## Features
- data extraction for all svg elements: cities, coast, heightlines, names
- land-sea mask finding algorithm robust over many variations
- terrain generation for both land and sea, with rivers taken into account
- biomes can be composed through color functions that act on height data
- heightmap + colormap export to .vox format
- filling of the sea with water
- conversion of water from diffuse to glass material for see-through effect
- desired camera parameters are injected into the generated .vox file
- current maps are 700x700 pixels, with the current bottlenecks 1000x1000 is also possible

## Future work
- Rivers: shapes of rivers, making sure rivers have actual water in them.
- More water types, water color tied to biome
- More styles of terrain
- Better biome coloring, more biomes, biomes tied to realm resources
- Adding clouds to the .vox. (helps with setting the scale vibe)
- Automatic rendering (now have to click "render' button)
- Remove conversion bottlenecks so that higher scales are possible

## Requirements
This pipeline has been tested on linux, but will likely also
work on Windows. For linux you need Wine > 6.

## Quickstart
- Requires Python 3.7+
- Download Conversion tools and MV: `$ bash setup.sh` 
- Run `$ git submodule update --init --recursive`
- Install a venv e.g.: `pipenv install -r requirements.txt`
- Check out `notebooks/pipeline.ipynb`

## Acknowledgements
- https://github.com/ephtracy/ephtracy.github.io
- https://github.com/Zarbuz/FileToVox
- https://github.com/alexhunsley/numpy-vox-io
