"""Star schema export for Power BI (or any BI tool).

fct_stays            one row per stay (intake), keys to the dimensions, intake and outcome dates
fct_in_care_monthly  periodic snapshot: one row per stay per month end it was in care
dim_date             one row per day, fiscal year (Apr-Mar) and quarter, month start, complete-month flag
dim_region, dim_animal_type, dim_custody, dim_intake_type   small lookup tables

The snapshot table exists because "in care at month end" is a stock, not a flow: averaging a stock in DAX
over a date filter is error-prone; summing a snapshot is not. tests/test_export.py checks that these tables
reproduce the published report numbers.

    uv run python -m shelter.export            # writes export/*.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb

from .db import ROOT, connect, first_incomplete_month

OUT = ROOT / "export"


def build_star(con: duckdb.DuckDBPyConnection) -> None:
    fim = first_incomplete_month(con)
    con.execute("""
        create or replace table dim_date as
        with d as (
            select unnest(generate_series(date '2013-10-01', date '2018-04-30', interval 1 day))::date as date
        )
        select
            date,
            date_trunc('month', date)::date                                   as month_start,
            strftime(date, '%Y-%m')                                           as month_label,
            case when month(date) >= 4 then year(date) else year(date) - 1 end as fy_start_year,
            (case when month(date) >= 4 then year(date) else year(date) - 1 end)::varchar || '-' ||
              right(((case when month(date) >= 4 then year(date) else year(date) - 1 end) + 1)::varchar, 2) as fiscal_year,
            'Q' || (((month(date) + 8) % 12) // 3 + 1)::varchar               as fiscal_quarter,
            ((month(date) + 8) % 12) + 1                                      as fiscal_month_number,
            date_trunc('month', date)::date < ?                               as is_complete_month
        from d
    """, [fim])
    con.execute("create or replace table dim_region as select distinct region_type from fct_stays order by 1")
    con.execute("create or replace table dim_animal_type as select distinct animal_type from fct_stays order by 1")
    con.execute("create or replace table dim_custody as select distinct custody_group, "
                "custody_group in ('Stray hold', 'Owner surrender') as in_shelter_custody from fct_stays order by 1")
    con.execute("create or replace table dim_intake_type as select distinct intake_type from fct_stays order by 1")
    con.execute("""
        create or replace table bi_fct_stays as
        select stay_id, animal_id, intake_seq, is_repeat_intake,
               intake_dt, intake_dt::date as intake_date, outcome_dt, outcome_dt::date as outcome_date,
               intake_type, intake_condition, animal_type, region_type, custody_group,
               outcome_type, deceased, days_in_care
        from fct_stays
    """)
    # Month end = the first instant of the next month (half-open rule: in care if intake < t and no outcome before t).
    con.execute("""
        create or replace table fct_in_care_monthly as
        with m as (
            select unnest(generate_series(date '2013-10-01', ?::date - interval 1 month, interval 1 month))::date as month_start
        )
        select m.month_start, s.stay_id, s.animal_id, s.animal_type, s.region_type, s.custody_group,
               date_diff('day', s.intake_dt, (m.month_start + interval 1 month)::timestamp) as days_in_care_at_month_end
        from m join fct_stays s
          on s.intake_dt < (m.month_start + interval 1 month)::timestamp
         and (s.outcome_dt is null or s.outcome_dt >= (m.month_start + interval 1 month)::timestamp)
    """, [fim])


TABLES = {
    "fct_stays": "bi_fct_stays",
    "fct_in_care_monthly": "fct_in_care_monthly",
    "dim_date": "dim_date",
    "dim_region": "dim_region",
    "dim_animal_type": "dim_animal_type",
    "dim_custody": "dim_custody",
    "dim_intake_type": "dim_intake_type",
}


def export(con: duckdb.DuckDBPyConnection, out: Path = OUT) -> dict[str, int]:
    build_star(con)
    out.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name, table in TABLES.items():
        con.execute(f"copy {table} to '{out / (name + '.csv')}' (header, delimiter ',')")
        counts[name] = con.execute(f"select count(*) from {table}").fetchone()[0]
    return counts


if __name__ == "__main__":
    for k, v in export(connect()).items():
        print(f"{k:<22} {v:>8,} rows")
    sys.exit(0)
