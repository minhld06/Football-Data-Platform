{% macro normalize_understat_position(column_name) %}
    case
        when {{ column_name }} is null then null
        when {{ column_name }} ~ '^GK' then 'Goalkeeper'
        when {{ column_name }} ~ '^D' then 'Defence'
        when {{ column_name }} ~ '^M' then 'Midfield'
        when {{ column_name }} ~ '^F' then 'Offence'
        else null
    end
{% endmacro %}
