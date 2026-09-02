from __future__ import annotations

import unittest
from unittest import mock

from pdf2zh.medical_glossary import (
    MEDICAL_ABBREVIATIONS,
    MEDICAL_GLOSSARY,
    protect_medical_terms,
    restore_medical_terms,
)
from pdf2zh.translator import ENGINES, GoogleMedicalTranslator


class ProtectMedicalTermsTests(unittest.TestCase):
    def test_protects_a_known_phrase_case_insensitively(self):
        protected, mapping = protect_medical_terms("Start Range Of Motion exercises today")
        self.assertNotIn("Range Of Motion", protected)
        self.assertEqual(len(mapping), 1)
        (translation,) = mapping.values()
        self.assertEqual(translation, MEDICAL_GLOSSARY["range of motion"])

    def test_prefers_the_longer_overlapping_phrase(self):
        protected, mapping = protect_medical_terms(
            "Discuss congestive heart failure with the patient"
        )
        self.assertEqual(len(mapping), 1)
        (translation,) = mapping.values()
        self.assertEqual(translation, MEDICAL_GLOSSARY["congestive heart failure"])

    def test_protects_an_exact_case_abbreviation_but_not_lowercase(self):
        protected, mapping = protect_medical_terms("Measure ROM before and after the rom check")
        self.assertEqual(len(mapping), 1)
        (translation,) = mapping.values()
        self.assertEqual(translation, MEDICAL_ABBREVIATIONS["ROM"])
        self.assertIn("rom check", protected)

    def test_leaves_ordinary_text_untouched(self):
        text = "The patient walked to the door and sat down."
        protected, mapping = protect_medical_terms(text)
        self.assertEqual(protected, text)
        self.assertEqual(mapping, {})

    def test_does_not_double_protect_a_phrase_containing_an_abbreviation_word(self):
        # "ADL" abbreviation and the phrase glossary must not both fire on the
        # same word inside an already-protected phrase.
        protected, mapping = protect_medical_terms("ADL training with the therapist")
        self.assertEqual(len(mapping), 1)


class RestoreMedicalTermsTests(unittest.TestCase):
    def test_restores_a_tag_pair_to_its_mapped_text(self):
        restored = restore_medical_terms("Hãy bắt đầu <m0></m0> ngay hôm nay", {"0": "tầm vận động"})
        self.assertEqual(restored, "Hãy bắt đầu tầm vận động ngay hôm nay")

    def test_strips_an_unresolved_tag_instead_of_leaking_markup(self):
        restored = restore_medical_terms("kết quả <m5></m5> không rõ", {"0": "x"})
        self.assertNotIn("<m5>", restored)
        self.assertNotIn("</m5>", restored)

    def test_no_op_with_an_empty_mapping(self):
        self.assertEqual(restore_medical_terms("plain text", {}), "plain text")


class GoogleMedicalTranslatorTests(unittest.TestCase):
    def test_registered_under_google_medical(self):
        self.assertIs(ENGINES["google-medical"], GoogleMedicalTranslator)

    def test_protects_then_restores_around_the_google_call(self):
        translator = GoogleMedicalTranslator.__new__(GoogleMedicalTranslator)
        with mock.patch.object(
            GoogleMedicalTranslator.__mro__[1],
            "do_translate",
            return_value="Hãy tăng <m0></m0> mỗi tuần",
        ) as parent_call:
            result = translator.do_translate("Increase range of motion every week")
        sent_text = parent_call.call_args.args[0]
        self.assertIn("<m0></m0>", sent_text)
        self.assertNotIn("range of motion", sent_text.lower())
        self.assertEqual(result, "Hãy tăng tầm vận động mỗi tuần")


if __name__ == "__main__":
    unittest.main()
