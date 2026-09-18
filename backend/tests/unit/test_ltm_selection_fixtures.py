"""Published cohort membership (SC-004). Requires a frozen calendar fixture to assert names."""

PUBLISHED_COHORTS = {
    "2020-08-27": {
        "ADANIGREEN", "AFFLE", "BSOFT", "DEEPAKNTR", "DIXON",
        "GRANULES", "INDIAMART", "LAURUSLABS", "NAVINFLUOR", "TATACOMM",
    },
    "2021-09-03": {
        "ADANIENSOL", "ADANIENT", "ATGL", "CGPOWER", "ELECON",
        "JSWENERGY", "PGEL", "SAREGAMA", "TEJASNET", "TTML",
    },
    "2022-09-09": {
        "ADANIPOWER", "ATGL", "CGPOWER", "CHENNPETRO", "ELGIEQUIP",
        "GMDCLTD", "JWL", "PGEL", "SCHAEFFLER", "TTML",
    },
    "2023-09-15": {
        "APARINDS", "FACT", "IRFC", "JINDALSAW", "JSL",
        "JWL", "MAZDOCK", "RVNL", "TARIL", "TITAGARH",
    },
    "2024-10-01": {
        "GALLANTT", "GVT&D", "IFCI", "INOXWIND", "NEULANDLAB",
        "PCBL", "PGEL", "TARIL", "TRENT", "WOCKPHARMA",
    },
    "2025-10-09": {
        "AIIL", "BSE", "CARTRADE", "FORCEMOT", "GABRIEL",
        "GALLANTT", "GVT&D", "LAURUSLABS", "PARADEEP", "SYRMA",
    },
}


def test_published_cohort_sizes():
    assert len(PUBLISHED_COHORTS) == 6
    for day, names in PUBLISHED_COHORTS.items():
        assert len(names) == 10, day
