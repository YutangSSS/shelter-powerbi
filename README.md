# shelter-powerbi

A star schema and a Power BI semantic model over public shelter intake and outcome data. The model's
measures reproduce the numbers in the published quarterly reports, and the tests check that.

```
                 dim_date (fiscal year Apr-Mar, complete-month flag)
                /      |  (intake_date: active relationship, outcome_date: inactive)
fct_in_care_monthly    fct_stays ──── dim_region, dim_animal_type, dim_custody, dim_intake_type
  (one row per stay per month end in care)
```

## Build the data

```bash
uv run python scripts/fetch_data.py      # public data, pinned revision, SHA-256 checked
uv run python -m shelter.export          # writes export/*.csv: 7 tables, about 14 MB
uv run pytest -q                         # 8 tests
```

`models/*.sql` builds `fct_stays` from the raw CSVs in DuckDB. `shelter/export.py` shapes it into the star.

## Design choices

- **A snapshot table for the stock.** "In care at month end" is a stock, not a flow. Averaging a stock over a
  date filter in DAX is easy to get wrong, but counting rows in a month-end snapshot is not, so
  `fct_in_care_monthly` holds one row per stay per month end it was in care (49,321 rows).
- **One fact, two date roles.** Intakes use the active relationship on `intake_date`. Stays closed use
  `USERELATIONSHIP` on `outcome_date`, so there's no duplicate fact table.
- **Complete months only.** `dim_date[is_complete_month]` keeps the partial last month (March 2018) out of
  monthly averages, so it doesn't drag them down.

## Measures

| Measure | DAX idea | Why it is written this way |
|---|---|---|
| Intakes | `COUNTROWS(fct_stays)` | Active relationship on intake date |
| Stays Closed | `USERELATIONSHIP(outcome_date, date)` | Same fact, second date role |
| Intakes per Month | `DIVIDE(Intakes, Months in Context)` | Divides by complete months only |
| In Care at Month End (avg) | `AVERAGEX(months, COALESCE(COUNTROWS(snapshot), 0))` | COALESCE keeps months with 0 in the average; AVERAGEX would skip a blank month |
| Intakes per Month % Change | `ROUND` both sides, then `DIVIDE` | % change from the numbers shown, so a reader's calculator agrees |
| Data Through | last complete month | Subtitle on every page |

## What is tested, and what isn't

The tests in `tests/` check:

- `fct_stays` matches [metric-report-harness](https://github.com/YutangSSS/metric-report-harness) exactly: an
  MD5 over every row and column (80,160 rows).
- The exported tables reproduce three report numbers: FY 2016-17 intakes by region, FY 2016-17 stays closed,
  and the 2017-18 year-to-date average in care by custody group.
- Every column the model reads, relates or uses in a measure exists in the CSVs, and every measure it
  references is defined.

**The model has not been opened in Power BI Desktop**, which runs on Windows only. The first refresh there is
the real test of the TMDL syntax and the Power Query steps.

## Open it in Power BI Desktop

1. Copy the repo, with `export/`, to a Windows machine.
2. In Power BI Desktop, turn on *Options > Preview features > Power BI Project (.pbip) save option* and *TMDL format*.
3. Create a new report and save it as a .pbip. Replace its `.SemanticModel/definition` folder with
   `ShelterReporting.SemanticModel/definition` (or open the folder in Tabular Editor and deploy it).
4. Set the `DataFolder` parameter to the `export` folder, then refresh.

## Report pages to build

1. **Placemat**: cards for Intakes per Month, Stays Closed and In Care (avg), each with % change. Add a matrix by region type and slicers for fiscal year and quarter.
2. **Monthly summary**: a matrix of months × intake type with *Show items with no data* on, so empty months show 0.
3. **List (drill-through)**: from a month and category, drill through to the list of stays. Add a row-count card so the list visibly matches the summary cell.
4. **Point in time**: a matrix of animal type × region type from `fct_in_care_monthly` for one month end.

## Data

Austin Animal Center intakes and outcomes (80,187 intakes, Oct 2013 to Mar 2018), City of Austin open data, mirrored on Hugging Face as
[jason1966/aaronschlegel_austin-animal-center-shelter-intakes-and-outcomes](https://huggingface.co/datasets/jason1966/aaronschlegel_austin-animal-center-shelter-intakes-and-outcomes).
