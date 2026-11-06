"""Country and nationality words the daily game hides in its excerpts.

"the Spanish port of Tarragona" would give the answer away, so these words are
replaced with a blank. Matching is case-sensitive (so "turkey" or "china" in
lower case stay); words that are often first names or common nouns ("Frank",
"Pole", "Union", "Maya") are left out and also covers a trailing plural "s" ("Romans", "Ottomans").
Current countries and the historical states and peoples that appear often in
Wikipedia's history articles are both listed.
"""

COUNTRIES = """
Afghanistan Albania Algeria Andorra Angola Argentina Armenia Australia Austria Azerbaijan
Bahamas Bahrain Bangladesh Barbados Belarus Belgium Belize Benin Bhutan Bolivia Bosnia
Herzegovina Botswana Brazil Brunei Bulgaria Burkina Burundi Cambodia Cameroon Canada Chile
China Colombia Comoros Congo Croatia Cuba Cyprus Czechia Czechoslovakia Denmark Djibouti
Dominica Ecuador Egypt Eritrea Estonia Eswatini Ethiopia Fiji Finland France Gabon Gambia
Georgia Germany Ghana Greece Grenada Guatemala Guinea Guyana Haiti Honduras Hungary Iceland
India Indonesia Iran Iraq Ireland Israel Italy Jamaica Japan Jordan Kazakhstan Kenya Kiribati
Korea Kosovo Kuwait Kyrgyzstan Laos Latvia Lebanon Lesotho Liberia Libya Liechtenstein
Lithuania Luxembourg Madagascar Malawi Malaysia Maldives Mali Malta Mauritania Mauritius
Mexico Micronesia Moldova Monaco Mongolia Montenegro Morocco Mozambique Myanmar Burma Namibia
Nauru Nepal Netherlands Nicaragua Niger Nigeria Macedonia Norway Oman Pakistan Palau
Palestine Panama Paraguay Peru Philippines Poland Portugal Qatar Romania Russia Rwanda Samoa
Senegal Serbia Seychelles Singapore Slovakia Slovenia Somalia Spain Sudan Suriname Sweden
Switzerland Syria Taiwan Tajikistan Tanzania Thailand Togo Tonga Trinidad Tobago Tunisia
Turkey Türkiye Turkmenistan Tuvalu Uganda Ukraine Uruguay Uzbekistan Vanuatu Venezuela Vietnam
Yemen Yugoslavia Zambia Zimbabwe Ceylon Persia Prussia Bavaria Saxony Siam Abyssinia Rhodesia
Zaire Bohemia Moravia Hispania Gaul Britannia Anatolia Mesopotamia Byzantium Carthage Macedon
Babylonia Assyria Phoenicia Judea Judaea Castile Aragon Navarre Granada Flanders Holland
Burgundy Brittany Normandy Wales Scotland England Britain Austria-Hungary Manchuria Tibet
Kurdistan Armenia Mughal Ottoman Seljuk
""".split() + [
    "United States", "United Kingdom", "Soviet Union", "New Zealand", "South Africa",
    "Saudi Arabia", "Sri Lanka", "Costa Rica", "El Salvador", "Ivory Coast", "Côte d'Ivoire",
    "Sierra Leone", "Papua New Guinea", "East Timor", "Timor-Leste", "Dominican Republic",
    "Czech Republic", "Central African Republic", "Equatorial Guinea", "Burkina Faso",
    "Cape Verde", "San Marino", "Vatican City", "Holy Roman Empire", "Papal States",
    "Byzantine Empire", "Roman Empire", "Russian Empire", "German Empire", "British Empire",
    "Ottoman Empire", "Mughal Empire", "Qing dynasty", "Ming dynasty", "Han dynasty",
    "Tang dynasty", "Song dynasty", "Yuan dynasty", "Kievan Rus'", "Polish–Lithuanian Commonwealth",
    "Great Britain", "North Korea", "South Korea", "North Vietnam", "South Vietnam",
    "East Germany", "West Germany", "Hong Kong", "Gold Coast", "New France", "New Spain",
    "Golden Horde", "Dutch Republic", "Low Countries", "Middle East", "Latin America",
    "Northern Ireland", "Bosnia and Herzegovina", "North Macedonia",
]

NATIONALITIES = """
Afghan Albanian Algerian American Angolan Argentine Argentinian Armenian Australian Austrian
Azerbaijani Bangladeshi Belarusian Belgian Bolivian Bosnian Brazilian British Briton Bulgarian
Burmese Cambodian Cameroonian Canadian Chilean Chinese Colombian Congolese Croatian Cuban
Cypriot Czech Danish Dane Dutch Ecuadorian Egyptian English Englishman Englishmen Eritrean
Estonian Ethiopian Filipino Finnish Finn French Frenchman Frenchmen Georgian German Ghanaian
Greek Guatemalan Haitian Honduran Hungarian Icelandic Indian Indonesian Iranian Iraqi Irish
Israeli Italian Jamaican Japanese Jordanian Kazakh Kenyan Korean Kuwaiti Kyrgyz Lao Laotian
Latvian Lebanese Liberian Libyan Lithuanian Malagasy Malaysian Malian Maltese Mexican
Moldovan Mongol Mongolian Montenegrin Moroccan Mozambican Namibian Nepalese Nepali
Nicaraguan Nigerian Nigerien Norwegian Omani Pakistani Palestinian Panamanian Paraguayan
Persian Peruvian Polish Portuguese Prussian Qatari Romanian Russian Rwandan Saudi
Scottish Scot Scots Senegalese Serbian Serb Sicilian Singaporean Slovak Slovene Slovenian
Somali Spanish Spaniard Sudanese Swedish Swede Swiss Syrian Taiwanese Tajik Tanzanian Thai
Tunisian Turkish Turk Turkmen Ugandan Ukrainian Uruguayan Uzbek Venezuelan Vietnamese Welsh
Yemeni Yugoslav Zambian Zimbabwean Soviet Byzantine Roman Ottoman Seljuk Mughal Habsburg
Bavarian Saxon Bohemian Castilian Aragonese Catalan Basque Navarrese Andalusian Flemish
Burgundian Breton Norman Gaulish Gallic Celtic Carthaginian Macedonian Athenian Spartan
Theban Corinthian Assyrian Babylonian Phoenician Hittite Sumerian Akkadian Judean Judaean
Hebrew Arab Arabian Berber Moorish Moor Saracen Kurdish Kurd Tatar Tartar Cossack Manchu
Tibetan Aztec Inca Incan Mayan Zulu Maori Māori Hawaiian Venetian Genoese Florentine
Milanese Neapolitan Sardinian Piedmontese Lombard Visigoth Visigothic Ostrogoth Ostrogothic
Goth Gothic Frankish Vandal Hun Viking Danish Anglo-Saxon Mercian Northumbrian Scythian
Parthian Sasanian Sassanid Achaemenid Seleucid Ptolemaic Abbasid Umayyad Fatimid Ayyubid
Mamluk Safavid Timurid Rajput Maratha Sikh Bengali Punjabi Gujarati Tamil Sinhalese Javanese
Balinese Malay Siamese Khmer Champa Annamese Korean Joseon Goryeo Silla Baekje Goguryeo
Yamato Ryukyuan Confederate Yankee Texan Californian Mexican Hispanic Iberian Hellenic
Anglo-French Anglo-Spanish Franco-Spanish Franco-Prussian Austro-Hungarian Russo-Japanese
Sino-Japanese Anglo-Dutch Franco-Dutch Polish-Lithuanian Anglo-Allied Franco-Italian
Indo-Pakistani Russo-Turkish Anglo-Scottish Anglo-Irish Anglo-American Franco-British
""".split() + ["Holy Roman", "Anglo-Saxons", "Native American"]
