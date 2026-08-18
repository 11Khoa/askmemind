# RAG Benchmark

- Dataset: `evaluation/datasets/rag_eval.json`
- Top K: `5`

## Summary

| Metric | Total | Pass/Hit Rate | MRR |
|---|---:|---:|---:|
| Retrieval | 18 | 11.11% | 0.11 |
| Citation Relevance | 18 | 11.11% | 0.11 |
| Citation Integrity | 18 | 100.00% | - |

## Retrieval By Question Language

| Language | Total | Hit Rate | MRR |
|---|---:|---:|---:|
| en | 9 | 22.22% | 0.22 |
| vi | 9 | 0.00% | 0.00 |

## Citation By Question Language

| Language | Total | Hit Rate | MRR |
|---|---:|---:|---:|
| en | 9 | 22.22% | 0.22 |
| vi | 9 | 0.00% | 0.00 |

## Retrieval Results

| Test ID | Language | Status | Expected Pages | Retrieved Pages | Matched Pages | Best Rank | MRR |
|---|---|---|---|---|---|---:|---:|
| chainlink_en_001 | en | PASS | [2, 6] | [6] | [6] | 1 | 1.00 |
| chainlink_en_002 | en | FAIL | [7, 8] | [2, 6, 57, 35] | - | - | 0.00 |
| chainlink_en_003 | en | FAIL | [9, 10] | [2, 35] | - | - | 0.00 |
| chainlink_en_004 | en | FAIL | [24, 25] | - | - | - | 0.00 |
| chainlink_en_005 | en | FAIL | [35] | - | - | - | 0.00 |
| chainlink_en_006 | en | FAIL | [43, 45] | - | - | - | 0.00 |
| chainlink_en_007 | en | PASS | [57, 58] | [57] | [57] | 1 | 1.00 |
| chainlink_en_008 | en | FAIL | [65, 70] | - | - | - | 0.00 |
| chainlink_en_009 | en | FAIL | [80, 81] | - | - | - | 0.00 |
| chainlink_vi_001 | vi | FAIL | [2, 6] | - | - | - | 0.00 |
| chainlink_vi_002 | vi | FAIL | [7, 8] | - | - | - | 0.00 |
| chainlink_vi_003 | vi | FAIL | [9, 10] | - | - | - | 0.00 |
| chainlink_vi_004 | vi | FAIL | [24, 25] | - | - | - | 0.00 |
| chainlink_vi_005 | vi | FAIL | [35] | - | - | - | 0.00 |
| chainlink_vi_006 | vi | FAIL | [43, 45] | - | - | - | 0.00 |
| chainlink_vi_007 | vi | FAIL | [57, 58] | - | - | - | 0.00 |
| chainlink_vi_008 | vi | FAIL | [65, 70] | - | - | - | 0.00 |
| chainlink_vi_009 | vi | FAIL | [80, 81] | - | - | - | 0.00 |

## Citation Results

| Test ID | Language | Status | Expected Pages | Cited Pages | Matched Pages | Best Rank | MRR |
|---|---|---|---|---|---|---:|---:|
| chainlink_en_001 | en | PASS | [2, 6] | [6] | [6] | 1 | 1.00 |
| chainlink_en_002 | en | FAIL | [7, 8] | [2, 6, 57, 35] | - | - | 0.00 |
| chainlink_en_003 | en | FAIL | [9, 10] | [2, 35] | - | - | 0.00 |
| chainlink_en_004 | en | FAIL | [24, 25] | - | - | - | 0.00 |
| chainlink_en_005 | en | FAIL | [35] | - | - | - | 0.00 |
| chainlink_en_006 | en | FAIL | [43, 45] | - | - | - | 0.00 |
| chainlink_en_007 | en | PASS | [57, 58] | [57] | [57] | 1 | 1.00 |
| chainlink_en_008 | en | FAIL | [65, 70] | - | - | - | 0.00 |
| chainlink_en_009 | en | FAIL | [80, 81] | - | - | - | 0.00 |
| chainlink_vi_001 | vi | FAIL | [2, 6] | - | - | - | 0.00 |
| chainlink_vi_002 | vi | FAIL | [7, 8] | - | - | - | 0.00 |
| chainlink_vi_003 | vi | FAIL | [9, 10] | - | - | - | 0.00 |
| chainlink_vi_004 | vi | FAIL | [24, 25] | - | - | - | 0.00 |
| chainlink_vi_005 | vi | FAIL | [35] | - | - | - | 0.00 |
| chainlink_vi_006 | vi | FAIL | [43, 45] | - | - | - | 0.00 |
| chainlink_vi_007 | vi | FAIL | [57, 58] | - | - | - | 0.00 |
| chainlink_vi_008 | vi | FAIL | [65, 70] | - | - | - | 0.00 |
| chainlink_vi_009 | vi | FAIL | [80, 81] | - | - | - | 0.00 |

## Citation Integrity Results

| Test ID | Language | Status | Retrieved Chunks | Citations | Errors |
|---|---|---|---:|---:|---|
| chainlink_en_001 | en | PASS | 1 | 1 | - |
| chainlink_en_002 | en | PASS | 4 | 4 | - |
| chainlink_en_003 | en | PASS | 2 | 2 | - |
| chainlink_en_004 | en | PASS | 0 | 0 | - |
| chainlink_en_005 | en | PASS | 0 | 0 | - |
| chainlink_en_006 | en | PASS | 0 | 0 | - |
| chainlink_en_007 | en | PASS | 1 | 1 | - |
| chainlink_en_008 | en | PASS | 0 | 0 | - |
| chainlink_en_009 | en | PASS | 0 | 0 | - |
| chainlink_vi_001 | vi | PASS | 0 | 0 | - |
| chainlink_vi_002 | vi | PASS | 0 | 0 | - |
| chainlink_vi_003 | vi | PASS | 0 | 0 | - |
| chainlink_vi_004 | vi | PASS | 0 | 0 | - |
| chainlink_vi_005 | vi | PASS | 0 | 0 | - |
| chainlink_vi_006 | vi | PASS | 0 | 0 | - |
| chainlink_vi_007 | vi | PASS | 0 | 0 | - |
| chainlink_vi_008 | vi | PASS | 0 | 0 | - |
| chainlink_vi_009 | vi | PASS | 0 | 0 | - |
