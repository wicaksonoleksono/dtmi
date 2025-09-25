from enum import Enum


class Filter(Enum):
    TEXT = "text"
    IMAGE = "image"
    ROW_TAB = "table_row"
    CAP_TAB = "table_caption"
    TENDIK = "tendik"

    @staticmethod
    def from_string(s: str):
        for member in Filter:
            if member.value == s:
                return member
        raise ValueError(f"'{s}' bukan jenis query yang valid.")



class Year(Enum):
    YEAR_SARJANA = "SARJANA"
    YEAR_MAGISTER = "MAGISTER"
    YEAR_DOKTOR = "DOKTOR"
    YEAR_GENERAL = "GENERAL"

    @staticmethod
    def from_string(s: str):
        for member in Year:
            if member.value == s:
                return member
        raise ValueError(f"'{s}' is not a valid year. Available years: SARJANA, MAGISTER, DOKTOR, GENERAL")

