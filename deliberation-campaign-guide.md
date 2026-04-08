# Deliberation Campaign Matrix Benchmark Guide

This guide explains the repeated-deliberation campaign surface in the Swarm CLI, including both the canonical baseline/candidate benchmark and the multi-candidate matrix benchmark.

## Two knobs, two meanings

- `sample_count` is the outer loop. It tells Swarm how many comparable campaign samples to run.
- `stability_runs` is the inner loop. It tells each sample how many internal repeats to run to estimate intra-run stability.

They are related, but they do not do the same job.

`sample_count` is what you use when you want several comparable executions of the same deliberation configuration and then compare the results across samples.

`stability_runs` is what you use when you want one run to repeat itself and measure whether the same configuration stays stable within that run.

## What this does not mean

- It does not promise backend seed control.
- It does not imply deterministic backend sampling unless the backend itself already supports that.
- It does not replace runtime-level comparability metadata such as `runtime_used`, `engine_used`, `stability_sample_count`, or the guard flags.

## Reading status at a glance

- `completed`: all samples completed successfully.
- `partial`: some samples failed, but at least one sample completed.
- `failed`: no sample completed successfully.

For a quick read, the persisted report also surfaces `sample_count_completed`, `sample_count_failed`, `fallback_guard_applied`, and the score or confidence aggregates.

## Reading comparability mismatches

Use `compare-deliberation-campaigns` when you want a strict campaign-to-campaign read:

```bash
python main.py compare-deliberation-campaigns <campaign-a> <campaign-b>
python main.py compare-deliberation-campaigns --latest --json
```

The comparison report exposes:

- `summary.comparable` to say whether the selected campaigns are aligned enough for a like-for-like comparison
- `summary.mismatch_reasons` to explain where they diverge
- `entries` for the per-campaign metrics that were compared

## Audit And Export

The comparison command now persists a report under `data/deliberation_campaign_comparisons/<comparison-id>/report.json`.
The audit/export commands persist derived exports under `data/deliberation_campaign_comparison_exports/<export-id>/`, with a `manifest.json` plus `content.md` or `content.json`.
The canonical comparison report from the core bundle remains the source of truth; audit and export only materialize derived views around that report.

One-shot workflow:

1. Run `compare-deliberation-campaigns` to persist the canonical comparison report.
2. Run `audit-deliberation-campaign-comparison` if you want the structured audit view.
3. Run `export-deliberation-campaign-comparison` to materialize the derived export artifact.
4. Use `read-deliberation-campaign-comparison-export` or `list-deliberation-campaign-comparison-exports` to revisit the derived export later.

## Benchmark Matrix

When you want to benchmark two fresh campaign setups instead of only comparing already persisted reports, use `benchmark-deliberation-campaigns` in CLI or `benchmark_deliberation_campaigns` in MCP.

The intended flow is:

1. Run a baseline campaign.
2. Run a candidate campaign with the same shared evaluation context.
3. Feed both into the canonical comparison bundle from the core.
4. Materialize audit and export from that bundle.

This keeps the comparison logic in the core bundle helper, so CLI and MCP stay thin wrappers around the same source of truth.

The benchmark bundle is still intentionally compact: one baseline, one candidate, one persisted comparison, and the derived audit/export artifacts that hang off that pair.

The benchmark surface exposes the two campaign configurations explicitly, especially:

- baseline runtime and engine preference
- candidate runtime and engine preference
- shared topic, objective, sample count, and stability runs
- output directories for campaign reports, comparison reports, and exports

The reason for this shape is simple: it lets you compare how the same problem behaves under two setups without manually stitching the reports together afterward, while keeping the naming stable for the CLI, MCP, and persisted artifact paths.

The benchmark run itself is also persisted as its own artifact, so you can revisit the full baseline/candidate bundle later instead of only keeping the derived comparison:

- `read-deliberation-campaign-benchmark <benchmark-id>` to reopen the persisted benchmark report
- `list-deliberation-campaign-benchmarks` to browse recent benchmark runs
- `benchmark_deliberation_campaigns` in MCP for the same persisted benchmark surface

The persisted benchmark report lives under `data/deliberation_campaign_benchmarks/<benchmark-id>/report.json`, alongside the campaign, comparison, and export artifacts it created.

## Matrix Benchmark

When you want one shared baseline against several candidates, use the matrix surface:

```bash
python main.py benchmark-deliberation-campaign-matrix "Choose the launch strategy" \
  --baseline-runtime pydanticai \
  --candidate-runtime legacy \
  --candidate-runtime pydanticai \
  --candidate-engine-preference oasis \
  --candidate-engine-preference agentsociety \
  --matrix-id launch_matrix_demo \
  --json
```

This matrix command expands the candidate space as a runtime x engine grid, then persists one matrix artifact that references all candidate comparisons.

The matrix surface exposes:

- `benchmark-deliberation-campaign-matrix` in CLI
- `read-deliberation-campaign-benchmark-matrix <matrix-id>` in CLI
- `list-deliberation-campaign-benchmark-matrices` in CLI
- `audit-deliberation-campaign-benchmark-matrix <matrix-id>` in CLI
- `export-deliberation-campaign-benchmark-matrix <matrix-id>` in CLI
- `read-deliberation-campaign-benchmark-matrix-export <export-id>` in CLI
- `list-deliberation-campaign-benchmark-matrix-exports` in CLI
- `benchmark_deliberation_campaign_matrix` in MCP
- `read_deliberation_campaign_benchmark_matrix_artifact` in MCP
- `list_deliberation_campaign_benchmark_matrix_artifacts` in MCP
- `audit_deliberation_campaign_benchmark_matrix_artifact` in MCP
- `export_deliberation_campaign_benchmark_matrix_artifact` in MCP
- `read_deliberation_campaign_benchmark_matrix_export_artifact` in MCP
- `list_deliberation_campaign_benchmark_matrix_export_artifacts` in MCP

The persisted matrix report lives under `data/deliberation_campaign_matrix_benchmarks/<matrix-id>/report.json`.

## Matrix Benchmark Audit And Export

When you want a compact operator view of one persisted matrix benchmark, use the audit/export surface:

```bash
python main.py audit-deliberation-campaign-benchmark-matrix <matrix-id>
python main.py export-deliberation-campaign-benchmark-matrix <matrix-id> --format markdown
python main.py read-deliberation-campaign-benchmark-matrix-export <export-id> --json
python main.py list-deliberation-campaign-benchmark-matrix-exports --limit 10 --json
```

The corresponding MCP tools are:

- `audit_deliberation_campaign_benchmark_matrix_artifact`
- `export_deliberation_campaign_benchmark_matrix_artifact`
- `read_deliberation_campaign_benchmark_matrix_export_artifact`
- `list_deliberation_campaign_benchmark_matrix_export_artifacts`

The intended exported artifact path is `data/deliberation_campaign_matrix_benchmark_exports/<export-id>/`.

## Matrix Export Comparison

When you want to compare several already materialized matrix benchmark exports, use the dedicated export-comparison surface:

```bash
python main.py compare-deliberation-campaign-benchmark-matrix-exports <export-a> <export-b>
python main.py compare-deliberation-campaign-benchmark-matrix-exports --latest 3 --json
```

The currently exposed export-comparison surfaces are:

- `compare-deliberation-campaign-benchmark-matrix-exports` in CLI
- `compare-deliberation-campaign-benchmark-matrix-exports-audit-export` in CLI
- `read-deliberation-campaign-benchmark-matrix-export-comparison <comparison-id>` in CLI
- `list-deliberation-campaign-benchmark-matrix-export-comparisons` in CLI
- `audit-deliberation-campaign-benchmark-matrix-export-comparison <comparison-id>` in CLI
- `export-deliberation-campaign-benchmark-matrix-export-comparison <comparison-id>` in CLI
- `read-deliberation-campaign-benchmark-matrix-export-comparison-export <export-id>` in CLI
- `list-deliberation-campaign-benchmark-matrix-export-comparison-exports` in CLI
- `compare_deliberation_campaign_benchmark_matrix_exports` in MCP
- `compare_audit_export_deliberation_campaign_benchmark_matrix_exports` in MCP
- `read_deliberation_campaign_benchmark_matrix_export_comparison_artifact` in MCP
- `list_deliberation_campaign_benchmark_matrix_export_comparison_artifacts` in MCP
- `audit_deliberation_campaign_benchmark_matrix_export_comparison_artifact` in MCP
- `export_deliberation_campaign_benchmark_matrix_export_comparison_artifact` in MCP
- `read_deliberation_campaign_benchmark_matrix_export_comparison_export_artifact` in MCP
- `list_deliberation_campaign_benchmark_matrix_export_comparison_export_artifacts` in MCP

The canonical persisted paths are:

```text
data/deliberation_campaign_matrix_benchmark_export_comparisons/<comparison-id>/report.json
data/deliberation_campaign_matrix_benchmark_export_comparison_exports/<export-id>/
```

## Matrix Comparison

When you want to compare two already persisted matrix benchmarks, use the dedicated matrix comparison surface:

```bash
python main.py compare-deliberation-campaign-benchmark-matrices <matrix-a> <matrix-b>
python main.py compare-deliberation-campaign-benchmark-matrices --latest --json
```

The comparison report behaves like the regular campaign comparison surface, but at the matrix level. It is the canonical persisted artifact for the matrix comparison pair and exposes:

- `summary.comparable` to say whether the two matrices are aligned enough for a like-for-like comparison
- `summary.mismatch_reasons` to explain where they diverge
- per-matrix entries so you can inspect baseline, candidate sets, and mismatch counts

The currently exposed matrix comparison surfaces are:

- `compare-deliberation-campaign-benchmark-matrices` in CLI
- `compare-deliberation-campaign-benchmark-matrices-audit-export` in CLI
- `read-deliberation-campaign-benchmark-matrix-comparison <comparison-id>` in CLI
- `list-deliberation-campaign-benchmark-matrix-comparisons` in CLI
- `audit-deliberation-campaign-benchmark-matrix-comparison <comparison-id>` in CLI
- `export-deliberation-campaign-benchmark-matrix-comparison <comparison-id>` in CLI
- `read-deliberation-campaign-benchmark-matrix-comparison-export <export-id>` in CLI
- `list-deliberation-campaign-benchmark-matrix-comparison-exports` in CLI
- `compare_deliberation_campaign_benchmark_matrices` in MCP
- `compare_audit_export_deliberation_campaign_benchmark_matrices` in MCP
- `read_deliberation_campaign_benchmark_matrix_comparison_artifact` in MCP
- `list_deliberation_campaign_benchmark_matrix_comparison_artifacts` in MCP
- `audit_deliberation_campaign_benchmark_matrix_comparison_artifact` in MCP
- `export_deliberation_campaign_benchmark_matrix_comparison_artifact` in MCP
- `read_deliberation_campaign_benchmark_matrix_comparison_export_artifact` in MCP
- `list_deliberation_campaign_benchmark_matrix_comparison_export_artifacts` in MCP

The core also exposes the canonical matrix bundle helper `compare_deliberation_campaign_matrix_benchmark_comparison_bundle(...)`, which materializes the comparison audit and export on top of the persisted comparison report.

The intended persisted report path is:

```text
data/deliberation_campaign_matrix_comparisons/<comparison-id>/report.json
```

The exported matrix benchmark artifacts live under:

```text
data/deliberation_campaign_matrix_benchmark_exports/<export-id>/
```

The exported matrix comparison artifacts live under:

```text
data/deliberation_campaign_matrix_benchmark_comparison_exports/<export-id>/
```

The matrix comparison family now follows the same pattern as the campaign comparison family: persisted comparison report first, then audit, then materialized export, plus a one-shot bundle surface on top.

## Global Index

If you want a single mental model for the persisted surfaces, think in eleven buckets:

- campaigns: `list-deliberation-campaigns` and `read-deliberation-campaign`
- comparisons: `list-deliberation-campaign-comparisons` and `read-deliberation-campaign-comparison`
- comparison exports: `list-deliberation-campaign-comparison-exports` and `read-deliberation-campaign-comparison-export`
- benchmarks: `list-deliberation-campaign-benchmarks` and `read-deliberation-campaign-benchmark`
- matrix benchmarks: `list-deliberation-campaign-benchmark-matrices` and `read-deliberation-campaign-benchmark-matrix`
- matrix benchmark audits: `audit-deliberation-campaign-benchmark-matrix` and `export-deliberation-campaign-benchmark-matrix`
- matrix benchmark exports: `list-deliberation-campaign-benchmark-matrix-exports` and `read-deliberation-campaign-benchmark-matrix-export`
- matrix benchmark export comparisons: `list-deliberation-campaign-benchmark-matrix-export-comparisons` and `read-deliberation-campaign-benchmark-matrix-export-comparison`
- matrix benchmark export comparison exports: `list-deliberation-campaign-benchmark-matrix-export-comparison-exports` and `read-deliberation-campaign-benchmark-matrix-export-comparison-export`
- matrix benchmark comparisons: `list-deliberation-campaign-benchmark-matrix-comparisons` and `read-deliberation-campaign-benchmark-matrix-comparison`
- matrix benchmark comparison exports: `list-deliberation-campaign-benchmark-matrix-comparison-exports` and `read-deliberation-campaign-benchmark-matrix-comparison-export`

The same buckets are available in MCP with the matching tool names:

- `list_deliberation_campaigns` and `read_deliberation_campaign_artifact`
- `list_deliberation_campaign_comparison_artifacts` and `read_deliberation_campaign_comparison_artifact`
- `list_deliberation_campaign_comparison_export_artifacts` and `read_deliberation_campaign_comparison_export_artifact`
- `list_deliberation_campaign_benchmarks` and `read_deliberation_campaign_benchmark_artifact`
- `list_deliberation_campaign_benchmark_matrix_artifacts` and `read_deliberation_campaign_benchmark_matrix_artifact`
- `list_deliberation_campaign_benchmark_matrix_export_artifacts` and `read_deliberation_campaign_benchmark_matrix_export_artifact`
- `list_deliberation_campaign_benchmark_matrix_export_comparison_artifacts` and `read_deliberation_campaign_benchmark_matrix_export_comparison_artifact`
- `list_deliberation_campaign_benchmark_matrix_export_comparison_export_artifacts` and `read_deliberation_campaign_benchmark_matrix_export_comparison_export_artifact`
- `list_deliberation_campaign_benchmark_matrix_comparison_artifacts` and `read_deliberation_campaign_benchmark_matrix_comparison_artifact`
- `list_deliberation_campaign_benchmark_matrix_comparison_export_artifacts` and `read_deliberation_campaign_benchmark_matrix_comparison_export_artifact`

These read/list surfaces all go through the canonical helpers in the core, including the benchmark and matrix benchmark read/list paths, so the CLI and MCP stay thin and consistent.

## Dashboard View

For a compact global index, use:

```bash
python main.py deliberation-campaign-index --limit 10 --json
```
Both `deliberation-campaign-index` and `deliberation-campaign-dashboard` accept `--matrix-benchmark-export-output-dir` and `--matrix-benchmark-comparison-export-output-dir` when you want to point the matrix export views at custom stores, and the same global views now also surface matrix benchmark export comparison rows and their derived exports when those artifacts exist in the canonical stores.

For a more filterable dashboard view, use:

```bash
python main.py deliberation-campaign-dashboard --kind campaign --kind benchmark --sort-by quality_score_mean --comparable-only --json
```

The dashboard is designed to be triable and filter-friendly, so you can skim recent artifacts without opening each report individually.
It shows the same buckets as the global index, including benchmark matrix rows, matrix benchmark export rows, matrix benchmark export comparison rows, matrix benchmark export comparison export rows, matrix benchmark comparison rows, and matrix benchmark comparison export rows alongside the canonical benchmark rows, and it is also exposed in MCP as `deliberation_campaign_dashboard`.

Use the stored report when you want an audit trail or a machine-readable export:

```bash
python main.py read-deliberation-campaign-comparison <comparison-id> --json
python main.py audit-deliberation-campaign-comparison <comparison-id>
python main.py export-deliberation-campaign-comparison <comparison-id> --format markdown
python main.py read-deliberation-campaign-comparison-export <comparison-id> --format markdown
python main.py list-deliberation-campaign-comparison-exports --limit 10 --json
python main.py list-deliberation-campaign-comparisons --limit 10 --json
```

The same surface is available through MCP with `read_deliberation_campaign_comparison_artifact`, `audit_deliberation_campaign_comparison_artifact`, `export_deliberation_campaign_comparison_artifact`, `read_deliberation_campaign_comparison_export_artifact` and `list_deliberation_campaign_comparison_export_artifacts`.
The exported artifact path is included in the CLI and MCP payloads when you need to hand it to another tool.

The matrix comparison equivalent is available end-to-end too:

```bash
python main.py audit-deliberation-campaign-benchmark-matrix-comparison <comparison-id>
python main.py export-deliberation-campaign-benchmark-matrix-comparison <comparison-id> --format markdown
python main.py read-deliberation-campaign-benchmark-matrix-comparison-export <export-id> --json
python main.py list-deliberation-campaign-benchmark-matrix-comparison-exports --limit 10 --json
python main.py compare-deliberation-campaign-benchmark-matrices-audit-export <matrix-a> <matrix-b> --format json
```

And in MCP:

- `audit_deliberation_campaign_benchmark_matrix_comparison_artifact`
- `export_deliberation_campaign_benchmark_matrix_comparison_artifact`
- `read_deliberation_campaign_benchmark_matrix_comparison_export_artifact`
- `list_deliberation_campaign_benchmark_matrix_comparison_export_artifacts`
- `compare_audit_export_deliberation_campaign_benchmark_matrices`

## Where the reports live

- Campaign reports are persisted under `data/deliberation_campaigns/<campaign-id>/report.json`.
- Comparison reports are persisted under `data/deliberation_campaign_comparisons/<comparison-id>/report.json`.
- Matrix benchmark reports are persisted under `data/deliberation_campaign_matrix_benchmarks/<matrix-id>/report.json`.
- Matrix benchmark exports are persisted under `data/deliberation_campaign_matrix_benchmark_exports/<export-id>/`.
- Matrix benchmark comparison reports are persisted under `data/deliberation_campaign_matrix_comparisons/<comparison-id>/report.json`.
- Matrix benchmark comparison exports are persisted under `data/deliberation_campaign_matrix_benchmark_comparison_exports/<export-id>/`.

To read a single report or list the persisted set:

```bash
python main.py read-deliberation-campaign <campaign-id> --json
python main.py list-deliberation-campaigns --limit 10
python main.py list-deliberation-campaigns --status completed --json
python main.py read-deliberation-campaign-comparison <comparison-id> --json
python main.py audit-deliberation-campaign-comparison <comparison-id>
python main.py export-deliberation-campaign-comparison <comparison-id> --format json
python main.py read-deliberation-campaign-comparison-export <comparison-id> --format json
python main.py list-deliberation-campaign-comparison-exports --limit 10 --json
python main.py list-deliberation-campaign-comparisons --limit 10 --json
python main.py compare-deliberation-campaign-benchmark-matrices <matrix-a> <matrix-b> --json
python main.py audit-deliberation-campaign-benchmark-matrix <matrix-id>
python main.py export-deliberation-campaign-benchmark-matrix <matrix-id> --format json
python main.py read-deliberation-campaign-benchmark-matrix-export <export-id> --json
python main.py list-deliberation-campaign-benchmark-matrix-exports --limit 10 --json
python main.py audit-deliberation-campaign-benchmark-matrix-comparison <comparison-id>
python main.py export-deliberation-campaign-benchmark-matrix-comparison <comparison-id> --format json
python main.py read-deliberation-campaign-benchmark-matrix-comparison-export <export-id> --json
python main.py list-deliberation-campaign-benchmark-matrix-comparison-exports --limit 10 --json
python main.py list-deliberation-campaign-benchmark-matrix-comparisons --limit 10 --json
```

The most important mismatch reasons are:

- `topic_mismatch`
- `mode_mismatch`
- `runtime_mismatch`
- `engine_mismatch`
- `sample_count_mismatch`
- `stability_runs_mismatch`
- `comparison_key_mismatch`

## Practical rule

- Use `sample_count` when you want campaign-level comparison.
- Use `stability_runs` when you want one run to self-check its stability.
- Use both when you want repeated samples and each sample to self-check internally.

## Example

Run three comparable samples, each with two internal stability repeats:

```bash
python main.py deliberation-campaign \
  "Choose the launch strategy" \
  --sample-count 3 \
  --stability-runs 2 \
  --json
```

Short readback:

```bash
python main.py read-deliberation-campaign <campaign-id> --json
```

List persisted campaigns and filter by status when needed:

```bash
python main.py list-deliberation-campaigns --limit 10
python main.py list-deliberation-campaigns --status completed --json
```

By default, the persisted report lives at:

```text
data/deliberation_campaigns/<campaign-id>/report.json
```

## Reading the result

When the campaign is reported back, look for:

- sample identifiers
- aggregate scores across samples
- fallback and guard signals
- comparability metadata

That is the useful signal for deciding whether the campaign is becoming more stable, more comparable, or simply more repetitive.
