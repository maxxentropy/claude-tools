# Evaluation Comparison Report

Generated: {{timestamp}}

## Evaluations Compared

| Property | Evaluation A | Evaluation B |
|----------|--------------|--------------|
| ID | {{eval_a.id}} | {{eval_b.id}} |
| Date | {{eval_a.date}} | {{eval_b.date}} |
| Model | {{eval_a.model}} | {{eval_b.model}} |
| Target | {{eval_a.target}} | {{eval_b.target}} |
| Total Findings | {{eval_a.finding_count}} | {{eval_b.finding_count}} |

## Metrics

| Metric | Value | Interpretation |
|--------|-------|----------------|
| Overlap (Jaccard) | {{metrics.overlap}} | % of findings in both evaluations |
| Precision (A→B) | {{metrics.precision}} | Of A's findings, % also in B |
| Recall (A→B) | {{metrics.recall}} | Of B's findings, % also in A |
| Severity Agreement | {{metrics.severity_agreement}} | Matched findings with same severity |
| Category Agreement | {{metrics.category_agreement}} | Matched findings with same category |

## Consistency Score: {{consistency_score}}

{{consistency_badge}}

---

## Finding Comparison

### Matched Findings ({{matched_count}})

| A Finding | B Finding | Match Type | Severity | Category |
|-----------|-----------|------------|----------|----------|
{{#matched}}
| {{a.id}} | {{b.id}} | {{match_type}} | {{severity_match}} | {{category_match}} |
{{/matched}}

### Only in A ({{only_a_count}}) - Potentially missed by B

{{#only_a}}
- **{{id}}**: {{title}} (`{{location}}`)
{{/only_a}}

### Only in B ({{only_b_count}}) - Potentially missed by A

{{#only_b}}
- **{{id}}**: {{title}} (`{{location}}`)
{{/only_b}}

---

## Score Comparison

| Category | A | B | Delta |
|----------|---|---|-------|
{{#categories}}
| {{name}} | {{score_a}} | {{score_b}} | {{delta}} |
{{/categories}}
| **Overall** | {{overall_a}} | {{overall_b}} | {{overall_delta}} |

---

## Interpretation Guide

### Consistency Score Meaning

- **90-100%**: Excellent - Highly reproducible results
- **80-89%**: Good - Minor variations, acceptable for most purposes
- **60-79%**: Moderate - Significant variations, investigate differences
- **<60%**: Poor - Results not reproducible, review methodology

### When Findings Don't Match

1. **Different severity** - May indicate calibration differences
2. **Different category** - May be classification ambiguity
3. **Only in one** - Could be:
   - True miss (evaluation quality issue)
   - False positive (one evaluation wrong)
   - Scope difference (evaluated different areas)

### Recommended Actions

{{#action_items}}
- {{.}}
{{/action_items}}
