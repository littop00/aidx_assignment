CATEGORY_MAJOR_MAP = {
    "HVAC": "HVAC",
    "EVAP": "HVAC",
    "HTR": "HVAC",
    "REAR MODE UNIT": "HVAC",
    "INLET DUCT": "HVAC",
    "REAR COOLER": "HVAC",
    "REAR EVAP": "HVAC",
    "CRFM": "CRFM",
    "ECOMP": "E-COMP",
    "TTMM": "TTMM",
}

def major_of(category):
    return CATEGORY_MAJOR_MAP.get(category, category or "기타")

CATEGORY_GROUP_MAP = {
    "HVAC": "HVAC ASS'Y", "EVAP": "HVAC ASS'Y", "HTR": "HVAC ASS'Y",
    "REAR COOLER": "REAR COOLER ASS'Y", "REAR EVAP": "REAR COOLER ASS'Y",
}

def group_of(category):
    return CATEGORY_GROUP_MAP.get(category, category)
