"""Curated English-to-Vietnamese medical/rehabilitation terminology.

Used by ``GoogleMedicalTranslator`` (see ``pdf2zh/translator.py``) to protect
clinical terms from Google Translate's generic, context-free word choice.
Google Translate has no medical context, so common clinical terms are
routinely mistranslated — e.g. "conduction" becomes "dẫn điện" (electrical
conduction) even in a heat-transfer passage, or a rehabilitation abbreviation
gets expanded into an unrelated everyday word. Every entry below is matched
in the source English text and swapped out before the request is sent, so
Google never gets a chance to choose a word for it; the curated Vietnamese
translation is restored verbatim after translation.

Edit this file directly to add, remove, or correct terms — no other code
needs to change for a new entry to take effect. Longer phrases are always
matched before shorter ones, so "congestive heart failure" is protected as
one phrase rather than being split into "heart" and "failure" separately.

Scope note: this is a fixed-translation glossary, not a context-aware
translator. It is deliberately conservative — every entry below has one
standard Vietnamese rendering regardless of surrounding sentence, which is
true for the great majority of anatomical, procedural, and rehabilitation
terms but not for every English medical word (a handful are genuinely
ambiguous, e.g. "discharge" as in leaving hospital vs. wound discharge, and
are left out on purpose rather than guessed at). Review translated documents
before publication or clinical use, same as with any machine translation.
"""

from __future__ import annotations

import re

# Multi-word phrases and unambiguous single words, matched case-insensitively
# on a whole-word/whole-phrase basis. Keys are lowercase.
MEDICAL_GLOSSARY: dict[str, str] = {
    # --- General rehabilitation / physical therapy -------------------------
    "physical therapy": "vật lý trị liệu",
    "physical therapist": "kỹ thuật viên vật lý trị liệu",
    "occupational therapy": "hoạt động trị liệu",
    "occupational therapist": "kỹ thuật viên hoạt động trị liệu",
    "range of motion": "tầm vận động",
    "active range of motion": "tầm vận động chủ động",
    "passive range of motion": "tầm vận động thụ động",
    "active-assisted range of motion": "tầm vận động chủ động có trợ giúp",
    "activities of daily living": "hoạt động sinh hoạt hàng ngày",
    "therapeutic exercise": "bài tập trị liệu",
    "home exercise program": "chương trình bài tập tại nhà",
    "resistance training": "tập luyện đề kháng",
    "resistance exercise": "bài tập đề kháng",
    "strength training": "tập luyện sức mạnh",
    "strengthening exercise": "bài tập tăng cường sức mạnh",
    "muscle strength": "sức mạnh cơ",
    "muscle strengthening": "tăng cường sức mạnh cơ",
    "stretching exercise": "bài tập kéo giãn",
    "joint mobilization": "di động khớp",
    "soft tissue mobilization": "di động mô mềm",
    "manual therapy": "trị liệu bằng tay",
    "aquatic therapy": "vật lý trị liệu dưới nước",
    "core stability": "ổn định vùng lõi",
    "core stabilization": "ổn định vùng lõi",
    "core strengthening": "tăng cường cơ vùng lõi",
    "proprioceptive neuromuscular facilitation": "tạo thuận cảm thụ bản thể thần kinh cơ",
    "gait training": "tập luyện dáng đi",
    "balance training": "tập luyện thăng bằng",
    "weight-bearing": "chịu trọng lượng",
    "non-weight-bearing": "không chịu trọng lượng",
    "partial weight-bearing": "chịu trọng lượng một phần",
    "isometric exercise": "bài tập đẳng trường",
    "isotonic exercise": "bài tập đẳng trương",
    "isokinetic exercise": "bài tập đẳng động",
    "assistive device": "dụng cụ hỗ trợ",
    "goniometer": "thước đo góc khớp",
    "manual muscle testing": "kiểm tra cơ bằng tay",

    # --- Orthopedics / spine ------------------------------------------------
    "discectomy": "phẫu thuật cắt đĩa đệm",
    "lumbar discectomy": "phẫu thuật cắt đĩa đệm thắt lưng",
    "microdiscectomy": "phẫu thuật vi phẫu cắt đĩa đệm",
    "laminectomy": "phẫu thuật cắt cung sau đốt sống",
    "herniated disc": "thoát vị đĩa đệm",
    "disc herniation": "thoát vị đĩa đệm",
    "intervertebral disc": "đĩa đệm gian đốt sống",
    "lumbar spine": "cột sống thắt lưng",
    "cervical spine": "cột sống cổ",
    "thoracic spine": "cột sống ngực",
    "spinal fusion": "phẫu thuật hàn xương cột sống",
    "spinal stenosis": "hẹp ống sống",
    "sciatica": "đau thần kinh tọa",
    "radiculopathy": "bệnh rễ thần kinh",
    "post-operative": "hậu phẫu",
    "postoperative": "hậu phẫu",
    "post-surgical": "sau phẫu thuật",

    # --- Cardiology / cardiac ------------------------------------------------
    "cardiac transplant": "ghép tim",
    "heart transplant": "ghép tim",
    "cardiac rehabilitation": "phục hồi chức năng tim mạch",
    "cardiac rehab": "phục hồi chức năng tim mạch",
    "ejection fraction": "phân suất tống máu",
    "congestive heart failure": "suy tim sung huyết",
    "heart failure": "suy tim",
    "myocardial infarction": "nhồi máu cơ tim",
    "arrhythmia": "rối loạn nhịp tim",
    "immunosuppressant": "thuốc ức chế miễn dịch",
    "immunosuppression": "ức chế miễn dịch",
    "transplant rejection": "thải ghép",
    "graft rejection": "thải ghép",
    "pacemaker": "máy tạo nhịp tim",
    "echocardiogram": "siêu âm tim",

    # --- Respiratory / pulmonary ---------------------------------------------
    "pulmonary rehabilitation": "phục hồi chức năng hô hấp",
    "chronic obstructive pulmonary disease": "bệnh phổi tắc nghẽn mạn tính",
    "dyspnea": "khó thở",
    "shortness of breath": "khó thở",
    "oxygen saturation": "độ bão hòa oxy",
    "pursed-lip breathing": "thở chúm môi",
    "diaphragmatic breathing": "thở cơ hoành",
    "bronchodilator": "thuốc giãn phế quản",
    "spirometry": "đo chức năng hô hấp",

    # --- General clinical -----------------------------------------------------
    "contraindication": "chống chỉ định",
    "precaution": "thận trọng",
    "informed consent": "đồng ý sau khi được thông tin",
    "vital signs": "dấu hiệu sinh tồn",
    "adverse event": "biến cố bất lợi",
    "follow-up appointment": "lịch tái khám",
    "discharge instructions": "hướng dẫn xuất viện",
    "differential diagnosis": "chẩn đoán phân biệt",
}

# Abbreviations, matched as exact-case whole words only (so "PT" is protected
# but not "pt" or "part"). Keep this list conservative: an abbreviation is
# only worth protecting here if it is effectively unambiguous inside a
# clinical/rehabilitation document, since a false match forces a fixed
# translation onto text that was never the medical term at all.
MEDICAL_ABBREVIATIONS: dict[str, str] = {
    "ROM": "tầm vận động",
    "PNF": "tạo thuận cảm thụ bản thể thần kinh cơ",
    "ADL": "hoạt động sinh hoạt hàng ngày",
    "ADLs": "hoạt động sinh hoạt hàng ngày",
    "COPD": "bệnh phổi tắc nghẽn mạn tính",
    "PT": "vật lý trị liệu",
    "OT": "hoạt động trị liệu",
}


def _phrase_pattern() -> re.Pattern[str]:
    terms = sorted(MEDICAL_GLOSSARY, key=len, reverse=True)
    escaped = "|".join(re.escape(term) for term in terms)
    return re.compile(rf"(?i:\b(?:{escaped})\b)")


def _abbreviation_pattern() -> re.Pattern[str]:
    terms = sorted(MEDICAL_ABBREVIATIONS, key=len, reverse=True)
    escaped = "|".join(re.escape(term) for term in terms)
    return re.compile(rf"\b(?:{escaped})\b")


# Compiled once at import time; the glossary above is static within a run.
_PHRASE_PATTERN = _phrase_pattern()
_ABBREVIATION_PATTERN = _abbreviation_pattern()
_RESTORE_PATTERN = re.compile(r"<m(\d+)></m\1>")


def protect_medical_terms(text: str) -> tuple[str, dict[str, str]]:
    """Swap known medical terms/abbreviations for numbered placeholder tags.

    Returns the tagged text plus a mapping from each tag's identifier to the
    Vietnamese text that should replace it after translation. Matches from
    the phrase glossary are resolved first (longest phrases first), then
    abbreviations are matched against whatever text is left, so a phrase
    match is never partially re-matched by an abbreviation.
    """
    mapping: dict[str, str] = {}
    counter = iter(range(10_000_000))

    def _tag(translation: str) -> str:
        index = next(counter)
        mapping[str(index)] = translation
        return f"<m{index}></m{index}>"

    def _sub_phrase(match: re.Match[str]) -> str:
        translation = MEDICAL_GLOSSARY.get(match.group(0).lower())
        return _tag(translation) if translation is not None else match.group(0)

    def _sub_abbreviation(match: re.Match[str]) -> str:
        translation = MEDICAL_ABBREVIATIONS.get(match.group(0))
        return _tag(translation) if translation is not None else match.group(0)

    text = _PHRASE_PATTERN.sub(_sub_phrase, text)
    text = _ABBREVIATION_PATTERN.sub(_sub_abbreviation, text)
    return text, mapping


def restore_medical_terms(translated: str, mapping: dict[str, str]) -> str:
    """Replace surviving placeholder tags with their curated Vietnamese text.

    A tag pair that Google's translation dropped or reordered in transit is
    stripped rather than raised as an error: losing one protected term is a
    quality regression for that phrase, not a corrupted document the way a
    lost formula placeholder would be, so this degrades gracefully instead
    of failing the whole segment or leaking raw "<m3></m3>"-style markup
    into the final PDF text.
    """
    if not mapping:
        return translated

    def _sub(match: re.Match[str]) -> str:
        return mapping.get(match.group(1), match.group(0))

    restored = _RESTORE_PATTERN.sub(_sub, translated)
    # Belt-and-suspenders: remove any tag fragment that didn't come back as a
    # clean pair (e.g. Google separated the two halves), instead of showing it.
    return re.sub(r"</?m\d+>", "", restored)
