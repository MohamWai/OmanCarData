"""Approximate coordinates for OpenSooq city/governorate labels in Oman."""

OMAN_CITY_COORDS: dict[str, tuple[float, float]] = {
    "Muscat": (23.5880, 58.3829),
    "Al Batinah": (24.1300, 56.6500),
    "Al Dakhiliya": (22.9333, 57.5333),
    "Al Dhahirah": (23.2254, 56.5150),
    "Al Sharqiya": (22.5667, 59.5289),
    "Al Wustaa": (19.9590, 56.2750),
    "Buraimi": (24.2500, 55.7830),
    "Dhofar": (17.0195, 54.0890),
    "Musandam": (26.1790, 56.2470),
}

# Major neighborhoods (mostly Muscat metro) for optional detail map.
OMAN_NEIGHBORHOOD_COORDS: dict[str, tuple[float, float]] = {
    "Al Maabilah": (23.561, 58.205),
    "Al Khoud": (23.601, 58.191),
    "Seeb": (23.670, 58.189),
    "Sohar": (24.364, 56.746),
    "Salala": (17.019, 54.092),
    "Barka": (23.678, 57.886),
    "Al-Hail": (23.534, 58.216),
    "Al Khuwair": (23.596, 58.454),
    "Nizwa": (22.933, 57.533),
    "Al Masnaah": (23.783, 57.617),
    "Amerat": (23.545, 58.492),
    "Suwaiq": (23.849, 57.439),
    "Azaiba": (23.582, 58.088),
    "Rustaq": (23.391, 57.424),
    "Al Mawaleh": (23.562, 58.089),
    "Bosher": (23.557, 58.382),
    "Halban": (23.562, 58.251),
    "Al Mouj": (23.625, 58.248),
    "Al Ansab": (23.551, 58.409),
    "Ansab": (23.551, 58.409),
}
