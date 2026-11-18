"""Regions for the daily game's clues and hints.

``REGION_WORDS`` says in which part of the world a country, people or state
named in an excerpt lies. The game replaces such words with that region
("the [Southern Europe] port of Tarragona") instead of a bare blank, so the clue
stays readable and still points the player somewhere without naming the answer.
Words that are in no list (compounds like "Franco-Prussian", rare peoples) keep
a plain blank.

``REGION_POINTS`` are rough centres, used by the hint for events whose country is
unknown: the nearest centre names the region (or ocean) of the event.
"""

import math

REGION_WORDS: dict[str, str] = {
    "Western Europe": """
        France French Frenchman Frenchmen Belgium Belgian Netherlands Dutch Holland Flanders Flemish
        Luxembourg Burgundy Burgundian Brittany Breton Normandy Norman Gaul Gaulish Gallic Frankish
        Monaco
    """,
    "British Isles": """
        England English Englishman Englishmen Britain British Briton Britannia Scotland Scottish Scot
        Scots Wales Welsh Ireland Irish Anglo-Saxon Mercian Northumbrian
    """,
    "Southern Europe": """
        Spain Spanish Spaniard Portugal Portuguese Italy Italian Greece Greek Malta Maltese Cyprus
        Cypriot Andorra Castile Castilian Aragon Aragonese Navarre Navarrese Catalan Basque Andalusian
        Granada Hispania Iberian Hellenic Athenian Spartan Theban Corinthian Venetian Genoese
        Florentine Milanese Neapolitan Sardinian Piedmontese Lombard Sicilian Visigoth Visigothic
        Ostrogoth Ostrogothic
    """,
    "Balkans": """
        Albania Albanian Croatia Croatian Slovenia Slovene Slovenian Bosnia Bosnian Herzegovina Serbia
        Serbian Serb Montenegro Montenegrin Kosovo Bulgaria Bulgarian Yugoslavia Yugoslav Macedonia
        Macedonian Macedon
    """,
    "Mediterranean": """
        Roman Byzantine Byzantium Carthage Carthaginian Phoenicia Phoenician
    """,
    "Central Europe": """
        Germany German Prussia Prussian Bavaria Bavarian Saxony Saxon Bohemia Bohemian Moravia Austria
        Austrian Habsburg Hungary Hungarian Czech Czechia Czechoslovakia Slovakia Slovak Poland Polish
        Switzerland Swiss Liechtenstein
    """,
    "Northern Europe": """
        Sweden Swedish Swede Denmark Danish Dane Norway Norwegian Finland Finnish Finn Iceland Icelandic
        Viking Estonia Estonian Latvia Latvian Lithuania Lithuanian
    """,
    "Eastern Europe": """
        Russia Russian Soviet Ukraine Ukrainian Belarus Belarusian Moldova Moldovan Romania Romanian
        Cossack Tatar Tartar Scythian
    """,
    "Middle East": """
        Turkey Türkiye Turkish Turk Ottoman Anatolia Persia Persian Iran Iranian Iraq Iraqi Syria Syrian
        Lebanon Lebanese Israel Israeli Palestine Palestinian Jordan Jordanian Saudi Yemen Yemeni
        Kuwait Kuwaiti Oman Omani Qatar Qatari Bahrain Mesopotamia Assyria Assyrian Babylonia
        Babylonian Hittite Sumerian Akkadian Judea Judaea Judean Judaean Hebrew Arab Arabian Saracen
        Seljuk Abbasid Umayyad Safavid Sasanian Sassanid Achaemenid Parthian Seleucid Kurdistan
        Kurdish Kurd Mamluk
    """,
    "Caucasus": "Armenia Armenian Azerbaijan Azerbaijani Georgia Georgian",
    "North Africa": """
        Egypt Egyptian Libya Libyan Tunisia Tunisian Algeria Algerian Morocco Moroccan Berber Moorish
        Moor Ptolemaic Sudan Sudanese Mauritania Fatimid Ayyubid
    """,
    "Sub-Saharan Africa": """
        Ethiopia Ethiopian Abyssinia Eritrea Eritrean Somalia Somali Kenya Kenyan Uganda Ugandan
        Tanzania Tanzanian Rwanda Rwandan Burundi Nigeria Nigerian Ghana Ghanaian Senegal Senegalese
        Mali Malian Niger Nigerien Cameroon Cameroonian Congo Congolese Zaire Angola Angolan
        Mozambique Mozambican Zambia Zambian Zimbabwe Zimbabwean Rhodesia Namibia Namibian Botswana
        Zulu Madagascar Malagasy Liberia Liberian Gambia Guinea Benin Togo Gabon Malawi Lesotho
        Eswatini Comoros Djibouti Mauritius Seychelles Burkina Chad Chadian
    """,
    "Central Asia": """
        Afghanistan Afghan Kazakhstan Kazakh Kyrgyzstan Kyrgyz Tajikistan Tajik Turkmenistan Turkmen
        Uzbekistan Uzbek Timurid
    """,
    "South Asia": """
        India Indian Pakistan Pakistani Bangladesh Bangladeshi Nepal Nepali Nepalese Bhutan Ceylon
        Sinhalese Mughal Rajput Maratha Sikh Bengali Punjabi Gujarati Tamil Maldives
    """,
    "East Asia": """
        China Chinese Japan Japanese Korea Korean Taiwan Taiwanese Mongolia Mongolian Mongol Manchuria
        Manchu Tibet Tibetan Joseon Goryeo Silla Baekje Goguryeo Yamato Ryukyuan
    """,
    "Southeast Asia": """
        Vietnam Vietnamese Thailand Thai Siam Siamese Cambodia Cambodian Khmer Laos Lao Laotian Myanmar
        Burma Burmese Malaysia Malaysian Malay Indonesia Indonesian Javanese Balinese Philippines
        Philippine Filipino Singapore Singaporean Brunei Champa Annamese
    """,
    "North America": """
        American Confederate Yankee Texan Californian Canada Canadian
    """,
    "Central America and the Caribbean": """
        Mexico Mexican Cuba Cuban Haiti Haitian Jamaica Jamaican Guatemala Guatemalan Honduras Honduran
        Nicaragua Nicaraguan Panama Panamanian Dominica Bahamas Barbados Grenada Belize Trinidad Tobago
        Hispanic Aztec Mayan
    """,
    "South America": """
        Brazil Brazilian Argentina Argentine Argentinian Chile Chilean Colombia Colombian Peru Peruvian
        Venezuela Venezuelan Bolivia Bolivian Ecuador Ecuadorian Paraguay Paraguayan Uruguay Uruguayan
        Guyana Suriname Inca Incan
    """,
    "Oceania": """
        Australia Australian Maori Māori Hawaiian Fiji Samoa Tonga Vanuatu Kiribati Nauru Palau
        Micronesia Tuvalu
    """,
}

# Multi-word names (listed in place_words.COUNTRIES).
_PHRASES: dict[str, list[str]] = {
    "Western Europe": ["Low Countries", "Dutch Republic"],
    "British Isles": ["Great Britain", "United Kingdom", "Northern Ireland", "British Empire", "Anglo-Saxons"],
    "Southern Europe": ["San Marino", "Vatican City", "Papal States"],
    "Balkans": ["Bosnia and Herzegovina", "North Macedonia"],
    "Mediterranean": ["Roman Empire", "Byzantine Empire"],
    "Central Europe": ["Holy Roman Empire", "Holy Roman", "German Empire", "West Germany", "East Germany",
                       "Czech Republic", "Polish–Lithuanian Commonwealth", "Polish-Lithuanian",
                       "Austria-Hungary", "Austro-Hungarian"],
    "Eastern Europe": ["Soviet Union", "Russian Empire", "Golden Horde", "Kievan Rus'"],
    "Middle East": ["Ottoman Empire", "Saudi Arabia", "Middle East"],
    "Sub-Saharan Africa": ["South Africa", "Sierra Leone", "Ivory Coast", "Côte d'Ivoire", "Burkina Faso",
                           "Cape Verde", "Central African Republic", "Equatorial Guinea", "Gold Coast"],
    "South Asia": ["Sri Lanka", "Mughal Empire"],
    "East Asia": ["North Korea", "South Korea", "Hong Kong", "Qing dynasty", "Ming dynasty", "Han dynasty",
                  "Tang dynasty", "Song dynasty", "Yuan dynasty"],
    "Southeast Asia": ["North Vietnam", "South Vietnam", "East Timor", "Timor-Leste"],
    "North America": ["United States", "Native American", "New France"],
    "Central America and the Caribbean": ["Costa Rica", "El Salvador", "Dominican Republic", "New Spain"],
    "Latin America": ["Latin America"],
    "Oceania": ["New Zealand", "Papua New Guinea"],
}


def _build() -> dict[str, str]:
    lookup: dict[str, str] = {}
    for region, words in REGION_WORDS.items():
        for word in words.split():
            lookup.setdefault(word.lower(), region)
    for region, phrases in _PHRASES.items():
        for phrase in phrases:
            lookup.setdefault(phrase.lower(), region)
    return lookup


_LOOKUP = _build()


def region_of_word(word: str) -> str | None:
    """The region of a matched country/nationality word (also with a plural "s"), or None."""
    key = word.lower()
    for candidate in (key, key[:-2] if key.endswith("es") else None, key[:-1] if key.endswith("s") else None):
        if candidate and candidate in _LOOKUP:
            return _LOOKUP[candidate]
    return None


# (name, latitude, longitude): several centres can share a name. A name is
# used as in "it happened in <name>".
REGION_POINTS: tuple[tuple[str, float, float], ...] = (
    ("Western Europe", 48.0, 3.0), ("British Isles", 54.0, -3.0), ("Northern Europe", 61.0, 15.0),
    ("Southern Europe", 40.0, -4.0), ("Southern Europe", 42.0, 13.0), ("Southern Europe", 39.5, 22.0),
    ("Central Europe", 50.0, 15.0), ("Eastern Europe", 53.0, 32.0), ("Northern Asia", 62.0, 95.0),
    ("the Middle East", 31.0, 44.0), ("the Middle East", 38.5, 35.0), ("the Caucasus", 41.5, 44.5),
    ("Central Asia", 43.0, 65.0), ("South Asia", 24.0, 78.0), ("East Asia", 35.0, 113.0),
    ("East Asia", 36.0, 137.0), ("Southeast Asia", 12.0, 105.0), ("Southeast Asia", -3.0, 115.0),
    ("North Africa", 28.0, 12.0), ("North Africa", 27.0, 30.0), ("West Africa", 10.0, -3.0),
    ("East Africa", 4.0, 38.0), ("Central Africa", -2.0, 22.0), ("Southern Africa", -23.0, 25.0),
    ("North America", 45.0, -100.0), ("North America", 38.0, -88.0), ("North America", 58.0, -105.0),
    ("Central America and the Caribbean", 16.0, -80.0), ("South America", -15.0, -60.0),
    ("Australia and Oceania", -25.0, 135.0), ("Australia and Oceania", -40.0, 174.0),
    ("the Pacific Ocean", 0.0, -150.0), ("the Pacific Ocean", 5.0, 170.0), ("the Pacific Ocean", -30.0, -110.0),
    ("the Atlantic Ocean", 28.0, -40.0), ("the Atlantic Ocean", -20.0, -15.0),
    ("the Indian Ocean", -15.0, 75.0), ("the Arctic", 80.0, 0.0), ("Antarctica", -80.0, 0.0),
)


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(a)))


def region_at(lat: float, lon: float) -> str:
    """The name of the region whose centre is nearest to the point (a rough guide, not borders)."""
    return min(REGION_POINTS, key=lambda p: _km(lat, lon, p[1], p[2]))[0]
