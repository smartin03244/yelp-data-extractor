# yelp-data-extractor Expansion Roadmap

## Purpose

This document captures possible directions for growing `yelp-data-extractor`
beyond a standalone Yelp Academic Dataset CSV pipeline. The main theme is to
keep the extraction core independent while adding optional interfaces, analysis
tools, and source-specific adapters around it.

## High-Level Potential

The current project already has useful foundation pieces:

- streaming JSONL ingestion;
- category mapping;
- balanced reservoir sampling;
- configurable CSV output;
- logging and error handling;
- an install script and command-line interface.

Those pieces can support three larger directions:

- data analysis and reporting;
- REST API and background job execution;
- adapters for additional review or listing sources.

## Data Analysis Layer

The most natural next step is an analysis layer that reads the generated CSV and
produces repeatable summaries. This would build directly on the existing output
format without changing the extractor.

Useful analyses include:

- rating distribution by category;
- review volume by category;
- positive, neutral, and negative review trends over time;
- most common terms by category and rating group;
- category comparison reports;
- sample-quality reports that show selected row counts by stratum;
- missing-field and data-quality checks.

A first implementation could be a small module such as:

```text
src/analysis/
  __init__.py
  summaries.py
  reports.py
```

Possible outputs:

- console summary;
- CSV summary files;
- static HTML report;
- notebook-ready tables.

This should stay separate from the extraction pipeline. The extractor should
produce data; the analysis layer should consume data.

## REST API Direction

A REST API would make sense if the extractor needs to be triggered by another
application, dashboard, scheduler, or user interface.

Recommended API shape:

```text
POST /jobs
GET /jobs/{job_id}
GET /jobs/{job_id}/output
GET /config/output-columns
PUT /config/output-columns
GET /health
```

The API should not run long extraction jobs inside a blocking request. A better
pattern is:

```text
API request -> create job -> background worker runs extraction -> API reports status
```

This keeps HTTP responses fast and makes progress, failures, logs, and output
downloads easier to manage.

Future API components could be organized as:

```text
src/api/
  __init__.py
  app.py
  jobs.py
  schemas.py
```

The API should call the same core pipeline used by the CLI. Avoid duplicating
extraction logic inside web handlers.

## Adapter Architecture For Other Sites

To support other review sources, separate source-specific parsing from the common
pipeline. Yelp should become one adapter rather than the whole application
identity.

Yelp-specific responsibilities today include:

- business JSONL parsing;
- review JSONL parsing;
- Yelp field names;
- category mapping;
- rating normalization.

Common responsibilities include:

- sampling;
- output column configuration;
- CSV writing;
- logging;
- size-limit handling;
- CLI/API orchestration.

A future structure could look like:

```text
src/
  core/
    pipeline.py
    sampling.py
    output_generator.py
    config.py
  adapters/
    yelp.py
    google_reviews.py
    tripadvisor.py
  analysis/
    summaries.py
    reports.py
  api/
    app.py
    jobs.py
```

Each adapter should expose a small common interface, for example:

```text
load_reference_records()
stream_source_records()
normalize_record()
rating_group()
```

The pipeline can then work with normalized rows instead of knowing where those
rows came from.

## Standalone Or Larger Application

The project can support both standalone use and larger application use if the
core stays decoupled from interfaces.

Keep these layers separate:

```text
core extraction logic
CLI wrapper
REST API wrapper
analysis/reporting tools
installer
```

The core should not depend on CLI arguments, HTTP request objects, or UI state.
It should accept normal Python values and return structured results. This makes
the same behavior reusable from:

- command line;
- REST API;
- scheduled job;
- desktop UI;
- larger web application.

## Scraping And External Site Considerations

The current project processes the Yelp Academic Dataset, which is cleaner than
scraping live pages because the input is an explicit dataset.

If future adapters scrape live websites, each adapter should account for:

- site terms of service;
- robots.txt guidance;
- rate limits;
- retry and backoff behavior;
- user privacy;
- data retention rules;
- source attribution requirements;
- changes in page structure or API behavior.

Scraping code should be isolated in adapters so policy, parsing, and rate-limit
rules do not leak into the core pipeline.

## Suggested Roadmap

### Phase 1: Analysis Reports

Add a small analysis module that reads generated CSV files and emits summary
tables. Start with rating distribution and category counts.

### Phase 2: Pipeline Boundaries

Move source-independent logic into a `core` package. Keep Yelp parsing in a Yelp
adapter. Preserve the current CLI behavior while making internals easier to
reuse.

### Phase 3: Job Model

Introduce a job/result model that records:

- input paths;
- output path;
- status;
- row count;
- selected columns;
- log path;
- error message when failed.

This prepares the project for API or scheduler integration.

### Phase 4: REST API

Add an API layer that creates extraction jobs and reports status. Use background
workers for long-running extraction.

### Phase 5: Additional Source Adapter

Add one non-Yelp adapter to validate the abstraction. Choose a source with a
clear data format before attempting browser scraping.

## Guiding Principle

Keep the extraction core small, boring, and reusable. Add richer interfaces and
source-specific behavior around the core, not inside it.
