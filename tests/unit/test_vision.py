"""Asking a model about a drawing area: places are grid cells, a yes with no place is not believed, and pictures stay local."""

import io

import pytest
from PIL import Image

from reviewpulse.interpreter import vision
from reviewpulse.llm.openai_compat import LLMError, OpenAICompatClient


class Says:
    def __init__(self, answer):
        self.answer, self.images = answer, None

    def complete(self, system, user, schema, images=()):
        self.images = images
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def test_a_yes_names_cells_and_a_yes_without_a_place_is_only_unsure():
    assert vision.ask(Says({"answer": "yes", "cells": ["B2", "B2", "Z9"]}), b"x", "a door") == {"answer": "yes", "cells": ["B2"]}
    assert vision.ask(Says({"answer": "yes", "cells": []}), b"x", "a door")["answer"] == "unsure"
    assert vision.ask(Says({"answer": "no", "cells": ["A1"]}), b"x", "a door") == {"answer": "no", "cells": []}
    assert vision.ask(Says(LLMError("down")), b"x", "a door")["answer"] == "error"


def test_the_grid_adds_a_margin_and_cells_map_back_into_the_area():
    png = vision.with_grid(Image.new("RGB", (400, 200), "white"))
    assert Image.open(io.BytesIO(png)).size == (400 + vision.MARGIN, 200 + vision.MARGIN)
    assert vision.cell_box("A1") == (0.0, 0.0, 0.25, 0.25)
    assert vision.cell_box("D4", within=(0.5, 0.5, 1.0, 1.0)) == (0.875, 0.875, 1.0, 1.0)


def test_tiles_cover_the_area_and_overlap():
    got = vision.tiles(2, 0.1)
    assert len(got) == 4 and got[0][0] == 0.0 and got[3][2] == 1.0
    assert got[0][2] > got[1][0]
    assert vision.tile_page_box((0.2, 0.2, 0.6, 0.4), (0.0, 0.0, 0.5, 0.5)) == pytest.approx((0.2, 0.2, 0.4, 0.3))


def test_tile_answers_combine_yes_over_unsure_over_no():
    yes = {"answer": "yes", "cells": ["A1"]}
    no, unsure = {"answer": "no", "cells": []}, {"answer": "unsure", "cells": []}
    whole = (0.0, 0.0, 1.0, 1.0)
    assert vision.combine([(whole, no), (whole, yes)])["answer"] == "yes"
    assert vision.combine([(whole, no), (whole, unsure)])["answer"] == "unsure"
    assert vision.combine([(whole, no), (whole, no)])["answer"] == "no"


def test_pictures_of_drawings_never_leave_the_network():
    outside = OpenAICompatClient("https://api.example.com/v1", "k", "m", provider="hosted")
    with pytest.raises(LLMError, match="not sent"):
        outside.complete("s", "u", {"type": "object"}, images=(b"png",))


def test_a_picture_goes_with_the_question_to_a_local_model(monkeypatch):
    sent = {}

    def post(self, body):
        sent.update(body)
        return {"choices": [{"message": {"content": '{"answer": "no", "cells": []}'}}], "usage": {}}

    monkeypatch.setattr(OpenAICompatClient, "_post", post)
    local = OpenAICompatClient("http://127.0.0.1:1/v1", None, "m", structured="json_schema")
    assert local.complete("s", "is it there?", vision.SCHEMA, images=(b"abc",))["answer"] == "no"
    content = sent["messages"][1]["content"]
    assert content[0]["image_url"]["url"].startswith("data:image/png;base64,") and content[-1]["text"] == "is it there?"
