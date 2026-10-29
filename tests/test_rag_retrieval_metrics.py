"""Human-labelled retrieval metric tests; no PDF or live model required."""
import asyncio
import pytest
from aura.book_semantics import BookSemanticIndex


class FakeIndex(BookSemanticIndex):
    def __init__(self, results):
        self.results = results

    async def search(self, question, **kwargs):
        return [{'passage_id': passage_id} for passage_id in self.results[question]][:kwargs['limit']]


def test_precision_recall_mrr_and_hit():
    index = FakeIndex({'first': ['p2', 'p1', 'other'],
                       'second': ['other1', 'other2', 'other3']})
    cases = [{'question': 'first', 'gold_passage_ids': ['p1', 'p2', 'p3']},
             {'question': 'second', 'gold_passage_ids': ['missing']}]
    result = asyncio.run(index.evaluate_retrieval(cases, limit=3))
    assert result['hit_at_k'] == 0.5
    assert result['mrr'] == 0.5
    assert result['recall_at_k'] == 0.333
    assert result['precision_at_k'] == 0.333
    assert result['details'][0]['matched_gold'] == 2
    assert result['details'][0]['gold_count'] == 3


def test_duplicate_gold_ids_not_double_counted():
    index = FakeIndex({'first': ['p1', 'other', 'p2']})
    result = asyncio.run(index.evaluate_retrieval(
        [{'question': 'first', 'gold_passage_ids': ['p1', 'p1', 'p2']}], limit=3))
    assert result['recall_at_k'] == 1.0
    assert result['precision_at_k'] == 0.667
    assert result['mrr'] == 1.0


@pytest.mark.parametrize('cases,limit', [
    ([{'question': 'first', 'gold_passage_ids': []}], 3),
    ([{'question': 'first', 'gold_passage_ids': ['']}], 3),
    ([{'question': 'first', 'gold_passage_ids': ['p1']}], 0),
    ([{'question': 'first', 'gold_passage_ids': ['p1']}], 21),
])
def test_invalid_gold_sets_or_k_rejected(cases, limit):
    index = FakeIndex({'first': ['p1']})
    with pytest.raises(ValueError):
        asyncio.run(index.evaluate_retrieval(cases, limit=limit))
