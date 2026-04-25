# Phase 3: Dependency Detection Core - Discussion Log (Assumptions Mode)

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the analysis.

**Date:** 2026-04-25
**Phase:** 03-dependency-detection-core
**Mode:** assumptions (--auto)
**Areas analyzed:** Module Architecture, Text Preprocessing, Signal Design, Weighted Scoring, Interface Contract

## Assumptions Presented

### Module Architecture
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| New file `src/bot/detection/dependency.py` (one-module-per-concern pattern) | Confident | `filters.py`, `fee_model.py`, `yes_no_arb.py` all follow this pattern |
| Single file, not subpackage (scope similar to `filters.py` at ~96 lines) | Likely | No existing subpackage pattern in detection module |

### Text Preprocessing
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Python stdlib only (`str.lower()` + `re.findall()`) | Confident | No NLP deps in `requirements.txt`; spaCy/transformers explicitly out of scope |
| 30-50 word hardcoded stopword frozenset | Likely | `fee_model.py` uses hardcoded frozensets for keyword matching |

### Signal Design
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| All signals use existing `question` field + `event_id` from `_event_groups` | Confident | `fee_model.py` line 55 and `cross_market.py` already use `question` |
| Regex extraction for numeric/time signals | Likely | No `import re` exists yet; no structured numeric/date fields on market dicts |

### Weighted Scoring
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Simple weighted linear combination (no ML) | Confident | Codebase uses arithmetic scoring throughout |
| Weights as function params (not BotConfig yet) | Likely | Phase 3 is standalone; BotConfig integration is Phase 4's job |

### Interface Contract
| Assumption | Confidence | Evidence |
|------------|-----------|----------|
| Single `classify_pair()` pure function returning `DependencyResult` dataclass | Confident | Phase 3 SC5 requires pure function; `ArbitrageOpportunity`, `FilterDiagnostics` precedent |

## Corrections Made

No corrections — all assumptions confirmed (--auto mode).

## Auto-Resolved

- Module structure: auto-selected single file `dependency.py` (recommended, matches codebase convention)
- Stopword list: auto-selected 30-50 word frozenset (balance between coverage and signal preservation)
- Numeric/time extraction: auto-selected simple regex patterns for 80% case (recommended)
- Weight storage: auto-selected function parameters with defaults (recommended, pure function contract)
