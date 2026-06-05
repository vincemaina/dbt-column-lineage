select
    id as customer_id,
    first_name,
    last_name,
    coalesce(first_name, 'unknown') as first_name_clean
from RAW.JAFFLE.RAW_CUSTOMERS