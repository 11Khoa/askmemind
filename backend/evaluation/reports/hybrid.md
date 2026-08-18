# RAG Benchmark

- Dataset: `evaluation/datasets/rag_eval.json`
- Top K: `5`

## Summary

| Metric | Total | Pass/Hit Rate | MRR |
|---|---:|---:|---:|
| Retrieval | 18 | 100.00% | 0.71 |
| Citation Relevance | 18 | 100.00% | 0.71 |
| Citation Integrity | 18 | 100.00% | - |

## Retrieval By Question Language

| Language | Total | Hit Rate | MRR |
|---|---:|---:|---:|
| en | 9 | 100.00% | 0.79 |
| vi | 9 | 100.00% | 0.62 |

## Citation By Question Language

| Language | Total | Hit Rate | MRR |
|---|---:|---:|---:|
| en | 9 | 100.00% | 0.79 |
| vi | 9 | 100.00% | 0.62 |

## Retrieval Results

| Test ID | Language | Status | Expected Pages | Retrieved Pages | Matched Pages | Best Rank | MRR |
|---|---|---|---|---|---|---:|---:|
| chainlink_en_001 | en | PASS | [2, 6] | [6, 1, 6, 2, 6] | [6, 6, 2, 6] | 1 | 1.00 |
| chainlink_en_002 | en | PASS | [7, 8] | [6, 2, 19, 7, 19] | [7] | 4 | 0.25 |
| chainlink_en_003 | en | PASS | [9, 10] | [9, 9, 9, 11, 11] | [9, 9, 9] | 1 | 1.00 |
| chainlink_en_004 | en | PASS | [24, 25] | [24, 25, 7, 7, 24] | [24, 25, 24] | 1 | 1.00 |
| chainlink_en_005 | en | PASS | [35] | [35, 35, 34, 35, 35] | [35, 35, 35, 35] | 1 | 1.00 |
| chainlink_en_006 | en | PASS | [43, 45] | [15, 45, 3, 43, 52] | [45, 43] | 2 | 0.50 |
| chainlink_en_007 | en | PASS | [57, 58] | [57, 27, 4, 11, 28] | [57] | 1 | 1.00 |
| chainlink_en_008 | en | PASS | [65, 70] | [65, 17, 102, 2, 65] | [65, 65] | 1 | 1.00 |
| chainlink_en_009 | en | PASS | [80, 81] | [17, 17, 80, 80, 1] | [80, 80] | 3 | 0.33 |
| chainlink_vi_001 | vi | PASS | [2, 6] | [1, 6, 6, 6, 2] | [6, 6, 6, 2] | 2 | 0.50 |
| chainlink_vi_002 | vi | PASS | [7, 8] | [6, 19, 7, 2, 8] | [7, 8] | 3 | 0.33 |
| chainlink_vi_003 | vi | PASS | [9, 10] | [9, 9, 42, 58, 11] | [9, 9] | 1 | 1.00 |
| chainlink_vi_004 | vi | PASS | [24, 25] | [24, 25, 7, 7, 24] | [24, 25, 24] | 1 | 1.00 |
| chainlink_vi_005 | vi | PASS | [35] | [35, 35, 37, 34, 35] | [35, 35, 35] | 1 | 1.00 |
| chainlink_vi_006 | vi | PASS | [43, 45] | [3, 52, 15, 43, 45] | [43, 45] | 4 | 0.25 |
| chainlink_vi_007 | vi | PASS | [57, 58] | [27, 4, 11, 28, 57] | [57] | 5 | 0.20 |
| chainlink_vi_008 | vi | PASS | [65, 70] | [65, 17, 2, 102, 65] | [65, 65] | 1 | 1.00 |
| chainlink_vi_009 | vi | PASS | [80, 81] | [17, 17, 80, 80, 1] | [80, 80] | 3 | 0.33 |

## Citation Results

| Test ID | Language | Status | Expected Pages | Cited Pages | Matched Pages | Best Rank | MRR |
|---|---|---|---|---|---|---:|---:|
| chainlink_en_001 | en | PASS | [2, 6] | [6, 1, 6, 2, 6] | [6, 6, 2, 6] | 1 | 1.00 |
| chainlink_en_002 | en | PASS | [7, 8] | [6, 2, 19, 7, 19] | [7] | 4 | 0.25 |
| chainlink_en_003 | en | PASS | [9, 10] | [9, 9, 9, 11, 11] | [9, 9, 9] | 1 | 1.00 |
| chainlink_en_004 | en | PASS | [24, 25] | [24, 25, 7, 7, 24] | [24, 25, 24] | 1 | 1.00 |
| chainlink_en_005 | en | PASS | [35] | [35, 35, 34, 35, 35] | [35, 35, 35, 35] | 1 | 1.00 |
| chainlink_en_006 | en | PASS | [43, 45] | [15, 45, 3, 43, 52] | [45, 43] | 2 | 0.50 |
| chainlink_en_007 | en | PASS | [57, 58] | [57, 27, 4, 11, 28] | [57] | 1 | 1.00 |
| chainlink_en_008 | en | PASS | [65, 70] | [65, 17, 102, 2, 65] | [65, 65] | 1 | 1.00 |
| chainlink_en_009 | en | PASS | [80, 81] | [17, 17, 80, 80, 1] | [80, 80] | 3 | 0.33 |
| chainlink_vi_001 | vi | PASS | [2, 6] | [1, 6, 6, 6, 2] | [6, 6, 6, 2] | 2 | 0.50 |
| chainlink_vi_002 | vi | PASS | [7, 8] | [6, 19, 7, 2, 8] | [7, 8] | 3 | 0.33 |
| chainlink_vi_003 | vi | PASS | [9, 10] | [9, 9, 42, 58, 11] | [9, 9] | 1 | 1.00 |
| chainlink_vi_004 | vi | PASS | [24, 25] | [24, 25, 7, 7, 24] | [24, 25, 24] | 1 | 1.00 |
| chainlink_vi_005 | vi | PASS | [35] | [35, 35, 37, 34, 35] | [35, 35, 35] | 1 | 1.00 |
| chainlink_vi_006 | vi | PASS | [43, 45] | [3, 52, 15, 43, 45] | [43, 45] | 4 | 0.25 |
| chainlink_vi_007 | vi | PASS | [57, 58] | [27, 4, 11, 28, 57] | [57] | 5 | 0.20 |
| chainlink_vi_008 | vi | PASS | [65, 70] | [65, 17, 2, 102, 65] | [65, 65] | 1 | 1.00 |
| chainlink_vi_009 | vi | PASS | [80, 81] | [17, 17, 80, 80, 1] | [80, 80] | 3 | 0.33 |

## Citation Integrity Results

| Test ID | Language | Status | Retrieved Chunks | Citations | Errors |
|---|---|---|---:|---:|---|
| chainlink_en_001 | en | PASS | 5 | 5 | - |
| chainlink_en_002 | en | PASS | 5 | 5 | - |
| chainlink_en_003 | en | PASS | 5 | 5 | - |
| chainlink_en_004 | en | PASS | 5 | 5 | - |
| chainlink_en_005 | en | PASS | 5 | 5 | - |
| chainlink_en_006 | en | PASS | 5 | 5 | - |
| chainlink_en_007 | en | PASS | 5 | 5 | - |
| chainlink_en_008 | en | PASS | 5 | 5 | - |
| chainlink_en_009 | en | PASS | 5 | 5 | - |
| chainlink_vi_001 | vi | PASS | 5 | 5 | - |
| chainlink_vi_002 | vi | PASS | 5 | 5 | - |
| chainlink_vi_003 | vi | PASS | 5 | 5 | - |
| chainlink_vi_004 | vi | PASS | 5 | 5 | - |
| chainlink_vi_005 | vi | PASS | 5 | 5 | - |
| chainlink_vi_006 | vi | PASS | 5 | 5 | - |
| chainlink_vi_007 | vi | PASS | 5 | 5 | - |
| chainlink_vi_008 | vi | PASS | 5 | 5 | - |
| chainlink_vi_009 | vi | PASS | 5 | 5 | - |
