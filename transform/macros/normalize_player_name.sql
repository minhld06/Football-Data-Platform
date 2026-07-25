{% macro normalize_player_name(column_name) %}
    lower(regexp_replace(unaccent({{ column_name }}), '[^a-z0-9]+', ' ', 'g'))
{% endmacro %}