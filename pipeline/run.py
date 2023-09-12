"""
This file holds the main run logic for the pipeline.
Author: rvorias
"""
import os
import sys
import click
from omegaconf import OmegaConf
from pathlib import Path

import numpy as np
import random as rand
from random import choice

import matplotlib.pyplot as plt
import PIL
import PIL.ImageOps
import skimage
import skimage.filters

import json
from functools import partial

import logging

logger = logging.getLogger("realms")

sys.path.append("terrain-erosion-3-ways/")
from river_network import *

sys.path.append("pipeline")
from svg_extraction import SVGExtractor, get_heightline_centers, get_city_coordinates
from image_ops import close_svg, slice_cont, generate_city, put_cities, extract_land_sea_direction
from utils import *

# from coloring import biomes, WATER_COLORS, color_from_json

def run_pipeline(realm_path, config="pipeline/config.yaml", debug=False):
    OUTPUT_SIZE = config.svg.output_size
    REL_SEA_SCALING = config.terrain.relative_sea_depth_scaling
    HSCALES = config.terrain.height_scales
    # hscale = choice(list(HSCALES))
    hscale = "hi"
    # PAD = config.pipeline.general_padding
    MAIN_OUTPUT_DIR = Path(config.pipeline.main_output_dir)
    RESOURCES_DIR = Path(config.pipeline.resources_dir)
    wind_directions = ("E", "SE", "S", "SW", "W", "NW", "N", "NE")

    DEBUG_IMG_SIZE = (10, 10)
    if debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    realm_number = int(realm_path.replace("svgs/", "").replace("svgs\\", "").replace(".svg", "").replace("../", ""))
    step = partial(Step, realm_number=realm_number)

    with step("Creating output folder if needed"):
        
        subdirs = [
            "colors",
            "directions",
            "errors",
            "flood_configs",
            "heights",
            "heights_no_cities",
            "hslices",
            "masks",
            "metadata",
            "palettes",
            "rivers",
        ]
        if not os.path.isdir(MAIN_OUTPUT_DIR):
            os.mkdir(MAIN_OUTPUT_DIR)
        for subdir in subdirs:
            if not os.path.isdir(MAIN_OUTPUT_DIR /subdir):
                os.mkdir(MAIN_OUTPUT_DIR / subdir)
            
    with step("Set seeds and init"):
        logging.info(f"Processing realm number: {realm_number}")
        np.random.seed(realm_number)
        rand.seed(realm_number)

    with step("Randomizing config parameters"):
        config.terrain.land.river_downcutting_constant = rand.uniform(0.1, 0.3)
        config.terrain.land.default_water_level = rand.uniform(0.9, 1.1)
        config.terrain.evaporation_rate = rand.uniform(0.1, 0.3)
        config.terrain.coastal_dropoff = rand.uniform(70, 90)

    with step("Setting up extractor"):
        extractor = SVGExtractor(realm_path, scale=config.svg.scaling)
        if debug:
            extractor.show(DEBUG_IMG_SIZE)

    with step("Extracting coast"):
        coast_drawing = extractor.coast()

    with step("Extracting heightlines"):
        heightline_drawing = extractor.height()

    #############################################
    # MASKING
    #############################################

    with step("Starting ground-sea mask logic"):
        # uses a fixed padding of 32
        # print(realm_number)
        mask = close_svg(coast_drawing, debug=debug, output_size=OUTPUT_SIZE, scaling=config.svg.scaling)
        print('mask_1', mask.size)

        centers = get_heightline_centers(heightline_drawing)
        sum = _sum = 0
        _mask = (mask - 1) // 255
        for center in centers:
            sum += mask[int(center[0]), int(center[1])]
            _sum += _mask[int(center[0]), int(center[1])]
        if _sum > sum:
            mask = _mask

        # add islands
        mask += close_svg(coast_drawing, debug=debug, islands_only=True)
        mask = mask.clip(0, 1)

        # extend land towards edges
        # h, w = mask.shape
        # for i in range(PAD):
        #     mask[:, i] = mask[:, PAD]
        #     mask[:, -i - 1] = mask[:, w - PAD]
        #     mask[i, :] = mask[PAD, :]
        #     mask[-i - 1, :] = mask[h - PAD, :]

        if debug:
            logger.debug(f"mask_shape: {mask.shape}")
            plt.figure(figsize=DEBUG_IMG_SIZE)
            plt.title("land-sea mask")
            plt.imshow(mask)
            plt.show()

    with step("---Calculating land-sea direction"):
        # direction = extract_land_sea_direction(mask[PAD:-PAD,PAD:-PAD], debug=debug)
        direction = extract_land_sea_direction(mask, debug=debug)
        with open(MAIN_OUTPUT_DIR / f"directions/{realm_number}_{direction:3f}.direction", "w") as file:
            file.write("")
        if debug:
            # imshow(mask[PAD:-PAD,PAD:-PAD], "cropped mask")
            imshow(mask, "cropped mask")

    # ------------------------------------------------------------------------------
    with step("----Extracting rivers"):
        extractor.rivers()
        rivers = np.asarray(extractor.get_img())  # rivers is now [0,255]
        original_rivers = rivers.copy()

        # make bit thicker
        rivers = skimage.filters.gaussian(
            rivers,
            sigma=config.pipeline.river_gaussian / config.pipeline.extra_scaling,
            channel_axis=-1
        )[..., 0]  # rivers is now [0,1]
        rivers = (rivers < 0.99) * 1
        rivers = rivers.astype(np.uint8)
        original_rivers = skimage.filters.gaussian(
            original_rivers,
            sigma=0.2,
            channel_axis=-1
        )[..., 0]  # rivers is now [0,1]
        original_rivers = (original_rivers < 0.85) * 1
        original_rivers = original_rivers.astype(np.uint8)

        if debug:
            plt.figure(figsize=DEBUG_IMG_SIZE)
            plt.title("fat rivers")
            plt.imshow(rivers)
            plt.show()
            plt.figure(figsize=DEBUG_IMG_SIZE)
            plt.title("original rivers")
            plt.imshow(original_rivers)
            plt.show()

    with step("----Combining coast and rivers"):
        final_mask = (mask & ~rivers) * 255
        anti_final_mask = np.where(final_mask == 255, 0, 255)
        if debug:
            print(f"unique final_mask: {np.unique(final_mask)}")
            print(f"unique mask: {np.unique(mask)}")
            print(f"unique rivers: {np.unique(rivers)}")
            plt.figure(figsize=DEBUG_IMG_SIZE)
            plt.title("final water")
            plt.imshow(final_mask)
            plt.show()

    #############################################
    # GENERATION
    #############################################

    # ------------------------------------------------------------------------------
    # image_scaling
    if config.pipeline.extra_scaling != 1:
        import scipy.ndimage
        final_mask = scipy.ndimage.zoom(final_mask, config.pipeline.extra_scaling, order=0)
        anti_final_mask = scipy.ndimage.zoom(anti_final_mask, config.pipeline.extra_scaling, order=0)
        rivers = scipy.ndimage.zoom(rivers, config.pipeline.extra_scaling, order=0)
        original_rivers = scipy.ndimage.zoom(original_rivers, config.pipeline.extra_scaling, order=0)

    with step("----Terrain generation"):
        wpad = config.terrain.water_padding
        if wpad > 0:
            wp = np.zeros(
                (final_mask.shape[0] + 2 * wpad,
                 final_mask.shape[1] + 2 * wpad))
            wp[wpad:-wpad, wpad:-wpad] = final_mask
            final_mask = wp
        terrain_height = generate_terrain(final_mask, **config.terrain.land)
        if debug:
            plt.figure(figsize=DEBUG_IMG_SIZE)
            plt.title("terrain height")
            plt.imshow(terrain_height)
            plt.show()

    # ------------------------------------------------------------------------------
    # with step("----Underwater generation"):
    #     wpad = config.terrain.water_padding
    #     if wpad > 0:
    #         wp = np.ones(
    #             (anti_final_mask.shape[0] + 2 * wpad,
    #              anti_final_mask.shape[1] + 2 * wpad)) * 255
    #         wp[wpad:-wpad, wpad:-wpad] = anti_final_mask
    #         anti_final_mask = wp
    #     water_depth = generate_terrain(anti_final_mask, **config.terrain.water)

    #     if debug:
    #         plt.figure(figsize=DEBUG_IMG_SIZE)
    #         plt.title("water depth pre scaling")
    #         plt.imshow(water_depth)
    #         plt.show()

    #     # some postprocessing to make sure that land is at 0
    #     land_level = np.where(anti_final_mask == 0, water_depth, 0)
    #     land_level_mean = (land_level[land_level > 0]).mean()
    #     # water_depth = water_depth.clip(land_level_mean, water_depth.max())
    #     # water_depth = norm(water_depth)
    #     if debug:
    #         print("sea stats")
    #         print(f"land_level_min = {land_level.min()}")
    #         print(f"land_level_max = {land_level.max()}")
    #         print(f"land_level_mean = {land_level_mean}")

    #         plt.figure(figsize=DEBUG_IMG_SIZE)
    #         plt.title("anti_final_mask")
    #         plt.imshow(anti_final_mask)
    #         plt.show()
    #         plt.figure(figsize=DEBUG_IMG_SIZE)
    #         plt.title("water depth")
    #         plt.imshow(water_depth)
    #         plt.show()

    # ------------------------------------------------------------------------------
    with step("----Combining terrain and water heights"):
        combined = terrain_height

        # final_mask = final_mask[wpad:-wpad, wpad:-wpad] if wpad > 0 else final_mask
        # _final_mask = final_mask < 255
        # terrain_height = terrain_height[wpad:-wpad, wpad:-wpad] if wpad > 0 else terrain_height
        # water_depth = water_depth[wpad:-wpad, wpad:-wpad] if wpad > 0 else water_depth

        # EXTRA_OFFSET = 0.04  # used to enchance contrast with rivers
        # combined = 1.1 * terrain_height - REL_SEA_SCALING * _final_mask * water_depth

        # fix rivers height
        # combined = np.where(((combined > 0) & (original_rivers > 0)), 55, combined)
        # combined = np.where(original_rivers > 0, REL_SEA_SCALING, combined+EXTRA_OFFSET)

        # if config.pipeline.extra_scaling != 1:
        #     PAD = int(PAD * config.pipeline.extra_scaling)
        # combined = combined[PAD:-PAD, PAD:-PAD]
        # final_mask = final_mask[PAD:-PAD, PAD:-PAD]

        # this snippet takes care of holes in the sea floor
        # sometimes the bottom layer gets remove so we just set one voxel to be the lowest.
        # co = np.unravel_index(np.argmin(combined, axis=None), combined.shape)
        # lowest_val = combined[co]
        # combined = combined.clip(combined.min()+0.02, combined.max())
        # combined[co] = lowest_val

        # if debug:
        #     plt.figure(figsize=DEBUG_IMG_SIZE)
        #     plt.title("combined map")
        #     plt.imshow(combined)
        #     plt.show()

    #############################################
    # CITIES
    #############################################

    # with step("Extracting cities"):
    #     cities_drawing = extractor.cities()
    #     city_centers = get_city_coordinates(cities_drawing)

    #############################################
    # EXPORT 1
    #############################################

    with step("Scaling height map"):
        hmap = norm(combined)

        # transform the sea level
        rescaled_coast_height = norm(0., combined)
        # rescale the height of the map
        if debug:
            print(f"hmap_min = {hmap.min()}.")
            print(f"hmap_max = {hmap.max()}.")
            print(f"rescaled coast height = {rescaled_coast_height}.")
        hmap = np.where(
            hmap > rescaled_coast_height,
            (hmap - rescaled_coast_height) * HSCALES[hscale] + rescaled_coast_height,
            hmap
        )
        if debug:
            print(f"Rescaling hmap.")
            print(f"hmap_min = {combined.min()}.")
            print(f"hmap_max = {combined.max()}.")
            print(f"combined_min = {combined.min()}.")
            print(f"combined_max = {combined.max()}.")
        # also scale the combined map, as this will be used for coloring
        combined = np.where(
            combined > 0,
            combined * HSCALES[hscale],
            combined
        )

        final_mask = np.where(
            final_mask > 0,
            final_mask * HSCALES[hscale],
            final_mask
        )

        if debug:
            print(f"Rescaling combined by {HSCALES[hscale]}.")
            print(f"combined_min = {combined.min()}.")
            print(f"combined_max = {combined.max()}.")

    # with step("Exporting height map without cities"):
    #     hmap_export = (hmap * 255).astype(np.uint8)
    #     hmap_export = PIL.Image.fromarray(hmap_export).convert('L')
    #     if config.export.size > 0:
    #         himg = hmap_export.resize(
    #             (config.export.size, config.export.size),
    #             PIL.Image.NEAREST
    #         )
    #     hmap_export = PIL.ImageOps.mirror(hmap_export)
    #     hmap_export.save(MAIN_OUTPUT_DIR / f"heights_no_cities/heightsnc_{realm_number}.png")

    # with step("Generating and drawing cities onto heightmap"):
    #     cities = []
    #     for city_center in city_centers:
    #         city_height, city_colors = generate_city(int(city_center[2] * config.pipeline.extra_scaling))
    #         cities.append((*city_center, city_height, city_colors))

    #     hmap_with_cities, _ = put_cities(
    #         cities,
    #         hmap=np.copy(hmap),
    #         extra_scaling=config.pipeline.extra_scaling,
    #         sealevel=rescaled_coast_height
    #     )
    #     hmap_cities = hmap_with_cities - hmap
    #     hmap = hmap_with_cities

    #     if debug:
    #         plt.figure(figsize=DEBUG_IMG_SIZE)
    #         plt.title("citied map")
    #         plt.imshow(hmap)
    #         plt.show()

    with step("Exporting height map"):
        hmap = (hmap * 255).astype(np.uint8)
        himg = PIL.Image.fromarray(hmap).convert('LA')

        # final_mask = (final_mask * 255).astype(np.uint8)
        mask_img = PIL.Image.fromarray(final_mask).convert('L')
        himg.putalpha(mask_img)
        
        if config.export.size > 0:
            himg = himg.resize("L",
                (config.export.size, config.export.size),
                PIL.Image.NEAREST
            )
        # himg = PIL.ImageOps.mirror(himg)
        himg.save(MAIN_OUTPUT_DIR / f"heights/height_{realm_number}.png")

    #############################################
    # COLORING
    #############################################

    # with step("Coloring"):
    #     rand.seed(realm_number)
    #     primary_biome = choice(biomes)
    #     water_color = choice(WATER_COLORS)
    #     secondary_biome = "none"
    #     # primary_colorqmap = run_coloring(biomes[primary_biome], combined)
    #     # secondary_colorqmap = run_coloring(biomes[secondary_biome], combined)
    #     primary_colorqmap = color_from_json(combined, primary_biome)
    #     # secondary_colorqmap = color_from_json(combined, secondary_biome)
    #     # biome_noise = generate_fractal_noise_2d(primary_colorqmap.shape[:2], (2,2), 5)
    #     # # mix biomes
    #     # biome_noise = np.expand_dims(biome_noise, -1)
    #     # biome_mask = np.expand_dims(final_mask[PAD:-PAD,PAD:-PAD], -1)
    #     # colorqmap = np.where(biome_mask*(biome_noise>0.1), secondary_colorqmap, primary_colorqmap)
    #     colorqmap = primary_colorqmap

    #     # if debug:
    #     #     plt.figure(figsize=DEBUG_IMG_SIZE)
    #     #     plt.title("anti final mask")

    #     #     plt.imshow(biome_mask*(biome_noise>0.1))
    #     #     plt.show()
    #     #     plt.figure(figsize=DEBUG_IMG_SIZE)
    #     #     plt.title("biome noise")
    #     #     plt.imshow(biome_noise>0)
    #     #     plt.show()
    #     #     print(f"primary biome: {primary_biome}")
    #     #     print(f"secondary biome: {secondary_biome}")

    #############################################
    # EXPORT 2
    #############################################

    # with step("Exporting color map"):
    #     colorqmap_export = colorqmap.astype(np.uint8)

    #     with step("Drawing cities onto colormap"):
    #         _, colorqmap_export = put_cities(
    #             cities,
    #             cmap=colorqmap_export,
    #             extra_scaling=config.pipeline.extra_scaling
    #         )

    #     with step("Injecting water color"):
    #         # oops, quick reconvert
    #         colorqmap = np.array(colorqmap_export)
    #         # colorqmap = inject_water_tile(colorqmap, final_mask, water_color) #m1 is the landmap
    #         colorqmap_export = colorqmap.astype(np.uint8)
    #         colorqmap_export = PIL.Image.fromarray(colorqmap_export)

    #     if config.export.size > 0:
    #         colorqmap_export = colorqmap_export.resize(
    #             (config.export.size, config.export.size),
    #             PIL.Image.NEAREST
    #         )

    #     if debug:
    #         cmap_debug = colorqmap.astype(np.uint8)
    #         plt.figure(figsize=DEBUG_IMG_SIZE)
    #         plt.title("pre-mirrored colormap")
    #         plt.imshow(colorqmap_export)
    #         plt.show()

    #     colorqmap_export = PIL.ImageOps.mirror(colorqmap_export)
    #     colorqmap_export.save(MAIN_OUTPUT_DIR / f"colors/color_{realm_number}.png")

    # with step("---Exporting mask and rivers"):
    #     original_pad = int(PAD/config.pipeline.extra_scaling)
    #     mask_export = PIL.Image.fromarray(mask[original_pad:-original_pad,original_pad:-original_pad]*255)
    #     if config.pipeline.extra_scaling != 1.:
    #         mask_export = mask_export.resize((int(mask_export.size[0]*config.pipeline.extra_scaling), int(mask_export.size[1]*config.pipeline.extra_scaling)))
    #     mask_export.save(MAIN_OUTPUT_DIR / f"masks/mask_{realm_number}.png")
    #     rivers_export = PIL.Image.fromarray(original_rivers[PAD:-PAD,PAD:-PAD]*255)
    #     rivers_export = PIL.ImageOps.mirror(rivers_export)
    #     rivers_export.save(MAIN_OUTPUT_DIR / f"rivers/rivers_{realm_number}.png")
        

    #############################################
    # Prepare for FileToVox
    #############################################

    # with step("Finding index of water tile"):
    #     # need to do an exhaustive check here
    #     colors_used = np.unique(np.reshape(colorqmap, [-1, 3]), axis=0)
    #     for i, c in enumerate(list(colors_used)):
    #         if np.array_equal(c, water_color):
    #             break
    #     water_index = len(list(colors_used)) - i
    #     logger.debug(f"water_index: {water_index}")

    #     with open(RESOURCES_DIR / "flood.json") as json_file:
    #         data = json.load(json_file)
    #     # change flooding water index
    #     data["steps"][0]["TargetColorIndex"] = water_index - 1
    #     data["steps"][0]["water_color"] = [
    #         int(water_color[0]),
    #         int(water_color[1]),
    #         int(water_color[2]),
    #     ]
    #     # data["steps"][0]["hm_param"] = HSCALES[hscale][1]
    #     # data["steps"][0]["Limit"] = HSCALES[hscale][2]
    #     with open(MAIN_OUTPUT_DIR / f"flood_configs/flood_{realm_number}.json", "w") as json_file:
    #         json.dump(data, json_file)

    #     palette = np.expand_dims(np.unique(np.reshape(colorqmap, (-1, 3)), axis=0), 0)
    #     palette = PIL.Image.fromarray(palette)

    #     palette.save(MAIN_OUTPUT_DIR / f"palettes/palette_{realm_number}.png")

    with step("Exporting metadata"):
        metadata = {
            # "primary_biome": primary_biome,
            "landscape_height": hscale,
            "wind_direction": get_wind_direction(direction)
        }
        with open(MAIN_OUTPUT_DIR / f"metadata/{realm_number}.json", "w") as json_file:
            json.dump(metadata, json_file)
        
    
    # with step("Creating slices"):
    #     slice_cont(
    #         hmap,
    #         colorqmap.astype(np.uint8),
    #         realm_number=realm_number,
    #         water_mask=_final_mask[PAD:-PAD, PAD:-PAD],
    #         water_color=water_color,
    #         hmap_cities=hmap_cities,
    #         output_dir=str(MAIN_OUTPUT_DIR / "hslices")
    #     )

    if debug:
        # also save intermediate files
        def export_np_array(arr, name):
            arr = arr.astype(np.uint8)
            img = PIL.Image.fromarray(arr)
            if config.export.size > 0:
                img = img.resize(
                    (config.export.size, config.export.size),
                    PIL.Image.NEAREST
                )
            # img = PIL.ImageOps.mirror(img)
            img.save(f"debug/debug_{name}.png")

        export_np_array(rivers, "rivers")
        export_np_array(final_mask, "final_mask")
        export_np_array(terrain_height, "terrain_height")
        # export_np_array(water_depth, "water_depth")

        return {
            "hmap": hmap,
            "combined": combined,
            "final_mask": final_mask,
            "terrain_height": terrain_height,
            # "water_depth": water_depth,
            "rivers": rivers,
            # "colormap": cmap_debug,
        }

    #############################################
    # VOX
    #############################################

    # subprocess.call(f"wine FileToVox-v1.13-win/FileToVox.exe \
    # --i output/height_{realm_number}.png \
    # -o MagicaVoxel-0.99.6.4-win64/vox/map_{realm_number} \
    # --hm=32 \
    # --cm output/color_{realm_number}.png", shell=True)


@click.command()
@click.argument("realm_path")
@click.option("--config", default="pipeline/config.yaml")
@click.option("--debug", default=False)
def parse(realm_path, config, debug):
    config = OmegaConf.load(config)
    run_pipeline(realm_path, config, debug)


if __name__ == "__main__":
    parse()
