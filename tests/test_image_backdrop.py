"""A supplied picture as a backdrop: placed, recorded in Panel Core, described (#70).

The solver is given the picture's size and nothing else, and resolves where it lands:
centred, scaled to fill the panel (`cover`) or to fit inside it (`contain`), never
stretched. Panel Core records that rectangle with the facts a renderer needs -- the path
as written, the media type, a digest of the bytes -- so the emitter decides nothing.

What the picture shows is unknown to the compiler, and that has three consequences
checked here: it costs a balloon nothing to sit on it, it does not move the camera, and
a generated description names no place and no hour, only the weather drawn over it.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scenet.core import CoreBackdrop, CoreImage, PanelCore
from scenet.frontends.yaml_front import parse_panel
from scenet.geom import BBox
from scenet.ir import Fit, SettingSpec, Weather
from scenet.pipeline import compile_source
from scenet.solve.backdrop import fit_box, seed_for, solve_backdrop
from scenet.solve.describe import describe
from tests.images import jpeg, png

PANEL = BBox(0.0, 0.0, 1200.0, 600.0)
CAST = "cast: {alice: {reference: alice, at: left_third}, bob: {reference: bob, at: right_third}}\n"
SCRIPT = (
    "script:\n"
    "  - say: {by: alice, text: 'Did you paint all this?'}\n"
    "  - say: {by: bob, text: Every brick.}\n"
)
FILES = {"art/street.png": png(960, 640), "art/tall.jpg": jpeg(640, 960)}


def _compile(setting: str, *, cast: str = CAST, script: str = SCRIPT) -> PanelCore:
    text = f"panel: {{size: [1200, 600]}}\n{cast}{script}{setting}"
    return compile_source(text, base=FILES).core


class TestTheFit:
    def test_cover_fills_the_panel_and_crops_what_overhangs_evenly(self):
        assert fit_box((960, 640), PANEL, Fit.COVER) == BBox(0.0, -100.0, 1200.0, 800.0)

    def test_contain_shows_the_whole_picture_centred(self):
        assert fit_box((960, 640), PANEL, Fit.CONTAIN) == BBox(150.0, 0.0, 900.0, 600.0)

    def test_a_tall_picture_overhangs_top_and_bottom_under_cover(self):
        assert fit_box((640, 960), PANEL, Fit.COVER) == BBox(0.0, -600.0, 1200.0, 1800.0)

    def test_a_tall_picture_leaves_the_sides_under_contain(self):
        assert fit_box((640, 960), PANEL, Fit.CONTAIN) == BBox(400.0, 0.0, 400.0, 600.0)

    @pytest.mark.parametrize("fit", list(Fit))
    def test_a_picture_the_panel_s_shape_fills_it_either_way(self, fit: Fit):
        assert fit_box((2400, 1200), PANEL, fit) == PANEL

    @pytest.mark.parametrize("pixels", [(1, 1), (7, 3), (3, 7), (4000, 3000), (1, 9999)])
    @pytest.mark.parametrize("fit", list(Fit))
    def test_never_stretched_always_centred(self, pixels: tuple[int, int], fit: Fit):
        box = fit_box(pixels, PANEL, fit)
        assert box.width / box.height == pytest.approx(pixels[0] / pixels[1])
        assert box.x + box.width / 2 == pytest.approx(PANEL.width / 2)
        assert box.y + box.height / 2 == pytest.approx(PANEL.height / 2)
        if fit is Fit.COVER:
            assert box.width >= PANEL.width - 1e-9
            assert box.height >= PANEL.height - 1e-9
            assert min(box.width - PANEL.width, box.height - PANEL.height) == pytest.approx(0)
        else:
            assert box.width <= PANEL.width + 1e-9
            assert box.height <= PANEL.height + 1e-9
            assert max(box.width - PANEL.width, box.height - PANEL.height) == pytest.approx(0)

    def test_a_panel_away_from_the_origin_is_fitted_where_it_is(self):
        shifted = BBox(100.0, 50.0, 1200.0, 600.0)
        assert fit_box((960, 640), shifted, Fit.CONTAIN) == BBox(250.0, 50.0, 900.0, 600.0)


class TestTheSolver:
    def test_an_image_alone_is_a_backdrop(self):
        """With clear weather and no masses there used to be nothing behind the cast."""
        backdrop = solve_backdrop(SettingSpec(image="art/a.png"), PANEL, pixels=(960, 640))
        assert backdrop is not None
        assert backdrop.image is not None
        assert backdrop.image.box == BBox(0.0, -100.0, 1200.0, 800.0)
        assert (backdrop.masses, backdrop.atmosphere, backdrop.horizon) == ((), None, None)

    def test_the_fit_defaults_to_cover(self):
        backdrop = solve_backdrop(SettingSpec(image="art/a.png"), PANEL, pixels=(960, 640))
        assert backdrop is not None
        assert backdrop.image is not None
        assert backdrop.image.fit is Fit.COVER

    def test_weather_is_drawn_over_it(self):
        setting = SettingSpec(image="art/a.png", weather=Weather.RAIN)
        backdrop = solve_backdrop(setting, PANEL, pixels=(960, 640))
        assert backdrop is not None
        assert backdrop.atmosphere is not None
        assert backdrop.atmosphere.streaks

    def test_the_picture_is_not_part_of_the_seed(self):
        """Renaming the file, or replacing the picture, does not move a raindrop."""
        one = SettingSpec(image="art/a.png", weather=Weather.RAIN)
        other = SettingSpec(image="art/elsewhere/b.jpg", fit=Fit.CONTAIN, weather=Weather.RAIN)
        assert seed_for(one, 1200, 600) == seed_for(other, 1200, 600)

    def test_it_is_no_cost_for_a_balloon(self):
        backdrop = solve_backdrop(SettingSpec(image="art/a.png"), PANEL, pixels=(960, 640))
        assert backdrop is not None
        assert backdrop.occluders() == ()

    def test_a_setting_without_a_picture_is_given_no_pixels(self):
        with pytest.raises(ValueError, match="pixels"):
            solve_backdrop(SettingSpec(), PANEL, pixels=(960, 640))

    def test_a_picture_needs_its_pixels(self):
        with pytest.raises(ValueError, match="pixels"):
            solve_backdrop(SettingSpec(image="art/a.png"), PANEL)


class TestPanelCore:
    def test_it_records_what_a_renderer_needs(self):
        image = _compile("setting: {image: art/street.png}\n").backdrop
        assert image is not None
        assert image.image is not None
        recorded = image.image
        assert recorded.href == "art/street.png"
        assert recorded.media_type == "image/png"
        assert recorded.pixels == (960, 640)
        assert recorded.fit is Fit.COVER
        assert recorded.preserve_aspect_ratio == "xMidYMid slice"
        assert (recorded.box.x, recorded.box.y, recorded.box.width, recorded.box.height) == (
            0.0,
            -100.0,
            1200.0,
            800.0,
        )

    def test_contain_is_svg_s_meet(self):
        backdrop = _compile("setting: {image: art/tall.jpg, fit: contain}\n").backdrop
        assert backdrop is not None
        assert backdrop.image is not None
        assert backdrop.image.preserve_aspect_ratio == "xMidYMid meet"
        assert backdrop.image.media_type == "image/jpeg"

    def test_the_digest_is_of_the_bytes(self):
        import hashlib  # noqa: PLC0415 -- only this test needs it

        backdrop = _compile("setting: {image: art/street.png}\n").backdrop
        assert backdrop is not None
        assert backdrop.image is not None
        assert backdrop.image.sha256 == hashlib.sha256(FILES["art/street.png"]).hexdigest()

    def test_the_json_has_no_horizon_over_a_picture(self):
        written = json.loads(_compile("setting: {image: art/street.png}\n").to_json())
        assert "horizon" not in written["backdrop"]
        assert written["backdrop"]["image"]["href"] == "art/street.png"
        assert written["format_version"] == 1

    def test_a_backdrop_of_masses_writes_no_image_key(self):
        written = json.loads(_compile("setting: {place: street}\n").to_json())
        assert "image" not in written["backdrop"]
        assert "horizon" in written["backdrop"]

    @pytest.mark.parametrize(
        "setting",
        [
            "setting: {image: art/street.png}\n",
            "setting: {image: art/tall.jpg, fit: contain, weather: snow}\n",
            "setting: {place: docks, weather: fog}\n",
        ],
    )
    def test_it_round_trips_byte_for_byte(self, setting: str):
        text = _compile(setting).to_json()
        assert PanelCore.from_json(text).to_json() == text

    @pytest.mark.parametrize("href", ["/srv/a.png", "C:/a.png", "art\\a.png", "", "art/\u0000.png"])
    def test_a_hand_edited_href_is_refused(self, href: str):
        backdrop = _compile("setting: {image: art/street.png}\n").backdrop
        assert backdrop is not None
        assert backdrop.image is not None
        payload = backdrop.image.model_dump(mode="json")
        with pytest.raises(ValidationError):
            CoreImage.model_validate({**payload, "href": href})

    def test_a_core_written_before_images_still_reads(self):
        old = {"horizon": 300.0, "seed": 7, "masses": []}
        assert CoreBackdrop.model_validate(old).image is None

    def test_it_is_byte_identical_across_runs(self):
        setting = "setting: {image: art/street.png, weather: rain}\n"
        assert _compile(setting).to_json() == _compile(setting).to_json()

    def test_no_folder_reaches_it(self, tmp_path: Path):
        art = tmp_path / "comic" / "art"
        art.mkdir(parents=True)
        (art / "street.png").write_bytes(FILES["art/street.png"])
        core = compile_source(
            f"{CAST}setting: {{image: art/street.png}}\n", base=tmp_path / "comic"
        ).core
        assert str(tmp_path) not in core.to_json()
        assert tmp_path.as_posix() not in core.to_json()


class TestNothingElseMoves:
    """The solver knows nothing of what the picture shows, so it changes nothing else."""

    def test_no_balloon_moves(self):
        bare, painted = _compile(""), _compile("setting: {image: art/street.png}\n")
        assert painted.balloons == bare.balloons

    def test_the_camera_does_not_move(self):
        for shot in ("long_shot", "full_shot", "close_up"):
            camera = f"camera: {{shot: {shot}}}\n"
            bare = _compile(camera)
            painted = _compile(camera + "setting: {image: art/tall.jpg, fit: contain}\n")
            assert painted.actors == bare.actors, shot


class TestTheDescription:
    """Generated words name only what the compiler knows: never what the picture shows."""

    def test_no_place_and_no_hour_are_said(self):
        described = _compile("setting: {image: art/street.png, time: night}\n").description
        assert described is not None
        assert "Outdoors" not in described
        assert "night" not in described
        assert described.startswith("Medium shot. Alice")

    def test_the_weather_is_said_since_it_is_drawn(self):
        described = _compile("setting: {image: art/street.png, weather: rain}\n").description
        assert described is not None
        assert described.startswith("Medium shot. In the rain. Alice")

    def test_a_picture_with_nobody_in_it_is_not_called_empty(self):
        """A panel with no cast cannot be staged, but describing one is still defined."""
        panel = parse_panel("setting: {image: art/street.png}")
        assert describe(panel, {}, 1200.0) == "A panel with no figures."

    def test_weather_over_nobody_is_said(self):
        panel = parse_panel("setting: {image: art/street.png, weather: fog}")
        assert describe(panel, {}, 1200.0) == "In fog."

    def test_the_author_s_words_win(self):
        core = _compile(
            "setting: {image: art/street.png}\ndescription: A brick street at dusk, painted.\n"
        )
        assert core.description == "A brick street at dusk, painted."
