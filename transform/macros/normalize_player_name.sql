{% macro normalize_player_name(column_name) %}
    lower(regexp_replace(unaccent(replace({{ column_name }}, '&#039;', '''')), '[^a-z0-9]+', ' ', 'g'))
{% endmacro %}