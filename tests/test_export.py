"""The star schema must reproduce the published report numbers. Each check mirrors one DAX measure in
ShelterReporting.SemanticModel, computed from the exported CSVs only.

The expected values come from metric-report-harness (harness.metrics.measure), captured on 2026-11-13 from
the same pinned data revision. The fct_stays fingerprint ties this repo's models to the harness's.
"""
import duckdb
import pytest

from shelter.export import export

FCT_STAYS_ROWS = 80160
FCT_STAYS_MD5 = "d11c6b0d4adcce4aa79c0bcdeadddbac"
INTAKES_2016_17 = {"City of Austin": 14731, "Outside jurisdiction": 221, "Rest of Travis County": 2668}
STAYS_CLOSED_2016_17 = 17732
IN_CARE_AVG_2017_18_YTD = {  # average of 11 complete month ends, Apr 2017 to Feb 2018
    "Other": 175 / 11, "Owner surrender": 3096 / 11, "Public assist": 697 / 11, "Stray hold": 7762 / 11,
}


@pytest.fixture(scope="module")
def star(con, tmp_path_factory):
    out = tmp_path_factory.mktemp("star")
    counts = export(con, out)
    bi = duckdb.connect()
    for name in counts:
        bi.execute(f"create table {name} as select * from read_csv_auto('{out / (name + '.csv')}', header=true)")
    return bi, counts


def test_models_match_the_harness_fingerprint(con):
    got = con.execute("""
        select count(*), md5(string_agg(concat_ws('|', stay_id, animal_id, intake_seq, is_repeat_intake, intake_dt,
               intake_type, intake_condition, animal_type, region_type, custody_group, outcome_id, outcome_dt,
               outcome_type, outcome_subtype, deceased, days_in_care), chr(10) order by stay_id))
        from fct_stays""").fetchone()
    assert got == (FCT_STAYS_ROWS, FCT_STAYS_MD5)


def test_row_counts(star):
    _, counts = star
    assert counts["fct_stays"] == FCT_STAYS_ROWS
    assert counts["dim_region"] == 3


def test_intakes_measure(star):
    bi, _ = star
    # DAX: Intakes = COUNTROWS(fct_stays), filtered through the active intake_date -> dim_date relationship
    got = dict(bi.execute("""select s.region_type, count(*) from fct_stays s join dim_date d on d.date = s.intake_date
                             where d.fiscal_year = '2016-17' group by 1""").fetchall())
    assert got == INTAKES_2016_17


def test_stays_closed_measure_uses_outcome_date(star):
    bi, _ = star
    # DAX: Stays Closed = CALCULATE(COUNTROWS(fct_stays), USERELATIONSHIP(fct_stays[outcome_date], dim_date[date]))
    (got,) = bi.execute("""select count(*) from fct_stays s join dim_date d on d.date = s.outcome_date
                           where d.fiscal_year = '2016-17'""").fetchone()
    assert got == STAYS_CLOSED_2016_17


def test_in_care_monthly_average_measure(star):
    bi, _ = star
    # DAX: In Care Avg = AVERAGEX(VALUES(dim_date[month_start]), COALESCE(CALCULATE(COUNTROWS(fct_in_care_monthly)), 0))
    got = dict(bi.execute("""
        with months as (select distinct month_start from dim_date where fiscal_year = '2017-18' and is_complete_month),
             per as (select m.month_start, c.custody_group, count(c.stay_id) n
                     from months m left join fct_in_care_monthly c on c.month_start = m.month_start group by all)
        select custody_group, sum(n)::double / (select count(*) from months) from per where custody_group is not null group by 1
    """).fetchall())
    assert got.keys() == IN_CARE_AVG_2017_18_YTD.keys()
    for k, want in IN_CARE_AVG_2017_18_YTD.items():
        assert got[k] == pytest.approx(want)


def test_fiscal_calendar(star):
    bi, _ = star
    rows = dict(bi.execute("select date::varchar, fiscal_quarter || ' ' || fiscal_year from dim_date "
                           "where date in ('2017-04-01', '2017-12-31', '2018-03-31')").fetchall())
    assert rows == {"2017-04-01": "Q1 2017-18", "2017-12-31": "Q3 2017-18", "2018-03-31": "Q4 2017-18"}
