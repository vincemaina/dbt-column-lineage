select
    o.order_id,
    o.amount,
    c.first_name as customer_first_name
from ANALYTICS.STAGING.STG_ORDERS o
left join ANALYTICS.STAGING.STG_CUSTOMERS c
    on o.customer_id = c.customer_id