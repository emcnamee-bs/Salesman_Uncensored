import json

from astroturf.catalog import (
    format_catalog_summary,
    load_catalog,
    relevant_items,
)


def write(path, obj):
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path


def test_flat_list_of_dicts(tmp_path):
    p = write(
        tmp_path / "catalog.json",
        [
            {"name": "Venom Hoodie", "category": "Superheroes", "subcategory": "Marvel"},
            {"title": "Spiderman Tee", "theme": "Superheroes"},
        ],
    )
    items = load_catalog(p)
    assert len(items) == 2
    assert items[0].name == "Venom Hoodie"
    assert items[0].category == "Superheroes"
    assert items[1].name == "Spiderman Tee"


def test_nested_categories(tmp_path):
    p = write(
        tmp_path / "catalog.json",
        {
            "categories": [
                {
                    "name": "Superheroes",
                    "subcategories": [
                        {"name": "Marvel", "items": [{"name": "Venom Hoodie"}, {"name": "Spiderman Tee"}]},
                        {"name": "DC", "items": [{"name": "Batman Zip"}]},
                    ],
                },
                {"name": "Gaming", "subcategories": [{"name": "Retro", "items": ["Pixel Shirt"]}]},
            ]
        },
    )
    items = load_catalog(p)
    names = [i.name for i in items]
    assert "Venom Hoodie" in names
    assert "Batman Zip" in names
    assert "Pixel Shirt" in names
    venom = next(i for i in items if i.name == "Venom Hoodie")
    assert venom.category == "Superheroes"
    assert venom.subcategory == "Marvel"
    pixel = next(i for i in items if i.name == "Pixel Shirt")
    assert pixel.category == "Gaming" and pixel.subcategory == "Retro"


def test_key_hierarchy_shape(tmp_path):
    # shape where the hierarchy lives in dict KEYS, not values
    p = write(
        tmp_path / "catalog.json",
        {"categories": {"Superheroes": {"Marvel": ["Venom Hoodie"]}}},
    )
    items = load_catalog(p)
    assert len(items) == 1
    assert items[0].name == "Venom Hoodie"
    assert items[0].category == "Superheroes"
    assert items[0].subcategory == "Marvel"


def test_plain_strings_and_dedup(tmp_path):
    p = write(
        tmp_path / "catalog.json",
        {"items": ["Cool Mug", "cool mug", {"name": "Cool Mug"}]},
    )
    items = load_catalog(p)
    assert [i.name for i in items] == ["Cool Mug"]


def test_missing_file_raises(tmp_path):
    from astroturf.config import ConfigError

    try:
        load_catalog(tmp_path / "nope.json")
        assert False, "expected ConfigError"
    except ConfigError as e:
        assert "not found" in str(e)


def test_relevant_items_ranks_matches_first():
    items = [
        type("I", (), {"name": n, "category": "", "subcategory": "", "description": ""})()
        for n in ["Venom Hoodie", "Spiderman Tee", "Plain White Tee"]
    ]
    out = relevant_items(items, ["venom"])
    assert [i.name for i in out] == ["Venom Hoodie", "Spiderman Tee", "Plain White Tee"]


def test_relevant_items_fallback_first_ten():
    items = [
        type("I", (), {"name": f"Item {n}", "category": "", "subcategory": "", "description": ""})()
        for n in range(30)
    ]
    out = relevant_items(items, ["zebra"])
    assert len(out) == 10
    assert out[0].name == "Item 0"


def test_relevant_items_cap_25():
    items = [
        type("I", (), {"name": f"Hero Shirt {n}", "category": "", "subcategory": "", "description": ""})()
        for n in range(40)
    ]
    out = relevant_items(items, ["hero"])
    assert len(out) == 25


def test_format_catalog_summary_lines():
    items = [
        type("I", (), {"name": "Venom Hoodie", "category": "Superheroes", "subcategory": "Marvel", "description": ""})(),
        type("I", (), {"name": "Plain Tee", "category": "", "subcategory": "", "description": ""})(),
    ]
    text = format_catalog_summary(items)
    assert "Venom Hoodie" in text and "Superheroes" in text and "Marvel" in text
    assert "Plain Tee" in text
