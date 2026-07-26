{% macro normalize_player_name(column_name) %}
    regexp_replace(lower(unaccent(replace({{ column_name }}, '&#039;', ''''))), '[^a-z0-9]+', ' ', 'g')
{% endmacro %}