select
    id as order_id,
    customer_id,
    cast(amount as number(38, 2)) as amount,
    status,
    ordered_at
from RAW.JAFFLE.RAW_ORDERS