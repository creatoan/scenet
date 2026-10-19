"""The artwork contract: what a supplied picture draws, in its own pixels (#71)."""

import hashlib
from pathlib import Path

import pytest

from scenet.assets.artwork import (
    CONTRACT_RULE,
    ArtworkContract,
    ContractError,
    contract_path,
    load_contract,
)
from scenet.errors import PanelSyntaxError
from scenet.images import SuppliedImage, load_image
from tests.images import contract, png

ANA = {"face": {"center": [100, 50], "radius": 20}, "mouth": [100, 60]}
LOC = ("setting", "image")


def _picture(width: int = 300, height: int = 200) -> SuppliedImage:
    return load_image("art/a.png", {"art/a.png": png(width, height)}, loc=LOC)


def _load(text: str | bytes, *, picture: SuppliedImage | None = None):
    data = text.encode("utf-8") if isinstance(text, str) else text
    return load_contract(picture or _picture(), {"art/a.art.yaml": data}, loc=LOC)


def _fault(text: str | bytes) -> ContractError:
    with pytest.raises(ContractError) as caught:
        _load(text)
    error = caught.value
    assert error.rule == CONTRACT_RULE
    assert error.loc == LOC
    return error


class TestWhereItIs:
    @pytest.mark.parametrize(
        ("image", "expected"),
        [
            ("art/p01-street.png", "art/p01-street.art.yaml"),
            ("p01.jpg", "p01.art.yaml"),
            ("cover.final.jpeg", "cover.final.art.yaml"),
            ("a/b/c/x.PNG", "a/b/c/x.art.yaml"),
        ],
    )
    def test_beside_its_picture_with_the_extension_replaced(self, image: str, expected: str):
        assert contract_path(image) == expected

    def test_a_picture_written_with_dot_slash_finds_it_among_files_sent(self):
        picture = load_image("./art/a.png", {"art/a.png": png(300, 200)}, loc=LOC)
        loaded = load_contract(picture, {"art/a.art.yaml": contract((300, 200))}, loc=LOC)
        assert loaded.contract.size == (300, 200)

    def test_in_a_folder(self, tmp_path: Path):
        (tmp_path / "art").mkdir()
        (tmp_path / "art" / "a.png").write_bytes(png(300, 200))
        (tmp_path / "art" / "a.art.yaml").write_bytes(contract((300, 200), {"ana": ANA}))
        picture = load_image("art/a.png", tmp_path, loc=LOC)
        assert list(load_contract(picture, tmp_path, loc=LOC).contract.figures) == ["ana"]

    def test_a_missing_contract_is_reported_where_the_picture_is_named(self):
        with pytest.raises(PanelSyntaxError) as caught:
            load_contract(_picture(), {}, loc=LOC)
        assert not isinstance(caught.value, ContractError)
        assert caught.value.rule == CONTRACT_RULE
        assert caught.value.loc == LOC
        assert "'art/a.art.yaml' was not found" in str(caught.value)

    def test_without_a_folder_it_cannot_be_read(self):
        with pytest.raises(PanelSyntaxError) as caught:
            load_contract(_picture(), None, loc=LOC)
        assert caught.value.rule == CONTRACT_RULE


class TestWhatItDeclares:
    def test_a_contract_reads_as_written(self):
        data = contract(
            (300, 200),
            {
                "ana": {**ANA, "body": [[60, 40], [140, 40], [150, 200], [50, 200]]},
                "ben": {"face": {"center": [250.5, 60], "radius": 18.25}},
            },
            keep_out=[[(0, 0), (40, 0), (40, 30), (0, 30)]],
        )
        loaded = _load(data)
        assert loaded.path == "art/a.art.yaml"
        assert loaded.sha256 == hashlib.sha256(data).hexdigest()
        ana, ben = loaded.contract.figures.values()
        assert ana.face.center == (100.0, 50.0)
        assert ana.mouth == (100.0, 60.0)
        assert ana.body is not None
        assert len(ana.body) == 4
        assert ben.mouth is None
        assert ben.body is None
        assert loaded.contract.keep_out[0][2] == (40.0, 30.0)

    def test_figures_keep_the_order_they_are_written_in(self):
        names = ["zed", "ana", "mo"]
        data = contract((300, 200), dict.fromkeys(names, ANA))
        assert list(_load(data).contract.figures) == names

    def test_a_contract_with_no_figures_is_valid(self):
        assert _load(contract((300, 200))).contract.figures == {}

    def test_points_on_the_picture_edge_are_on_it(self):
        edge = {"face": {"center": [0, 0], "radius": 5}, "mouth": [300, 200]}
        assert _load(contract((300, 200), {"ana": edge})).contract.figures["ana"].mouth == (
            300.0,
            200.0,
        )


class TestEachFaultIsLocatedInTheContract:
    def test_an_unknown_key_is_named_at_its_line(self):
        error = _fault(
            "size: [300, 200]\nfigures:\n  ana:\n"
            "    face: {center: [1, 1], radius: 1}\n    mouht: [5, 5]\n"
        )
        assert error.inner == ("figures", "ana", "mouht")
        assert error.region is not None
        assert error.region.start.line == 5
        assert "'art/a.art.yaml', line 5" in str(error)
        assert "not a key an artwork contract has" in str(error)

    def test_a_radius_must_be_positive(self):
        error = _fault(contract((300, 200), {"ana": {"face": {"center": [1, 1], "radius": 0}}}))
        assert error.inner == ("figures", "ana", "face", "radius")
        assert error.region is not None
        assert error.region.start.line == 4

    @pytest.mark.parametrize("number", [".nan", ".inf", "-.inf"])
    def test_a_number_must_be_finite(self, number: str):
        error = _fault(
            f"size: [300, 200]\nfigures:\n  ana:\n    face: {{center: [{number}, 1], radius: 1}}\n"
        )
        assert error.inner[:4] == ("figures", "ana", "face", "center")

    @pytest.mark.parametrize(
        ("figure", "inner"),
        [
            ({"face": {"center": [301, 50], "radius": 5}}, ("figures", "ana", "face", "center")),
            (
                {"face": {"center": [10, 10], "radius": 5}, "mouth": [10, -1]},
                ("figures", "ana", "mouth"),
            ),
            (
                {"face": {"center": [10, 10], "radius": 5}, "body": [[0, 0], [10, 0], [10, 201]]},
                ("figures", "ana", "body", 2),
            ),
        ],
    )
    def test_a_point_off_the_picture_is_refused(
        self, figure: dict[str, object], inner: tuple[object, ...]
    ):
        error = _fault(contract((300, 200), {"ana": figure}))
        assert error.inner == inner
        assert "off the picture, which is 300 by 200 pixels" in str(error)

    def test_x_and_y_swapped_on_a_portrait_picture_is_caught(self):
        error = _fault(contract((300, 200), {"ana": {"face": {"center": [150, 250], "radius": 5}}}))
        assert error.inner == ("figures", "ana", "face", "center")

    def test_a_region_needs_three_corners(self):
        error = _fault(contract((300, 200), keep_out=[[(0, 0), (10, 10)]]))
        assert error.inner == ("keep_out", 0)

    @pytest.mark.parametrize(
        "region",
        [
            [(0, 0), (10, 10), (10, 0), (0, 10)],  # a bow tie: its edges cross
            [(0, 0), (5, 5), (10, 10)],  # three corners on one line: no inside
        ],
    )
    def test_a_region_must_be_a_simple_polygon(self, region: list[tuple[float, float]]):
        error = _fault(contract((300, 200), keep_out=[region]))
        assert error.inner == ("keep_out", 0)
        assert "simple polygon" in str(error)

    def test_a_body_must_be_a_simple_polygon(self):
        bow_tie = [[0, 0], [10, 10], [10, 0], [0, 10]]
        error = _fault(contract((300, 200), {"ana": {**ANA, "body": bow_tie}}))
        assert error.inner == ("figures", "ana", "body")

    def test_a_key_written_twice_is_found_at_the_second(self):
        error = _fault(
            "size: [300, 200]\nfigures:\n"
            "  ana: {face: {center: [1, 1], radius: 1}}\n"
            "  ana: {face: {center: [2, 2], radius: 1}}\n"
        )
        assert error.region is not None
        assert error.region.start.line == 4
        assert "appears twice" in str(error)

    def test_text_that_is_not_yaml_is_found_at_its_line(self):
        error = _fault("size: [300, 200]\nfigures: {ana: [unclosed\n")
        assert error.region is not None
        assert "not valid YAML" in str(error)

    @pytest.mark.parametrize("text", ["- a list\n", "just words\n", ""])
    def test_it_must_be_a_mapping(self, text: str):
        error = _fault(text)
        assert "must be a mapping" in str(error)
        assert error.region is None

    def test_it_must_be_text(self):
        error = _fault(b"\xff\xfe\x00size")
        assert "not UTF-8" in str(error)

    def test_a_missing_size_is_a_missing_key(self):
        error = _fault("figures: {}\n")
        assert error.inner == ("size",)

    def test_a_figure_with_no_face_is_refused(self):
        error = _fault("size: [300, 200]\nfigures:\n  ana: {mouth: [1, 1]}\n")
        assert error.inner == ("figures", "ana", "face")


class TestTheSizeIsThePictures:
    def test_a_contract_measured_on_another_export_is_refused_at_its_size(self):
        with pytest.raises(ContractError) as caught:
            _load(contract((600, 400), {"ana": ANA}))
        error = caught.value
        assert error.inner == ("size",)
        assert error.region is not None
        assert error.region.start.line == 1
        assert "measured on a picture 600 by 400 pixels" in str(error)
        assert "'art/a.png' is 300 by 200" in str(error)

    def test_even_one_pixel_out_is_another_picture(self):
        with pytest.raises(ContractError):
            _load(contract((300, 200)), picture=_picture(300, 201))


class TestTheModel:
    def test_is_strict_and_frozen(self):
        model = ArtworkContract.model_validate({"size": [3, 2]})
        with pytest.raises(ValueError, match="frozen"):
            model.size = (4, 2)  # ty: ignore[invalid-assignment]

    def test_a_figure_name_must_be_holdable_text(self):
        with pytest.raises(ValueError, match="control character"):
            ArtworkContract.model_validate(
                {"size": [3, 2], "figures": {"a\x00b": {"face": {"center": [1, 1], "radius": 1}}}}
            )
