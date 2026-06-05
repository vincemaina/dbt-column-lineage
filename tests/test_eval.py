"""Regression gate over the evaluation harness (curated, hand-verified Snowflake patterns).
Fails if edge precision/recall or transform-chain accuracy drops below perfect on the known cases."""

from tests.eval_harness import run


def test_edge_precision_and_recall_perfect():
    for name, metrics in run().items():
        assert metrics["precision"] == 1.0, (name, "extra edges:", metrics["extra"])
        assert metrics["recall"] == 1.0, (name, "missing edges:", metrics["missing"])


def test_transform_chain_accuracy_perfect():
    for name, metrics in run().items():
        assert metrics["chain_acc"] == 1.0, (name, "chain mismatches:", metrics["chain_mismatch"])
