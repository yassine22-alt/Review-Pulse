"""A sheet that says it is not to scale, with nothing but its title block for a ratio, gives no sizes."""

import pytest

from reviewpulse import pipeline
from reviewpulse.annotate.scale import not_to_scale, unmeasurable
from reviewpulse.app.service import PACKS_ROOT
from reviewpulse.engine.run import NO_SIZE, run
from reviewpulse.factgraph.from_building import MEASURED_FACTS, from_building
from reviewpulse.schema import BuildingModel, load
from reviewpulse.synth.make_plan import make_plan


@pytest.fixture(scope="module")
def model(tmp_path_factory):
    work = tmp_path_factory.mktemp("nts")
    made = make_plan(work / "plan", seed=3, png=False)
    pipeline.inspect(made["pdf"], work, run_id="run")
    pipeline.extract(work / "run")
    pipeline.build(work / "run")
    return load(BuildingModel, work / "run" / "building_0.json")


def marked(model, note, method):
    copy = model.model_copy(deep=True)
    copy.sheet.scale.method = method
    copy.sheet.texts.append(copy.sheet.texts[0].model_copy(update={"id": "nts", "text": note, "kind": "unknown"}))
    return copy


def sizes(model):
    graph = from_building(model)
    found = {k for n in graph.nodes for k in n.attrs if k in MEASURED_FACTS | {"exit_distance_m", "window_area_m2"}}
    return found | {k for e in graph.edges for k in e.attrs if k in MEASURED_FACTS}


def test_the_words_real_sheets_use_are_recognised(model):
    for words in ("FOR ILLUSTRATION ONLY        NO SCALE", "N.T.S.", "Not to scale"):
        assert not_to_scale(marked(model, words, "title_block").sheet)
    assert not not_to_scale(marked(model, "SCALE 1:100", "title_block").sheet)


def test_no_size_is_read_when_only_a_disowned_title_gives_the_ratio(model):
    disowned = marked(model, "NO SCALE", "title_block")
    assert unmeasurable(disowned.sheet) and sizes(disowned) == set()
    rules = pipeline.load_packs(PACKS_ROOT / "starter")
    measured = [f for f in run(disowned, rules) if NO_SIZE in f.message]
    assert measured and all(f.verdict == "NOT_EVALUATED" and f.detected is None for f in measured)
    assert not any(ch.isdigit() for f in measured for ch in f.message.split(":", 1)[-1])


def test_sizes_confirmed_by_written_dimensions_are_still_read(model):
    confirmed = marked(model, "NO SCALE", "dimension_consensus")
    assert unmeasurable(confirmed.sheet) is None and {"area_m2", "width_m"} <= sizes(confirmed)
