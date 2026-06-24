"""V10 W1 Track B Day 2 — Map national-team names to eloratings.net codes.

eloratings.net uses non-standard 2-letter codes (mostly ISO 3166-1
alpha-2, but with edge cases like SQ for Scotland instead of SC).
This module is the canonical bridge between:

  - API-Football team names (e.g., "Scotland", "Türkiye", "Bosnia & Herzegovina")
  - eloratings.net country_code (e.g., "SQ", "TR", "BA")

Source of codes: scraped from https://www.eloratings.net/World.tsv
Verified manually for all 48 WC 2026 participants + 32 WC 2022.

If a team is missing here, add the mapping AND open the WC 2026 fixture
list to confirm we're not gating predictions on a country we can't score.
"""

# WC 2026 (48) + historical WC 2022 union. Add more as needed.
TEAM_NAME_TO_ELO_CODE: dict[str, str] = {
    # WC 2022 + 2026 overlap
    "Argentina":            "AR",
    "Australia":            "AU",
    "Belgium":              "BE",
    "Brazil":               "BR",
    "Cameroon":             "CM",
    "Canada":               "CA",
    "Costa Rica":           "CR",
    "Croatia":              "HR",
    "Denmark":              "DK",
    "Ecuador":              "EC",
    "England":              "EN",
    "France":               "FR",
    "Germany":              "DE",
    "Ghana":                "GH",
    "Iran":                 "IR",
    "Japan":                "JP",
    "Mexico":               "MX",
    "Morocco":              "MA",
    "Netherlands":          "NL",
    "Poland":               "PL",
    "Portugal":             "PT",
    "Qatar":                "QA",
    "Saudi Arabia":         "SA",
    "Senegal":              "SN",
    "Serbia":               "RS",
    "South Korea":          "KR",
    "Spain":                "ES",
    "Switzerland":          "CH",
    "Tunisia":              "TN",
    "USA":                  "US",
    "Uruguay":              "UY",
    "Wales":                "WA",
    # WC 2026 new entrants
    "Algeria":              "DZ",
    "Austria":              "AT",
    "Bosnia & Herzegovina": "BA",
    "Cape Verde Islands":   "CV",
    "Colombia":             "CO",
    "Congo DR":             "CD",
    "Curaçao":              "CW",
    "Czech Republic":       "CZ",
    "Egypt":                "EG",
    "Haiti":                "HT",
    "Iraq":                 "IQ",
    "Ivory Coast":          "CI",
    "Jordan":               "JO",
    "New Zealand":          "NZ",
    "Norway":               "NO",
    "Panama":               "PA",
    "Paraguay":             "PY",
    # eloratings: Scotland = SQ (not SC; SC is Seychelles)
    "Scotland":             "SQ",
    "South Africa":         "ZA",
    "Sweden":               "SE",
    # API-Football uses "Türkiye" (Turkish official); eloratings uses TR
    "Türkiye":              "TR",
    "Turkey":               "TR",   # legacy spelling alias
    "Uzbekistan":           "UZ",
    # Historical (WC 2018) additions for training-data completeness
    "Russia":               "RU",
    "Peru":                 "PE",
    "Iceland":              "IS",
    "Nigeria":              "NG",
    # Alternate spellings the cross-source feeds use interchangeably (FIFA /
    # official-short names). MEASURED, not guessed — the CLV name-join sentinel
    # surfaced "Czechia" live in odds_snapshots. See [[cross-source-team-name-mismatch]].
    "Czechia":              "CZ",   # = Czech Republic (Pinnacle/odds_snapshots spelling)
    "Korea Republic":       "KR",   # = South Korea (FIFA spelling)
}


def lookup_elo_code(team_name: str) -> str | None:
    """Return eloratings 2-letter code for a national team name, or None.

    Caller should treat None as "no Elo signal available" and fall back
    to a market-based prior (e.g., Pinnacle implied probability) rather
    than gating prediction entirely.
    """
    return TEAM_NAME_TO_ELO_CODE.get(team_name)


__all__ = ["TEAM_NAME_TO_ELO_CODE", "lookup_elo_code"]
