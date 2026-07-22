{#
  History is only captured when this snapshot actually runs. `dbt run` alone
  does NOT invoke snapshots — always run `dbt run` (rebuilds silver.standings,
  which is materialized='table' and overwritten each time) THEN `dbt snapshot`
  (or use `dbt build`, which does both in dependency order). Skipping the
  snapshot step after a rebuild silently loses that version's history.
#}
{% snapshot snapshot_football_data_org__standings %}
{{
    config(
      target_schema='snapshots',
      unique_key=['league', 'season', 'team_id'],
      strategy='check',
      check_cols=['position','played_games','won','draw','lost','points',
                  'goals_for','goals_against','goal_difference','form'],
    )
}}
select * from {{ ref('standings') }}
{% endsnapshot %}
