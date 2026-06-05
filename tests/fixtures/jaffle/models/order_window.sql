select
    order_id,
    customer_id,
    row_number() over (partition by customer_id order by ordered_at) as order_seq
from ANALYTICS.STAGING.STG_ORDERS