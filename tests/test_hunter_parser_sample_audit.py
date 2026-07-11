import unittest

from tools.hunter_parser_sample_audit import _classify_company_names


class HunterParserSampleAuditTests(unittest.TestCase):
    def test_company_classifier_splits_hard_errors_from_review_candidates(self):
        classification = _classify_company_names(
            [
                "Be responsible for Pfizer hospital channel of urology TA, Viagra and Cardura Pfizer",
                "contract sign off and handover. Novo Nordisk (China) Pharmaceuticals Co., Ltd.",
                "Hangzhou Merck & Sharp Dhome Pharmaceutical Co., Ltd.",
                "WuXi Clinical Development Services (Shanghai) Co., Ltd",
                "hospital and retail strategy and maximize value/margin with 1 Billion+ RMB",
                "receive the inspection and QC from self-company",
                "(Cross TA); HCP360; Internet Hospital & E-commerce platform; Micro-Targeting;",
                "colleges\\CAMH\\the key project management team s from Anzhen and Anding hospital s, etc.",
            ]
        )

        self.assertIn(
            "Be responsible for Pfizer hospital channel of urology TA, Viagra and Cardura Pfizer",
            classification["hard"],
        )
        self.assertIn(
            "contract sign off and handover. Novo Nordisk (China) Pharmaceuticals Co., Ltd.",
            classification["hard"],
        )
        self.assertIn(
            "hospital and retail strategy and maximize value/margin with 1 Billion+ RMB",
            classification["hard"],
        )
        self.assertIn("receive the inspection and QC from self-company", classification["hard"])
        self.assertIn("(Cross TA); HCP360; Internet Hospital & E-commerce platform; Micro-Targeting;", classification["hard"])
        self.assertIn(
            "colleges\\CAMH\\the key project management team s from Anzhen and Anding hospital s, etc.",
            classification["hard"],
        )
        self.assertIn("Hangzhou Merck & Sharp Dhome Pharmaceutical Co., Ltd.", classification["review"])
        self.assertIn("WuXi Clinical Development Services (Shanghai) Co., Ltd", classification["review"])
        self.assertNotIn("Hangzhou Merck & Sharp Dhome Pharmaceutical Co., Ltd.", classification["hard"])
        self.assertNotIn("WuXi Clinical Development Services (Shanghai) Co., Ltd", classification["hard"])


if __name__ == "__main__":
    unittest.main()
