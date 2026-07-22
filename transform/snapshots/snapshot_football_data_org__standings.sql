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
